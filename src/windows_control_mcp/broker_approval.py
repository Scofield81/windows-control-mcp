"""Magyar, témaérzékeny felhasználói jóváhagyó ablak a Windows brokerhez."""

from __future__ import annotations

import json
import sys
import tkinter as tk
from tkinter import scrolledtext

try:
    from .broker_client import approve_and_run as broker_approve_and_run
except ImportError:  # PyInstaller közvetlen belépési pontja
    from windows_control_mcp.broker_client import approve_and_run as broker_approve_and_run


def _is_dark_mode() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
    except (OSError, ValueError, ImportError):
        return False


def _palette() -> dict[str, str]:
    if _is_dark_mode():
        return {"bg": "#202124", "panel": "#2b2d31", "fg": "#f1f3f4", "muted": "#bdc1c6",
                "accent": "#8ab4f8", "deny": "#f28b82", "button_fg": "#202124"}
    return {"bg": "#f7f9fc", "panel": "#ffffff", "fg": "#202124", "muted": "#5f6368",
            "accent": "#1a73e8", "deny": "#b3261e", "button_fg": "#ffffff"}


def _grant_service_query_access() -> None:
    """Let LocalService verify this helper process without broadening access."""
    try:
        import win32api
        import win32con
        import win32security
        handle = win32api.GetCurrentProcess()
        descriptor = win32security.GetSecurityInfo(
            handle, win32security.SE_KERNEL_OBJECT,
            win32security.DACL_SECURITY_INFORMATION)
        dacl = descriptor.GetSecurityDescriptorDacl()
        local_service = win32security.ConvertStringSidToSid("S-1-5-19")
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION_DS, 0,
            win32con.PROCESS_QUERY_LIMITED_INFORMATION, local_service)
        win32security.SetSecurityInfo(
            handle, win32security.SE_KERNEL_OBJECT,
            win32security.DACL_SECURITY_INFORMATION, None, None, dacl, None)
    except Exception:
        # The broker remains fail-closed if it cannot authenticate this process.
        return


def _message_window(title: str, message: str, error: bool = False) -> None:
    colors = _palette()
    root = tk.Tk()
    root.title(title or "Windows Control MCP")
    root.configure(bg=colors["bg"])
    root.resizable(False, False)
    root.attributes("-topmost", True)
    frame = tk.Frame(root, bg=colors["panel"], padx=24, pady=20)
    frame.pack(padx=18, pady=18)
    tk.Label(frame, text="Művelet állapota", bg=colors["panel"], fg=colors["deny"] if error else colors["accent"],
             font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x")
    tk.Label(frame, text=("A művelet nem indult el."
                         if error else "A művelet befejeződött."),
             bg=colors["panel"], fg=colors["fg"], font=("Segoe UI", 10, "bold"),
             justify="left", wraplength=460, anchor="w").pack(fill="x", pady=(12, 8))
    tk.Label(frame, text="A részletes technikai okot a Részletek gombbal nézheted meg.",
             bg=colors["panel"], fg=colors["muted"], font=("Segoe UI", 9),
             justify="left", wraplength=460, anchor="w").pack(fill="x", pady=(0, 12))
    details = scrolledtext.ScrolledText(frame, width=62, height=6, wrap="word",
                                        bg=colors["bg"], fg=colors["fg"], relief="flat")
    details.insert("1.0", message)
    details.configure(state="disabled")
    details.pack_forget()
    def toggle_details() -> None:
        if details.winfo_viewable():
            details.pack_forget()
            detail_button.configure(text="Részletek megjelenítése")
        else:
            details.pack(fill="both", pady=(0, 12))
            detail_button.configure(text="Részletek elrejtése")
        root.update_idletasks()
    detail_button = tk.Button(frame, text="Részletek megjelenítése", command=toggle_details,
                              bg=colors["panel"], fg=colors["accent"], relief="groove",
                              padx=12, pady=5, font=("Segoe UI", 9))
    detail_button.pack(anchor="w", pady=(0, 12))
    tk.Button(frame, text="Rendben", command=root.destroy, bg=colors["accent"], fg=colors["button_fg"],
              activebackground=colors["accent"], relief="flat", padx=18, pady=7,
              font=("Segoe UI", 10, "bold")).pack(anchor="e")
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.update_idletasks()
    root.mainloop()


def _approval_dialog(main_text: str, short_info: str, details_text: str) -> bool:
    colors = _palette()
    root = tk.Tk()
    root.title("Felhasználói jóváhagyás")
    root.configure(bg=colors["bg"])
    root.resizable(False, False)
    root.attributes("-topmost", True)
    decision = {"allowed": False}
    frame = tk.Frame(root, bg=colors["panel"], padx=26, pady=22)
    frame.pack(padx=18, pady=18)
    tk.Label(frame, text="Felhasználói jóváhagyás", bg=colors["panel"], fg=colors["accent"],
             font=("Segoe UI", 15, "bold"), anchor="w").pack(fill="x")
    tk.Label(frame, text=main_text, bg=colors["panel"], fg=colors["fg"], font=("Segoe UI", 10),
             justify="left", anchor="w", wraplength=500).pack(fill="x", pady=(8, 10))
    tk.Label(frame, text=short_info, bg=colors["panel"], fg=colors["muted"], font=("Segoe UI", 9),
             justify="left", anchor="w", wraplength=500).pack(fill="x", pady=(0, 10))
    details = scrolledtext.ScrolledText(frame, width=62, height=7, wrap="word",
                                        bg=colors["bg"], fg=colors["fg"], relief="flat")
    details.insert("1.0", details_text)
    details.configure(state="disabled")
    details.pack_forget()
    def toggle_details() -> None:
        if details.winfo_viewable():
            details.pack_forget()
            detail_button.configure(text="Technikai részletek megjelenítése")
        else:
            details.pack(fill="both", pady=(0, 14))
            detail_button.configure(text="Technikai részletek elrejtése")
        root.update_idletasks()
    detail_button = tk.Button(frame, text="Technikai részletek megjelenítése", command=toggle_details,
                              bg=colors["panel"], fg=colors["accent"], relief="groove",
                              padx=12, pady=5, font=("Segoe UI", 9))
    detail_button.pack(anchor="w", pady=(0, 14))
    tk.Label(frame, text="Ha elutasítod, a művelet nem indul el, és a rendszer nem módosít semmit.",
             bg=colors["panel"], fg=colors["muted"], font=("Segoe UI", 9, "italic"),
             anchor="w", wraplength=500).pack(fill="x", pady=(0, 16))
    buttons = tk.Frame(frame, bg=colors["panel"])
    buttons.pack(fill="x")
    def deny() -> None:
        decision["allowed"] = False
        root.destroy()
    def allow() -> None:
        decision["allowed"] = True
        root.destroy()
    tk.Button(buttons, text="Elutasítom", command=deny, bg=colors["panel"], fg=colors["deny"],
              activebackground=colors["panel"], relief="groove", padx=14, pady=7,
              font=("Segoe UI", 10)).pack(side="left")
    tk.Button(buttons, text="Engedélyezem", command=allow, bg=colors["accent"], fg=colors["button_fg"],
              activebackground=colors["accent"], relief="flat", padx=14, pady=7,
              font=("Segoe UI", 10, "bold")).pack(side="right")
    root.protocol("WM_DELETE_WINDOW", deny)
    root.update_idletasks()
    root.mainloop()
    return decision["allowed"]


def _approval_text(request: dict) -> tuple[str, str, str]:
    profile = str(request.get("profile_id", ""))
    arguments = request.get("arguments", [])
    timeout_ms = int(request.get("timeout_ms", 30_000))
    if profile == "whoami-safe":
        main = ("A Windows Control MCP egy biztonságos ellenőrző műveletet szeretne futtatni.\n\n"
                "Ez csak azt ellenőrzi, hogy a rendszer melyik Windows-felhasználó nevében fut.\n"
                "Nem módosít fájlokat, nem telepít programot, és nem változtatja meg a rendszer beállításait.")
        short = "Várható idő: néhány másodperc\nKockázat: alacsony\nMűvelet típusa: csak olvasás / ellenőrzés"
    else:
        main = ("A Windows Control MCP egy engedélyköteles műveletet szeretne végrehajtani.\n\n"
                "Az engedélyezés nélkül a művelet nem indul el. Ha nem ismerős a kérés, válaszd az Elutasítom gombot.")
        short = "A művelet hatását és a pontos technikai adatokat a részletek alatt láthatod."
    args_text = "nincs" if not arguments else json.dumps(arguments, ensure_ascii=False)
    details = (f"Profil: {profile or 'nincs megadva'}\n"
               f"Argumentumok: {args_text}\n"
               f"Időkorlát: {timeout_ms} ms")
    return main, short, details


def _write_result(request: dict, result: dict) -> None:
    result_path = request.get("result_path")
    if isinstance(result_path, str) and result_path:
        with open(result_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False)


def approve_and_run() -> int:
    _grant_service_query_access()
    if len(sys.argv) != 2:
        _message_window("Windows Control MCP – broker hiba", "A jóváhagyási kérelem JSON-fájlútvonala szükséges.", True)
        return 2
    try:
        with open(sys.argv[1], encoding="utf-8") as handle:
            request = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        _message_window("Windows Control MCP – broker hiba", f"A jóváhagyási kérelem nem olvasható: {exc}", True)
        return 2
    main_text, short_info, details_text = _approval_text(request)
    if not _approval_dialog(main_text, short_info, details_text):
        _write_result(request, {"status": "denied"})
        return 1
    result = broker_approve_and_run(str(request["approval_id"]), int(request.get("timeout_ms", 30_000)))
    _write_result(request, result)
    return 0 if result.get("status") == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(approve_and_run())
