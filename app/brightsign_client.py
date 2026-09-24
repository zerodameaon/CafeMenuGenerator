"""Talks to a BrightSign player's Local DWS REST API over the LAN.

Protocol reference: BrightSign's own player-cli tool
(github.com/brightsign/player-cli), whose source was read directly since
docs.brightsign.biz is JS-rendered and can't be fetched as plain HTML.
Endpoints are http(s)://<ip>/api/v1/..., authenticated with standard HTTP
Digest auth — the same scheme requests.auth.HTTPDigestAuth implements, so
no manual challenge-response handling is needed here.

Confirmed against this cafe's actual player (XT245, BrightSignOS 9.1.151,
2026-09-24): the REST API is served over **HTTPS on port 443** with a
self-signed certificate (port 80 just 302-redirects there). Port 8080 on
this player is NOT the DWS API — it's the brightAuthor:connected
presentation's own little web server, which is why every /api/v1 call
there 404'd with "Missing handler" in the earlier investigation. Port is
still an explicit argument (it's a per-player setting); port 443 selects
https, anything else plain http.

Response shapes below are the real ones seen from that player, not guesses
from player-cli: file listings are {"data": {"result": {"files": [...]}}}
with each entry {"name", "type": "file"|"dir", "stat": {"size", ...}};
file reads (?contents) return the bytes base64-encoded in
data.result.contents.
"""
from __future__ import annotations

import base64
import hashlib
import time

import requests
import urllib3
from requests.auth import HTTPDigestAuth

DEFAULT_STORAGE = "sd"
DEFAULT_PORT = 443
# (connect timeout, read timeout) — a short connect timeout so a wrong/
# unreachable IP fails fast in the GUI instead of hanging.
LIST_TIMEOUT = (5, 15)
READ_TIMEOUT = (5, 60)
UPLOAD_TIMEOUT = (5, 120)

# The player's HTTPS certificate is self-signed (issued by the player to
# itself), so it can't be verified against any CA. Traffic only ever goes to
# a player on the local network that the user typed in, and digest auth never
# sends the password itself — so skip verification and silence the warning
# rather than failing every request.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BrightSignError(Exception):
    pass


# Populated after every listing request (success or failure) so callers can
# show the real raw response if a JSON shape ever turns out to differ from
# what's expected — this has bitten this project once already.
last_raw_response: dict = {"text": None}


class Player:
    def __init__(self, ip: str, port: int, username: str, password: str, storage: str = DEFAULT_STORAGE):
        self.ip, self.port, self.storage = ip, port, storage
        self._auth = HTTPDigestAuth(username, password)
        scheme = "https" if port == 443 else "http"
        self._base = f"{scheme}://{ip}:{port}/api/v1"

    # -- plumbing ----------------------------------------------------------

    def _request(self, method: str, route: str, timeout, **kwargs) -> requests.Response:
        url = f"{self._base}/{route}"
        try:
            resp = requests.request(method, url, auth=self._auth, verify=False, timeout=timeout, **kwargs)
        except requests.RequestException as e:
            raise BrightSignError(f"Couldn't reach player at {self.ip}:{self.port}: {e}") from e
        if resp.status_code == 401:
            raise BrightSignError("Player rejected the username/password.")
        return resp

    def _result(self, resp: requests.Response, what: str):
        if not resp.ok:
            raise BrightSignError(f"{what} failed ({resp.status_code}): {resp.text[:300]}")
        try:
            return resp.json()["data"]["result"]
        except (KeyError, ValueError) as e:
            raise BrightSignError(f"Unexpected response to {what}: {resp.text[:300]}") from e

    def _files_route(self, path: str) -> str:
        path = path.strip("/")
        return f"files/{self.storage}/{path}" if path else f"files/{self.storage}"

    # -- read-only ---------------------------------------------------------

    def info(self) -> dict:
        return self._result(self._request("GET", "info", LIST_TIMEOUT), "info")

    def list_files(self, path: str = "") -> list[dict]:
        """Lists files/folders at `path` on the player's storage. Read-only —
        safe to call against a live production player at any time."""
        resp = self._request("GET", self._files_route(path), LIST_TIMEOUT)
        last_raw_response["text"] = resp.text
        return self._result(resp, f"listing {path or '(root)'}")["files"]

    def read_file(self, path: str) -> bytes:
        resp = self._request("GET", self._files_route(path) + "?contents", READ_TIMEOUT)
        result = self._result(resp, f"reading {path}")
        try:
            return base64.b64decode(result["contents"])
        except (KeyError, ValueError) as e:
            raise BrightSignError(f"Unexpected response reading {path}: {resp.text[:300]}") from e

    def snapshot(self) -> bytes:
        """Screenshot of what the player is showing right now, as JPEG bytes.
        The API response only carries a thumbnail; the full-size image is
        saved on the player's storage and read back from there."""
        result = self._result(self._request("POST", "snapshot", READ_TIMEOUT), "snapshot")
        full_path = result.get("filename", "").lstrip("/")
        if full_path.startswith(self.storage + "/"):
            try:
                return self.read_file(full_path[len(self.storage) + 1:])
            except BrightSignError:
                pass
        return base64.b64decode(result["remoteSnapshotThumbnail"].split(",", 1)[1])

    # -- writes ------------------------------------------------------------

    def upload(self, data: bytes, dest_dir: str, filename: str) -> None:
        """Writes `data` to dest_dir/filename, overwriting any existing file,
        then reads it back and checks it arrived intact.

        Quirk confirmed on the real player: a PUT into a folder that doesn't
        exist yet only *creates the folder* — it still answers
        {"success": true}, but no file is written. A second PUT (now that the
        folder exists) writes the file. So verify after every upload and
        retry once, rather than trusting the success flag."""
        dest = f"{dest_dir.strip('/')}/{filename}" if dest_dir.strip("/") else filename
        want = hashlib.sha1(data).hexdigest()
        for _ in range(2):
            resp = self._request(
                "PUT", self._files_route(dest_dir), UPLOAD_TIMEOUT, files={"file": (filename, data)},
            )
            self._result(resp, f"uploading {dest}")
            try:
                if hashlib.sha1(self.read_file(dest)).hexdigest() == want:
                    return
            except BrightSignError:
                pass  # not there yet — the folder-creation quirk; try again
        raise BrightSignError(f"Uploaded {dest}, but the player doesn't have an intact copy of it.")

    def reboot_and_wait(self, timeout_s: int = 300) -> None:
        """Reboots the player and returns once its API answers again.
        Detects the restart by uptime going *down*, since the player keeps
        answering for a few seconds after accepting the reboot command."""
        before = int(self.info().get("upTimeSeconds", 10**9))
        try:
            self._result(self._request("PUT", "control/reboot", LIST_TIMEOUT), "reboot")
        except BrightSignError as e:
            # A player that restarts the instant it gets the command can drop
            # the connection before answering. That's only a failure if it
            # never actually restarts — which the wait below will tell.
            if "Couldn't reach" not in str(e):
                raise
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            time.sleep(5)
            try:
                if int(self.info().get("upTimeSeconds", 10**9)) < before:
                    return
            except BrightSignError:
                pass  # still restarting
        raise BrightSignError(f"Player didn't come back within {timeout_s // 60} minutes of rebooting.")
