from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from ctypes import wintypes

from app.paths import AppPaths


WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
INFINITE = 0xFFFFFFFF
SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
EVENT_MODIFY_STATE = 0x0002
FILE_READ_ATTRIBUTES = 0x0080
FILE_SHARE_ALL = 0x00000007
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class ShutdownError(RuntimeError):
    pass


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]


@dataclass(frozen=True)
class ExecutableIdentity:
    canonical_path: str
    volume_serial: int | None
    file_index: int | None

    @property
    def file_id(self) -> tuple[int, int] | None:
        if self.volume_serial is None or self.file_index is None:
            return None
        return self.volume_serial, self.file_index


def _kernel32():
    if sys.platform != "win32":
        raise ShutdownError("Windows shutdown signaling is unavailable")
    return ctypes.WinDLL("Kernel32.dll", use_last_error=True)


def shutdown_event_name(paths: AppPaths) -> str:
    identity = hashlib.sha256(str(paths.user_root).casefold().encode("utf-8")).hexdigest()[:20]
    return rf"Local\FuelOptShutdown-{identity}"


def _normalize_windows_path(value: str | Path) -> str:
    text = str(value)
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[8:]
    elif text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normcase(os.path.normpath(os.path.abspath(text)))


def executable_identity(path: str | Path) -> ExecutableIdentity:
    api = _kernel32()
    api.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    api.CreateFileW.restype = wintypes.HANDLE
    handle = api.CreateFileW(
        str(path),
        FILE_READ_ATTRIBUTES,
        FILE_SHARE_ALL,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if not handle or int(handle) == INVALID_HANDLE_VALUE:
        return ExecutableIdentity(_normalize_windows_path(path), None, None)
    try:
        api.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        api.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        final_length = api.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        canonical = _normalize_windows_path(buffer.value if final_length else path)

        api.GetFileInformationByHandle.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ByHandleFileInformation),
        ]
        api.GetFileInformationByHandle.restype = wintypes.BOOL
        info = _ByHandleFileInformation()
        if not api.GetFileInformationByHandle(handle, ctypes.byref(info)):
            return ExecutableIdentity(canonical, None, None)
        file_index = (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow)
        return ExecutableIdentity(canonical, int(info.dwVolumeSerialNumber), file_index)
    finally:
        api.CloseHandle(handle)


def same_executable(left: str | Path, right: str | Path) -> bool:
    left_identity = executable_identity(left)
    right_identity = executable_identity(right)
    if left_identity.file_id is not None and right_identity.file_id is not None:
        return left_identity.file_id == right_identity.file_id
    return left_identity.canonical_path == right_identity.canonical_path


@dataclass
class ShutdownEvent:
    name: str
    handle: int

    @classmethod
    def create(cls, paths: AppPaths) -> "ShutdownEvent":
        api = _kernel32()
        api.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        api.CreateEventW.restype = wintypes.HANDLE
        name = shutdown_event_name(paths)
        handle = api.CreateEventW(None, True, False, name)
        if not handle:
            raise ShutdownError(f"CreateEventW failed: {ctypes.get_last_error()}")
        return cls(name=name, handle=int(handle))

    def wait(self) -> None:
        api = _kernel32()
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        result = api.WaitForSingleObject(self.handle, INFINITE)
        if result != WAIT_OBJECT_0:
            raise ShutdownError(f"shutdown event wait failed: {result}")

    def set(self) -> None:
        api = _kernel32()
        api.SetEvent.argtypes = [wintypes.HANDLE]
        api.SetEvent.restype = wintypes.BOOL
        if not api.SetEvent(self.handle):
            raise ShutdownError(f"SetEvent failed: {ctypes.get_last_error()}")

    def close(self) -> None:
        api = _kernel32()
        api.CloseHandle(self.handle)


def write_runtime_record(paths: AppPaths, event: ShutdownEvent, port: int) -> None:
    paths.user_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "pid": os.getpid(),
        "executable": str(current_process_path()),
        "port": port,
        "shutdown_event": event.name,
    }
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=paths.user_root, prefix=".runtime.", suffix=".tmp", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, paths.runtime_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def remove_runtime_record(paths: AppPaths, pid: int) -> None:
    try:
        payload = json.loads(paths.runtime_path.read_text(encoding="utf-8"))
        if payload.get("pid") == pid:
            paths.runtime_path.unlink(missing_ok=True)
    except (OSError, json.JSONDecodeError, AttributeError):
        pass


def _open_process(pid: int) -> int | None:
    api = _kernel32()
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    handle = api.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    return int(handle) if handle else None


def _process_path(handle: int) -> Path:
    api = _kernel32()
    api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, wintypes.LPDWORD]
    api.QueryFullProcessImageNameW.restype = wintypes.BOOL
    size = wintypes.DWORD(32768)
    buffer = ctypes.create_unicode_buffer(size.value)
    if not api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
        raise ShutdownError(f"QueryFullProcessImageNameW failed: {ctypes.get_last_error()}")
    return Path(buffer.value)


def current_process_path() -> Path:
    process = _open_process(os.getpid())
    if process is None:
        raise ShutdownError("could not open the current process")
    try:
        return _process_path(process)
    finally:
        _kernel32().CloseHandle(process)


def request_existing_shutdown(paths: AppPaths, expected_executable: Path, timeout_ms: int = 20_000) -> str:
    try:
        payload = json.loads(paths.runtime_path.read_text(encoding="utf-8"))
        pid = int(payload["pid"])
        event_name = str(payload["shutdown_event"])
        recorded_executable = str(payload.get("executable") or "")
    except FileNotFoundError:
        return "absent"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ShutdownError("runtime record is invalid") from exc

    process = _open_process(pid)
    if process is None:
        paths.runtime_path.unlink(missing_ok=True)
        return "stale"
    api = _kernel32()
    try:
        if event_name != shutdown_event_name(paths):
            raise ShutdownError("runtime shutdown event does not belong to this FuelOpt data root")
        if not recorded_executable or not same_executable(recorded_executable, expected_executable):
            raise ShutdownError("runtime record does not belong to the installed FuelOpt executable")
        if not same_executable(_process_path(process), expected_executable):
            raise ShutdownError("runtime PID does not belong to the installed FuelOpt executable")
        api.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        api.OpenEventW.restype = wintypes.HANDLE
        event_handle = api.OpenEventW(EVENT_MODIFY_STATE, False, event_name)
        if not event_handle:
            raise ShutdownError("shutdown event is unavailable")
        try:
            api.SetEvent(event_handle)
        finally:
            api.CloseHandle(event_handle)
        result = api.WaitForSingleObject(process, timeout_ms)
        if result != WAIT_OBJECT_0:
            raise ShutdownError("FuelOpt did not stop within the allowed time")
        paths.runtime_path.unlink(missing_ok=True)
        return "stopped"
    finally:
        api.CloseHandle(process)
