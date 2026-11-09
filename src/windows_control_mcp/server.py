"""Dependency-light MCP stdio server for native Windows controls."""

from __future__ import annotations

import json
import hashlib
import os
import secrets
import sys
import threading
import time
import traceback
from typing import Any, Callable
from pathlib import Path

from . import __version__
from . import native
try:
    from . import dev_overrides as _dev_overrides
except ImportError:  # public export: no developer override module is shipped
    _dev_overrides = None

MODE_ORDER = {"SAFE": 0, "NORMAL": 1, "ADMIN": 2}
MODE = os.environ.get("WINDOWS_CONTROL_MODE", "SAFE").upper()
AUTO_APPROVE = _dev_overrides.auto_approve() if _dev_overrides else False
# `restricted` is the safe default. `direct` is an explicit local-development
# mode and must not be used as a public security boundary.
EXECUTION_POLICY = _dev_overrides.execution_policy() if _dev_overrides else "restricted"
PERMISSION_LOCK = threading.RLock()
PERMISSION_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WindowsControlMCP"
PERMISSION_PATH = PERMISSION_ROOT / "permissions.json"
BROKER_PATH = PERMISSION_ROOT / "execution-broker.json"
ONE_TIME_APPROVALS: dict[str, int] = {}
ONE_TIME_DENIALS: dict[str, int] = {}
SESSION_APPROVALS: dict[str, str] = {}
SESSION_DENIALS: dict[str, str] = {}
APPROVAL_TOKENS: dict[str, dict[str, Any]] = {}
PENDING_APPROVALS: dict[str, dict[str, Any]] = {}

# A normál asztali vezérlés egy korlátozott képességcsoport. A csoport nem
# örököl jogosultságot fájl-, terminál-, folyamat-, kamera-, broker- vagy ADMIN-
# műveletekre; azok továbbra is paraméterhez kötött külön engedélyt kapnak.
COMPUTER_CONTROL_ACTIONS = frozenset({
    "mouse_move", "mouse_click", "mouse_drag", "mouse_scroll",
    "key_press", "hotkey", "type_text", "window_focus",
    "window_set_state", "window_resize", "ui_invoke", "ui_set_value",
    "ui_select", "ui_toggle", "ui_scroll", "ui_focus",
})
CAPABILITY_GROUPS = {
    "computer_control": {
        "title": "A számítógép vezérlésének engedélyezése az AI-ügynök számára",
        "summary": "képernyő-, ablak-, egér-, billentyűzet- és böngészővezérlés",
        "actions": sorted(COMPUTER_CONTROL_ACTIONS),
    },
}


def _text(value: Any) -> list[dict[str, str]]:
    return [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}]


def _permission_scope(action: str, args: dict[str, Any]) -> str:
    # Bind every approval to the complete operation parameters. Control fields
    # only affect authorization transport and must not change the operation.
    operation_args = {key: value for key, value in args.items()
                      if key not in {"confirm", "approval_token"}}
    canonical = json.dumps(operation_args, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"v2:{action}:sha256:{digest}"


def _capability_group(action: str, needed: str) -> str | None:
    """Return a bounded group for ordinary NORMAL desktop control only."""
    if needed == "NORMAL" and action in COMPUTER_CONTROL_ACTIONS:
        return "computer_control"
    return None


def _capability_scope(group: str) -> str:
    if group not in CAPABILITY_GROUPS:
        raise ValueError("Ismeretlen engedélyképesség-csoport.")
    return f"v3:capability:{group}"


def _permission_data() -> dict[str, Any]:
    with PERMISSION_LOCK:
        if not PERMISSION_PATH.is_file():
            return {"version": 1, "active": {}, "history": []}
        try:
            value = json.loads(PERMISSION_PATH.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                value.setdefault("version", 1)
                value.setdefault("active", {})
                value.setdefault("history", [])
                return value
        except (OSError, json.JSONDecodeError):
            pass
        return {"version": 1, "active": {}, "history": []}


def _save_permission_data(data: dict[str, Any]) -> None:
    PERMISSION_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = PERMISSION_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, PERMISSION_PATH)


def _record_permission(scope: str, decision: str, source: str) -> None:
    data = _permission_data()
    history = data.setdefault("history", [])
    history.append({"scope": scope, "decision": decision, "source": source,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    data["history"] = history[-200:]
    _save_permission_data(data)


def _permission_risk(action: str, needed: str) -> str:
    if needed == "ADMIN" or action in {"application_uninstall", "file_delete", "service_control", "process_stop"}:
        return "high"
    return "medium"


def _capability_group_target(group: str | None) -> str:
    if group in CAPABILITY_GROUPS:
        item = CAPABILITY_GROUPS[group]
        return f"{item['title']} – {item['summary']}"
    return "A megjelölt engedélyképesség-csoport"


def _permission_target(action: str, args: dict[str, Any]) -> str:
    if action == "terminal_run":
        command = str(args.get("command", ""))
        shell = str(args.get("shell", "powershell"))
        return f"{shell}: {command[:1000]}"
    if action == "launch_application":
        command = str(args.get("command", ""))
        arguments = args.get("arguments", [])
        return f"Indítás: {command[:400]} {json.dumps(arguments, ensure_ascii=False)[:600]}"
    if action == "terminal_start":
        return f"Interaktív terminál indítása: {args.get('shell', 'powershell')}"
    if action == "terminal_input":
        text = str(args.get("text", ""))
        return f"Terminálbemenet {args.get('session_id', '')}: {text[:1000]}"
    if action in {"terminal_poll", "terminal_stop"}:
        return f"Terminál-munkamenet: {args.get('session_id', '')}"
    key = {"application_uninstall": "package_id", "application_update": "package_id", "file_delete": "path",
           "file_write": "path", "file_move": "source", "file_copy": "source",
           "service_control": "name", "process_stop": "pid"}.get(action)
    if key:
        value = str(args.get(key, ""))[:300]
        if action == "file_write":
            text = str(args.get("text", ""))
            return f"{value} (tartalom: {len(text)} karakter, előnézet: {text[:300]})"
        return value
    visible = {key: value for key, value in args.items()
               if key not in {"confirm", "approval_token"}}
    return json.dumps(visible, ensure_ascii=False, sort_keys=True, default=str)[:1000] or "asztali művelet"


def _targets_permission_store(action: str, args: dict[str, Any]) -> bool:
    protected_root = str(PERMISSION_ROOT.resolve()).casefold()
    protected_file = str(PERMISSION_PATH.resolve()).casefold()
    broker_file = str(BROKER_PATH.resolve()).casefold()
    for key in ("path", "source", "destination"):
        if key in args:
            try:
                target = str(Path(str(args[key])).expanduser().resolve()).casefold()
                if target in {protected_file, broker_file} or target.startswith(protected_root + os.sep):
                    return True
            except (OSError, ValueError):
                pass
    return False


def _execution_policy_error(action: str) -> dict | None:
    if action in {"terminal_run", "terminal_start", "terminal_input", "terminal_poll", "terminal_stop",
                  "launch_application"} and EXECUTION_POLICY != "direct":
        return {"error": "execution_broker_required",
                "message": "Ez az általános végrehajtó csak külön engedélyezett brokerrel vagy explicit helyi direct módban használható.",
                "action": action, "policy": EXECUTION_POLICY}
    if EXECUTION_POLICY not in {"restricted", "direct"}:
        return {"error": "invalid_execution_policy", "message": "Ismeretlen végrehajtási házirend."}
    return None


def _permission(args: dict[str, Any], action: str, needed: str) -> dict | None:
    if MODE_ORDER.get(MODE, 0) < MODE_ORDER[needed]:
        return {"error": "permission_denied", "message": f"{action} requires {needed} mode."}
    scope = _permission_scope(action, args)
    capability_group = _capability_group(action, needed)
    capability_scope = _capability_scope(capability_group) if capability_group else None
    policy_error = _execution_policy_error(action)
    if policy_error:
        return policy_error
    if _targets_permission_store(action, args):
        return {"error": "permission_denied", "message": "Az engedélytároló közvetlen módosítása tiltott.",
                "scope": scope}
    if AUTO_APPROVE:
        return None
    with PERMISSION_LOCK:
        now = time.time()
        for request_id, request in list(PENDING_APPROVALS.items()):
            try:
                if now - time.mktime(time.strptime(request["created"].split("+", 1)[0], "%Y-%m-%dT%H:%M:%S")) > 600:
                    PENDING_APPROVALS.pop(request_id, None)
            except (KeyError, ValueError, OverflowError):
                pass
        data = _permission_data()
        scopes = [scope] + ([capability_scope] if capability_scope else [])
        now = time.time()
        # Exact denies have priority; a broad capability grant can never
        # override a more specific rejection for the same operation.
        for candidate in scopes:
            active = data.get("active", {}).get(candidate, {})
            decision = active.get("decision") if isinstance(active, dict) else None
            if decision == "always":
                decision = "always_allow"
            elif decision == "deny":
                decision = "always_deny"
            expires = active.get("expires") if isinstance(active, dict) else None
            if expires is not None and float(expires) <= now:
                decision = None
            if decision == "always_deny":
                return {"error": "permission_denied", "message": "Ezt a műveleti kört a felhasználó elutasította.",
                        "scope": candidate, "capability_group": capability_group}
            if SESSION_DENIALS.get(candidate):
                return {"error": "permission_denied", "message": "A munkamenetben ezt a műveleti kört elutasították.",
                        "scope": candidate, "capability_group": capability_group}
        for candidate in scopes:
            active = data.get("active", {}).get(candidate, {})
            decision = active.get("decision") if isinstance(active, dict) else None
            if decision in {"always", "always_allow"}:
                return None
            if SESSION_APPROVALS.get(candidate):
                return None
        for candidate in scopes:
            if ONE_TIME_DENIALS.get(candidate, 0) > 0:
                ONE_TIME_DENIALS[candidate] -= 1
                return {"error": "permission_denied", "message": "Ezt az egy műveletet a felhasználó elutasította.",
                        "scope": candidate, "capability_group": capability_group}
        for candidate in scopes:
            if ONE_TIME_APPROVALS.get(candidate, 0) > 0:
                ONE_TIME_APPROVALS[candidate] -= 1
                return None
        token = args.get("approval_token")
        if token and token in APPROVAL_TOKENS:
            token_info = APPROVAL_TOKENS.pop(token)
            if token_info.get("scope") in scopes and token_info.get("expires", 0) > now:
                return None
    target = (_capability_group_target(capability_group)
              if capability_group else _permission_target(action, args))
    request_scope = capability_scope or scope
    request_id = secrets.token_urlsafe(18)
    with PERMISSION_LOCK:
        PENDING_APPROVALS[request_id] = {
            "request_id": request_id, "tool": action, "scope": request_scope,
            "scope_kind": "capability_group" if capability_group else "exact_parameters",
            "capability_group": capability_group,
            "target": target, "risk": _permission_risk(action, needed),
            "parameters_hash": scope.rsplit(":", 1)[-1] if not capability_group else None,
            "agent": os.environ.get("WINDOWS_CONTROL_AGENT", "ismeretlen kliens"),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "needed": needed,
        }
    return {"error": "approval_required", "message": "Felhasználói engedély szükséges ehhez a művelethez.",
            "approval": {"request_id": request_id, "tool": action, "scope": request_scope,
                          "scope_kind": "capability_group" if capability_group else "exact_parameters",
                          "capability_group": capability_group, "target": target,
                          "parameters_hash": scope.rsplit(":", 1)[-1] if not capability_group else None,
                          "agent": os.environ.get("WINDOWS_CONTROL_AGENT", "ismeretlen kliens"),
                          "risk": _permission_risk(action, needed),
                          "duration_choices": ["once", "session", "always"],
                          "decision_choices": ["allow", "deny", "revoke"],
                          "next": "permission_prompt"}}


TOOLS = [
    ("system_info", "SAFE", "Windows and storage information", {}, native.system_info),
    ("permission_status", "SAFE", "List active and historical local approval decisions", {}, None),
    ("execution_broker_profiles", "SAFE", "List hash-pinned local execution broker profiles", {}, native.execution_broker_profiles),
    ("execution_broker_status", "SAFE", "Report local and Windows-service broker policy state", {}, native.execution_broker_status),
    ("system_metrics", "SAFE", "Bounded CPU, memory, uptime and storage metrics", {}, native.system_metrics),
    ("network_adapters", "SAFE", "Read Windows network adapters and addresses", {}, native.network_adapters),
    ("installed_applications", "SAFE", "List standard Windows installed application entries", {"limit": {"type": "integer"}}, native.installed_applications),
    ("installed_application_summary", "SAFE", "Summarize installed application count and estimated size", {"limit": {"type": "integer"}}, native.installed_application_summary),
    ("application_updates", "SAFE", "List best-effort WinGet application updates without installing", {}, native.application_updates),
    ("application_maintenance_history", "SAFE", "Read local application update and uninstall history", {"limit": {"type": "integer"}}, native.application_maintenance_history),
    ("registry_read", "SAFE", "Read one Windows registry key or value", {"root": {"type": "string"}, "subkey": {"type": "string"}, "value_name": {"type": "string"}}, native.registry_read),
    ("display_list", "SAFE", "List all connected displays", {}, native.display_list),
    ("cursor_position", "SAFE", "Read the cursor position", {}, native.cursor_position),
    ("window_list", "SAFE", "List visible windows", {}, native.window_list),
    ("active_window", "SAFE", "Read the foreground window", {}, native.active_window),
    ("ui_tree", "SAFE", "Read a bounded Windows UI Automation tree", {"hwnd": {"type": "integer"}, "max_nodes": {"type": "integer"}}, native.ui_tree),
    ("ui_find", "SAFE", "Find one exact UI Automation element", {"name": {"type": "string"}, "automation_id": {"type": "string"}, "hwnd": {"type": "integer"}}, native.ui_find),
    ("ui_properties", "SAFE", "Read UI Automation element properties and supported patterns", {"name": {"type": "string"}, "automation_id": {"type": "string"}, "hwnd": {"type": "integer"}}, native.ui_properties),
    ("ui_get_text", "SAFE", "Read text or value from one UI Automation element", {"name": {"type": "string"}, "automation_id": {"type": "string"}, "hwnd": {"type": "integer"}}, native.ui_get_text),
    ("ocr_image", "SAFE", "Recognize Hungarian text in a local image", {"path": {"type": "string"}, "max_chars": {"type": "integer"}}, native.ocr_image),
    ("camera_list", "SAFE", "List DirectShow video devices", {}, native.camera_list),
    ("process_list", "SAFE", "List running processes", {"limit": {"type": "integer", "minimum": 1, "maximum": 500}}, native.process_list),
    ("service_list", "SAFE", "List Windows services", {"limit": {"type": "integer", "minimum": 1, "maximum": 500}}, native.service_list),
    ("file_list", "SAFE", "List a directory", {"path": {"type": "string"}, "limit": {"type": "integer"}}, native.file_list),
    ("file_read", "SAFE", "Read a bounded UTF-8 text-file segment", {"path": {"type": "string"}, "max_bytes": {"type": "integer"}, "offset": {"type": "integer"}, "length": {"type": "integer"}}, native.file_read),
    ("file_search", "SAFE", "Search files by name", {"path": {"type": "string"}, "pattern": {"type": "string"}, "recursive": {"type": "boolean"}, "limit": {"type": "integer"}}, native.file_search),
    ("file_properties", "SAFE", "Read file or directory metadata", {"path": {"type": "string"}}, native.file_properties),
    ("screenshot", "SAFE", "Capture a monitor, virtual desktop, window, or bounded region", {"path": {"type": "string"}, "left": {"type": "integer"}, "top": {"type": "integer"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "monitor": {"type": "string"}, "monitor_index": {"type": "integer"}, "virtual_desktop": {"type": "boolean"}, "hwnd": {"type": "integer"}, "image_format": {"type": "string"}, "quality": {"type": "integer"}, "max_dimension": {"type": "integer"}}, native.screenshot),
    ("screen_compare", "SAFE", "Compare two captured images using bounded SHA-256 metadata", {"path_a": {"type": "string"}, "path_b": {"type": "string"}}, native.screen_compare),
    ("screen_wait_change", "SAFE", "Wait for a captured screen region to change", {"path": {"type": "string"}, "timeout_ms": {"type": "integer"}, "interval_ms": {"type": "integer"}, "left": {"type": "integer"}, "top": {"type": "integer"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "monitor": {"type": "string"}, "monitor_index": {"type": "integer"}, "virtual_desktop": {"type": "boolean"}, "hwnd": {"type": "integer"}}, native.screen_wait_change),
    ("mouse_move", "NORMAL", "Move the mouse in the virtual desktop", {"x": {"type": "integer"}, "y": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.mouse_move),
    ("mouse_click", "NORMAL", "Click with physical/logical or window-relative coordinates", {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string"}, "hwnd": {"type": "integer"}, "relative": {"type": "boolean"}, "coordinate_space": {"type": "string"}, "monitor": {"type": "string"}, "monitor_index": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.mouse_click),
    ("mouse_drag", "NORMAL", "Drag the mouse", {"x1": {"type": "integer"}, "y1": {"type": "integer"}, "x2": {"type": "integer"}, "y2": {"type": "integer"}, "duration_ms": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.mouse_drag),
    ("mouse_scroll", "NORMAL", "Scroll the mouse wheel", {"amount": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.mouse_scroll),
    ("key_press", "NORMAL", "Press one virtual key", {"vk": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.key_press),
    ("hotkey", "NORMAL", "Press a virtual-key combination", {"vks": {"type": "array"}, "confirm": {"type": "boolean"}}, native.hotkey),
    ("type_text", "NORMAL", "Type literal Unicode text into the focused window", {"text": {"type": "string"}, "confirm": {"type": "boolean"}}, native.type_text),
    ("clipboard_read", "NORMAL", "Read the current Unicode clipboard", {"max_chars": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.clipboard_read),
    ("clipboard_write", "NORMAL", "Replace the Unicode clipboard", {"text": {"type": "string"}, "confirm": {"type": "boolean"}}, native.clipboard_write),
    ("window_focus", "NORMAL", "Focus a visible window", {"hwnd": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.window_focus),
    ("window_set_state", "NORMAL", "Minimize, maximize, or restore a window", {"hwnd": {"type": "integer"}, "state": {"type": "string"}, "confirm": {"type": "boolean"}}, native.window_set_state),
    ("window_resize", "NORMAL", "Move and resize a window", {"hwnd": {"type": "integer"}, "x": {"type": "integer"}, "y": {"type": "integer"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.window_resize),
    ("window_close", "NORMAL", "Request that a window closes", {"hwnd": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.window_close),
    ("ui_invoke", "NORMAL", "Invoke or toggle one exact UI Automation element", {"name": {"type": "string"}, "automation_id": {"type": "string"}, "hwnd": {"type": "integer"}, "action": {"type": "string"}, "confirm": {"type": "boolean"}}, native.ui_invoke),
    ("ui_set_value", "NORMAL", "Set the value of one exact UI Automation element", {"name": {"type": "string"}, "automation_id": {"type": "string"}, "hwnd": {"type": "integer"}, "value": {"type": "string"}, "confirm": {"type": "boolean"}}, native.ui_set_value),
    ("ui_select", "NORMAL", "Select one exact UI Automation item", {"name": {"type": "string"}, "automation_id": {"type": "string"}, "hwnd": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.ui_select),
    ("ui_toggle", "NORMAL", "Toggle one exact UI Automation element", {"name": {"type": "string"}, "automation_id": {"type": "string"}, "hwnd": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.ui_toggle),
    ("ui_scroll", "NORMAL", "Scroll one exact UI Automation item into view", {"name": {"type": "string"}, "automation_id": {"type": "string"}, "hwnd": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.ui_scroll),
    ("ui_focus", "NORMAL", "Focus one exact UI Automation element", {"name": {"type": "string"}, "automation_id": {"type": "string"}, "hwnd": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.ui_focus),
    ("camera_snapshot", "NORMAL", "Capture one camera frame when explicitly enabled", {"device": {"type": "string"}, "path": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.camera_snapshot),
    ("launch_application", "NORMAL", "Launch a local application", {"command": {"type": "string"}, "arguments": {"type": "array"}, "confirm": {"type": "boolean"}}, native.launch_application),
    ("file_write", "NORMAL", "Write a UTF-8 text file", {"path": {"type": "string"}, "text": {"type": "string"}, "confirm": {"type": "boolean"}}, native.file_write),
    ("file_copy", "NORMAL", "Copy one file", {"source": {"type": "string"}, "destination": {"type": "string"}, "overwrite": {"type": "boolean"}, "confirm": {"type": "boolean"}}, native.file_copy),
    ("file_move", "NORMAL", "Move one file", {"source": {"type": "string"}, "destination": {"type": "string"}, "overwrite": {"type": "boolean"}, "confirm": {"type": "boolean"}}, native.file_move),
    ("file_delete", "NORMAL", "Delete one file", {"path": {"type": "string"}, "confirm": {"type": "boolean"}}, native.file_delete),
    ("terminal_run", "NORMAL", "Run a bounded PowerShell or CMD command", {"command": {"type": "string"}, "shell": {"type": "string"}, "timeout_ms": {"type": "integer"}, "max_output": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.terminal_run),
    ("terminal_start", "NORMAL", "Start an in-memory interactive terminal session", {"shell": {"type": "string"}, "confirm": {"type": "boolean"}}, native.terminal_start),
    ("terminal_input", "NORMAL", "Send text to an interactive terminal session", {"session_id": {"type": "string"}, "text": {"type": "string"}, "confirm": {"type": "boolean"}}, native.terminal_input),
    ("terminal_poll", "NORMAL", "Read bounded output from an interactive terminal session", {"session_id": {"type": "string"}, "max_lines": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.terminal_poll),
    ("terminal_stop", "NORMAL", "Stop an interactive terminal session", {"session_id": {"type": "string"}, "confirm": {"type": "boolean"}}, native.terminal_stop),
    ("application_uninstall", "NORMAL", "Uninstall one exact WinGet package", {"package_id": {"type": "string"}, "timeout_ms": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.application_uninstall),
    ("application_update", "NORMAL", "Update one exact WinGet package", {"package_id": {"type": "string"}, "timeout_ms": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.application_update),
    ("workflow_run", "NORMAL", "Run an ordered, conditional, bounded SAFE/NORMAL workflow", {"steps": {"type": "array"}, "timeout_ms": {"type": "integer"}, "confirm": {"type": "boolean"}}, None),
    ("permission_prompt", "NORMAL", "Show a visible user approval dialog for a pending request", {"request_id": {"type": "string"}, "scope": {"type": "string"}, "title": {"type": "string"}, "message": {"type": "string"}, "expires_seconds": {"type": "integer"}}, native.permission_prompt),
    ("execution_broker_run", "NORMAL", "Run one hash-pinned broker profile without a shell", {"profile_id": {"type": "string"}, "arguments": {"type": "array"}, "timeout_ms": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.execution_broker_run),
    ("process_stop", "ADMIN", "Stop one process tree", {"pid": {"type": "integer"}, "confirm": {"type": "boolean"}}, native.process_stop),
    ("service_control", "ADMIN", "Request start or stop for one Windows service", {"name": {"type": "string"}, "action": {"type": "string"}, "confirm": {"type": "boolean"}}, native.service_control),
]
TOOL_MAP = {name: (mode, description, schema, function) for name, mode, description, schema, function in TOOLS}


def _path_value(value: Any, path: str) -> Any:
    current = value
    for part in path.split(".") if path else []:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(path)
    return current


def _resolve_workflow_refs(value: Any, results: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        reference = value[2:-1]
        step_id, _, path = reference.partition(".")
        if step_id not in results:
            raise ValueError(f"Ismeretlen workflow-hivatkozás: {step_id}")
        return _path_value(results[step_id], path)
    if isinstance(value, dict):
        return {key: _resolve_workflow_refs(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_workflow_refs(item, results) for item in value]
    return value


def _workflow_condition(condition: dict[str, Any], results: dict[str, Any]) -> bool:
    step_id = str(condition.get("step", ""))
    if step_id not in results:
        return False
    try:
        actual = _path_value(results[step_id], str(condition.get("path", "")))
    except KeyError:
        return False
    if "equals" in condition:
        return actual == condition["equals"]
    if "exists" in condition:
        return bool(actual) is bool(condition["exists"])
    if "not_equals" in condition:
        return actual != condition["not_equals"]
    return bool(actual)


def _run_workflow(args: dict[str, Any]) -> dict[str, Any]:
    steps = args.get("steps")
    if not isinstance(steps, list) or not steps or len(steps) > 32:
        raise ValueError("A workflow 1-32 lépésből állhat.")
    timeout_ms = max(100, min(int(args.get("timeout_ms", 120000)), 120000))
    started = time.perf_counter()
    deadline = started + timeout_ms / 1000
    results: dict[str, Any] = {}
    step_reports: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def record(step_id: str, status: str, result: Any = None, error: str = "") -> None:
        report = {"id": step_id, "status": status}
        if result is not None:
            report["result"] = result
        if error:
            report["error"] = error
        step_reports.append(report)
        results[step_id] = report

    for index, raw_step in enumerate(steps):
        if not isinstance(raw_step, dict):
            raise ValueError(f"A workflow {index + 1}. lépése nem objektum.")
        step_id = str(raw_step.get("id", f"step_{index + 1}"))
        if not step_id or step_id in seen_ids:
            raise ValueError(f"Duplikált vagy üres workflow-azonosító: {step_id!r}")
        seen_ids.add(step_id)
        if time.perf_counter() >= deadline:
            record(step_id, "not_run", error="workflow_timeout")
            for rest in steps[index + 1:]:
                rest_id = str(rest.get("id", f"step_{steps.index(rest) + 1}")) if isinstance(rest, dict) else "unknown"
                record(rest_id, "not_run", error="workflow_timeout")
            return {"status": "timed_out", "steps": step_reports,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
        condition = raw_step.get("when")
        if condition is not None and (not isinstance(condition, dict) or not _workflow_condition(condition, results)):
            record(step_id, "skipped", error="condition_false")
            continue

        try:
            if "wait_for" in raw_step:
                wait = raw_step["wait_for"]
                if not isinstance(wait, dict):
                    raise ValueError("A wait_for lépés objektum kell legyen.")
                tool = str(wait.get("tool", ""))
                if tool not in TOOL_MAP or TOOL_MAP[tool][0] != "SAFE" or tool == "workflow_run":
                    raise ValueError("A wait_for csak SAFE eszközt hívhat.")
                wait_timeout = max(100, min(int(wait.get("timeout_ms", 10000)), 120000))
                interval = max(50, min(int(wait.get("interval_ms", 250)), 5000)) / 1000
                wait_deadline = min(deadline, time.perf_counter() + wait_timeout / 1000)
                attempts = 0
                last = None
                while time.perf_counter() < wait_deadline:
                    attempts += 1
                    try:
                        last = dispatch(tool, _resolve_workflow_refs(wait.get("arguments", {}), results))
                        until = wait.get("until", {})
                        if isinstance(until, dict) and _workflow_condition({"step": "_wait", **until}, {"_wait": last}):
                            record(step_id, "succeeded", {"attempts": attempts, "result": last})
                            break
                    except Exception as exc:
                        last = {"error": str(exc)}
                    time.sleep(interval)
                else:
                    record(step_id, "timed_out", {"attempts": attempts, "last": last}, "wait_timeout")
                    return {"status": "timed_out", "steps": step_reports,
                            "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
                continue

            tool = str(raw_step.get("tool", ""))
            if tool not in TOOL_MAP or tool == "workflow_run":
                raise ValueError(f"Ismeretlen vagy nem beágyazható workflow-eszköz: {tool}")
            arguments = _resolve_workflow_refs(raw_step.get("arguments", {}), results)
            if not isinstance(arguments, dict):
                raise ValueError("A workflow arguments objektum kell legyen.")
            result = dispatch(tool, arguments)
            embedded_status = result.get("status") if isinstance(result, dict) else None
            if embedded_status is not None and embedded_status != "succeeded":
                message = f"A beágyazott {tool} művelet státusza: {embedded_status}."
                record(step_id, "failed", result, message)
                if not bool(raw_step.get("continue_on_error", False)):
                    return {"status": "failed", "steps": step_reports,
                            "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
                continue
            if isinstance(result, dict) and result.get("error"):
                message = f"{result['error']}: {result.get('message', '')}".strip()
                record(step_id, "failed", result, message)
                if not bool(raw_step.get("continue_on_error", False)):
                    return {"status": "failed", "steps": step_reports,
                            "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
                continue
            record(step_id, "succeeded", result)
        except Exception as exc:
            record(step_id, "failed", error=str(exc))
            if not bool(raw_step.get("continue_on_error", False)):
                return {"status": "failed", "steps": step_reports,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2)}

    status = "succeeded" if all(item["status"] in {"succeeded", "skipped"} for item in step_reports) else "partial"
    return {"status": status, "steps": step_reports,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2)}


def _permission_status() -> dict[str, Any]:
    data = _permission_data()
    active = {}
    expired = []
    now = time.time()
    for scope, entry in data.get("active", {}).items():
        if isinstance(entry, dict) and entry.get("expires") is not None and float(entry["expires"]) <= now:
            expired.append({"scope": scope, "entry": entry})
        else:
            active[scope] = entry
    with PERMISSION_LOCK:
        one_time = {scope: count for scope, count in ONE_TIME_APPROVALS.items() if count > 0}
        one_time_denied = {scope: count for scope, count in ONE_TIME_DENIALS.items() if count > 0}
    capability_active = {scope: entry for scope, entry in active.items()
                         if scope.startswith("v3:capability:")}
    return {"path": str(PERMISSION_PATH), "active": active, "expired": expired,
            "capability_groups": capability_active,
            "session_allowed": sorted(SESSION_APPROVALS),
            "session_denied": sorted(SESSION_DENIALS),
            "one_time": one_time, "one_time_denied": one_time_denied,
            "pending": list(PENDING_APPROVALS.values()), "history": data.get("history", [])}


def _apply_user_decision(scope: str, decision: str, expires_seconds: int | None = None,
                         request_id: str | None = None) -> dict[str, Any]:
    decision = decision.lower()
    if not scope or len(scope) > 300 or any(char in scope for char in "\r\n\x00"):
        raise ValueError("Érvénytelen engedélykör.")
    if decision not in {"once_allow", "session_allow", "always_allow", "once_deny",
                        "session_deny", "always_deny", "revoke"}:
        raise ValueError("Érvénytelen felhasználói döntés.")
    expires = None if expires_seconds is None else time.time() + max(60, min(int(expires_seconds), 31_536_000))
    with PERMISSION_LOCK:
        data = _permission_data()
        active = data.setdefault("active", {})
        if decision == "once_allow":
            ONE_TIME_APPROVALS[scope] = ONE_TIME_APPROVALS.get(scope, 0) + 1
        elif decision == "once_deny":
            ONE_TIME_DENIALS[scope] = ONE_TIME_DENIALS.get(scope, 0) + 1
        elif decision == "session_allow":
            SESSION_APPROVALS[scope] = "session"
            SESSION_DENIALS.pop(scope, None)
        elif decision == "session_deny":
            SESSION_DENIALS[scope] = "session"
            SESSION_APPROVALS.pop(scope, None)
        elif decision == "revoke":
            active.pop(scope, None)
            ONE_TIME_APPROVALS.pop(scope, None)
            ONE_TIME_DENIALS.pop(scope, None)
            SESSION_APPROVALS.pop(scope, None)
            SESSION_DENIALS.pop(scope, None)
        else:
            active[scope] = {"decision": decision,
                             "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            if expires is not None:
                active[scope]["expires"] = expires
            SESSION_APPROVALS.pop(scope, None)
            SESSION_DENIALS.pop(scope, None)
            ONE_TIME_APPROVALS.pop(scope, None)
            ONE_TIME_DENIALS.pop(scope, None)
        _save_permission_data(data)
        _record_permission(scope, decision, "user_prompt")
        if request_id:
            PENDING_APPROVALS.pop(request_id, None)
    result = {"scope": scope, "decision": decision, "saved": True}
    if decision == "once_allow":
        token = secrets.token_urlsafe(24)
        APPROVAL_TOKENS[token] = {"scope": scope, "expires": time.time() + 300}
        result["approval_token"] = token
    return result


def tool_descriptions() -> list[dict]:
    result = []
    for name, mode, description, properties, _function in TOOLS:
        result.append({
            "name": name,
            "description": f"{description} [minimum mode: {mode}]",
            "inputSchema": {"type": "object", "properties": properties, "additionalProperties": False},
        })
    return result


def dispatch(name: str, args: dict[str, Any]) -> dict:
    if name not in TOOL_MAP:
        return {"error": "unknown_tool", "message": name}
    mode, _description, schema, function = TOOL_MAP[name]
    if name != "permission_prompt" and mode != "SAFE":
        denied = _permission(args, name, mode)
        if denied:
            return denied
    if name == "permission_status":
        return _permission_status()
    if name == "permission_prompt":
        request_id = str(args.get("request_id", ""))
        request = PENDING_APPROVALS.get(request_id) if request_id else None
        if request is not None:
            scope = request["scope"]
            group = request.get("capability_group")
            title = str(args.get("title") or
                         (CAPABILITY_GROUPS[group]["title"] if group in CAPABILITY_GROUPS
                          else "Windows Control MCP – jóváhagyás"))
            duration_text = ("A választás a korlátozott számítógép-vezérlési képességcsoportra vonatkozik; "
                             "nem ad fájl-, terminál-, kamera-, broker- vagy rendszergazdai jogot."
                             if group else "A választás csak a megjelölt pontos műveletre vonatkozik.")
            message = (f"Művelet: {request['target']}\n"
                       f"Kérő kliens: {request['agent']}\nKockázat: {request['risk']}\n"
                       f"{duration_text}\nVálassz döntést a művelet előtt.")
        else:
            scope = str(args.get("scope", ""))
            if not scope:
                return {"error": "approval_request_not_found", "message": "A jóváhagyási kérés nem található."}
            title = str(args.get("title", "Windows Control MCP – engedélykezelés"))
            message = str(args.get("message", f"Engedélykör kezelése: {scope}"))
        result = function(title, message, int(args.get("timeout_ms", 120000)))
        if result.get("decision") in {"once_allow", "session_allow", "always_allow",
                                       "once_deny", "session_deny", "always_deny", "revoke"}:
            result["permission"] = _apply_user_decision(
                scope, result["decision"], int(args["expires_seconds"]) if "expires_seconds" in args else None,
                request_id or None)
        return result
    if name == "workflow_run":
        return _run_workflow(args)
    if name == "process_list":
        return function(int(args.get("limit", 200)))
    if name == "system_metrics":
        return function()
    if name == "execution_broker_profiles":
        return function()
    if name == "network_adapters":
        return function()
    if name == "installed_applications":
        return function(int(args.get("limit", 500)))
    if name == "installed_application_summary":
        return function(int(args.get("limit", 2000)))
    if name == "application_updates":
        return function()
    if name == "application_maintenance_history":
        return function(int(args.get("limit", 200)))
    if name == "execution_broker_run":
        return function(str(args["profile_id"]), [str(value) for value in args.get("arguments", [])],
                        int(args.get("timeout_ms", 30000)))
    if name == "registry_read":
        return function(str(args["root"]), str(args["subkey"]),
                        str(args["value_name"]) if "value_name" in args else None)
    if name == "service_list":
        return function(int(args.get("limit", 200)))
    if name == "file_list":
        return function(str(args["path"]), int(args.get("limit", 200)))
    if name == "file_read":
        return function(str(args["path"]), int(args.get("max_bytes", 1_000_000)),
                        int(args.get("offset", 0)),
                        int(args["length"]) if "length" in args else None)
    if name == "file_search":
        return function(str(args["path"]), str(args["pattern"]), bool(args.get("recursive", True)), int(args.get("limit", 200)))
    if name == "file_properties":
        return function(str(args["path"]))
    if name == "screenshot":
        return function(args.get("path"), int(args.get("left", 0)), int(args.get("top", 0)),
                        int(args["width"]) if "width" in args else None,
                        int(args["height"]) if "height" in args else None,
                        args.get("monitor"), int(args["monitor_index"]) if "monitor_index" in args else None,
                        bool(args.get("virtual_desktop", False)), int(args.get("hwnd", 0)),
                        str(args.get("image_format", "bmp")), int(args.get("quality", 90)),
                        int(args["max_dimension"]) if "max_dimension" in args else None)
    if name == "screen_compare":
        return function(str(args["path_a"]), str(args["path_b"]))
    if name == "screen_wait_change":
        return function(str(args["path"]), int(args.get("timeout_ms", 10000)),
                        int(args.get("interval_ms", 250)), int(args.get("left", 0)),
                        int(args.get("top", 0)), int(args["width"]) if "width" in args else None,
                        int(args["height"]) if "height" in args else None, args.get("monitor"),
                        int(args["monitor_index"]) if "monitor_index" in args else None,
                        bool(args.get("virtual_desktop", False)), int(args.get("hwnd", 0)))
    if name == "ui_tree":
        return function(int(args.get("hwnd", 0)), int(args.get("max_nodes", 200)))
    if name in {"ui_find", "ui_properties", "ui_get_text", "ui_set_value", "ui_select", "ui_toggle", "ui_scroll", "ui_focus"}:
        return function(str(args.get("name", "")), str(args.get("automation_id", "")),
                        int(args.get("hwnd", 0)), **({"value": str(args.get("value", ""))} if name == "ui_set_value" else {}))
    if name == "ocr_image":
        return function(str(args["path"]), int(args.get("max_chars", 100_000)))
    if name == "ui_invoke":
        return function(str(args.get("name", "")), str(args.get("automation_id", "")),
                        int(args.get("hwnd", 0)), str(args.get("action", "invoke")))
    if name == "camera_list":
        return function()
    if name == "camera_snapshot":
        return function(str(args["device"]), str(args["path"]), int(args.get("width", 1280)),
                        int(args.get("height", 720)))
    if name == "mouse_move":
        return function(int(args["x"]), int(args["y"]))
    if name == "mouse_click":
        return function(int(args["x"]), int(args["y"]), args.get("button", "left"),
                        int(args.get("hwnd", 0)), bool(args.get("relative", False)),
                        str(args.get("coordinate_space", "physical")), args.get("monitor"),
                        int(args["monitor_index"]) if "monitor_index" in args else None)
    if name == "mouse_drag":
        return function(int(args["x1"]), int(args["y1"]), int(args["x2"]), int(args["y2"]), int(args.get("duration_ms", 300)))
    if name == "mouse_scroll":
        return function(int(args["amount"]))
    if name == "key_press":
        return function(int(args["vk"]))
    if name == "hotkey":
        return function([int(value) for value in args["vks"]])
    if name == "type_text":
        return function(str(args["text"]))
    if name == "clipboard_read":
        return function(int(args.get("max_chars", 100_000)))
    if name == "clipboard_write":
        return function(str(args["text"]))
    if name == "window_focus":
        return function(int(args["hwnd"]))
    if name == "window_set_state":
        return function(int(args["hwnd"]), str(args["state"]))
    if name == "window_resize":
        return function(int(args["hwnd"]), int(args["x"]), int(args["y"]), int(args["width"]), int(args["height"]))
    if name == "window_close":
        return function(int(args["hwnd"]))
    if name == "launch_application":
        return function(str(args["command"]), [str(value) for value in args.get("arguments", [])])
    if name == "file_write":
        return function(str(args["path"]), str(args["text"]))
    if name == "file_copy":
        return function(str(args["source"]), str(args["destination"]), bool(args.get("overwrite", False)))
    if name == "file_move":
        return function(str(args["source"]), str(args["destination"]), bool(args.get("overwrite", False)))
    if name == "file_delete":
        return function(str(args["path"]))
    if name == "terminal_run":
        return function(str(args["command"]), str(args.get("shell", "powershell")),
                        int(args.get("timeout_ms", 30000)), int(args.get("max_output", 20000)))
    if name == "terminal_start":
        return function(str(args.get("shell", "powershell")))
    if name == "terminal_input":
        return function(str(args["session_id"]), str(args["text"]))
    if name == "terminal_poll":
        return function(str(args["session_id"]), int(args.get("max_lines", 100)))
    if name == "terminal_stop":
        return function(str(args["session_id"]))
    if name == "application_uninstall":
        return function(str(args["package_id"]), int(args.get("timeout_ms", 120000)))
    if name == "application_update":
        return function(str(args["package_id"]), int(args.get("timeout_ms", 120000)))
    if name == "process_stop":
        return function(int(args["pid"]))
    if name == "service_control":
        return function(str(args["name"]), str(args["action"]))
    return function()


def handle(message: dict) -> dict | None:
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": message.get("params", {}).get("protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "windows-control-mcp", "version": __version__},
            "instructions": f"Local Windows MCP. Current mode: {MODE}. Input is disabled unless explicitly confirmed.",
        }}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tool_descriptions()}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/call":
        params = message.get("params", {})
        try:
            value = dispatch(params.get("name", ""), params.get("arguments") or {})
            is_error = isinstance(value, dict) and bool(value.get("error"))
            return {"jsonrpc": "2.0", "id": request_id, "result": {"content": _text(value), "isError": is_error}}
        except Exception as exc:
            print(json.dumps({"event": "tool_error", "tool": params.get("name"), "error": str(exc)}), file=sys.stderr)
            return {"jsonrpc": "2.0", "id": request_id, "result": {"content": _text({"error": "execution_failed", "message": str(exc)}), "isError": True}}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}


def main() -> None:
    for raw in sys.stdin:
        if not raw.strip():
            continue
        try:
            message = json.loads(raw)
            response = handle(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            print(json.dumps({"event": "protocol_error", "error": str(exc), "trace": traceback.format_exc()[-500:]}), file=sys.stderr)


if __name__ == "__main__":
    main()

