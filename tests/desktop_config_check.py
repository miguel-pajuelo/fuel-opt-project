from __future__ import annotations

import io
import json
import logging
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.legacy_migration import find_legacy_root, migrate_legacy_ors_credential
from app.paths import resolve_app_paths
from app.user_config import RefreshInterval, UserConfig, UserConfigError, load_user_config, save_user_config
from app.windows_credentials import (
    ORS_CREDENTIAL_TARGET,
    CredentialStoreError,
    SecretRedactionFilter,
    WindowsCredentialStore,
    install_secret_redaction,
    resolve_ors_api_key,
)


SECRET = "patch2-ors-secret-SENTINEL"


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


class MemoryCredentialStore:
    def __init__(self, *, fail_write: bool = False) -> None:
        self.values: dict[str, str] = {}
        self.fail_write = fail_write

    def read(self, target: str) -> str | None:
        return self.values.get(target)

    def write(self, target: str, secret: str, *, username: str = "FuelOpt") -> None:
        if self.fail_write:
            raise CredentialStoreError("simulated write failure")
        self.values[target] = secret

    def delete(self, target: str) -> bool:
        return self.values.pop(target, None) is not None


def test_app_paths_are_separate_and_side_effect_free() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        project = base / "source tree"
        module_file = project / "app" / "paths.py"
        local = base / "Local App Data"
        env = {"LOCALAPPDATA": str(local)}
        paths = resolve_app_paths(environ=env, module_file=module_file, frozen=False)
        _assert(paths.resource_root == project.resolve(), paths)
        _assert(paths.install_root == project.resolve(), paths)
        _assert(paths.user_root == (local / "FuelOpt").resolve(), paths)
        _assert(paths.config_path == paths.user_root / "config.json", paths)
        _assert(paths.user_db_path == paths.user_root / "data" / "db" / "gas_stations.sqlite", paths)
        _assert(paths.legacy_db_path == project.resolve() / "data" / "db" / "gas_stations.sqlite", paths)
        _assert(not paths.user_root.exists(), "path resolution must not create user directories")


def test_explicit_roots_and_frozen_install_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        resource = base / "bundle resources"
        user = base / "profile"
        executable = base / "Programs" / "FuelOpt" / "FuelOpt.exe"
        paths = resolve_app_paths(
            environ={"FUELOPT_PROJECT_ROOT": str(resource), "FUELOPT_USER_DATA_ROOT": str(user)},
            executable=executable,
            frozen=True,
        )
        _assert(paths.resource_root == resource.resolve(), paths)
        _assert(paths.install_root == executable.resolve().parent, paths)
        _assert(paths.user_root == user.resolve(), paths)


def test_user_config_roundtrip_is_atomic_and_contains_no_secret() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nested" / "config.json"
        config = UserConfig(refresh_interval=RefreshInterval.EIGHT_HOURS.value, ors_credential_migrated=True)
        save_user_config(path, config)
        _assert(load_user_config(path) == config, path.read_text(encoding="utf-8"))
        text = path.read_text(encoding="utf-8")
        _assert(SECRET not in text and "ORS_API_KEY" not in text, text)
        _assert(not list(path.parent.glob("*.tmp")), "atomic config temp file was left behind")


def test_invalid_config_is_rejected_without_rewrite() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        original = '{"schema_version":1,"refresh_interval":"7h"}'
        path.write_text(original, encoding="utf-8")
        try:
            load_user_config(path)
        except UserConfigError:
            pass
        else:
            raise AssertionError("invalid refresh interval should be rejected")
        _assert(path.read_text(encoding="utf-8") == original, "invalid config was rewritten")


def test_credential_precedence_and_environment_fallback() -> None:
    store = MemoryCredentialStore()
    store.values[ORS_CREDENTIAL_TARGET] = "credential-value"
    _assert(
        resolve_ors_api_key(environ={"ORS_API_KEY": "environment-value"}, store=store) == "credential-value",
        "Credential Manager should take precedence",
    )
    store.values.clear()
    _assert(
        resolve_ors_api_key(environ={"ORS_API_KEY": "environment-value"}, store=store) == "environment-value",
        "environment fallback should remain available",
    )
    _assert(resolve_ors_api_key(environ={"ORS_API_KEY": "replace-me"}, store=store) is None, "placeholder accepted")


def test_legacy_env_migration_is_verified_and_does_not_rewrite_env() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        legacy = base / "legacy"
        legacy.mkdir()
        env_path = legacy / ".env"
        original = f"ORS_API_KEY={SECRET}\nGMAIL_USER=legacy@example.com\n"
        env_path.write_text(original, encoding="utf-8")
        paths = resolve_app_paths(
            environ={"FUELOPT_PROJECT_ROOT": str(legacy), "FUELOPT_USER_DATA_ROOT": str(base / "user")},
            module_file=legacy / "app" / "paths.py",
            frozen=False,
        )
        store = MemoryCredentialStore()
        result = migrate_legacy_ors_credential(paths, explicit_root=legacy, environ={}, store=store)
        _assert(result.status == "migrated", result)
        _assert(store.values[ORS_CREDENTIAL_TARGET] == SECRET, "credential was not imported")
        _assert(env_path.read_text(encoding="utf-8") == original, "legacy .env was modified")
        config_text = paths.config_path.read_text(encoding="utf-8")
        _assert(SECRET not in config_text and "ORS_API_KEY" not in config_text, config_text)
        _assert(json.loads(config_text)["ors_credential_migrated"] is True, config_text)
        _assert(SECRET not in repr(result), "migration result leaked secret")


def test_failed_credential_migration_writes_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        legacy = base / "legacy"
        legacy.mkdir()
        (legacy / ".env").write_text(f"ORS_API_KEY={SECRET}\n", encoding="utf-8")
        paths = resolve_app_paths(
            environ={"FUELOPT_PROJECT_ROOT": str(legacy), "FUELOPT_USER_DATA_ROOT": str(base / "user")},
            module_file=legacy / "app" / "paths.py",
            frozen=False,
        )
        result = migrate_legacy_ors_credential(
            paths,
            explicit_root=legacy,
            environ={},
            store=MemoryCredentialStore(fail_write=True),
        )
        _assert(result.status == "write_failed", result)
        _assert(not paths.config_path.exists(), "config should not be created after credential failure")
        _assert(SECRET not in repr(result), "failure result leaked secret")


def test_legacy_root_detection_is_bounded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        legacy = base / "FuelOptApp"
        legacy.mkdir()
        (legacy / ".env").write_text("ORS_API_KEY=replace-me\n", encoding="utf-8")
        paths = resolve_app_paths(
            environ={"FUELOPT_PROJECT_ROOT": str(base), "FUELOPT_USER_DATA_ROOT": str(base / "user")},
            module_file=base / "app" / "paths.py",
            frozen=False,
        )
        _assert(find_legacy_root(paths, environ={}) == legacy.resolve(), "expected bounded FuelOptApp detection")


def test_logging_filter_redacts_message_and_arguments() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("fuelopt.patch2.secret-test")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    install_secret_redaction(logger, SECRET)
    logger.info("key=%s payload=%s", SECRET, {"token": SECRET})
    output = stream.getvalue()
    _assert(SECRET not in output, output)
    _assert(output.count("[REDACTED]") == 2, output)
    logger.handlers.clear()


def test_logging_filter_redacts_exception_traceback() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("fuelopt.patch2.exception-secret-test")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.ERROR)
    logger.addHandler(handler)
    install_secret_redaction(logger, SECRET)
    try:
        raise RuntimeError(f"provider rejected key {SECRET}")
    except RuntimeError:
        logger.exception("credential provider failure")
    output = stream.getvalue()
    _assert(SECRET not in output, output)
    _assert("[REDACTED]" in output, output)
    logger.handlers.clear()


def test_redaction_filter_accepts_empty_secret() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "ordinary", (), None)
    _assert(SecretRedactionFilter(None).filter(record) is True, "empty filter should be a no-op")


def test_real_windows_credential_manager_opt_in() -> None:
    if os.getenv("FUELOPT_TEST_WINDOWS_CREDENTIAL_MANAGER") != "1":
        return
    target = "FuelOpt/Test/ORS_API_KEY"
    store = WindowsCredentialStore()
    try:
        store.write(target, SECRET)
        _assert(store.read(target) == SECRET, "real Credential Manager roundtrip failed")
        _assert(store.delete(target) is True, "real Credential Manager delete failed")
        _assert(store.read(target) is None, "test credential still exists")
    finally:
        try:
            store.delete(target)
        except CredentialStoreError:
            pass


def run() -> None:
    test_app_paths_are_separate_and_side_effect_free()
    test_explicit_roots_and_frozen_install_path()
    test_user_config_roundtrip_is_atomic_and_contains_no_secret()
    test_invalid_config_is_rejected_without_rewrite()
    test_credential_precedence_and_environment_fallback()
    test_legacy_env_migration_is_verified_and_does_not_rewrite_env()
    test_failed_credential_migration_writes_nothing()
    test_legacy_root_detection_is_bounded()
    test_logging_filter_redacts_message_and_arguments()
    test_logging_filter_redacts_exception_traceback()
    test_redaction_filter_accepts_empty_secret()
    test_real_windows_credential_manager_opt_in()
    print("OK: desktop paths, config and credential checks passed")


if __name__ == "__main__":
    run()
