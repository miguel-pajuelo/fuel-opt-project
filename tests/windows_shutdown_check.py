from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fuelopt_launcher as launcher
import app.windows_shutdown as shutdown
from app.paths import resolve_app_paths
from app.windows_shutdown import ExecutableIdentity, ShutdownError, request_existing_shutdown


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _paths(root: Path):
    install_root = root / "programs" / "FuelOpt"
    return resolve_app_paths(
        environ={"FUELOPT_USER_DATA_ROOT": str(root / "data"), "FUELOPT_PROJECT_ROOT": str(install_root)},
        module_file=install_root / "app" / "paths.py",
        executable=install_root / "FuelOpt.exe",
        frozen=True,
    )


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def _runtime(paths, executable: Path, *, pid: int = 1234, event_name: str | None = None) -> None:
    paths.user_root.mkdir(parents=True, exist_ok=True)
    paths.runtime_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pid": pid,
                "executable": str(executable),
                "port": 8001,
                "shutdown_event": event_name or shutdown.shutdown_event_name(paths),
            }
        ),
        encoding="utf-8",
    )


class _NativeCall:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[object, ...]] = []

    def __call__(self, *args: object) -> object:
        self.calls.append(args)
        return self.result


class FakeKernel32:
    def __init__(self, *, wait_result: int = shutdown.WAIT_OBJECT_0) -> None:
        self.OpenEventW = _NativeCall(4321)
        self.SetEvent = _NativeCall(True)
        self.WaitForSingleObject = _NativeCall(wait_result)
        self.CloseHandle = _NativeCall(True)


def _request_with_fake_process(paths, expected: Path, running: Path, api: FakeKernel32) -> str:
    with (
        patch.object(shutdown, "_open_process", return_value=123),
        patch.object(shutdown, "_process_path", return_value=running),
        patch.object(shutdown, "same_executable", side_effect=_same_path),
        patch.object(shutdown, "_kernel32", return_value=api),
    ):
        return request_existing_shutdown(paths, expected, timeout_ms=25)


def test_absent_and_stale_runtime_are_idempotent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        expected = paths.install_root / "FuelOpt.exe"
        _assert(request_existing_shutdown(paths, expected) == "absent", "missing runtime must be successful")

        _runtime(paths, expected, pid=9999)
        with patch.object(shutdown, "_open_process", return_value=None):
            _assert(request_existing_shutdown(paths, expected) == "stale", "dead PID was not classified stale")
        _assert(not paths.runtime_path.exists(), "stale runtime record was not removed")


def test_installed_process_is_signaled_and_stopped_cooperatively() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        expected = paths.install_root / "FuelOpt.exe"
        _runtime(paths, expected)
        api = FakeKernel32()

        _assert(_request_with_fake_process(paths, expected, expected, api) == "stopped", "owned process did not stop")
        _assert(len(api.OpenEventW.calls) == 1 and len(api.SetEvent.calls) == 1, "owned process was not signaled once")
        _assert(len(api.WaitForSingleObject.calls) == 1, "owned process was not awaited")
        _assert(not paths.runtime_path.exists(), "owned runtime record survived shutdown")


def test_development_and_portable_processes_are_foreign_and_untouched() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        expected = paths.install_root / "FuelOpt.exe"
        foreign_executables = [
            Path(tmp) / "Python" / "python.exe",
            Path(tmp) / "portable" / "FuelOpt.exe",
        ]
        for foreign in foreign_executables:
            _runtime(paths, foreign)
            api = FakeKernel32()

            _assert(_request_with_fake_process(paths, expected, foreign, api) == "foreign", foreign)
            _assert(not api.OpenEventW.calls and not api.SetEvent.calls, "foreign process received a shutdown signal")
            _assert(not api.WaitForSingleObject.calls, "foreign process was awaited")
            _assert(paths.runtime_path.exists(), "foreign runtime record was removed")

        with (
            patch.object(launcher, "APP_PATHS", paths),
            patch.object(launcher, "current_process_path", return_value=expected),
            patch.object(launcher, "request_existing_shutdown", return_value="foreign"),
        ):
            _assert(launcher.shutdown_existing() == 0, "foreign runtime must not block uninstall")


def test_incoherent_or_invalid_live_runtime_fails_without_signaling() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        expected = paths.install_root / "FuelOpt.exe"
        foreign = Path(tmp) / "Python" / "python.exe"

        for recorded, running in ((expected, foreign), (foreign, expected)):
            _runtime(paths, recorded)
            api = FakeKernel32()
            try:
                _request_with_fake_process(paths, expected, running, api)
            except ShutdownError as exc:
                _assert("identity" in str(exc), exc)
            else:
                raise AssertionError("incoherent executable identity was accepted")
            _assert(not api.OpenEventW.calls and not api.SetEvent.calls, "incoherent runtime was signaled")
            _assert(paths.runtime_path.exists(), "incoherent runtime record was removed")

        _runtime(paths, foreign, event_name="Local\\FuelOptShutdown-unrelated")
        api = FakeKernel32()
        try:
            _request_with_fake_process(paths, expected, foreign, api)
        except ShutdownError as exc:
            _assert("event" in str(exc), exc)
        else:
            raise AssertionError("runtime from another data root was accepted")
        _assert(not api.OpenEventW.calls and not api.SetEvent.calls, "wrong data-root event was signaled")

        paths.runtime_path.write_text("not-json", encoding="utf-8")
        try:
            request_existing_shutdown(paths, expected)
        except ShutdownError as exc:
            _assert("invalid" in str(exc), exc)
        else:
            raise AssertionError("invalid JSON was accepted")


def test_owned_process_timeout_remains_an_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        expected = paths.install_root / "FuelOpt.exe"
        _runtime(paths, expected)
        api = FakeKernel32(wait_result=shutdown.WAIT_TIMEOUT)

        try:
            _request_with_fake_process(paths, expected, expected, api)
        except ShutdownError as exc:
            _assert("allowed time" in str(exc), exc)
        else:
            raise AssertionError("owned process timeout was accepted")
        _assert(len(api.SetEvent.calls) == 1, "owned process did not receive cooperative shutdown signal")
        _assert(paths.runtime_path.exists(), "timeout removed the runtime record")


def test_executable_identity_comparison_uses_file_id_then_canonical_path() -> None:
    same_file = ExecutableIdentity("first", 7, 9)
    same_alias = ExecutableIdentity("second", 7, 9)
    other_file = ExecutableIdentity("first", 7, 10)
    with patch.object(shutdown, "executable_identity", side_effect=[same_file, same_alias]):
        _assert(shutdown.same_executable("first", "second"), "matching file IDs were rejected")
    with patch.object(shutdown, "executable_identity", side_effect=[same_file, other_file]):
        _assert(not shutdown.same_executable("first", "second"), "different file IDs were accepted")

    canonical = ExecutableIdentity(os.path.normcase(os.path.abspath("same.exe")), None, None)
    with patch.object(shutdown, "executable_identity", side_effect=[canonical, canonical]):
        _assert(shutdown.same_executable("same.exe", "same.exe"), "canonical fallback was rejected")


def run() -> None:
    test_absent_and_stale_runtime_are_idempotent()
    test_installed_process_is_signaled_and_stopped_cooperatively()
    test_development_and_portable_processes_are_foreign_and_untouched()
    test_incoherent_or_invalid_live_runtime_fails_without_signaling()
    test_owned_process_timeout_remains_an_error()
    test_executable_identity_comparison_uses_file_id_then_canonical_path()
    print("OK: mocked Windows shutdown checks passed")


if __name__ == "__main__":
    run()
