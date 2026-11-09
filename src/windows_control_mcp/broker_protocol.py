"""Shared validation and wire-format helpers for the isolated Windows broker."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

BROKER_PIPE = r"\\.\pipe\WindowsControlMCP-Broker"
PROGRAM_DATA = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "WindowsControlMCP"
POLICY_PATH = PROGRAM_DATA / "broker-policy.json"
APPROVAL_HELPER_NAME = "WindowsControlMCPApproval.exe"
BLOCKED_EXECUTABLES = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "python.exe", "pythonw.exe", "py.exe",
    "wscript.exe", "cscript.exe", "mshta.exe", "rundll32.exe", "regsvr32.exe",
    "installutil.exe", "msiexec.exe",
}


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def request_digest(profile_id: str, arguments: list[str], timeout_ms: int) -> str:
    payload = {"profile_id": profile_id, "arguments": arguments, "timeout_ms": int(timeout_ms)}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def load_policy(path: Path = POLICY_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("A védett brokerházirend nem olvasható.") from exc
    if not isinstance(data, dict) or data.get("version") != 1:
        raise RuntimeError("A brokerházirend verziója érvénytelen.")
    if not isinstance(data.get("profiles"), dict):
        raise RuntimeError("A brokerházirend profiles mezője érvénytelen.")
    if not isinstance(data.get("allowed_user_sid"), str) or not data["allowed_user_sid"]:
        raise RuntimeError("A brokerházirend nem tartalmaz engedélyezett felhasználói SID-et.")
    return data


def validate_profile(profile_id: str, profile: dict) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", profile_id):
        raise ValueError("Érvénytelen brokerprofil-azonosító.")
    if not isinstance(profile, dict) or profile.get("kind") != "process":
        raise ValueError("Csak process brokerprofil támogatott.")
    executable = Path(str(profile.get("executable", "")))
    if not executable.is_absolute() or not executable.is_file() or executable.is_symlink():
        raise ValueError("A brokerprofil végrehajtható fájlútvonala érvénytelen.")
    if executable.name.casefold() in BLOCKED_EXECUTABLES:
        raise ValueError("Shell- vagy scriptértelmező nem lehet brokerprofil.")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(profile.get("sha256", ""))):
        raise ValueError("A brokerprofil hash-e nem érvényes SHA-256 érték.")
    if not isinstance(profile.get("allow_arguments"), bool):
        raise ValueError("A brokerprofil allow_arguments mezője kötelező és logikai érték.")
    fixed = profile.get("fixed_arguments", [])
    if not isinstance(fixed, list) or any(not isinstance(item, str) for item in fixed):
        raise ValueError("A fixed_arguments mező érvénytelen.")


def validate_request(profile_id: str, arguments: list[str], timeout_ms: int) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", profile_id):
        raise ValueError("Érvénytelen brokerprofil-azonosító.")
    if not isinstance(arguments, list) or any(not isinstance(arg, str) for arg in arguments):
        raise ValueError("A broker argumentumai listában, szövegként adhatók meg.")
    if len(arguments) > 32 or any("\x00" in arg or len(arg) > 2000 for arg in arguments):
        raise ValueError("A broker argumentumai túl hosszúak vagy túl sokan vannak.")
    if not 100 <= int(timeout_ms) <= 120_000:
        raise ValueError("A broker időkorlátja 100 és 120000 ms között lehet.")
