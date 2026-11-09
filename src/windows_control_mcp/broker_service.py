"""Windows LocalService broker with named-pipe caller and approval checks."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import pywintypes
import win32api
import win32con
import win32file
import win32pipe
import win32process
import win32security
import win32service
import win32serviceutil

try:
    from .broker_protocol import BROKER_PIPE, POLICY_PATH, load_policy, request_digest, validate_profile, validate_request
except ImportError:  # pywin32 loads the service module by file path.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from windows_control_mcp.broker_protocol import BROKER_PIPE, POLICY_PATH, load_policy, request_digest, validate_profile, validate_request


def _pipe_security():
    # The pipe is reachable by authenticated local users, but every request is
    # checked against the policy SID after impersonation. SYSTEM and admins are
    # retained for service management and diagnostics.
    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        "D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU)", win32security.SDDL_REVISION_1)
    sa = pywintypes.SECURITY_ATTRIBUTES()
    sa.SECURITY_DESCRIPTOR = sd
    sa.bInheritHandle = False
    return sa


def _caller_sid(pipe) -> str:
    win32security.ImpersonateNamedPipeClient(pipe)
    try:
        token = win32security.OpenThreadToken(win32api.GetCurrentThread(), win32con.TOKEN_QUERY, True)
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        return win32security.ConvertSidToStringSid(sid)
    finally:
        win32security.RevertToSelf()


def _client_pid(pipe) -> int:
    return int(win32pipe.GetNamedPipeClientProcessId(pipe))


def _process_path(pid: int) -> Path:
    handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    try:
        return Path(win32process.GetModuleFileNameEx(handle, 0)).resolve()
    finally:
        win32api.CloseHandle(handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _terminate_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                   capture_output=True, check=False)


def _run_bounded(argv: list[str], timeout_ms: int) -> dict:
    out_path = err_path = ""
    process = None
    try:
        out_fd, out_path = tempfile.mkstemp(prefix="windows-control-broker-", suffix=".stdout")
        err_fd, err_path = tempfile.mkstemp(prefix="windows-control-broker-", suffix=".stderr")
        os.close(out_fd)
        os.close(err_fd)
        with open(out_path, "wb") as stdout, open(err_path, "wb") as stderr:
            process = subprocess.Popen(argv, shell=False, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr,
                                       creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            try:
                process.wait(timeout=timeout_ms / 1000)
                status = "succeeded" if process.returncode == 0 else "failed"
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                _terminate_tree(process.pid)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                status = "timed_out"
                exit_code = None
        return {"status": status, "exit_code": exit_code,
                "stdout": Path(out_path).read_bytes()[:20_000].decode("utf-8", "replace"),
                "stderr": Path(err_path).read_bytes()[:20_000].decode("utf-8", "replace")}
    finally:
        for path in (out_path, err_path):
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass


class BrokerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "WindowsControlMCPBroker"
    _svc_display_name_ = "Windows Control MCP Broker"
    _svc_description_ = "Isolated, profile-limited Windows Control MCP execution broker."
    # The installer stages a writable, service-readable pywin32 host next to a
    # private copy of this package.  Keeping this optional preserves normal
    # developer/debug invocation while avoiding the protected Microsoft Store
    # Python directory during service registration.
    _exe_name_ = os.environ.get("WINDOWS_CONTROL_MCP_SERVICE_HOST") or None

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = threading.Event()
        self.pending: dict[str, dict] = {}

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stop_event.set()

    def SvcDoRun(self):
        self._serve()

    def _serve(self):
        while not self.stop_event.is_set():
            pipe = None
            try:
                pipe = win32pipe.CreateNamedPipe(
                    BROKER_PIPE, win32pipe.PIPE_ACCESS_DUPLEX,
                    win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_NOWAIT,
                    8, 1_000_000, 1_000_000, 1000, _pipe_security())
                connected = False
                while not self.stop_event.is_set():
                    try:
                        win32pipe.ConnectNamedPipe(pipe, None)
                        connected = True
                        break
                    except pywintypes.error as exc:
                        if exc.winerror == 536:  # ERROR_PIPE_LISTENING; poll without blocking stop.
                            time.sleep(0.05)
                            continue
                        if exc.winerror == 535:  # ERROR_PIPE_CONNECTED
                            connected = True
                            break
                        raise
                if not connected:
                    break
                _, raw = win32file.ReadFile(pipe, 1_000_000)
                response = self._handle(raw.decode("utf-8"), pipe)
                win32file.WriteFile(pipe, (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
            except Exception as exc:  # service loop must survive malformed clients
                if pipe is not None:
                    try:
                        win32file.WriteFile(pipe, (json.dumps({"status": "rejected", "error": str(exc)}) + "\n").encode("utf-8"))
                    except Exception:
                        pass
            finally:
                if pipe is not None:
                    try:
                        win32pipe.DisconnectNamedPipe(pipe)
                    except Exception:
                        pass
                    win32file.CloseHandle(pipe)

    def _handle(self, raw: str, pipe) -> dict:
        request = json.loads(raw)
        policy = load_policy()
        caller_sid = _caller_sid(pipe)
        if caller_sid != policy["allowed_user_sid"]:
            return {"status": "rejected", "error": "caller_sid_not_allowed"}
        operation = request.get("operation")
        if operation == "prepare":
            return self._prepare(request, policy)
        if operation == "approve_and_run":
            return self._approve_and_run(request, policy, _client_pid(pipe))
        return {"status": "rejected", "error": "unsupported_operation"}

    def _prepare(self, request: dict, policy: dict) -> dict:
        profile_id = str(request.get("profile_id", ""))
        raw_arguments = request.get("arguments", [])
        if not isinstance(raw_arguments, list):
            return {"status": "rejected", "error": "arguments_must_be_list"}
        arguments = raw_arguments
        timeout_ms = int(request.get("timeout_ms", 30_000))
        validate_request(profile_id, arguments, timeout_ms)
        profile = policy["profiles"].get(profile_id)
        validate_profile(profile_id, profile)
        if not profile["allow_arguments"] and arguments:
            return {"status": "rejected", "error": "profile_arguments_not_allowed"}
        approval_id = os.urandom(24).hex()
        digest = request_digest(profile_id, arguments, timeout_ms)
        self.pending[approval_id] = {"digest": digest, "expires": time.time() + 120,
                                     "profile_id": profile_id, "arguments": arguments,
                                     "timeout_ms": timeout_ms}
        return {"status": "approval_required", "approval_id": approval_id, "request_digest": digest}

    def _approve_and_run(self, request: dict, policy: dict, pid: int) -> dict:
        approval_id = str(request.get("approval_id", ""))
        pending = self.pending.pop(approval_id, None)
        if not pending or pending["expires"] < time.time():
            return {"status": "rejected", "error": "approval_expired"}
        helper = policy.get("approval_helper", {})
        helper_path = Path(str(helper.get("path", ""))).resolve()
        if not helper_path.is_file() or not pid or _process_path(pid) != helper_path:
            return {"status": "rejected", "error": "approval_helper_not_authenticated"}
        if _sha256(helper_path).lower() != str(helper.get("sha256", "")).lower():
            return {"status": "rejected", "error": "approval_helper_hash_mismatch"}
        profile = policy["profiles"].get(pending["profile_id"])
        try:
            validate_profile(pending["profile_id"], profile)
            validate_request(pending["profile_id"], pending["arguments"], pending["timeout_ms"])
        except (TypeError, ValueError) as exc:
            return {"status": "rejected", "error": "profile_or_request_invalid", "detail": str(exc)}
        if not profile["allow_arguments"] and pending["arguments"]:
            return {"status": "rejected", "error": "profile_arguments_not_allowed"}
        executable = Path(str(profile["executable"])).resolve()
        if _sha256(executable).lower() != str(profile["sha256"]).lower():
            return {"status": "rejected", "error": "profile_hash_mismatch"}
        argv = [str(executable), *profile["fixed_arguments"], *pending["arguments"]]
        result = _run_bounded(argv, pending["timeout_ms"])
        result["request_digest"] = pending["digest"]
        return result


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(BrokerService)
