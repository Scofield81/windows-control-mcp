"""Small native Windows adapter used by the first MCP milestone."""

from __future__ import annotations

import ctypes
import csv
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from ctypes import wintypes
from pathlib import Path

if os.name == "nt":
    USER32 = ctypes.windll.user32
    KERNEL32 = ctypes.windll.kernel32
    USER32.OpenClipboard.argtypes = [wintypes.HWND]
    USER32.OpenClipboard.restype = wintypes.BOOL
    USER32.GetClipboardData.argtypes = [wintypes.UINT]
    USER32.GetClipboardData.restype = wintypes.HANDLE
    USER32.CloseClipboard.restype = wintypes.BOOL
    USER32.EmptyClipboard.restype = wintypes.BOOL
    USER32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    USER32.SetClipboardData.restype = wintypes.HANDLE
    KERNEL32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    KERNEL32.GlobalLock.restype = wintypes.LPVOID
    KERNEL32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    KERNEL32.GlobalUnlock.restype = wintypes.BOOL
    KERNEL32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    KERNEL32.GlobalAlloc.restype = wintypes.HGLOBAL
    KERNEL32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    KERNEL32.GlobalFree.restype = wintypes.HGLOBAL
    KERNEL32.GetCurrentThreadId.restype = wintypes.DWORD
    try:
        USER32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        USER32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        USER32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        pass
else:  # pragma: no cover - development guard for non-Windows hosts
    USER32 = None
    KERNEL32 = None

TERMINAL_SESSIONS: dict[str, dict] = {}
TERMINAL_LOCK = threading.Lock()
BROKER_TRANSPORT = os.environ.get("WINDOWS_CONTROL_BROKER_TRANSPORT", "service").lower()


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


def _require_windows() -> None:
    if USER32 is None:
        raise RuntimeError("Ez a natív adapter csak Windows rendszeren működik.")


def system_info() -> dict:
    _require_windows()
    memory = ctypes.create_string_buffer(64)
    memory_size = ctypes.c_ulong(ctypes.sizeof(memory))
    total_memory = 0
    available_memory = 0
    if hasattr(KERNEL32, "GlobalMemoryStatusEx"):
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(status)
        if KERNEL32.GlobalMemoryStatusEx(ctypes.byref(status)):
            total_memory = status.ullTotalPhys
            available_memory = status.ullAvailPhys

    drives = {}
    for drive in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = f"{drive}:\\"
        if os.path.exists(root):
            try:
                usage = shutil.disk_usage(root)
                drives[drive] = {
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                }
            except OSError:
                pass
    return {
        "platform": platform.platform(),
        "windows_version": platform.version(),
        "architecture": platform.machine(),
        "user": os.environ.get("USERNAME", ""),
        "computer": os.environ.get("COMPUTERNAME", ""),
        "memory_total": total_memory,
        "memory_available": available_memory,
        "drives": drives,
    }


def _filetime_value(value: wintypes.FILETIME) -> int:
    return (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)


def system_metrics() -> dict:
    """Read a bounded CPU, memory, uptime and storage snapshot."""
    _require_windows()
    idle_a, kernel_a, user_a = (wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME())
    idle_b, kernel_b, user_b = (wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME())
    cpu_percent = None
    if hasattr(KERNEL32, "GetSystemTimes"):
        if KERNEL32.GetSystemTimes(ctypes.byref(idle_a), ctypes.byref(kernel_a), ctypes.byref(user_a)):
            time.sleep(0.1)
            if KERNEL32.GetSystemTimes(ctypes.byref(idle_b), ctypes.byref(kernel_b), ctypes.byref(user_b)):
                idle_delta = _filetime_value(idle_b) - _filetime_value(idle_a)
                total_delta = (_filetime_value(kernel_b) - _filetime_value(kernel_a) +
                               _filetime_value(user_b) - _filetime_value(user_a))
                if total_delta > 0:
                    cpu_percent = round(max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100)), 2)
    info = system_info()
    uptime_ms = int(KERNEL32.GetTickCount64()) if hasattr(KERNEL32, "GetTickCount64") else None
    return {
        "cpu_percent": cpu_percent,
        "memory_total": info["memory_total"],
        "memory_available": info["memory_available"],
        "memory_used_percent": round((1 - info["memory_available"] / info["memory_total"]) * 100, 2)
        if info["memory_total"] else None,
        "uptime_ms": uptime_ms,
        "drives": info["drives"],
    }


def _powershell_json(command: str, timeout: float = 15.0) -> Any:
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "PowerShell lekérdezési hiba.")[:1000])
    try:
        return json.loads(completed.stdout or "null")
    except json.JSONDecodeError as exc:
        raise RuntimeError("A PowerShell lekérdezés érvénytelen JSON-t adott.") from exc


def network_adapters() -> list[dict]:
    """Read adapter, address, gateway and DNS information without changing it."""
    _require_windows()
    command = r"""$ErrorActionPreference='Stop';
    $rows = @(Get-NetIPConfiguration | ForEach-Object {
      [pscustomobject]@{
        interface_alias=$_.InterfaceAlias;
        description=$_.NetAdapter.InterfaceDescription;
        status=$_.NetAdapter.Status.ToString();
        mac=$_.NetAdapter.MacAddress;
        ipv4=@($_.IPv4Address | ForEach-Object {$_.IPv4Address});
        ipv6=@($_.IPv6Address | ForEach-Object {$_.IPv6Address});
        gateway=@($_.IPv4DefaultGateway | ForEach-Object {$_.NextHop});
        dns=@($_.DNSServer.ServerAddresses)
      }
    }); $rows | ConvertTo-Json -Compress -Depth 5"""
    value = _powershell_json(command)
    return value if isinstance(value, list) else ([] if value is None else [value])


def installed_applications(limit: int = 500) -> list[dict]:
    """Read installed application entries from the standard uninstall keys."""
    _require_windows()
    import winreg
    limit = max(1, min(int(limit), 2000))
    locations = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM32"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU"),
    ]
    result: dict[str, dict] = {}
    for root, path, hive in locations:
        try:
            with winreg.OpenKey(root, path) as parent:
                for index in range(winreg.QueryInfoKey(parent)[0]):
                    try:
                        subkey = winreg.EnumKey(parent, index)
                        with winreg.OpenKey(parent, subkey) as item:
                            name = winreg.QueryValueEx(item, "DisplayName")[0]
                            if not isinstance(name, str) or not name.strip():
                                continue
                            record = {"name": name.strip(), "hive": hive}
                            for field, value_name in (("version", "DisplayVersion"),
                                                       ("publisher", "Publisher"),
                                                       ("install_location", "InstallLocation"),
                                                       ("install_date", "InstallDate"),
                                                       ("estimated_size_kb", "EstimatedSize")):
                                try:
                                    record[field] = winreg.QueryValueEx(item, value_name)[0]
                                except OSError:
                                    pass
                            result.setdefault(record["name"].casefold(), record)
                    except OSError:
                        continue
        except OSError:
            continue
    return sorted(result.values(), key=lambda item: item["name"].casefold())[:limit]


def installed_application_summary(limit: int = 2000) -> dict:
    applications = installed_applications(limit)
    known_sizes = [int(item["estimated_size_kb"]) for item in applications
                   if isinstance(item.get("estimated_size_kb"), (int, float))]
    return {"application_count": len(applications),
            "known_size_count": len(known_sizes),
            "estimated_size_kb": sum(known_sizes),
            "estimated_size_bytes": sum(known_sizes) * 1024,
            "applications": applications}


def application_updates() -> dict:
    """Best-effort read-only WinGet upgrade listing; never installs anything."""
    _require_windows()
    winget = shutil.which("winget.exe") or shutil.which("winget")
    if not winget:
        return {"status": "unavailable", "reason": "winget_not_found", "updates": []}
    completed = subprocess.run(
        [winget, "upgrade", "--include-unknown", "--disable-interactivity"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=45, check=False,
    )
    updates = []
    column_starts = None
    for raw in completed.stdout.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Name") and all(token in line for token in ("Id", "Version", "Available")):
            column_starts = [line.find(token) for token in ("Id", "Version", "Available", "Source")]
            continue
        if stripped.startswith("---"):
            continue
        if stripped.startswith("The following") or "upgrades available" in stripped:
            column_starts = None
            continue
        if not column_starts or stripped.startswith("Name"):
            continue
        id_pos, version_pos, available_pos, source_pos = column_starts
        fields = [line[:id_pos].strip(), line[id_pos:version_pos].strip(),
                  line[version_pos:available_pos].strip(), line[available_pos:source_pos].strip(),
                  line[source_pos:].strip()]
        if len(fields) == 5 and fields[0] and fields[1] and fields[2] and fields[3]:
            updates.append({"name": fields[0], "id": fields[1], "version": fields[2],
                            "available": fields[3], "source": fields[4] or None})
    return {"status": "succeeded" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "updates": updates,
            "stdout": completed.stdout[:20_000], "stderr": completed.stderr[:5_000],
            "note": "Ez csak listáz; csomagot nem telepít és nem távolít el."}


def _application_history_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WindowsControlMCP" / "application-history.json"


def _record_application_event(action: str, package_id: str, status: str, exit_code: int | None) -> None:
    path = _application_history_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        history = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        if not isinstance(history, list):
            history = []
        history.append({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        "action": action, "package_id": package_id,
                        "status": status, "exit_code": exit_code})
        path.write_text(json.dumps(history[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass


def application_maintenance_history(limit: int = 200) -> list[dict]:
    path = _application_history_path()
    if not path.is_file():
        return []
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return history[-max(1, min(int(limit), 200)):] if isinstance(history, list) else []


def application_update(package_id: str, timeout_ms: int = 120_000) -> dict:
    """Update one exact WinGet package; caller must pass NORMAL approval."""
    _require_windows()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", package_id or ""):
        raise ValueError("Az alkalmazásazonosító csak pontos WinGet-azonosító lehet.")
    timeout_ms = max(1000, min(int(timeout_ms), 120_000))
    winget = shutil.which("winget.exe") or shutil.which("winget")
    if not winget:
        _record_application_event("update", package_id, "unavailable", None)
        return {"status": "unavailable", "reason": "winget_not_found", "package_id": package_id}
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [winget, "upgrade", "--id", package_id, "--exact", "--disable-interactivity"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_ms / 1000, check=False,
        )
        status = "succeeded" if completed.returncode == 0 else "failed"
        _record_application_event("update", package_id, status, completed.returncode)
        return {"status": status, "package_id": package_id,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[:20_000], "stderr": completed.stderr[:5_000],
                "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
    except subprocess.TimeoutExpired as exc:
        _record_application_event("update", package_id, "timed_out", None)
        return {"status": "timed_out", "package_id": package_id, "exit_code": None,
                "stdout": str(exc.stdout or "")[:20_000],
                "stderr": str(exc.stderr or "")[:5_000],
                "duration_ms": round((time.perf_counter() - started) * 1000, 2)}


def application_uninstall(package_id: str, timeout_ms: int = 120_000) -> dict:
    """Uninstall one exact WinGet package; caller must pass NORMAL confirmation."""
    _require_windows()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", package_id or ""):
        raise ValueError("Az alkalmazásazonosító csak pontos WinGet-azonosító lehet.")
    timeout_ms = max(1000, min(int(timeout_ms), 120_000))
    winget = shutil.which("winget.exe") or shutil.which("winget")
    if not winget:
        _record_application_event("uninstall", package_id, "unavailable", None)
        return {"status": "unavailable", "reason": "winget_not_found", "package_id": package_id}
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [winget, "uninstall", "--id", package_id, "--exact", "--disable-interactivity"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_ms / 1000, check=False,
        )
        status = "succeeded" if completed.returncode == 0 else "failed"
        _record_application_event("uninstall", package_id, status, completed.returncode)
        return {"status": status, "package_id": package_id,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[:20_000], "stderr": completed.stderr[:5_000],
                "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
    except subprocess.TimeoutExpired as exc:
        _record_application_event("uninstall", package_id, "timed_out", None)
        return {"status": "timed_out", "package_id": package_id, "exit_code": None,
                "stdout": str(exc.stdout or "")[:20_000],
                "stderr": str(exc.stderr or "")[:5_000],
                "duration_ms": round((time.perf_counter() - started) * 1000, 2)}


def permission_prompt(title: str, message: str, timeout_ms: int = 120_000) -> dict:
    """Show a visible, Hungarian, scope-specific Windows approval dialog."""
    _require_windows()
    if not title or len(title) > 160 or len(message) > 2000:
        raise ValueError("A jóváhagyási ablak szövege túl hosszú vagy üres.")
    timeout_ms = max(1000, min(int(timeout_ms), 120_000))
    command = r'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object System.Windows.Forms.Form
    $form.Text = 'Felhasználói jóváhagyás'
    $form.Width = 760; $form.Height = 410; $form.StartPosition = 'CenterScreen'
$form.TopMost = $true; $form.FormBorderStyle = 'FixedDialog'; $form.MaximizeBox = $false
$light = $true
try {
  $theme = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize' -Name AppsUseLightTheme -ErrorAction Stop
  $light = ([int]$theme.AppsUseLightTheme -ne 0)
} catch {}
$bg = if ($light) { [System.Drawing.Color]::White } else { [System.Drawing.Color]::FromArgb(32,33,36) }
$panel = if ($light) { [System.Drawing.Color]::White } else { [System.Drawing.Color]::FromArgb(43,45,49) }
$fg = if ($light) { [System.Drawing.Color]::FromArgb(32,33,36) } else { [System.Drawing.Color]::FromArgb(241,243,244) }
$muted = if ($light) { [System.Drawing.Color]::FromArgb(95,99,104) } else { [System.Drawing.Color]::FromArgb(189,193,198) }
$accent = if ($light) { [System.Drawing.Color]::FromArgb(26,115,232) } else { [System.Drawing.Color]::FromArgb(138,180,248) }
$form.BackColor = $bg
$label = New-Object System.Windows.Forms.Label
    $label.Text = $env:WCM_MAIN; $label.Left = 20; $label.Top = 18; $label.Width = 700; $label.Height = 118
    $label.ForeColor = $fg; $label.BackColor = $panel; $label.Font = New-Object System.Drawing.Font('Segoe UI',10)
$form.Controls.Add($label)
$detailButton = New-Object System.Windows.Forms.Button
    $detailButton.Text = 'Technikai részletek megjelenítése'; $detailButton.Left = 20; $detailButton.Top = 142; $detailButton.Width = 270; $detailButton.Height = 30
    $detailButton.BackColor = $panel; $detailButton.ForeColor = $accent
$form.Controls.Add($detailButton)
$detailBox = New-Object System.Windows.Forms.RichTextBox
    $detailBox.Text = $env:WCM_DETAILS; $detailBox.Left = 20; $detailBox.Top = 177; $detailBox.Width = 700; $detailBox.Height = 78; $detailBox.ReadOnly = $true; $detailBox.Visible = $false
    $detailBox.BackColor = $bg; $detailBox.ForeColor = $fg
$form.Controls.Add($detailBox)
$detailButton.Add_Click({
  $detailBox.Visible = -not $detailBox.Visible
  if ($detailBox.Visible) { $detailButton.Text = 'Technikai részletek elrejtése' } else { $detailButton.Text = 'Technikai részletek megjelenítése' }
})
    $buttons = @(@('Egyszer engedélyezem','once_allow',20,235), @('Munkamenetre engedélyezem','session_allow',265,235), @('Mindig engedélyezem','always_allow',510,235), @('Egyszer elutasítom','once_deny',20,280), @('Munkamenetre elutasítom','session_deny',265,280), @('Mindig elutasítom','always_deny',510,280), @('Engedély visszavonása','revoke',20,325))
    foreach($item in $buttons) {
  $button = New-Object System.Windows.Forms.Button
      $button.Text = $item[0]; $button.Tag = $item[1]; $button.Left = [int]$item[2]; $button.Top = [int]$item[3]; $button.Width = 210; $button.Height = 35
      $button.BackColor = $panel; $button.ForeColor = $fg
      if ($item[1] -eq 'always_allow') { $button.BackColor = $accent; $button.ForeColor = if ($light) { [System.Drawing.Color]::White } else { [System.Drawing.Color]::FromArgb(32,33,36) }; $button.Font = New-Object System.Drawing.Font('Segoe UI',9,[System.Drawing.FontStyle]::Bold) }
  $button.Add_Click({ $script:WcmDecision = $this.Tag; $form.Close() })
  $form.Controls.Add($button)
}
$script:WcmDecision = 'deny'
[void]$form.ShowDialog()
Write-Output $script:WcmDecision
'''
    environment = os.environ.copy()
    environment["WCM_TITLE"] = title
    lines = {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip()
             for line in message.splitlines() if ":" in line}
    operation = lines.get("Művelet", "ismeretlen művelet")
    target = lines.get("Cél", "a megjelölt alkalmazás vagy ablak")
    agent = lines.get("Kérő kliens", "ismeretlen kérő")
    risk = lines.get("Kockázat", "nem meghatározott")
    friendly_effects = {
        "window_focus": "A megjelölt alkalmazás ablakát előtérbe hozza.",
        "hotkey": "A megadott billentyűkombinációt elküldi a célablaknak.",
        "type_text": "A jóváhagyott szöveget beírja a célablakba.",
        "key_press": "A megadott billentyűt elküldi a célablaknak.",
        "ui_invoke": "A kiválasztott felületi elemen végrehajtja a megadott műveletet.",
    }
    effect = friendly_effects.get(operation, "A megadott műveletet végrehajtja a megjelölt célon.")
    # A beírandó szöveg nem alkalmazás- vagy célazonosító. Ne jelenítsük meg
    # célként a teljes keresőkifejezést a fő jóváhagyási szövegben; az a
    # technikai részletekben marad, miközben a felhasználó a tényleges hatást
    # látja.
    if operation == "type_text":
        target_label = "a kijelölt beviteli mező"
    elif operation in {"hotkey", "key_press", "window_focus", "ui_invoke"} and "5639316" in target:
        target_label = "Google Chrome"
    else:
        target_label = target
    is_capability_group = "képességcsoport" in message.lower() or "számítógép vezérlésének engedélyezése" in title.lower()
    scope_explanation = ("A választás a korlátozott számítógép-vezérlési képességcsoportra érvényes: képernyő-, ablak-, egér-, billentyűzet- és böngészővezérlésre. Fájl-, terminál-, kamera-, broker- és rendszergazdai műveletekre nem ad jogot."
                         if is_capability_group else
                         "A választott engedély csak erre a pontos műveletre és a kiválasztott időtartamra érvényes. Más alkalmazásra, fájlra vagy műveletre nem ad jogosultságot.")
    environment["WCM_MAIN"] = (f"Az ügynök a következő művelethez kér engedélyt:\n\n"
                                f"Művelet: {effect}\n"
                                f"Alkalmazás vagy cél: {target_label}\n"
                                f"Kérő: {agent}\n"
                                f"Várható hatás és kockázat: {effect} Kockázat: {risk}.\n\n"
                                f"{scope_explanation}")
    environment["WCM_DETAILS"] = ("Megnevezés: " + title + "\n\n" + message)
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_ms / 1000, check=False, env=environment,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timed_out", "decision": "once_deny"}
    decision = (completed.stdout.strip().splitlines()[-1].lower()
                if completed.stdout.strip() else "deny")
    if decision not in {"once_allow", "session_allow", "always_allow", "once_deny", "session_deny", "always_deny", "revoke"}:
        decision = "once_deny"
    return {"status": "succeeded" if completed.returncode == 0 else "failed",
            "decision": decision, "exit_code": completed.returncode}


def registry_read(root: str, subkey: str, value_name: str | None = None) -> dict:
    """Read one registry key or value; no registry writes are exposed."""
    _require_windows()
    import winreg
    roots = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE,
             "HKCR": winreg.HKEY_CLASSES_ROOT, "HKU": winreg.HKEY_USERS}
    root_name = str(root).upper()
    if root_name not in roots or not subkey or any(char in subkey for char in "\r\n\x00"):
        raise ValueError("Érvénytelen registry-útvonal.")
    with winreg.OpenKey(roots[root_name], subkey) as key:
        if value_name is not None:
            value, kind = winreg.QueryValueEx(key, value_name)
            return {"root": root_name, "subkey": subkey, "value_name": value_name,
                    "value": value, "type": kind}
        values = {}
        for index in range(winreg.QueryInfoKey(key)[1]):
            name, value, kind = winreg.EnumValue(key, index)
            values[name] = {"value": value, "type": kind}
        return {"root": root_name, "subkey": subkey, "values": values}


def file_properties(path: str) -> dict:
    """Read bounded file metadata and basic access flags."""
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise ValueError("A megadott útvonal nem létezik.")
    stat = target.stat()
    return {"path": str(target), "name": target.name, "directory": target.is_dir(),
            "size": stat.st_size, "created": stat.st_ctime, "modified": stat.st_mtime,
            "accessed": stat.st_atime, "readonly": not os.access(target, os.W_OK),
            "hidden": bool(target.name.startswith("."))}


def _broker_policy_path() -> Path:
    if BROKER_TRANSPORT == "service":
        root = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "WindowsControlMCP"
        return root / "broker-policy.json"
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WindowsControlMCP"
    return root / "execution-broker.json"


_BROKER_BLOCKED_EXECUTABLES = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "python.exe", "pythonw.exe",
    "py.exe", "wscript.exe", "cscript.exe", "mshta.exe", "rundll32.exe",
    "regsvr32.exe", "installutil.exe", "msiexec.exe",
}


def _broker_load_policy() -> dict:
    path = _broker_policy_path()
    if not path.is_file():
        raise RuntimeError("Nincs konfigurált execution broker házirend.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("A broker házirendje nem olvasható.") from exc
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("profiles"), dict):
        raise RuntimeError("A broker házirend sémája érvénytelen.")
    return data


def _broker_file_identity(path: Path) -> tuple[int, int, int, int]:
    try:
        stat = path.stat()
        attributes = int(getattr(stat, "st_file_attributes", 0))
        # FILE_ATTRIBUTE_REPARSE_POINT. Reparse points make lexical path
        # validation insufficient for a security-sensitive executable.
        if attributes & 0x400:
            raise RuntimeError("A broker végrehajtható fájlja reparse point.")
        if path.is_symlink():
            raise RuntimeError("A broker végrehajtható fájlja szimbolikus hivatkozás.")
        return int(getattr(stat, "st_dev", 0)), int(getattr(stat, "st_ino", 0)), int(stat.st_size), int(stat.st_mtime_ns)
    except OSError as exc:
        raise RuntimeError("A broker végrehajtható fájlja nem ellenőrizhető.") from exc


def _broker_validate_executable(profile: dict) -> tuple[Path, tuple[int, int, int, int]]:
    executable = Path(str(profile.get("executable", ""))).expanduser()
    if not executable.is_absolute() or not executable.is_file():
        raise RuntimeError("A broker-profil végrehajtható fájlja nem érvényes.")
    if executable.name.casefold() in _BROKER_BLOCKED_EXECUTABLES:
        raise RuntimeError("Általános parancsértelmező vagy scriptfuttató nem lehet brokerprofil.")
    identity_before = _broker_file_identity(executable)
    expected_hash = str(profile.get("sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise RuntimeError("A broker-profil nem tartalmaz érvényes SHA-256 pin-t.")
    try:
        actual_hash = hashlib.sha256(executable.read_bytes()).hexdigest().lower()
    except OSError as exc:
        raise RuntimeError("A broker végrehajtható fájlja nem olvasható.") from exc
    identity_after = _broker_file_identity(executable)
    if identity_before != identity_after or actual_hash != expected_hash:
        raise RuntimeError("A broker végrehajtható fájlja az ellenőrzés alatt megváltozott vagy a hash-e eltér.")
    return executable, identity_after


def execution_broker_profiles() -> list[dict]:
    """List explicitly configured, hash-pinned broker profiles."""
    path = _broker_policy_path()
    try:
        exists = path.is_file()
    except OSError:
        return []
    if not exists:
        return []
    data = _broker_load_policy()
    profiles = data["profiles"]
    result = []
    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        result.append({"profile_id": str(profile_id), "kind": profile.get("kind", "process"),
                       "executable": str(profile.get("executable", "")),
                       "sha256": str(profile.get("sha256", "")),
                       "fixed_argument_count": len(profile.get("fixed_arguments", []))})
    return result


def execution_broker_status() -> dict:
    """Report broker transport and policy locations without exposing secrets."""
    local_path = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WindowsControlMCP" / "execution-broker.json"
    service_path = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "WindowsControlMCP" / "broker-policy.json"
    selected = service_path if BROKER_TRANSPORT == "service" else local_path
    result = {
        "transport": BROKER_TRANSPORT,
        "selected_policy_path": str(selected),
        "local_policy_path": str(local_path),
        "service_policy_path": str(service_path),
        "selected_policy_state": "missing",
        "profiles_count": 0,
    }
    try:
        if not selected.exists():
            return result
        if not selected.is_file():
            result["selected_policy_state"] = "not_a_file"
            return result
        result["selected_policy_state"] = "present"
        data = json.loads(selected.read_text(encoding="utf-8-sig"))
        result["profiles_count"] = len(data.get("profiles", {})) if isinstance(data, dict) and isinstance(data.get("profiles"), dict) else 0
    except PermissionError:
        result["selected_policy_state"] = "inaccessible"
        result["error"] = "access_denied"
    except (OSError, json.JSONDecodeError):
        result["selected_policy_state"] = "unreadable"
        result["error"] = "policy_unreadable"
    return result


def execution_broker_run(profile_id: str, arguments: list[str] | None = None,
                         timeout_ms: int = 30_000) -> dict:
    """Run one hash-pinned executable profile without a shell."""
    if BROKER_TRANSPORT == "service":
        from .broker_client import prepare
        return prepare(profile_id, arguments, timeout_ms)
    if BROKER_TRANSPORT != "local":
        raise RuntimeError("Ismeretlen broker-átviteli mód.")
    if not profile_id or len(profile_id) > 128 or any(char in profile_id for char in "\r\n\x00"):
        raise ValueError("Érvénytelen broker-profilazonosító.")
    arguments = [] if arguments is None else [str(value) for value in arguments]
    if len(arguments) > 32 or any(len(value) > 2000 for value in arguments):
        raise ValueError("A broker argumentumai túl hosszúak vagy túl sokan vannak.")
    data = _broker_load_policy()
    profile = data["profiles"].get(profile_id)
    if not isinstance(profile, dict) or profile.get("kind", "process") != "process":
        raise RuntimeError("A broker-profil nem található vagy nem process profil.")
    executable, identity = _broker_validate_executable(profile)
    fixed_arguments = profile.get("fixed_arguments", [])
    if not isinstance(fixed_arguments, list) or any(not isinstance(value, str) for value in fixed_arguments):
        raise RuntimeError("A broker-profil fixed_arguments mezője érvénytelen.")
    if not bool(profile.get("allow_arguments", False)) and arguments:
        raise RuntimeError("Ez a broker-profil nem engedélyez további argumentumokat.")
    argv = [str(executable), *fixed_arguments, *arguments]
    timeout_ms = max(100, min(int(timeout_ms), 120_000))
    started = time.perf_counter()
    stdout_path = stderr_path = ""
    process = None
    child_processes_terminated = False
    try:
        # File-backed pipes prevent a child/grandchild that inherits stdout or
        # stderr from blocking the broker. The tree is terminated on timeout.
        stdout_fd, stdout_path = tempfile.mkstemp(prefix="windows-control-broker-", suffix=".stdout")
        stderr_fd, stderr_path = tempfile.mkstemp(prefix="windows-control-broker-", suffix=".stderr")
        os.close(stdout_fd)
        os.close(stderr_fd)
        with open(stdout_path, "wb") as stdout_file, open(stderr_path, "wb") as stderr_file:
            if _broker_file_identity(executable) != identity:
                raise RuntimeError("A broker végrehajtható fájlja az indítás előtt megváltozott.")
            process = subprocess.Popen(
                argv, shell=False, stdin=subprocess.DEVNULL, stdout=stdout_file, stderr=stderr_file,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            try:
                process.wait(timeout=timeout_ms / 1000)
                status = "succeeded" if process.returncode == 0 else "failed"
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                child_processes_terminated = _terminate_process_tree(process.pid)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                status = "timed_out"
                exit_code = None
            except KeyboardInterrupt:
                child_processes_terminated = _terminate_process_tree(process.pid)
                status = "interrupted"
                exit_code = None
    except OSError as exc:
        status = "unknown"
        exit_code = None
        error = str(exc)
    except RuntimeError as exc:
        status = "unknown"
        exit_code = None
        error = str(exc)
    else:
        error = ""
    finally:
        stdout = _bounded_text_file(stdout_path, 20_000) if stdout_path else ""
        stderr = _bounded_text_file(stderr_path, 20_000) if stderr_path else ""
        for path in (stdout_path, stderr_path):
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
    result = {"profile_id": profile_id, "status": status, "exit_code": exit_code,
              "duration_ms": round((time.perf_counter() - started) * 1000, 2),
              "stdout": stdout, "stderr": stderr,
              "children_terminated": child_processes_terminated}
    if error:
        result["error"] = error
    return result


def _monitor_dpi(handle: int) -> tuple[int, int]:
    """Read monitor DPI without requiring an extra Python package."""
    try:
        shcore = ctypes.windll.shcore
        dpi_x = ctypes.c_uint()
        dpi_y = ctypes.c_uint()
        # MDT_EFFECTIVE_DPI = 0
        if shcore.GetDpiForMonitor(handle, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
            return max(96, int(dpi_x.value)), max(96, int(dpi_y.value))
    except (AttributeError, OSError):
        pass
    return 96, 96


def _enumerate_monitors() -> list[dict]:
    _require_windows()
    monitors: list[dict] = []

    class MONITORINFOEX(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HMONITOR, wintypes.HDC,
                        ctypes.POINTER(RECT), wintypes.LPARAM)
    def callback(handle, _dc, _rect, _data):
        info = MONITORINFOEX()
        info.cbSize = ctypes.sizeof(MONITORINFOEX)
        if USER32.GetMonitorInfoW(handle, ctypes.byref(info)):
            bounds = info.rcMonitor
            work = info.rcWork
            dpi_x, dpi_y = _monitor_dpi(handle)
            monitors.append({
                "name": f"monitor-{len(monitors) + 1}",
                "device_name": str(info.szDevice).rstrip("\x00"),
                "handle": int(handle),
                "x": int(bounds.left), "y": int(bounds.top),
                "width": int(bounds.right - bounds.left),
                "height": int(bounds.bottom - bounds.top),
                "work_x": int(work.left), "work_y": int(work.top),
                "work_width": int(work.right - work.left),
                "work_height": int(work.bottom - work.top),
                "primary": bool(info.dwFlags & 1),
                "dpi_x": dpi_x, "dpi_y": dpi_y,
                "scale_percent_x": round(dpi_x * 100 / 96, 1),
                "scale_percent_y": round(dpi_y * 100 / 96, 1),
            })
        return True

    USER32.EnumDisplayMonitors(0, 0, callback, 0)
    if monitors:
        return monitors
    width = USER32.GetSystemMetrics(0)
    height = USER32.GetSystemMetrics(1)
    return [{"name": "primary", "device_name": "", "handle": 0,
             "x": 0, "y": 0, "width": width, "height": height,
             "work_x": 0, "work_y": 0, "work_width": width,
             "work_height": height, "primary": True, "dpi_x": 96,
             "dpi_y": 96, "scale_percent_x": 100.0, "scale_percent_y": 100.0}]


def display_list() -> list[dict]:
    started = time.perf_counter()
    monitors = _enumerate_monitors()
    for monitor in monitors:
        monitor["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return monitors


def _find_monitor(name: str | None = None, monitor_index: int | None = None) -> dict:
    monitors = _enumerate_monitors()
    if monitor_index is not None:
        if monitor_index < 1 or monitor_index > len(monitors):
            raise ValueError("A monitor_index nem létezik.")
        return monitors[monitor_index - 1]
    if not name:
        return next((item for item in monitors if item["primary"]), monitors[0])
    for item in monitors:
        if name in {item["name"], item["device_name"]}:
            return item
    raise ValueError("A megadott monitorazonosító nem található.")


def _virtual_desktop_rect() -> tuple[int, int, int, int]:
    return (USER32.GetSystemMetrics(76), USER32.GetSystemMetrics(77),
            USER32.GetSystemMetrics(78), USER32.GetSystemMetrics(79))


def _resolve_capture_rect(left: int = 0, top: int = 0, width: int | None = None,
                          height: int | None = None, monitor: str | None = None,
                          monitor_index: int | None = None,
                          virtual_desktop: bool = False, hwnd: int = 0) -> tuple[int, int, int, int, dict]:
    if hwnd:
        if not USER32.IsWindow(hwnd):
            raise ValueError("A kiválasztott ablakazonosító nem érvényes.")
        rect = RECT()
        USER32.GetWindowRect(hwnd, ctypes.byref(rect))
        target = {"name": "window", "x": rect.left, "y": rect.top,
                  "width": rect.right - rect.left, "height": rect.bottom - rect.top,
                  "primary": False}
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top, target
    if virtual_desktop:
        vx, vy, vw, vh = _virtual_desktop_rect()
        base = {"name": "virtual-desktop", "x": vx, "y": vy, "width": vw,
                "height": vh, "primary": False}
    elif monitor or monitor_index is not None:
        base = _find_monitor(monitor, monitor_index)
    else:
        base = _find_monitor()
    x = base["x"] + int(left) if (monitor or monitor_index is not None or virtual_desktop) else int(left)
    y = base["y"] + int(top) if (monitor or monitor_index is not None or virtual_desktop) else int(top)
    width = base["width"] - int(left) if width is None else int(width)
    height = base["height"] - int(top) if height is None else int(height)
    vx, vy, vw, vh = _virtual_desktop_rect()
    if width < 1 or height < 1 or x < vx or y < vy or x + width > vx + vw or y + height > vy + vh:
        raise ValueError("A képernyőrészlet a Windows virtuális asztal határain kívül esik.")
    return x, y, width, height, base


def cursor_position() -> dict:
    _require_windows()
    point = POINT()
    if not USER32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError()
    return {"x": point.x, "y": point.y}


def _window_title(hwnd: int) -> str:
    length = USER32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    USER32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def window_list() -> list[dict]:
    _require_windows()
    result: list[dict] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if USER32.IsWindowVisible(hwnd):
            title = _window_title(hwnd)
            if title:
                rect = RECT()
                USER32.GetWindowRect(hwnd, ctypes.byref(rect))
                pid = wintypes.DWORD()
                USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                result.append({
                    "hwnd": int(hwnd),
                    "pid": int(pid.value),
                    "title": title,
                    "left": rect.left,
                    "top": rect.top,
                    "right": rect.right,
                    "bottom": rect.bottom,
                })
        return True

    USER32.EnumWindows(callback, 0)
    return result


def active_window() -> dict:
    _require_windows()
    hwnd = USER32.GetForegroundWindow()
    if not hwnd:
        return {"hwnd": 0, "title": ""}
    rect = RECT()
    USER32.GetWindowRect(hwnd, ctypes.byref(rect))
    return {
        "hwnd": int(hwnd),
        "title": _window_title(hwnd),
        "left": rect.left,
        "top": rect.top,
        "right": rect.right,
        "bottom": rect.bottom,
    }


def _resolve_ui_hwnd(hwnd: int) -> int:
    """Use the caller's window, or the interactive foreground window.

    RootElement-wide UIA enumeration is expensive and often unavailable in a
    remote/non-interactive session. Resolving zero to the foreground window
    keeps the adapter bounded and makes the execution context explicit.
    """
    if hwnd < 0:
        raise ValueError("Az ablakazonosító nem lehet negatív.")
    if hwnd:
        return int(hwnd)
    foreground = int(USER32.GetForegroundWindow() or 0)
    if not foreground:
        raise RuntimeError("Nincs elérhető interaktív előtérablak a UI Automation számára.")
    return foreground


def ui_tree(hwnd: int = 0, max_nodes: int = 200) -> dict:
    """Read a bounded Windows UI Automation tree through the fixed local adapter."""
    _require_windows()
    effective_hwnd = _resolve_ui_hwnd(hwnd)
    max_nodes = max(1, min(int(max_nodes), 500))
    script = Path(__file__).resolve().parents[2] / "scripts" / "ui_automation.ps1"
    if not script.is_file():
        raise RuntimeError("A UI Automation adapterfájl nem található.")
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script),
         "-Hwnd", str(effective_hwnd), "-MaxNodes", str(max_nodes)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        timeout=10,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "UI Automation hiba."
        raise RuntimeError(message[:500])
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("A UI Automation adapter érvénytelen választ adott.") from exc
    return value


def ocr_image(path: str, max_chars: int = 100_000) -> dict:
    """Recognize Hungarian text using the built-in Windows OCR engine."""
    _require_windows()
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise ValueError("A megadott OCR-fájl nem található.")
    if target.stat().st_size > 50_000_000:
        raise ValueError("Az OCR-kép legfeljebb 50 MB lehet.")
    script = Path(__file__).resolve().parents[2] / "scripts" / "windows_ocr.ps1"
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script), "-Path", str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "Windows OCR hiba."
        raise RuntimeError(message[:500])
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("A Windows OCR adapter érvénytelen választ adott.") from exc
    value["text"] = str(value.get("text", ""))[:max(1, min(int(max_chars), 100_000))]
    value["lines"] = [str(line)[:10000] for line in value.get("lines", [])]
    return value


def _ffmpeg_path() -> str:
    executable = os.environ.get("WINDOWS_CONTROL_FFMPEG", "ffmpeg")
    resolved = shutil.which(executable) or (executable if Path(executable).is_file() else None)
    if not resolved:
        raise RuntimeError("Az ffmpeg nem található; kameraművelet nem érhető el.")
    return resolved


def camera_list() -> list[dict]:
    """List DirectShow cameras without opening a capture stream."""
    _require_windows()
    completed = subprocess.run([_ffmpeg_path(), "-hide_banner", "-list_devices", "true",
                                "-f", "dshow", "-i", "dummy"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", check=False,
                               timeout=10)
    devices = []
    for line in (completed.stderr + "\n" + completed.stdout).splitlines():
        match = re.search(r'"([^"]+)" \(video\)', line)
        if match and not any(item["name"] == match.group(1) for item in devices):
            devices.append({"name": match.group(1), "kind": "video"})
    return devices


def camera_snapshot(device: str, path: str, width: int = 1280, height: int = 720) -> dict:
    _require_windows()
    if os.environ.get("WINDOWS_CONTROL_CAMERA", "0") != "1":
        raise PermissionError("A kamera alapértelmezetten le van tiltva; állítsd WINDOWS_CONTROL_CAMERA=1 értékre.")
    if not device or len(device) > 256 or any(char in device for char in "\r\n"):
        raise ValueError("Érvénytelen kameranév.")
    if width < 160 or height < 120 or width > 3840 or height > 2160:
        raise ValueError("A kamera felbontása nem támogatott.")
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [_ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "dshow",
         "-video_size", f"{int(width)}x{int(height)}", "-i", f"video={device}",
         "-frames:v", "1", "-y", str(target)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False, timeout=30)
    if completed.returncode != 0 or not target.is_file():
        raise RuntimeError((completed.stderr or "Kamerakép készítése sikertelen.")[:500])
    return {"path": str(target), "device": device, "width": width, "height": height}


def ui_invoke(name: str = "", automation_id: str = "", hwnd: int = 0,
              action: str = "invoke") -> dict:
    """Invoke or toggle one UIA element identified by exact properties."""
    _require_windows()
    if not name and not automation_id:
        raise ValueError("Name vagy AutomationId szükséges.")
    if action not in {"invoke", "toggle"}:
        raise ValueError("Az action csak invoke vagy toggle lehet.")
    if len(name) > 500 or len(automation_id) > 500:
        raise ValueError("A UIA-azonosító legfeljebb 500 karakter lehet.")
    effective_hwnd = _resolve_ui_hwnd(hwnd)
    script = Path(__file__).resolve().parents[2] / "scripts" / "ui_automation_action.ps1"
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script), "-Hwnd", str(effective_hwnd), "-Name", name,
         "-AutomationId", automation_id, "-Action", action],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        timeout=15,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "UI Automation műveleti hiba."
        raise RuntimeError(message[:500])
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("A UI Automation műveleti adapter érvénytelen választ adott.") from exc


def _ui_query(name: str, automation_id: str, hwnd: int, operation: str,
              value: str = "") -> dict:
    """Run one exact-property UIA query through the fixed local adapter."""
    _require_windows()
    if not name and not automation_id:
        raise ValueError("Name vagy AutomationId szukseges.")
    allowed = {"find", "properties", "get_text", "set_value", "select", "toggle", "scroll", "focus"}
    if operation not in allowed:
        raise ValueError("Ismeretlen UI Automation muvelet.")
    if len(name) > 500 or len(automation_id) > 500 or len(value) > 100_000:
        raise ValueError("A UIA-azonosito vagy ertek tul hosszu.")
    effective_hwnd = _resolve_ui_hwnd(hwnd)
    script = Path(__file__).resolve().parents[2] / "scripts" / "ui_automation_query.ps1"
    if not script.is_file():
        raise RuntimeError("A UI Automation query adapterfajl nem talalhato.")
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script), "-Hwnd", str(effective_hwnd), "-Name", name,
         "-AutomationId", automation_id, "-Operation", operation, "-Value", value],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        timeout=15,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "UI Automation query hiba."
        raise RuntimeError(message[:500])
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("A UI Automation query adapter ervenytelen valaszt adott.") from exc


def ui_find(name: str = "", automation_id: str = "", hwnd: int = 0) -> dict:
    return _ui_query(name, automation_id, hwnd, "find")


def ui_properties(name: str = "", automation_id: str = "", hwnd: int = 0) -> dict:
    return _ui_query(name, automation_id, hwnd, "properties")


def ui_get_text(name: str = "", automation_id: str = "", hwnd: int = 0) -> dict:
    return _ui_query(name, automation_id, hwnd, "get_text")


def ui_set_value(name: str = "", automation_id: str = "", hwnd: int = 0,
                 value: str = "") -> dict:
    return _ui_query(name, automation_id, hwnd, "set_value", value)


def ui_select(name: str = "", automation_id: str = "", hwnd: int = 0) -> dict:
    return _ui_query(name, automation_id, hwnd, "select")


def ui_toggle(name: str = "", automation_id: str = "", hwnd: int = 0) -> dict:
    return _ui_query(name, automation_id, hwnd, "toggle")


def ui_scroll(name: str = "", automation_id: str = "", hwnd: int = 0) -> dict:
    return _ui_query(name, automation_id, hwnd, "scroll")


def ui_focus(name: str = "", automation_id: str = "", hwnd: int = 0) -> dict:
    return _ui_query(name, automation_id, hwnd, "focus")


def process_list(limit: int = 200) -> list[dict]:
    completed = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
        check=True,
    )
    rows = []
    for row in csv.reader(io.StringIO(completed.stdout)):
        if len(row) >= 2 and row[0] and row[1].isdigit():
            rows.append({"name": row[0], "pid": int(row[1])})
        if len(rows) >= limit:
            break
    return rows


def service_list(limit: int = 200) -> list[dict]:
    _require_windows()
    completed = subprocess.run(["sc.exe", "query", "type=", "service", "state=", "all"],
                               capture_output=True, text=True, encoding="mbcs",
                               errors="replace", check=True)
    result = []
    current: dict[str, str] = {}
    for raw in completed.stdout.splitlines():
        line = raw.strip()
        if line.startswith("SERVICE_NAME:"):
            if current:
                result.append(current)
            current = {"name": line.split(":", 1)[1].strip()}
        elif line.startswith("DISPLAY_NAME:") and current:
            current["display_name"] = line.split(":", 1)[1].strip()
        elif line.startswith("STATE") and current:
            parts = line.split()
            if len(parts) >= 4:
                current["state"] = parts[3]
        if len(result) >= max(1, min(int(limit), 500)):
            break
    if current and len(result) < max(1, min(int(limit), 500)):
        result.append(current)
    return result[:max(1, min(int(limit), 500))]


def _convert_screenshot(source: Path, target: Path, image_format: str, quality: int,
                        max_dimension: int | None) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "convert_screenshot.ps1"
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script), "-InputPath", str(source), "-OutputPath", str(target),
         "-Format", image_format, "-Quality", str(int(quality)),
         "-MaxDimension", str(int(max_dimension or 0))],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        timeout=20,
    )
    if completed.returncode != 0 or not target.is_file():
        raise RuntimeError((completed.stderr or completed.stdout or "Képkonverzió sikertelen.")[:500])


def _output_dimensions(width: int, height: int, max_dimension: int | None) -> tuple[int, int]:
    if not max_dimension or (width <= max_dimension and height <= max_dimension):
        return width, height
    scale = min(max_dimension / width, max_dimension / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def screenshot(path: str | None = None, left: int = 0, top: int = 0,
               width: int | None = None, height: int | None = None,
               monitor: str | None = None, monitor_index: int | None = None,
               virtual_desktop: bool = False, hwnd: int = 0,
               image_format: str = "bmp", quality: int = 90,
               max_dimension: int | None = None) -> dict:
    _require_windows()
    try:
        import win32con
        import win32gui
        import win32ui
    except ImportError as exc:  # pragma: no cover - depends on local Windows setup
        raise RuntimeError("A képernyőképhez a pywin32 csomag szükséges.") from exc

    started = time.perf_counter()
    left, top, width, height, target_monitor = _resolve_capture_rect(
        left, top, width, height, monitor, monitor_index, virtual_desktop, hwnd)
    image_format = str(image_format).lower()
    if image_format not in {"bmp", "png", "jpeg", "jpg"}:
        raise ValueError("A képformátum csak bmp, png vagy jpeg lehet.")
    if not 1 <= int(quality) <= 100:
        raise ValueError("A JPEG quality értéke 1 és 100 közötti legyen.")
    if max_dimension is not None and (int(max_dimension) < 64 or int(max_dimension) > 16000):
        raise ValueError("A max_dimension 64 és 16000 közötti legyen.")
    if path is None:
        root = Path(tempfile.gettempdir()) / "windows-control-mcp-screenshots"
        root.mkdir(parents=True, exist_ok=True)
        suffix = ".jpg" if image_format in {"jpg", "jpeg"} else f".{image_format}"
        path = str(root / f"screenshot_{int(time.time() * 1000)}{suffix}")
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_bmp: Path | None = None
    output_target = target
    if image_format != "bmp":
        temporary_bmp = Path(tempfile.gettempdir()) / f"windows_control_mcp_{uuid.uuid4().hex}.bmp"
        output_target = temporary_bmp

    desktop = win32gui.GetDesktopWindow()
    source_dc = win32gui.GetWindowDC(desktop)
    dc = win32ui.CreateDCFromHandle(source_dc)
    memory_dc = dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(dc, width, height)
    memory_dc.SelectObject(bitmap)
    memory_dc.BitBlt((0, 0), (width, height), dc, (left, top), win32con.SRCCOPY)
    bitmap.SaveBitmapFile(memory_dc, str(output_target))
    memory_dc.DeleteDC()
    dc.DeleteDC()
    win32gui.ReleaseDC(desktop, source_dc)
    if temporary_bmp is not None:
        try:
            _convert_screenshot(temporary_bmp, target,
                                "jpeg" if image_format in {"jpg", "jpeg"} else "png",
                                quality, max_dimension)
        finally:
            temporary_bmp.unlink(missing_ok=True)
    elif max_dimension is not None:
        raise ValueError("A max_dimension csak PNG/JPEG kimenetnél támogatott.")
    output_width, output_height = _output_dimensions(width, height, max_dimension)
    return {"path": str(target), "left": left, "top": top,
            "width": width, "height": height, "output_width": output_width,
            "output_height": output_height, "format": image_format,
            "monitor": target_monitor.get("name", ""),
            "virtual_desktop": bool(virtual_desktop),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}


def _file_digest(path: Path) -> tuple[str, int]:
    if not path.is_file():
        raise ValueError("A képfájl nem található.")
    if path.stat().st_size > 100_000_000:
        raise ValueError("Az összehasonlított képfájl legfeljebb 100 MB lehet.")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def screen_compare(path_a: str, path_b: str) -> dict:
    started = time.perf_counter()
    first = Path(path_a).expanduser().resolve()
    second = Path(path_b).expanduser().resolve()
    digest_a, size_a = _file_digest(first)
    digest_b, size_b = _file_digest(second)
    return {"same": digest_a == digest_b and size_a == size_b,
            "path_a": str(first), "path_b": str(second),
            "sha256_a": digest_a, "sha256_b": digest_b,
            "bytes_a": size_a, "bytes_b": size_b,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "comparison": "byte_hash"}


def screen_wait_change(path: str, timeout_ms: int = 10000, interval_ms: int = 250,
                       left: int = 0, top: int = 0, width: int | None = None,
                       height: int | None = None, monitor: str | None = None,
                       monitor_index: int | None = None,
                       virtual_desktop: bool = False, hwnd: int = 0) -> dict:
    _require_windows()
    timeout_ms = max(100, min(int(timeout_ms), 120_000))
    interval_ms = max(50, min(int(interval_ms), 5000))
    baseline = Path(path).expanduser().resolve()
    baseline_digest, baseline_size = _file_digest(baseline)
    started = time.perf_counter()
    attempts = 0
    temporary = Path(tempfile.gettempdir()) / f"windows_control_mcp_wait_{uuid.uuid4().hex}.bmp"
    try:
        while (time.perf_counter() - started) * 1000 < timeout_ms:
            attempts += 1
            screenshot(str(temporary), left, top, width, height, monitor,
                       monitor_index, virtual_desktop, hwnd, "bmp")
            digest, size = _file_digest(temporary)
            if digest != baseline_digest or size != baseline_size:
                return {"changed": True, "attempts": attempts,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                        "baseline": str(baseline), "comparison": "byte_hash"}
            time.sleep(interval_ms / 1000)
    finally:
        temporary.unlink(missing_ok=True)
    return {"changed": False, "attempts": attempts,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "baseline": str(baseline), "comparison": "byte_hash",
            "timed_out": True}


def _resolve_pointer(x: int, y: int, hwnd: int = 0, relative: bool = False,
                    coordinate_space: str = "physical", monitor: str | None = None,
                    monitor_index: int | None = None) -> tuple[int, int]:
    if coordinate_space not in {"physical", "logical"}:
        raise ValueError("A coordinate_space physical vagy logical lehet.")
    if relative:
        if not hwnd or not USER32.IsWindow(hwnd):
            raise ValueError("Relatív kattintáshoz érvényes hwnd szükséges.")
        point = POINT(int(x), int(y))
        if not USER32.ClientToScreen(hwnd, ctypes.byref(point)):
            raise ctypes.WinError()
        return int(point.x), int(point.y)
    px, py = int(x), int(y)
    if coordinate_space == "logical":
        target = _find_monitor(monitor, monitor_index)
        px = target["x"] + round((px - target["x"]) * target["dpi_x"] / 96)
        py = target["y"] + round((py - target["y"]) * target["dpi_y"] / 96)
    if hwnd:
        if not USER32.IsWindow(hwnd):
            raise ValueError("A célablak-azonosító nem érvényes.")
        rect = RECT()
        USER32.GetWindowRect(hwnd, ctypes.byref(rect))
        if not (rect.left <= px < rect.right and rect.top <= py < rect.bottom):
            raise ValueError("A kattintási pont a célablak határain kívül esik.")
    vx, vy, vw, vh = _virtual_desktop_rect()
    if not (vx <= px < vx + vw and vy <= py < vy + vh):
        raise ValueError("A kattintási pont a virtuális asztalon kívül esik.")
    return px, py


def mouse_click(x: int, y: int, button: str = "left", hwnd: int = 0,
               relative: bool = False, coordinate_space: str = "physical",
               monitor: str | None = None, monitor_index: int | None = None) -> dict:
    _require_windows()
    if button not in {"left", "right", "middle"}:
        raise ValueError("A gomb csak left, right vagy middle lehet.")
    x, y = _resolve_pointer(x, y, hwnd, relative, coordinate_space, monitor, monitor_index)
    if not USER32.SetCursorPos(x, y):
        raise ctypes.WinError()
    flags = {
        "left": (0x0002, 0x0004),
        "right": (0x0008, 0x0010),
        "middle": (0x0020, 0x0040),
    }[button]
    USER32.mouse_event(flags[0], 0, 0, 0, 0)
    USER32.mouse_event(flags[1], 0, 0, 0, 0)
    return {"x": x, "y": y, "button": button}


def mouse_move(x: int, y: int) -> dict:
    _require_windows()
    if not USER32.SetCursorPos(x, y):
        raise ctypes.WinError()
    return {"x": x, "y": y}


def mouse_drag(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> dict:
    _require_windows()
    mouse_move(x1, y1)
    USER32.mouse_event(0x0002, 0, 0, 0, 0)
    steps = max(2, min(100, duration_ms // 15))
    for index in range(1, steps + 1):
        mouse_move(x1 + (x2 - x1) * index // steps, y1 + (y2 - y1) * index // steps)
        time.sleep(max(0, duration_ms) / 1000 / steps)
    USER32.mouse_event(0x0004, 0, 0, 0, 0)
    return {"from": [x1, y1], "to": [x2, y2], "duration_ms": duration_ms}


def mouse_scroll(amount: int) -> dict:
    _require_windows()
    amount = max(-120, min(120, int(amount)))
    USER32.mouse_event(0x0800, 0, 0, amount * 120, 0)
    return {"amount": amount}


def key_press(vk: int) -> dict:
    _require_windows()
    if not 1 <= int(vk) <= 255:
        raise ValueError("A virtuális billentyűkód 1 és 255 közötti egész legyen.")
    USER32.keybd_event(int(vk), 0, 0, 0)
    USER32.keybd_event(int(vk), 0, 0x0002, 0)
    return {"vk": int(vk)}


def hotkey(vks: list[int]) -> dict:
    _require_windows()
    if not vks or len(vks) > 8 or any(not 1 <= int(vk) <= 255 for vk in vks):
        raise ValueError("A hotkey 1-8 darab, 1-255 közötti virtuális kódot tartalmazhat.")
    for vk in vks:
        USER32.keybd_event(int(vk), 0, 0, 0)
    for vk in reversed(vks):
        USER32.keybd_event(int(vk), 0, 0x0002, 0)
    return {"count": len(vks)}


def window_focus(hwnd: int) -> dict:
    _require_windows()
    if not USER32.IsWindow(hwnd):
        raise ValueError("Az ablakazonosító nem érvényes.")
    USER32.ShowWindow(hwnd, 9)
    target_thread = wintypes.DWORD()
    USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(target_thread))
    current_thread = KERNEL32.GetCurrentThreadId()
    attached = bool(target_thread.value and target_thread.value != current_thread and
                    USER32.AttachThreadInput(current_thread, target_thread.value, True))
    try:
        USER32.BringWindowToTop(hwnd)
        USER32.SetForegroundWindow(hwnd)
        if int(USER32.GetForegroundWindow()) != int(hwnd):
            # Windows allows a foreground transition after a user-like Alt key
            # transition; this does not bypass authentication or elevation.
            USER32.keybd_event(0x12, 0, 0, 0)
            USER32.SetForegroundWindow(hwnd)
            USER32.keybd_event(0x12, 0, 0x0002, 0)
    finally:
        if attached:
            USER32.AttachThreadInput(current_thread, target_thread.value, False)
    focused = int(USER32.GetForegroundWindow()) == int(hwnd)
    if not focused:
        raise RuntimeError("A Windows előtérbe-hozatali korlátozás miatt az ablak nem kapott fókuszt.")
    return {"hwnd": int(hwnd), "focused": True}


def window_set_state(hwnd: int, state: str) -> dict:
    _require_windows()
    if not USER32.IsWindow(hwnd):
        raise ValueError("Az ablakazonosító nem érvényes.")
    commands = {"minimize": 6, "maximize": 3, "restore": 9}
    if state not in commands:
        raise ValueError("Az állapot minimize, maximize vagy restore lehet.")
    USER32.ShowWindow(hwnd, commands[state])
    return {"hwnd": int(hwnd), "state": state}


def window_resize(hwnd: int, x: int, y: int, width: int, height: int) -> dict:
    _require_windows()
    if not USER32.IsWindow(hwnd):
        raise ValueError("Az ablakazonosító nem érvényes.")
    if width < 100 or height < 80 or width > 10000 or height > 10000:
        raise ValueError("Az ablakméret 100-10000 × 80-10000 közé essen.")
    if not USER32.SetWindowPos(hwnd, 0, int(x), int(y), int(width), int(height), 0x0040):
        raise ctypes.WinError()
    return {"hwnd": int(hwnd), "x": int(x), "y": int(y), "width": int(width), "height": int(height)}


def window_close(hwnd: int) -> dict:
    _require_windows()
    if not USER32.IsWindow(hwnd):
        raise ValueError("Az ablakazonosító nem érvényes.")
    if not USER32.PostMessageW(hwnd, 0x0010, 0, 0):  # WM_CLOSE
        raise ctypes.WinError()
    return {"hwnd": int(hwnd), "close_requested": True}


def launch_application(command: str, arguments: list[str] | None = None) -> dict:
    if not command or len(command) > 400:
        raise ValueError("Érvénytelen alkalmazásparancs.")
    arguments = arguments or []
    if len(arguments) > 32:
        raise ValueError("Legfeljebb 32 argumentum engedélyezett.")
    process = subprocess.Popen([command, *arguments], close_fds=True)
    return {"pid": process.pid, "command": command}


def file_list(path: str, limit: int = 200) -> list[dict]:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("A megadott útvonal nem könyvtár.")
    result = []
    for item in sorted(root.iterdir(), key=lambda entry: entry.name.lower())[:limit]:
        result.append({"name": item.name, "path": str(item), "directory": item.is_dir(),
                       "size": item.stat().st_size if item.is_file() else None})
    return result


def file_read(path: str, max_bytes: int = 1_000_000, offset: int = 0,
              length: int | None = None) -> dict:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise ValueError("A megadott útvonal nem fájl.")
    max_bytes = max(1, min(int(max_bytes), 10_000_000))
    offset = max(0, int(offset))
    length = max_bytes if length is None else max(0, min(int(length), max_bytes))
    with target.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(length)
    return {"path": str(target), "offset": offset, "bytes": len(data),
            "eof": offset + len(data) >= target.stat().st_size,
            "text": data.decode("utf-8", errors="replace")}


def file_search(path: str, pattern: str, recursive: bool = True, limit: int = 200) -> list[dict]:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("A keresési gyökér nem könyvtár.")
    if not pattern or len(pattern) > 200:
        raise ValueError("A keresési minta 1-200 karakter lehet.")
    iterator = root.rglob(pattern) if recursive else root.glob(pattern)
    result = []
    for item in iterator:
        if item.is_file():
            result.append({"path": str(item), "size": item.stat().st_size})
            if len(result) >= max(1, min(int(limit), 1000)):
                break
    return result


def file_write(path: str, text: str) -> dict:
    target = Path(path).expanduser().resolve()
    if len(text) > 1_000_000:
        raise ValueError("A szöveg túl nagy.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return {"path": str(target), "bytes": target.stat().st_size}


def file_copy(source: str, destination: str, overwrite: bool = False) -> dict:
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if not source_path.is_file():
        raise ValueError("A forrás csak egy létező fájl lehet.")
    if destination_path.exists() and not overwrite:
        raise FileExistsError("A célfájl már létezik; az overwrite külön engedélyezendő.")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    return {"source": str(source_path), "destination": str(destination_path), "bytes": destination_path.stat().st_size}


def file_move(source: str, destination: str, overwrite: bool = False) -> dict:
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if not source_path.exists():
        raise ValueError("A forrás nem található.")
    if destination_path.exists() and not overwrite:
        raise FileExistsError("A cél már létezik; az overwrite külön engedélyezendő.")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if overwrite and destination_path.exists():
        if destination_path.is_file():
            destination_path.unlink()
        else:
            raise ValueError("Könyvtár felülírása nem támogatott.")
    shutil.move(str(source_path), str(destination_path))
    return {"source": str(source_path), "destination": str(destination_path)}


def _bounded_text_file(path: str, max_output: int) -> str:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return ""
    return data[:max_output].decode("utf-8", errors="replace")


def _terminate_process_tree(pid: int) -> bool:
    completed = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True, text=True, encoding="mbcs", errors="replace", check=False,
    )
    return completed.returncode == 0


def terminal_run(command: str, shell: str = "powershell", timeout_ms: int = 30000,
                 max_output: int = 20000) -> dict:
    if not command or len(command) > 20000:
        raise ValueError("A parancs 1-20000 karakter lehet.")
    if shell not in {"powershell", "cmd"}:
        raise ValueError("A shell csak powershell vagy cmd lehet.")
    timeout_ms = max(100, min(int(timeout_ms), 120000))
    max_output = max(100, min(int(max_output), 100000))
    argv = (["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
            if shell == "powershell" else ["cmd.exe", "/d", "/s", "/c", command])
    started = time.perf_counter()
    stdout_fd, stdout_path = tempfile.mkstemp(prefix="windows-control-mcp-", suffix=".stdout")
    stderr_fd, stderr_path = tempfile.mkstemp(prefix="windows-control-mcp-", suffix=".stderr")
    os.close(stdout_fd)
    os.close(stderr_fd)
    process = None
    child_processes_terminated = False
    try:
        with open(stdout_path, "wb") as stdout_file, open(stderr_path, "wb") as stderr_file:
            process = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=stdout_file, stderr=stderr_file,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            try:
                process.wait(timeout=timeout_ms / 1000)
                status = "succeeded" if process.returncode == 0 else "failed"
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                child_processes_terminated = _terminate_process_tree(process.pid)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                status = "timed_out"
                exit_code = None
            except KeyboardInterrupt:
                child_processes_terminated = _terminate_process_tree(process.pid)
                status = "interrupted"
                exit_code = None
    except OSError as exc:
        status = "unknown"
        exit_code = None
        error = str(exc)
    else:
        error = ""
    finally:
        stdout = _bounded_text_file(stdout_path, max_output)
        stderr = _bounded_text_file(stderr_path, max_output)
        for path in (stdout_path, stderr_path):
            try:
                os.unlink(path)
            except OSError:
                pass
    return {"shell": shell, "status": status, "timed_out": status == "timed_out",
            "interrupted": status == "interrupted", "exit_code": exit_code,
            "pid": process.pid if process is not None else None,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "child_processes_terminated": child_processes_terminated,
            "stdout": stdout, "stderr": stderr, "error": error}


def terminal_start(shell: str = "powershell") -> dict:
    if shell not in {"powershell", "cmd"}:
        raise ValueError("A shell csak powershell vagy cmd lehet.")
    argv = (["powershell.exe", "-NoLogo", "-NoProfile"]
            if shell == "powershell" else ["cmd.exe", "/d", "/q"])
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                               errors="replace", bufsize=1, creationflags=0x00000200)
    session_id = uuid.uuid4().hex
    state = {"process": process, "shell": shell, "output": [], "closed": False}

    def collect() -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                with TERMINAL_LOCK:
                    state["output"].append(line[:10000])
                    if len(state["output"]) > 1000:
                        del state["output"][:-1000]
        except (ValueError, OSError):
            # terminal_stop may close the pipe while the reader is blocked.
            pass
        finally:
            with TERMINAL_LOCK:
                state["closed"] = True

    with TERMINAL_LOCK:
        TERMINAL_SESSIONS[session_id] = state
    threading.Thread(target=collect, name="windows-control-terminal", daemon=True).start()
    return {"session_id": session_id, "pid": process.pid, "shell": shell}


def terminal_poll(session_id: str, max_lines: int = 100) -> dict:
    with TERMINAL_LOCK:
        state = TERMINAL_SESSIONS.get(session_id)
        if state is None:
            raise ValueError("A terminál-munkamenet nem található.")
        lines = state["output"][-max(1, min(int(max_lines), 200)):]
        process = state["process"]
        return {"session_id": session_id, "pid": process.pid, "running": process.poll() is None,
                "lines": lines}


def terminal_input(session_id: str, text: str) -> dict:
    if len(text) > 10_000:
        raise ValueError("A terminálbemenet legfeljebb 10000 karakter lehet.")
    with TERMINAL_LOCK:
        state = TERMINAL_SESSIONS.get(session_id)
        if state is None:
            raise ValueError("A terminál-munkamenet nem található.")
        process = state["process"]
        if process.poll() is not None or process.stdin is None:
            raise RuntimeError("A terminál-munkamenet már leállt.")
        process.stdin.write(text)
        process.stdin.flush()
    return {"session_id": session_id, "characters": len(text), "sent": True}


def terminal_stop(session_id: str) -> dict:
    with TERMINAL_LOCK:
        state = TERMINAL_SESSIONS.get(session_id)
        if state is None:
            raise ValueError("A terminál-munkamenet nem található.")
        process = state["process"]
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if process.stdin is not None:
            process.stdin.close()
        if process.stdout is not None:
            process.stdout.close()
        TERMINAL_SESSIONS.pop(session_id, None)
    return {"session_id": session_id, "stopped": True}


def file_delete(path: str) -> dict:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise ValueError("Csak egyetlen fájl törölhető; könyvtár nem.")
    target.unlink()
    return {"path": str(target), "deleted": True}


def process_stop(pid: int) -> dict:
    if pid <= 0:
        raise ValueError("Érvénytelen PID.")
    completed = subprocess.run(["taskkill", "/PID", str(pid), "/T"], capture_output=True,
                               text=True, encoding="mbcs", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "taskkill failed")
    return {"pid": pid, "stopped": True}


def service_control(name: str, action: str) -> dict:
    if not name or len(name) > 256 or any(char in name for char in "\r\n\"'"):
        raise ValueError("Érvénytelen szolgáltatásnév.")
    if action not in {"start", "stop"}:
        raise ValueError("A művelet csak start vagy stop lehet.")
    completed = subprocess.run(["sc.exe", action, name], capture_output=True,
                               text=True, encoding="mbcs", errors="replace", check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "service control failed")
    return {"name": name, "action": action, "requested": True,
            "output": (completed.stdout.strip() or "")[:1000]}


def type_text(text: str) -> dict:
    _require_windows()
    if len(text) > 10000:
        raise ValueError("A szöveg legfeljebb 10000 karakter lehet.")
    # KEYEVENTF_UNICODE: safe literal text input, no shell interpretation.
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong)]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]

    USER32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    USER32.SendInput.restype = wintypes.UINT

    events = []
    for char in text:
        scan = ord(char)
        events.append(INPUT(1, INPUT_UNION(ki=KEYBDINPUT(0, scan, KEYEVENTF_UNICODE, 0, 0))))
        events.append(INPUT(1, INPUT_UNION(ki=KEYBDINPUT(0, scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0))))
    array = (INPUT * len(events))(*events)
    sent = USER32.SendInput(len(events), ctypes.cast(array, ctypes.POINTER(INPUT)), ctypes.sizeof(INPUT))
    if sent != len(events):
        raise ctypes.WinError()
    return {"characters": len(text)}


def clipboard_read(max_chars: int = 100_000) -> dict:
    _require_windows()
    CF_UNICODETEXT = 13
    if not USER32.OpenClipboard(0):
        raise ctypes.WinError()
    handle = None
    pointer = None
    try:
        handle = USER32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return {"text": "", "characters": 0}
        pointer = KERNEL32.GlobalLock(handle)
        if not pointer:
            raise ctypes.WinError()
        value = ctypes.wstring_at(pointer, max(1, min(int(max_chars), 100_000)))
        value = value.split("\x00", 1)[0]
        return {"text": value, "characters": len(value)}
    finally:
        if pointer:
            KERNEL32.GlobalUnlock(handle)
        USER32.CloseClipboard()


def clipboard_write(text: str) -> dict:
    _require_windows()
    if len(text) > 100_000:
        raise ValueError("A vágólapszöveg legfeljebb 100000 karakter lehet.")
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    if not USER32.OpenClipboard(0):
        raise ctypes.WinError()
    allocation = None
    try:
        if not USER32.EmptyClipboard():
            raise ctypes.WinError()
        encoded = (text + "\x00").encode("utf-16-le")
        allocation = KERNEL32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not allocation:
            raise ctypes.WinError()
        pointer = KERNEL32.GlobalLock(allocation)
        if not pointer:
            raise ctypes.WinError()
        try:
            ctypes.memmove(pointer, encoded, len(encoded))
        finally:
            KERNEL32.GlobalUnlock(allocation)
        if not USER32.SetClipboardData(CF_UNICODETEXT, allocation):
            raise ctypes.WinError()
        allocation = None  # ownership transferred to the clipboard
        return {"characters": len(text), "written": True}
    finally:
        if allocation:
            KERNEL32.GlobalFree(allocation)
        USER32.CloseClipboard()

