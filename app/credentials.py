"""Remembers the BrightSign player's password in the macOS Keychain, so
whoever runs the app on the cafe laptop doesn't have to hunt for it.

The password never goes into the repo or into the app's plain-text config
file (~/.cafe_menu_brightsign_player.json) — only into the logged-in macOS
user's login keychain, as a generic password item. It's per macOS user
account: someone on a different login enters it once for themselves.

Uses Apple's own /usr/bin/security tool rather than a Python keyring
library, for two reasons:
- No extra dependency to bundle with PyInstaller.
- Keychain ties each item's access list to the program that created it.
  Items created by /usr/bin/security stay readable by /usr/bin/security,
  so they keep working across app rebuilds (each ad-hoc-signed build would
  otherwise count as a new program and trigger an "allow access?" prompt)
  and between running from source and running the packaged .app.

The password is sent to `security` on stdin (its interactive mode), never
as a command-line argument, so it can't be seen in the process list.

Items are keyed by username@ip, so pointing the app at a different player
never sends it this player's password.
"""
from __future__ import annotations

import subprocess

SERVICE = "The Cafe Menu Sign Generator - BrightSign player"
SECURITY = "/usr/bin/security"


def _account(ip: str, username: str) -> str:
    return f"{username}@{ip}"


def _quote(value: str) -> str:
    # `security -i` parses its input line with shell-like double quoting.
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def load(ip: str, username: str) -> str:
    """The saved password for this player/username, or "" if none (or if
    the Keychain can't be read for any reason — a missing password just
    means the user types it)."""
    if not ip or not username:
        return ""
    try:
        result = subprocess.run(
            [SECURITY, "find-generic-password", "-s", SERVICE, "-a", _account(ip, username), "-w"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.rstrip("\n") if result.returncode == 0 else ""


def save(ip: str, username: str, password: str) -> bool:
    """Saves (or replaces) the password. Returns False if the Keychain
    refused — callers treat that as "not remembered", not as an error."""
    if not ip or not username or "\n" in password:
        return False
    line = (
        f"add-generic-password -U -s {_quote(SERVICE)} -a {_quote(_account(ip, username))} "
        f"-w {_quote(password)}\n"
    )
    try:
        result = subprocess.run([SECURITY, "-i"], input=line, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and load(ip, username) == password


def clear(ip: str, username: str) -> None:
    """Forgets the saved password for this player/username, if any."""
    if not ip or not username:
        return
    try:
        subprocess.run(
            [SECURITY, "delete-generic-password", "-s", SERVICE, "-a", _account(ip, username)],
            capture_output=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass
