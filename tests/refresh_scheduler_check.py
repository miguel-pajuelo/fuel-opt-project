from __future__ import annotations

import json
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.catalog.refresh_service import (
    EXIT_ALREADY_RUNNING,
    EXIT_OK,
    EXIT_SOURCE_FAILED,
    EXIT_VALIDATION_FAILED,
    RefreshRequest,
    run_catalog_refresh,
)
from app.paths import resolve_app_paths
from app.user_config import RefreshInterval, UserConfig, load_user_config, save_user_config
from app.windows_scheduler import (
    INTERVAL_DURATIONS,
    TASK_NAME,
    SchedulerError,
    SchedulerResult,
    TaskScheduler,
    _current_user_sid,
    render_task_xml,
    task_start_boundary,
)
from app.storage.validation import CatalogValidationRules, validate_catalog_db
import fuelopt_launcher as launcher


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _snapshot(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": "MINETUR",
                "fetched_at": "2026-07-12T10:00:00+02:00",
                "items": [
                    {
                        "IDEESS": "1001",
                        "Rótulo": "REPSOL",
                        "Dirección": "Calle Uno",
                        "C.P.": "28001",
                        "Municipio": "Madrid",
                        "Provincia": "Madrid",
                        "Latitud": "40,4000",
                        "Longitud (WGS84)": "-3,7000",
                        "Precio Gasoleo A": "1,500",
                        "Precio Gasolina 95 E5": "1,600",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _refresh_request(root: Path, *, min_stations: int = 1) -> RefreshRequest:
    snapshot = root / "cache" / "minetur_snapshot.json"
    _snapshot(snapshot)
    return RefreshRequest(
        db=root / "db" / "gas_stations.sqlite",
        source="snapshot",
        snapshot=snapshot,
        report_path=root / "logs" / "report.json",
        lock_path=root / "logs" / "refresh.lock",
        min_stations=min_stations,
        min_prices=2,
        max_unknown_brand_ratio=1.0,
        backup_retention=1,
    )


def test_direct_refresh_runs_without_fastapi() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        request = _refresh_request(Path(tmp))
        result = run_catalog_refresh(request)
        _assert(result.exit_code == EXIT_OK, result.report)
        _assert(result.report["refresh_status"] == "ok", result.report)
        _assert(request.db.exists(), "direct service did not publish active DB")
        rules = CatalogValidationRules(min_stations=1, min_prices=2, max_unknown_brand_ratio=1.0)
        _assert(validate_catalog_db(request.db, rules, readonly=True).ok, "published DB invalid")
        _assert(json.loads(request.report_path.read_text(encoding="utf-8"))["refresh_status"] == "ok", "report missing")


def test_direct_refresh_lock_has_distinct_exit_code() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        request = _refresh_request(Path(tmp))
        request.lock_path.parent.mkdir(parents=True, exist_ok=True)
        request.lock_path.write_text(
            json.dumps({"started_epoch": datetime.now().timestamp()}),
            encoding="utf-8",
        )
        result = run_catalog_refresh(request)
        _assert(result.exit_code == EXIT_ALREADY_RUNNING, result.report)
        _assert(result.report["refresh_status"] == "skipped", result.report)


def test_direct_refresh_validation_failure_keeps_active_absent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        request = _refresh_request(Path(tmp), min_stations=10)
        result = run_catalog_refresh(request)
        _assert(result.exit_code == EXIT_VALIDATION_FAILED, result.report)
        _assert(result.report["refresh_status"] == "failed_validation", result.report)
        _assert(not request.db.exists(), "invalid candidate was published")


def test_direct_refresh_source_failure_preserves_last_valid_database() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        request = _refresh_request(root)
        first = run_catalog_refresh(request)
        _assert(first.exit_code == EXIT_OK, first.report)
        active_hash = hashlib.sha256(request.db.read_bytes()).hexdigest()
        request.snapshot.write_text("not valid json", encoding="utf-8")

        failed = run_catalog_refresh(request)

        _assert(failed.exit_code == EXIT_SOURCE_FAILED, failed.report)
        _assert(hashlib.sha256(request.db.read_bytes()).hexdigest() == active_hash, "failed refresh changed active DB")


def _test_paths(base: Path):
    resource = base / "program files" / "FuelOpt"
    user = base / "local app data" / "FuelOpt"
    return resolve_app_paths(
        environ={"FUELOPT_PROJECT_ROOT": str(resource), "FUELOPT_USER_DATA_ROOT": str(user)},
        module_file=resource / "app" / "paths.py",
        executable=resource / "FuelOpt.exe",
        frozen=True,
    )


class FakeTaskRunner:
    def __init__(
        self,
        *,
        existing_xml: str | None = None,
        fail_first_create: bool = False,
        corrupt_first_create: bool = False,
        fail_delete: bool = False,
    ) -> None:
        self.existing_xml = existing_xml
        self.fail_first_create = fail_first_create
        self.corrupt_first_create = corrupt_first_create
        self.fail_delete = fail_delete
        self.calls: list[list[str]] = []
        self.created_xml: list[str] = []

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if "/Query" in args:
            return subprocess.CompletedProcess(args, 0, self.existing_xml or "", "") if self.existing_xml else subprocess.CompletedProcess(args, 1, "", "not found")
        if "/Delete" in args:
            if self.fail_delete:
                return subprocess.CompletedProcess(args, 1, "", "delete failed")
            self.existing_xml = None
            return subprocess.CompletedProcess(args, 0, "deleted", "")
        if "/Create" in args:
            xml_path = Path(args[args.index("/XML") + 1])
            raw = xml_path.read_bytes()
            encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
            self.created_xml.append(raw.decode(encoding))
            if self.fail_first_create:
                self.fail_first_create = False
                return subprocess.CompletedProcess(args, 1, "", "create failed")
            if self.corrupt_first_create:
                self.corrupt_first_create = False
                self.existing_xml = self.created_xml[-1].replace(
                    "--refresh-direct --silent", "--unexpected-command"
                )
            else:
                self.existing_xml = self.created_xml[-1]
            return subprocess.CompletedProcess(args, 0, "created", "")
        return subprocess.CompletedProcess(args, 1, "", "unexpected")


def test_scheduler_xml_for_every_frequency() -> None:
    now = datetime(2026, 7, 12, 12, 30, tzinfo=timezone(timedelta(hours=2)))
    namespace = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    for interval, duration in INTERVAL_DURATIONS.items():
        xml = render_task_xml(
            interval=interval,
            user_sid="S-1-5-21-1000",
            command=Path(r"C:\Program Files With Spaces\FuelOpt.exe"),
            arguments="--refresh-direct --silent",
            working_directory=Path(r"C:\Program Files With Spaces"),
            now=now,
        )
        root = ET.fromstring(xml)
        _assert(root.findtext(".//t:Interval", namespaces=namespace) == duration, xml)
        _assert(root.findtext(".//t:StartWhenAvailable", namespaces=namespace) == "true", xml)
        _assert(root.findtext(".//t:MultipleInstancesPolicy", namespaces=namespace) == "IgnoreNew", xml)
        _assert(root.findtext(".//t:Hidden", namespaces=namespace) == "true", xml)
        _assert(root.findtext(".//t:LogonType", namespaces=namespace) == "InteractiveToken", xml)
        _assert(root.findtext(".//t:RunLevel", namespaces=namespace) == "LeastPrivilege", xml)
        _assert(root.findtext(".//t:UserId", namespaces=namespace) == "S-1-5-21-1000", xml)
        _assert(root.findtext(".//t:Arguments", namespaces=namespace) == "--refresh-direct --silent", xml)
        expected = (now.astimezone() + {
            "1h": timedelta(hours=1), "2h": timedelta(hours=2), "4h": timedelta(hours=4),
            "8h": timedelta(hours=8), "12h": timedelta(hours=12), "24h": timedelta(hours=24),
        }[interval]).isoformat()
        _assert(task_start_boundary(interval, now=now) == expected, interval)


def test_scheduler_create_update_remove_and_rollback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _test_paths(Path(tmp))
        runner = FakeTaskRunner()
        scheduler = TaskScheduler(paths=paths, runner=runner)
        created = scheduler.configure(
            interval="4h",
            command=paths.install_root / "FuelOpt.exe",
            arguments="--refresh-direct --silent",
            working_directory=paths.install_root,
            user_sid="S-1-5-21-1000",
            now=datetime(2026, 7, 12, 12, 0).astimezone(),
        )
        _assert(created.action == "created", created)
        _assert(any("/F" in call and "/Create" in call for call in runner.calls), runner.calls)

        old_xml = runner.existing_xml
        updated = scheduler.configure(
            interval="8h",
            command=paths.install_root / "FuelOpt.exe",
            arguments="--refresh-direct --silent",
            working_directory=paths.install_root,
            user_sid="S-1-5-21-1000",
        )
        _assert(updated.action == "updated", updated)
        _assert(old_xml != runner.existing_xml, "updated task XML did not change")

        removed = scheduler.configure(
            interval=RefreshInterval.MANUAL.value,
            command=paths.install_root / "FuelOpt.exe",
            arguments="--refresh-direct --silent",
            working_directory=paths.install_root,
        )
        _assert(removed.action == "removed", removed)

        failing_runner = FakeTaskRunner(existing_xml=old_xml, fail_first_create=True)
        failing = TaskScheduler(paths=paths, runner=failing_runner)
        try:
            failing.configure(
                interval="2h",
                command=paths.install_root / "FuelOpt.exe",
                arguments="--refresh-direct --silent",
                working_directory=paths.install_root,
                user_sid="S-1-5-21-1000",
            )
        except SchedulerError:
            pass
        else:
            raise AssertionError("scheduler create failure should propagate")
        create_calls = [call for call in failing_runner.calls if "/Create" in call]
        _assert(len(create_calls) == 2, create_calls)


def test_scheduler_legacy_migration_is_restricted_and_verified() -> None:
    legacy_xml = """<?xml version="1.0"?>
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Actions><Exec>
<Command>cmd.exe</Command><Arguments>/d /c &quot;C:\\FuelOpt old\\scripts\\run_refresh_catalog.cmd&quot;</Arguments>
</Exec></Actions></Task>"""
    unrelated_xml = legacy_xml.replace("run_refresh_catalog.cmd", "run_unrelated_catalog.cmd")

    with tempfile.TemporaryDirectory() as tmp:
        paths = _test_paths(Path(tmp))
        command = paths.install_root / "FuelOpt.exe"
        runner = FakeTaskRunner(existing_xml=legacy_xml)
        scheduler = TaskScheduler(paths=paths, runner=runner)
        result = scheduler.configure(
            interval="4h",
            command=command,
            arguments="--refresh-direct --silent",
            working_directory=paths.install_root,
            user_sid="S-1-5-21-1000",
        )
        _assert(result.action == "updated", result)
        _assert("--refresh-direct --silent" in (runner.existing_xml or ""), "legacy task was not migrated")

        unrelated = FakeTaskRunner(existing_xml=unrelated_xml)
        try:
            TaskScheduler(paths=paths, runner=unrelated).configure(
                interval="manual",
                command=command,
                arguments="--refresh-direct --silent",
                working_directory=paths.install_root,
            )
        except SchedulerError as exc:
            _assert("unrecognized" in str(exc), exc)
        else:
            raise AssertionError("an unrelated task must never be removed")
        _assert(not any("/Delete" in call for call in unrelated.calls), unrelated.calls)

        corrupt = FakeTaskRunner(existing_xml=legacy_xml, corrupt_first_create=True)
        try:
            TaskScheduler(paths=paths, runner=corrupt).configure(
                interval="4h",
                command=command,
                arguments="--refresh-direct --silent",
                working_directory=paths.install_root,
                user_sid="S-1-5-21-1000",
            )
        except SchedulerError as exc:
            _assert("verification" in str(exc), exc)
        else:
            raise AssertionError("an invalid registered task must fail verification")
        _assert("run_refresh_catalog.cmd" in (corrupt.existing_xml or ""), "legacy task was not restored")


def test_configure_refresh_persists_every_allowed_value() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _test_paths(Path(tmp))
        runner = FakeTaskRunner()
        scheduler = TaskScheduler(paths=paths, runner=runner)
        original_paths = launcher.APP_PATHS
        original_report_dir = launcher.REPORT_DIR
        original_log_path = launcher.LOG_PATH
        launcher.APP_PATHS = paths
        launcher.REPORT_DIR = paths.logs_dir
        launcher.LOG_PATH = paths.logs_dir / "launcher.log"
        launcher.LOGGER.handlers.clear()
        try:
            for interval in [item.value for item in RefreshInterval]:
                code = launcher.configure_refresh(interval, scheduler=scheduler)
                _assert(code == 0, (interval, code))
                _assert(load_user_config(paths.config_path).refresh_interval == interval, interval)
        finally:
            launcher.LOGGER.handlers.clear()
            launcher.APP_PATHS = original_paths
            launcher.REPORT_DIR = original_report_dir
            launcher.LOG_PATH = original_log_path


def test_remove_refresh_task_identity_and_safety_regression() -> None:
    class RecordingScheduler:
        def __init__(self, action: str = "removed") -> None:
            self.action = action
            self.calls: list[tuple[Path, str]] = []

        def remove(self, *, command: Path, arguments: str) -> SchedulerResult:
            self.calls.append((command, arguments))
            return SchedulerResult(self.action)

    class FailingScheduler:
        def remove(self, *, command: Path, arguments: str) -> SchedulerResult:
            raise SchedulerError("simulated scheduler failure")

    with tempfile.TemporaryDirectory() as tmp:
        paths = _test_paths(Path(tmp))
        expected_command = paths.install_root / "FuelOpt.exe"
        expected_arguments = "--refresh-direct --silent"
        original_paths = launcher.APP_PATHS
        original_scheduler_command = launcher.scheduler_command
        original_report_dir = launcher.REPORT_DIR
        original_log_path = launcher.LOG_PATH
        launcher.APP_PATHS = paths
        launcher.REPORT_DIR = paths.logs_dir
        launcher.LOG_PATH = paths.logs_dir / "launcher.log"
        launcher.scheduler_command = lambda: (expected_command, expected_arguments)
        launcher.LOGGER.handlers.clear()
        try:
            for action in ("removed", "absent"):
                save_user_config(paths.config_path, UserConfig(refresh_interval="4h"))
                scheduler = RecordingScheduler(action)
                _assert(launcher.remove_refresh_task(scheduler=scheduler) == 0, action)
                _assert(scheduler.calls == [(expected_command, expected_arguments)], scheduler.calls)
                _assert(load_user_config(paths.config_path).refresh_interval == "manual", action)

            save_user_config(paths.config_path, UserConfig(refresh_interval="4h"))
            _assert(launcher.remove_refresh_task(scheduler=FailingScheduler()) == 7, "SchedulerError was not controlled")
            _assert(load_user_config(paths.config_path).refresh_interval == "4h", "failed removal changed configuration")
        finally:
            launcher.LOGGER.handlers.clear()
            launcher.APP_PATHS = original_paths
            launcher.REPORT_DIR = original_report_dir
            launcher.LOG_PATH = original_log_path
            launcher.scheduler_command = original_scheduler_command

    source = (ROOT / "fuelopt_launcher.py").read_text(encoding="utf-8")
    observed = " ".join(("TaskScheduler.remove()", "missing", "2", "required", "keyword-only", "arguments"))
    zero_argument_call = "".join(("TaskScheduler(paths=APP_PATHS)).", "remove", "()"))
    _assert("scheduler_instance.remove(command=command, arguments=arguments)" in source, "task identity is not explicit")
    _assert(zero_argument_call not in source, "zero-argument removal regression returned")
    _assert(observed not in source, "observed PyInstaller traceback leaked into source")


def test_scheduler_removes_only_managed_or_legacy_tasks() -> None:
    legacy_xml = """<?xml version="1.0"?>
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Actions><Exec>
<Command>cmd.exe</Command><Arguments>/d /c &quot;C:\\FuelOpt old\\scripts\\run_refresh_catalog.cmd&quot;</Arguments>
</Exec></Actions></Task>"""
    unrelated_xml = legacy_xml.replace("run_refresh_catalog.cmd", "run_unrelated_catalog.cmd")

    with tempfile.TemporaryDirectory() as tmp:
        paths = _test_paths(Path(tmp))
        command = paths.install_root / "FuelOpt.exe"
        arguments = "--refresh-direct --silent"
        managed_xml = render_task_xml(
            interval="4h",
            user_sid="S-1-5-21-1000",
            command=command,
            arguments=arguments,
            working_directory=paths.install_root,
        )
        for xml in (managed_xml, legacy_xml):
            runner = FakeTaskRunner(existing_xml=xml)
            result = TaskScheduler(paths=paths, runner=runner).remove(command=command, arguments=arguments)
            _assert(result.action == "removed", result)
            _assert(sum("/Delete" in call for call in runner.calls) == 1, runner.calls)

        absent = FakeTaskRunner()
        result = TaskScheduler(paths=paths, runner=absent).remove(command=command, arguments=arguments)
        _assert(result.action == "absent", result)
        _assert(not any("/Delete" in call for call in absent.calls), absent.calls)

        unrelated = FakeTaskRunner(existing_xml=unrelated_xml)
        try:
            TaskScheduler(paths=paths, runner=unrelated).remove(command=command, arguments=arguments)
        except SchedulerError as exc:
            _assert("unrecognized" in str(exc), exc)
        else:
            raise AssertionError("unrecognized task was removed")
        _assert(not any("/Delete" in call for call in unrelated.calls), unrelated.calls)

        failing = FakeTaskRunner(existing_xml=managed_xml, fail_delete=True)
        try:
            TaskScheduler(paths=paths, runner=failing).remove(command=command, arguments=arguments)
        except SchedulerError as exc:
            _assert("delete failed" in str(exc), exc)
        else:
            raise AssertionError("scheduler deletion failure was accepted")


def test_maintenance_cli_contains_unexpected_exceptions_without_traceback() -> None:
    sentinel = "sensitive-path-or-secret"
    cases = (
        ("shutdown_existing", ["fuelopt_launcher.py", "--shutdown-existing"], "shutdown-existing"),
        ("remove_refresh_task", ["fuelopt_launcher.py", "--remove-refresh-task"], "remove-refresh-task"),
        (
            "configure_refresh",
            ["fuelopt_launcher.py", "--configure-refresh", "--interval", "4h"],
            "configure-refresh",
        ),
    )
    original_argv = sys.argv
    original_log = launcher.log
    original_diagnostic_log = launcher.diagnostic_log
    originals = {name: getattr(launcher, name) for name, _argv, _operation in cases}

    def explode(*_args: object) -> int:
        raise RuntimeError(sentinel)

    try:
        launcher.diagnostic_log = lambda _message: None
        for name, argv, operation in cases:
            messages: list[str] = []
            launcher.log = messages.append
            setattr(launcher, name, explode)
            sys.argv = argv
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = launcher.main()
            _assert(code == launcher.MAINTENANCE_FAILURE_EXIT_CODE and code != 0, (operation, code))
            _assert(stderr.getvalue() == "", f"traceback escaped for {operation}: {stderr.getvalue()}")
            _assert(messages == [f"maintenance command failed operation={operation} exception=RuntimeError"], messages)
            _assert(sentinel not in "".join(messages), "exception details leaked into maintenance log")
            setattr(launcher, name, originals[name])
    finally:
        sys.argv = original_argv
        launcher.log = original_log
        launcher.diagnostic_log = original_diagnostic_log
        for name, original in originals.items():
            setattr(launcher, name, original)


def test_launcher_port_selection_and_start_lock() -> None:
    port, existing = launcher.select_launcher_port(
        8001,
        ready_check=lambda _url: False,
        free_check=lambda value: value == 8002,
    )
    _assert((port, existing) == (8002, False), (port, existing))
    port, existing = launcher.select_launcher_port(
        8001,
        ready_check=lambda _url: True,
        free_check=lambda _value: False,
    )
    _assert((port, existing) == (8001, True), (port, existing))
    port, existing = launcher.select_launcher_port(
        8001,
        ready_check=lambda url: url.endswith(":8002"),
        free_check=lambda _value: False,
    )
    _assert((port, existing) == (8002, True), (port, existing))

    with tempfile.TemporaryDirectory() as tmp:
        paths = _test_paths(Path(tmp))
        original_paths = launcher.APP_PATHS
        launcher.APP_PATHS = paths
        try:
            with launcher.launcher_start_lock():
                try:
                    with launcher.launcher_start_lock(timeout_sec=0.01):
                        pass
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("concurrent launcher lock should time out")
        finally:
            launcher.APP_PATHS = original_paths

    with tempfile.TemporaryDirectory() as tmp:
        paths = _test_paths(Path(tmp))
        paths.cache_dir.mkdir(parents=True, exist_ok=True)
        stale_lock = paths.cache_dir / "launcher-start.lock"
        stale_lock.write_text("  pid = 4294967294  \n", encoding="utf-8-sig")
        original_paths = launcher.APP_PATHS
        launcher.APP_PATHS = paths
        try:
            with launcher.launcher_start_lock(timeout_sec=0.5):
                _assert(stale_lock.exists(), "recovered lock should be owned by current launcher")
        finally:
            launcher.APP_PATHS = original_paths
        _assert(not stale_lock.exists(), "launcher lock should be removed on normal exit")

        stale_lock.write_text("partial lock", encoding="utf-8")
        _assert(not launcher._launcher_lock_is_stale(stale_lock), "fresh partial lock needs a grace period")
        old = time.time() - launcher.CORRUPT_LOCK_GRACE_SEC - 1
        os.utime(stale_lock, (old, old))
        _assert(launcher._launcher_lock_is_stale(stale_lock), "old corrupt lock should be recoverable")


def test_launcher_identity_port_race_and_child_cleanup() -> None:
    original_request_json = launcher.request_json
    try:
        launcher.request_json = lambda *_args, **_kwargs: {"status": "ok", "service": "Other"}
        _assert(not launcher.server_ready("http://127.0.0.1:8001"), "foreign 200 response must not be reused")
        launcher.request_json = lambda *_args, **_kwargs: {"status": "ok", "service": "FuelOpt"}
        _assert(launcher.server_ready("http://127.0.0.1:8001"), "FuelOpt identity should be reusable")
    finally:
        launcher.request_json = original_request_json

    class FakeProcess:
        def __init__(self, code: int | None) -> None:
            self.pid = 12345
            self.code = code
            self.terminated = False
            self.killed = False

        def poll(self):
            return self.code

        def terminate(self):
            self.terminated = True
            self.code = 1

        def kill(self):
            self.killed = True
            self.code = 1

        def wait(self, timeout=None):
            return self.code

    live = FakeProcess(None)
    launcher.stop_child_process(live)  # type: ignore[arg-type]
    _assert(live.terminated and live.poll() is not None, "failed child must be terminated")

    with tempfile.TemporaryDirectory() as tmp:
        paths = _test_paths(Path(tmp))
        original_paths = launcher.APP_PATHS
        original_select = launcher.select_launcher_port
        original_start = launcher.start_server
        original_wait = launcher.wait_for_server
        original_free = launcher.port_is_free
        original_ready = launcher.server_ready
        original_report_dir = launcher.REPORT_DIR
        original_log_path = launcher.LOG_PATH
        failed = FakeProcess(1)
        launcher.APP_PATHS = paths
        launcher.REPORT_DIR = paths.logs_dir
        launcher.LOG_PATH = paths.logs_dir / "launcher.log"
        launcher.LOGGER.handlers.clear()
        launcher.select_launcher_port = lambda requested: (8001, False) if requested == 8001 else (8002, True)
        launcher.start_server = lambda _host, _port: failed  # type: ignore[assignment]
        launcher.wait_for_server = lambda _url, **_kwargs: False
        launcher.port_is_free = lambda port, **_kwargs: port != 8001
        launcher.server_ready = lambda _url: False
        args = type("Args", (), {
            "port": 8001,
            "host": "127.0.0.1",
            "no_browser": True,
            "browser_host": "127.0.0.1",
            "no_refresh": True,
        })()
        try:
            _assert(launcher.run_launcher(args) == 0, "port race should retry the next port")
            _assert(args.port == 8002, args.port)
        finally:
            launcher.LOGGER.handlers.clear()
            launcher.APP_PATHS = original_paths
            launcher.REPORT_DIR = original_report_dir
            launcher.LOG_PATH = original_log_path
            launcher.select_launcher_port = original_select
            launcher.start_server = original_start
            launcher.wait_for_server = original_wait
            launcher.port_is_free = original_free
            launcher.server_ready = original_ready


def test_rotating_stdio_fallback_preserves_valid_streams() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "logs" / "launcher_console.log"
        stream = launcher._RotatingTextStream(path, max_bytes=32, backup_count=2)
        stream.write("a" * 24)
        stream.write("b" * 24)
        stream.flush()
        stream.close()
        _assert(path.exists() and path.with_name("launcher_console.log.1").exists(), "console log did not rotate")

    stdout = io.StringIO()
    stderr = io.StringIO()
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    try:
        sys.stdout = stdout
        sys.stderr = stderr
        launcher.ensure_standard_streams()
        _assert(sys.stdout is stdout and sys.stderr is stderr, "valid streams must not be replaced")
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr


def test_frozen_child_command_environment_and_browser_dispatch() -> None:
    had_frozen = hasattr(sys, "frozen")
    original_frozen = getattr(sys, "frozen", None)
    try:
        setattr(sys, "frozen", True)
        _assert(launcher.self_command("--server-only") == [sys.executable, "--server-only"], "frozen child must reuse executable")
        _assert(launcher.managed_env().get("PYINSTALLER_RESET_ENVIRONMENT") == "1", "independent frozen child must reset PyInstaller environment")
    finally:
        if had_frozen:
            setattr(sys, "frozen", original_frozen)
        else:
            delattr(sys, "frozen")

    with tempfile.TemporaryDirectory() as tmp:
        paths = _test_paths(Path(tmp))
        original_paths = launcher.APP_PATHS
        original_select = launcher.select_launcher_port
        original_open = launcher.webbrowser.open
        original_report_dir = launcher.REPORT_DIR
        original_log_path = launcher.LOG_PATH
        opened: list[str] = []
        launcher.APP_PATHS = paths
        launcher.REPORT_DIR = paths.logs_dir
        launcher.LOG_PATH = paths.logs_dir / "launcher.log"
        launcher.LOGGER.handlers.clear()
        launcher.select_launcher_port = lambda port: (port, True)
        launcher.webbrowser.open = lambda url: opened.append(url) or True
        args = type("Args", (), {
            "port": 8001,
            "host": "127.0.0.1",
            "no_browser": False,
            "browser_host": "127.0.0.1",
            "no_refresh": True,
        })()
        try:
            _assert(launcher.run_launcher(args) == 0, "launcher dispatch failed")
            _assert(opened == ["http://127.0.0.1:8001"], opened)
        finally:
            launcher.LOGGER.handlers.clear()
            launcher.APP_PATHS = original_paths
            launcher.REPORT_DIR = original_report_dir
            launcher.LOG_PATH = original_log_path
            launcher.select_launcher_port = original_select
            launcher.webbrowser.open = original_open
        _assert(not (paths.cache_dir / "launcher-start.lock").exists(), "launcher lock was not released")


def test_current_windows_sid_is_resolvable() -> None:
    if sys.platform == "win32":
        _assert(_current_user_sid().startswith("S-"), "current user SID was not resolved")


def test_show_settings_never_prints_ors_secret() -> None:
    sentinel = "patch4-ors-secret-sentinel"
    original = os.environ.get("ORS_API_KEY")
    os.environ["ORS_API_KEY"] = sentinel
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            code = launcher.show_settings()
    finally:
        if original is None:
            os.environ.pop("ORS_API_KEY", None)
        else:
            os.environ["ORS_API_KEY"] = original
    text = output.getvalue()
    _assert(code == 0, code)
    _assert(sentinel not in text, text)
    _assert(json.loads(text)["ors_configured"] is True, text)


def test_launcher_has_no_http_refresh_dependency_and_endpoint_remains() -> None:
    launcher = (ROOT / "fuelopt_launcher.py").read_text(encoding="utf-8")
    api = (ROOT / "app" / "api" / "main.py").read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "refresh_catalog.py").read_text(encoding="utf-8")
    _assert("/catalog/refresh" not in launcher, "launcher still refreshes over HTTP")
    _assert('@app.post("/catalog/refresh")' in api, "compatibility endpoint was removed")
    _assert("FUELOPT_ADMIN_TOKEN" in (ROOT / ".env.example").read_text(encoding="utf-8"), "admin token removed early")
    _assert("run_catalog_refresh" in api and "run_catalog_refresh" in script, "wrappers do not share direct service")


def run() -> None:
    test_direct_refresh_runs_without_fastapi()
    test_direct_refresh_lock_has_distinct_exit_code()
    test_direct_refresh_validation_failure_keeps_active_absent()
    test_direct_refresh_source_failure_preserves_last_valid_database()
    test_scheduler_xml_for_every_frequency()
    test_scheduler_create_update_remove_and_rollback()
    test_scheduler_legacy_migration_is_restricted_and_verified()
    test_configure_refresh_persists_every_allowed_value()
    test_remove_refresh_task_identity_and_safety_regression()
    test_scheduler_removes_only_managed_or_legacy_tasks()
    test_maintenance_cli_contains_unexpected_exceptions_without_traceback()
    test_launcher_port_selection_and_start_lock()
    test_launcher_identity_port_race_and_child_cleanup()
    test_rotating_stdio_fallback_preserves_valid_streams()
    test_frozen_child_command_environment_and_browser_dispatch()
    test_current_windows_sid_is_resolvable()
    test_show_settings_never_prints_ors_secret()
    test_launcher_has_no_http_refresh_dependency_and_endpoint_remains()
    print("OK: direct refresh and Windows Scheduler checks passed")


if __name__ == "__main__":
    run()
