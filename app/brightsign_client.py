"""Talks to a BrightSign player's Local DWS REST API over the LAN.

Protocol reference: BrightSign's own player-cli tool
(github.com/brightsign/player-cli), whose source was read directly since
docs.brightsign.biz is JS-rendered and can't be fetched as plain HTML.
Endpoints are GET/PUT http://<ip>/api/v1/files/<storage>/<path>,
authenticated with standard HTTP Digest auth (default admin / the player's
serial number) — the same scheme requests.auth.HTTPDigestAuth implements,
so no manual challenge-response handling is needed here.

Local DWS access must already be enabled on the player (it's off by default
on BrightSignOS 9.0.218+) before any of this will work. The port is NOT
reliably 80 — confirmed on this cafe's actual player, it runs on 8080
instead (found by loading http://<ip>:8080 directly in a browser, which
serves a plain BrightSign landing page with the player's name/serial/
firmware when DWS is actually reachable). Don't assume port 80; it's a
per-player/per-firmware setting, so it's a required, explicit argument
here rather than a hardcoded default.
"""
from __future__ import annotations

from pathlib import Path

import requests
from requests.auth import HTTPDigestAuth

DEFAULT_STORAGE = "sd"
# (connect timeout, read timeout) — a short connect timeout so a wrong/
# unreachable IP fails fast in the GUI instead of hanging.
LIST_TIMEOUT = (5, 15)
UPLOAD_TIMEOUT = (5, 60)


class BrightSignError(Exception):
    pass


# Populated after every request (success or failure) so callers can show the
# real raw response if something downstream (e.g. app.py's formatting code)
# chokes on a JSON shape that turned out to differ from what player-cli's
# source implied — that's inferred from reading someone else's client, not
# from this cafe's actual player, so treat the assumed shape as a guess
# until it's been seen working against real hardware.
last_raw_response: dict = {"text": None}


def _files_url(ip: str, port: int, storage: str, path: str) -> str:
    path = path.strip("/")
    url = f"http://{ip}:{port}/api/v1/files/{storage}"
    if path:
        url += f"/{path}"
    return url


def list_files(
    ip: str, port: int, username: str, password: str, path: str = "", storage: str = DEFAULT_STORAGE
) -> list[dict]:
    """Lists files/folders at `path` on the player's storage. Read-only —
    safe to call against a live production player at any time."""
    url = _files_url(ip, port, storage, path)
    try:
        resp = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=LIST_TIMEOUT)
    except requests.RequestException as e:
        raise BrightSignError(f"Couldn't reach player at {ip}:{port}: {e}") from e
    last_raw_response["text"] = resp.text
    if resp.status_code == 401:
        raise BrightSignError("Player rejected the username/password.")
    if not resp.ok:
        raise BrightSignError(f"Player returned {resp.status_code} for {url}: {resp.text[:300]}")
    try:
        return resp.json()["result"]["files"]
    except (KeyError, ValueError) as e:
        raise BrightSignError(f"Unexpected response from player: {resp.text[:300]}") from e


def upload_file(
    ip: str, port: int, username: str, password: str, local_path: Path, dest_dir: str,
    storage: str = DEFAULT_STORAGE,
) -> None:
    """Uploads local_path into dest_dir on the player's storage, overwriting
    any existing file there with the same name.

    Not currently wired to any GUI button — only call this once the exact
    dest_dir/filename a live presentation's zone reads from has been
    confirmed via list_files, on a specific player. Pushing to the wrong
    path is a no-op at best; overwriting the wrong file at worst.
    """
    url = _files_url(ip, port, storage, dest_dir)
    try:
        with open(local_path, "rb") as f:
            resp = requests.put(
                url, auth=HTTPDigestAuth(username, password),
                files={"file": (local_path.name, f)}, timeout=UPLOAD_TIMEOUT,
            )
    except requests.RequestException as e:
        raise BrightSignError(f"Couldn't reach player at {ip}: {e}") from e
    if resp.status_code == 401:
        raise BrightSignError("Player rejected the username/password.")
    if not resp.ok:
        raise BrightSignError(f"Upload failed ({resp.status_code}): {resp.text[:300]}")
