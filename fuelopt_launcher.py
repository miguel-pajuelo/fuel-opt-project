from __future__ import annotations

import argparse
import atexit
import asyncio
import ctypes
import getpass
import io
import json
import logging
import multiprocessing
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import contextmanager
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

if __name__ == "__main__":
    # PyInstaller multiprocessing children must be intercepted before project
    # modules are imported or any application initialization can run.
    multiprocessing.freeze_support()

from app.paths import resolve_app_paths
from app.user_config import RefreshInterval, UserConfig, UserConfigError, load_user_config, save_user_config
from app.windows_credentials import ORS_CREDENTIAL_TARGET, CredentialStoreError, default_credential_store
from app.windows_scheduler import SchedulerError, TaskScheduler
from app.windows_shutdown import (
    current_process_path,
    ShutdownError,
    ShutdownEvent,
    remove_runtime_record,
    request_existing_shutdown,
    write_runtime_record,
)


DEFAULT_HOST = "127.0.0.1"
LAN_HOST = "0.0.0.0"
DEFAULT_PORT = 8001
DEFAULT_BROWSER_HOST = "127.0.0.1"
HEALTH_TIMEOUT_SEC = 35
CORRUPT_LOCK_GRACE_SEC = 2.0


def _looks_like_project_root(path: Path) -> bool:
    return (
        (path / "static" / "index.html").is_file()
        and (
            (path / "app").is_dir()
            or (path / "resources" / "seed" / "gas_stations.seed.sqlite").is_file()
        )
    )


def project_root() -> Path:
    env_root = os.getenv("FUELOPT_PROJECT_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        if _looks_like_project_root(candidate):
            return candidate

    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            candidate = Path(bundle_root).resolve()
            if _looks_like_project_root(candidate):
                return candidate
        exe_dir = Path(sys.executable).resolve().parent
        candidates = (
            exe_dir,
            exe_dir / "FuelOptApp",
            exe_dir.parent,
            exe_dir.parent / "FuelOptApp",
        )
        for candidate in candidates:
            if _looks_like_project_root(candidate):
                return candidate
        return exe_dir
    return Path(__file__).resolve().parent


ROOT = project_root()
_PATH_ENV = {**os.environ, "FUELOPT_PROJECT_ROOT": str(ROOT)}
APP_PATHS = resolve_app_paths(environ=_PATH_ENV)
REPORT_DIR = APP_PATHS.logs_dir
LOG_PATH = REPORT_DIR / "launcher.log"
LOGGER = logging.getLogger("fuelopt_launcher")
_STDIO_FALLBACK: Any | None = None


class _RotatingTextStream(io.TextIOBase):
    def __init__(self, path: Path, *, max_bytes: int = 1_000_000, backup_count: int = 3) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8", buffering=1)

    @property
    def encoding(self) -> str:
        return "utf-8"

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return False

    def _rotate_if_needed(self, text: str) -> None:
        if self._handle.tell() + len(text.encode("utf-8", errors="replace")) <= self.max_bytes:
            return
        self._handle.close()
        try:
            for index in range(self.backup_count, 1, -1):
                older = self.path.with_name(f"{self.path.name}.{index - 1}")
                newer = self.path.with_name(f"{self.path.name}.{index}")
                if older.exists():
                    os.replace(older, newer)
            if self.path.exists():
                os.replace(self.path, self.path.with_name(f"{self.path.name}.1"))
        finally:
            self._handle = self.path.open("a", encoding="utf-8", buffering=1)

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            text = str(text)
        with self._lock:
            self._rotate_if_needed(text)
            written = self._handle.write(text)
            self._handle.flush()
            return written

    def flush(self) -> None:
        with self._lock:
            if not self._handle.closed:
                self._handle.flush()

    def close(self) -> None:
        with self._lock:
            if not self._handle.closed:
                self._handle.flush()
                self._handle.close()
        super().close()


def _stream_is_usable(stream: Any) -> bool:
    if stream is None or getattr(stream, "closed", False):
        return False
    try:
        return bool(stream.writable()) if hasattr(stream, "writable") else hasattr(stream, "write")
    except (OSError, ValueError):
        return False


def ensure_standard_streams() -> None:
    """Give windowed PyInstaller processes writable streams for logging.

    PyInstaller's ``console=False`` bootloader can expose ``None`` as stdout
    and stderr when the process is started without redirected handles. Uvicorn
    resolves both streams while configuring its log handlers, so they must be
    valid before importing/configuring Uvicorn.
    """
    global _STDIO_FALLBACK
    force_user_log = os.getenv("FUELOPT_CAPTURE_STDIO") == "1"
    stdout_ok = _stream_is_usable(sys.stdout)
    stderr_ok = _stream_is_usable(sys.stderr)
    if not force_user_log and stdout_ok and stderr_ok:
        return
    if not force_user_log and (stdout_ok or stderr_ok):
        usable = sys.stdout if stdout_ok else sys.stderr
        if not stdout_ok:
            sys.stdout = usable
        if not stderr_ok:
            sys.stderr = usable
        return
    if _STDIO_FALLBACK is None:
        try:
            _STDIO_FALLBACK = _RotatingTextStream(REPORT_DIR / "launcher_console.log")
        except OSError:
            fallback_path = Path(tempfile.gettempdir()) / "FuelOpt" / "launcher_console.log"
            try:
                _STDIO_FALLBACK = _RotatingTextStream(fallback_path)
            except OSError:
                system_stream = sys.__stderr__ if _stream_is_usable(sys.__stderr__) else sys.__stdout__
                _STDIO_FALLBACK = system_stream if _stream_is_usable(system_stream) else open(os.devnull, "w", encoding="utf-8")
        atexit.register(_STDIO_FALLBACK.close)
    if force_user_log or not stdout_ok:
        sys.stdout = _STDIO_FALLBACK
    if force_user_log or not stderr_ok:
        sys.stderr = _STDIO_FALLBACK


def log_runtime_state(stage: str) -> None:
    state = {
        "stage": stage,
        "pid": os.getpid(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "stdin_none": sys.stdin is None,
        "stdout_none": sys.stdout is None,
        "stderr_none": sys.stderr is None,
    }
    if os.getenv("FUELOPT_DIAGNOSTICS") == "1":
        state.update(
            cwd=str(Path.cwd()),
            executable=sys.executable,
            bundle_root=str(getattr(sys, "_MEIPASS", "")),
        )
    log("runtime " + json.dumps(state, ensure_ascii=False))


def diagnostic_log(message: str) -> None:
    if os.getenv("FUELOPT_DIAGNOSTICS") == "1":
        log(message)


def configure_logging() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if LOGGER.handlers:
        return
    handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def log(message: str) -> None:
    configure_logging()
    LOGGER.info(message)


def self_command(*args: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve()), *args]


def creation_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def managed_env() -> dict[str, str]:
    env = os.environ.copy()
    env["FUELOPT_PROJECT_ROOT"] = str(ROOT)
    if getattr(sys, "frozen", False):
        # A self-spawned frozen child is an independent PyInstaller process.
        # Resetting its environment is required by PyInstaller for both the
        # legacy one-file fallback and the onedir launcher.
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def request_json(method: str, url: str, timeout: int = 10) -> dict[str, Any]:
    request = urllib.request.Request(url, method=method)
    if method.upper() == "POST":
        request.add_header("Content-Type", "application/json")
        data = b"{}"
    else:
        data = None
    with urllib.request.urlopen(request, data=data, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def server_ready(base_url: str) -> bool:
    try:
        payload = request_json("GET", f"{base_url}/health", timeout=3)
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False
    return payload.get("status") == "ok" and payload.get("service") == "FuelOpt"


def wait_for_server(
    base_url: str,
    timeout_sec: int = HEALTH_TIMEOUT_SEC,
    process: subprocess.Popen[Any] | None = None,
) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if server_ready(base_url):
            return True
        if process is not None and process.poll() is not None:
            return False
        time.sleep(0.5)
    return False


def port_is_free(port: int, host: str = DEFAULT_HOST) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind((host, port))
        return True
    except OSError:
        return False


def select_launcher_port(
    requested_port: int,
    *,
    max_port: int = 8010,
    ready_check=server_ready,
    free_check=port_is_free,
) -> tuple[int, bool]:
    for port in range(requested_port, max_port + 1):
        if ready_check(f"http://127.0.0.1:{port}"):
            return port, True
        if free_check(port):
            return port, False
    raise RuntimeError(f"no available FuelOpt port in range {requested_port}-{max_port}")


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            exit_code = ctypes.c_uint32()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _launcher_lock_is_stale(lock_path: Path) -> bool:
    try:
        text = lock_path.read_text(encoding="utf-8-sig").lstrip("\ufeff").strip()
        age = time.time() - lock_path.stat().st_mtime
    except (FileNotFoundError, OSError):
        return False
    match = re.fullmatch(r"pid\s*=\s*(\d+)", text, flags=re.IGNORECASE)
    if match is not None:
        return not _process_is_running(int(match.group(1)))
    # A newly-created lock may be observed before its owner writes the PID.
    # Give partial/corrupt content a short grace period, then recover it.
    return age >= CORRUPT_LOCK_GRACE_SEC


def _try_acquire_os_lock(fd: int) -> bool:
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _release_os_lock(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def launcher_start_lock(timeout_sec: float = 15.0):
    APP_PATHS.cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = APP_PATHS.cache_dir / "launcher-start.lock"
    deadline = time.monotonic() + timeout_sec
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    if os.fstat(fd).st_size == 0:
        os.write(fd, b"\0")
    while not _try_acquire_os_lock(fd):
        if time.monotonic() >= deadline:
            os.close(fd)
            raise RuntimeError("timed out waiting for launcher startup lock")
        time.sleep(0.1)
    try:
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, f"pid={os.getpid()}\n".encode("utf-8"))
        os.fsync(fd)
        yield
    finally:
        try:
            _release_os_lock(fd)
        finally:
            os.close(fd)
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            # A waiting launcher may already have the file open. It will
            # remove the persistent lock file when its own critical section ends.
            pass


def start_server(host: str, port: int) -> subprocess.Popen[Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    env = managed_env()
    env["FUELOPT_CAPTURE_STDIO"] = "1"
    process = subprocess.Popen(
        self_command("--server-only", "--host", host, "--port", str(port)),
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creation_flags(),
    )
    log(f"server process requested host={host} port={port} pid={process.pid}")
    return process


def stop_child_process(process: subprocess.Popen[Any], timeout_sec: float = 5.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_sec)


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return DEFAULT_BROWSER_HOST


def browser_base_url(browser_host: str, port: int) -> str:
    host = lan_ip() if browser_host == "lan" else browser_host
    return f"http://{host}:{port}"


def allow_lan_from_env() -> bool:
    value = os.getenv("FUELOPT_ALLOW_LAN", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def resolve_bind_host(requested_host: str, lan: bool = False) -> str:
    if requested_host != DEFAULT_HOST:
        return requested_host
    if lan or allow_lan_from_env():
        return LAN_HOST
    return requested_host


def refresh_direct(*, silent: bool = False) -> int:
    from app.catalog.refresh_service import RefreshRequest, run_catalog_refresh

    log("direct refresh started")
    result = run_catalog_refresh(RefreshRequest.from_settings(source="auto"))
    status = result.report.get("refresh_status")
    log(f"direct refresh finished status={status} exit_code={result.exit_code}")
    if not silent:
        print(json.dumps(result.report, ensure_ascii=False, indent=2))
    return result.exit_code


def start_refresh_worker() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    env = managed_env()
    env["FUELOPT_CAPTURE_STDIO"] = "1"
    subprocess.Popen(
        self_command("--refresh-direct", "--silent"),
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creation_flags(),
    )
    log("direct background refresh process requested")


def scheduler_command() -> tuple[Path, str]:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve(), "--refresh-direct --silent"
    script = Path(__file__).resolve()
    arguments = subprocess.list2cmdline([str(script), "--refresh-direct", "--silent"])
    return Path(sys.executable).resolve(), arguments


def configure_refresh(interval: str, scheduler: TaskScheduler | None = None) -> int:
    try:
        current = load_user_config(APP_PATHS.config_path)
    except UserConfigError:
        # This is an explicit repair action, so replacing an invalid config is
        # intentional rather than an implicit startup rewrite.
        current = UserConfig()
    try:
        selected = RefreshInterval(interval).value
    except ValueError as exc:
        log(f"refresh configuration rejected: {exc}")
        return 2
    command, arguments = scheduler_command()
    scheduler_instance = scheduler or TaskScheduler(paths=APP_PATHS)
    try:
        scheduler_instance.configure(
            interval=selected,
            command=command,
            arguments=arguments,
            working_directory=APP_PATHS.install_root,
        )
    except SchedulerError as exc:
        log(f"refresh task configuration failed: {exc}")
        return 7
    try:
        save_user_config(APP_PATHS.config_path, replace(current, refresh_interval=selected))
    except OSError as exc:
        try:
            scheduler_instance.configure(
                interval=current.refresh_interval,
                command=command,
                arguments=arguments,
                working_directory=APP_PATHS.install_root,
            )
        except SchedulerError:
            pass
        log(f"refresh config write failed: {exc.__class__.__name__}")
        return 6
    log(f"refresh interval configured interval={selected}")
    return 0


def remove_refresh_task(scheduler: TaskScheduler | None = None) -> int:
    try:
        result = (scheduler or TaskScheduler(paths=APP_PATHS)).remove()
    except SchedulerError as exc:
        log(f"refresh task removal failed: {exc}")
        return 7
    try:
        current = load_user_config(APP_PATHS.config_path)
    except UserConfigError:
        current = UserConfig()
    try:
        save_user_config(
            APP_PATHS.config_path,
            replace(current, refresh_interval=RefreshInterval.MANUAL.value),
        )
    except OSError as exc:
        log(f"refresh config write failed after task removal: {exc.__class__.__name__}")
        return 6
    log(f"refresh task removal action={result.action}")
    return 0


def show_settings() -> int:
    try:
        config = load_user_config(APP_PATHS.config_path)
    except UserConfigError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    from app.config import load_settings

    ors_configured = bool(load_settings().ors_api_key)
    print(
        json.dumps(
            {
                "schema_version": config.schema_version,
                "refresh_interval": config.refresh_interval,
                "ors_configured": ors_configured,
                "user_data_root": str(APP_PATHS.user_root),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def set_ors_key() -> int:
    try:
        secret = getpass.getpass("ORS_API_KEY: ").strip()
        if not secret:
            return 2
        default_credential_store().write(ORS_CREDENTIAL_TARGET, secret)
    except (CredentialStoreError, EOFError, KeyboardInterrupt) as exc:
        log(f"ORS credential write failed: {exc.__class__.__name__}")
        return 2
    log("ORS credential configured")
    return 0


def clear_ors_key() -> int:
    try:
        default_credential_store().delete(ORS_CREDENTIAL_TARGET)
    except CredentialStoreError as exc:
        log(f"ORS credential removal failed: {exc.__class__.__name__}")
        return 2
    log("ORS credential removed")
    return 0


def shutdown_existing() -> int:
    expected = APP_PATHS.install_root / "FuelOpt.exe" if getattr(sys, "frozen", False) else current_process_path()
    try:
        action = request_existing_shutdown(APP_PATHS, expected)
    except ShutdownError as exc:
        log(f"shutdown existing failed: {exc}")
        return 9
    log(f"shutdown existing action={action}")
    return 0


def run_server(host: str, port: int) -> int:
    ensure_standard_streams()
    os.environ["FUELOPT_PROJECT_ROOT"] = str(ROOT)
    os.chdir(ROOT)
    log_runtime_state("server_runtime_configured")
    log(f"server initialization started host={host} port={port}")
    shutdown_event: ShutdownEvent | None = None
    try:
        log("user data bootstrap starting")
        from app.bootstrap import bootstrap_user_data

        bootstrap = bootstrap_user_data(APP_PATHS)
        log(
            "user data bootstrap completed "
            f"database_action={bootstrap.database_action} snapshot_action={bootstrap.snapshot_action}"
        )
        diagnostic_log("uvicorn import starting")
        import uvicorn
        diagnostic_log("uvicorn import completed")
        diagnostic_log("app.api.main import starting")
        from app.api.main import app

        diagnostic_log("app.api.main import completed")

        diagnostic_log("uvicorn.Config creation starting")
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            workers=1,
            reload=False,
            loop="asyncio",
            http="h11",
            lifespan="on",
            log_level="debug" if os.getenv("FUELOPT_DIAGNOSTICS") == "1" else "info",
            access_log=os.getenv("FUELOPT_DIAGNOSTICS") == "1",
        )
        diagnostic_log("uvicorn.Config creation completed loop=asyncio http=h11 lifespan=on workers=1 reload=false")

        class InstrumentedServer(uvicorn.Server):
            async def startup(self, sockets: list[socket.socket] | None = None) -> None:
                diagnostic_log("uvicorn startup/lifespan and socket binding starting")
                await super().startup(sockets=sockets)
                bound = []
                for active_server in self.servers:
                    for active_socket in active_server.sockets or []:
                        bound.append(str(active_socket.getsockname()))
                log(f"server listening sockets={bound}")

        diagnostic_log("uvicorn.Server creation starting")
        server = InstrumentedServer(config)
        diagnostic_log("uvicorn.Server creation completed")
        shutdown_event = ShutdownEvent.create(APP_PATHS)
        write_runtime_record(APP_PATHS, shutdown_event, port)

        async def serve() -> None:
            loop = asyncio.get_running_loop()
            diagnostic_log(f"event loop created type={type(loop).__name__}")
            diagnostic_log("server.serve starting")
            watcher = asyncio.create_task(asyncio.to_thread(shutdown_event.wait))
            server_task = asyncio.create_task(server.serve())
            done, _ = await asyncio.wait({watcher, server_task}, return_when=asyncio.FIRST_COMPLETED)
            if watcher in done and not server_task.done():
                log("cooperative shutdown requested")
                server.should_exit = True
            await server_task
            if not watcher.done():
                shutdown_event.set()
            await watcher
            diagnostic_log("server.serve returned")

        diagnostic_log("asyncio.run starting")
        asyncio.run(serve())
        diagnostic_log("asyncio.run returned")
    except BaseException:
        configure_logging()
        LOGGER.exception("server failed")
        raise
    finally:
        if shutdown_event is not None:
            remove_runtime_record(APP_PATHS, os.getpid())
            shutdown_event.close()
    return 0


def run_launcher(args: argparse.Namespace) -> int:
    os.environ["FUELOPT_PROJECT_ROOT"] = str(ROOT)
    try:
        with launcher_start_lock():
            next_port = args.port
            while True:
                port, existing_server = select_launcher_port(next_port)
                args.port = port
                base_url = f"http://127.0.0.1:{port}"
                if existing_server:
                    log("existing FuelOpt server is already healthy")
                    break
                process = start_server(args.host, port)
                if wait_for_server(base_url, process=process):
                    break
                stop_child_process(process)
                raced_with_foreign_service = not port_is_free(port) and not server_ready(base_url)
                if raced_with_foreign_service and port < 8010:
                    log(f"port race detected port={port}; retrying")
                    next_port = port + 1
                    continue
                log(f"server failed before becoming healthy port={port} exit_code={process.poll()}")
                return 8
    except RuntimeError as exc:
        log(f"launcher startup failed: {exc}")
        return 8

    if not args.no_browser:
        url = browser_base_url(args.browser_host, args.port)
        webbrowser.open(url)
        log(f"browser opened url={url}")

    try:
        refresh_interval = load_user_config(APP_PATHS.config_path).refresh_interval
    except UserConfigError as exc:
        log(f"invalid user config: {exc}")
        return 2
    if not args.no_refresh and refresh_interval == RefreshInterval.ON_OPEN.value:
        start_refresh_worker()

    return 0


def parse_args() -> argparse.Namespace:
    diagnostic_log("argument parsing starting")
    parser = argparse.ArgumentParser(description="FuelOpt local launcher.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server bind host. Defaults to localhost.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port.")
    parser.add_argument(
        "--browser-host",
        default=DEFAULT_BROWSER_HOST,
        help="Host opened in the browser. Use 'lan' to open this machine's LAN IP.",
    )
    parser.add_argument("--lan", action="store_true", help="Allow LAN access by binding the server to 0.0.0.0.")
    parser.add_argument("--no-browser", action="store_true", help="Start server without opening the browser.")
    parser.add_argument("--no-refresh", action="store_true", help="Do not request a background data refresh.")
    parser.add_argument("--configure-refresh", action="store_true", help="Configure the refresh policy.")
    parser.add_argument("--interval", choices=[item.value for item in RefreshInterval], help="Refresh interval.")
    parser.add_argument("--refresh-direct", action="store_true", help="Run the catalog refresh pipeline directly.")
    parser.add_argument("--remove-refresh-task", action="store_true", help="Remove the scheduled refresh task.")
    parser.add_argument("--show-settings", action="store_true", help="Show non-secret user settings.")
    parser.add_argument("--set-ors-key", action="store_true", help="Store ORS_API_KEY securely for the current user.")
    parser.add_argument("--clear-ors-key", action="store_true", help="Remove the stored ORS_API_KEY.")
    parser.add_argument("--shutdown-existing", action="store_true", help="Stop the installed FuelOpt server safely.")
    parser.add_argument("--silent", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--server-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--refresh-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--base-url", default=f"http://127.0.0.1:{DEFAULT_PORT}", help=argparse.SUPPRESS)
    args = parser.parse_args()
    lan_enabled = args.lan or allow_lan_from_env()
    args.host = resolve_bind_host(args.host, lan=args.lan)
    if lan_enabled and args.browser_host == DEFAULT_BROWSER_HOST:
        args.browser_host = "lan"
    diagnostic_log(f"argument parsing completed server_only={args.server_only} host={args.host} port={args.port}")
    return args


def main() -> int:
    diagnostic_log("main entered")
    if "--catalog-refresh-script" in sys.argv:
        marker_index = sys.argv.index("--catalog-refresh-script")
        sys.argv = [sys.argv[0], *sys.argv[marker_index + 1:]]
        from scripts.refresh_catalog import main as refresh_catalog_main

        return refresh_catalog_main()

    args = parse_args()
    if args.configure_refresh:
        if not args.interval:
            return 2
        return configure_refresh(args.interval)
    if args.remove_refresh_task:
        return remove_refresh_task()
    if args.show_settings:
        return show_settings()
    if args.set_ors_key:
        return set_ors_key()
    if args.clear_ors_key:
        return clear_ors_key()
    if args.shutdown_existing:
        return shutdown_existing()
    if args.server_only:
        diagnostic_log("server-only dispatch entered")
        return run_server(args.host, args.port)
    if args.refresh_direct or args.refresh_only:
        return refresh_direct(silent=args.silent)
    return run_launcher(args)


if __name__ == "__main__":
    ensure_standard_streams()
    log_runtime_state("entry_point_entered")
    raise SystemExit(main())
