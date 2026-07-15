from __future__ import annotations

import json
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.paths import resolve_app_paths
from app.windows_shutdown import (
    ShutdownError,
    ShutdownEvent,
    current_process_path,
    executable_identity,
    remove_runtime_record,
    request_existing_shutdown,
    same_executable,
    write_runtime_record,
)


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _paths(root: Path):
    return resolve_app_paths(
        environ={"FUELOPT_USER_DATA_ROOT": str(root), "FUELOPT_PROJECT_ROOT": str(ROOT)},
        module_file=ROOT / "app" / "paths.py",
        executable=Path(sys.executable),
        frozen=False,
    )


def _shutdown_helper() -> None:
    from app.paths import APP_PATHS

    event = ShutdownEvent.create(APP_PATHS)
    try:
        write_runtime_record(APP_PATHS, event, 0)
        event.wait()
        remove_runtime_record(APP_PATHS, os.getpid())
    finally:
        event.close()


def _short_path(path: Path) -> Path | None:
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    return Path(buffer.value) if length else None


def test_cooperative_shutdown_isolated() -> None:
    with tempfile.TemporaryDirectory(prefix="fuelopt shutdown á ") as tmp:
        user_root = Path(tmp) / "user data"
        paths = _paths(user_root)
        env = os.environ.copy()
        env["FUELOPT_USER_DATA_ROOT"] = str(user_root)
        env["FUELOPT_PROJECT_ROOT"] = str(ROOT)
        child = subprocess.Popen([sys.executable, __file__, "--shutdown-helper"], cwd=ROOT, env=env)
        try:
            for _ in range(100):
                if paths.runtime_path.exists():
                    break
                if child.poll() is not None:
                    raise AssertionError(f"shutdown helper exited early: {child.returncode}")
                time.sleep(0.05)
            _assert(paths.runtime_path.exists(), "runtime record was not created")
            _assert(request_existing_shutdown(paths, current_process_path(), timeout_ms=5000) == "stopped", "shutdown failed")
            _assert(child.wait(timeout=2) == 0, child.returncode)
            _assert(not paths.runtime_path.exists(), "runtime record survived shutdown")
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=2)


def test_corrupt_and_stale_records_are_safe() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        paths.user_root.mkdir(parents=True, exist_ok=True)
        paths.runtime_path.write_text("not-json", encoding="utf-8")
        try:
            request_existing_shutdown(paths, current_process_path())
        except ShutdownError:
            pass
        else:
            raise AssertionError("corrupt runtime record must not target a process")

        paths.runtime_path.write_text(
            json.dumps({"pid": 4_294_967_294, "shutdown_event": "Local\\FuelOptShutdown-test"}),
            encoding="utf-8",
        )
        _assert(request_existing_shutdown(paths, current_process_path()) == "stale", "stale record was not recovered")
        _assert(not paths.runtime_path.exists(), "stale runtime record was not removed")


def test_canonical_executable_identity_aliases_and_distinct_files() -> None:
    actual = current_process_path()
    identity = executable_identity(actual)
    _assert(identity.file_id is not None, "native executable file identity is unavailable")
    _assert(same_executable(actual, Path(str(actual).swapcase())), "case-only alias was rejected")
    _assert(same_executable(actual, Path("\\\\?\\" + str(actual))), "extended path alias was rejected")
    _assert(same_executable(actual, actual.resolve()), "resolved path was rejected")

    short = _short_path(actual)
    if short is not None:
        _assert(same_executable(actual, short), "short path alias was rejected")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        alias = root / "python-link.exe"
        try:
            alias.symlink_to(actual)
        except OSError:
            alias = None
        if alias is not None:
            _assert(same_executable(actual, alias), "symlink to the same executable was rejected")

        first = root / "first" / "python.exe"
        second = root / "second" / "python.exe"
        first.parent.mkdir()
        second.parent.mkdir()
        shutil.copy2(actual, first)
        shutil.copy2(actual, second)
        _assert(not same_executable(first, second), "different files with the same name were accepted")
        _assert(not same_executable(actual, first), "copied executable was accepted as the running image")

    base = Path(getattr(sys, "_base_executable", sys.executable))
    if not same_executable(Path(sys.executable), base):
        _assert(
            same_executable(actual, base),
            "the native process image must match the base executable when the venv launcher is distinct",
        )


def test_manipulated_live_runtime_record_cannot_signal_process() -> None:
    with tempfile.TemporaryDirectory(prefix="fuelopt runtime guard ") as tmp:
        paths = _paths(Path(tmp) / "data")
        env = os.environ.copy()
        env["FUELOPT_USER_DATA_ROOT"] = str(paths.user_root)
        env["FUELOPT_PROJECT_ROOT"] = str(ROOT)
        child = subprocess.Popen([sys.executable, __file__, "--shutdown-helper"], cwd=ROOT, env=env)
        try:
            for _ in range(100):
                if paths.runtime_path.exists():
                    break
                time.sleep(0.05)
            payload = json.loads(paths.runtime_path.read_text(encoding="utf-8"))
            original = dict(payload)
            payload["executable"] = str(Path(tempfile.gettempdir()) / "unrelated" / "FuelOpt.exe")
            paths.runtime_path.write_text(json.dumps(payload), encoding="utf-8")
            try:
                request_existing_shutdown(paths, current_process_path(), timeout_ms=500)
            except ShutdownError as exc:
                _assert("runtime record" in str(exc), exc)
            else:
                raise AssertionError("manipulated executable identity was accepted")
            _assert(child.poll() is None, "a manipulated runtime record stopped the process")

            payload = dict(original)
            payload["shutdown_event"] = "Local\\FuelOptShutdown-unrelated"
            paths.runtime_path.write_text(json.dumps(payload), encoding="utf-8")
            try:
                request_existing_shutdown(paths, current_process_path(), timeout_ms=500)
            except ShutdownError as exc:
                _assert("event" in str(exc), exc)
            else:
                raise AssertionError("manipulated event identity was accepted")
            _assert(child.poll() is None, "a manipulated event stopped the process")

            paths.runtime_path.write_text(json.dumps(original), encoding="utf-8")
            _assert(request_existing_shutdown(paths, current_process_path(), timeout_ms=5000) == "stopped", "cleanup shutdown failed")
            child.wait(timeout=2)
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=2)


def run() -> None:
    if sys.platform == "win32":
        test_cooperative_shutdown_isolated()
        test_corrupt_and_stale_records_are_safe()
        test_canonical_executable_identity_aliases_and_distinct_files()
        test_manipulated_live_runtime_record_cannot_signal_process()
    print("OK: isolated Windows shutdown checks passed")


if __name__ == "__main__":
    if "--shutdown-helper" in sys.argv:
        _shutdown_helper()
    else:
        run()
