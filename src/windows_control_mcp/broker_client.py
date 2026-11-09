"""Client for the separately installed Windows broker service."""

from __future__ import annotations

import json
import os
import time

from .broker_protocol import BROKER_PIPE, request_digest, validate_request


def _call(request: dict, timeout_ms: int) -> dict:
    import pywintypes
    import win32file

    deadline = time.monotonic() + min(30, max(1, timeout_ms / 1000 + 5))
    handle = None
    try:
        while True:
            try:
                handle = win32file.CreateFile(
                    BROKER_PIPE, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0, None, win32file.OPEN_EXISTING, 0, None)
                break
            except pywintypes.error as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError("A broker szolgáltatás nem érhető el.") from exc
                time.sleep(0.1)
        payload = (json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        win32file.WriteFile(handle, payload)
        _, raw = win32file.ReadFile(handle, 1_000_000)
        return json.loads(raw.decode("utf-8"))
    finally:
        if handle is not None:
            win32file.CloseHandle(handle)


def prepare(profile_id: str, arguments: list[str] | None = None, timeout_ms: int = 30_000) -> dict:
    arguments = [] if arguments is None else [str(value) for value in arguments]
    validate_request(profile_id, arguments, timeout_ms)
    return _call({"version": 1, "operation": "prepare", "profile_id": profile_id,
                  "arguments": arguments, "timeout_ms": int(timeout_ms),
                  "request_digest": request_digest(profile_id, arguments, timeout_ms)}, timeout_ms)


def approve_and_run(approval_id: str, timeout_ms: int = 30_000) -> dict:
    return _call({"version": 1, "operation": "approve_and_run", "approval_id": approval_id}, timeout_ms)
