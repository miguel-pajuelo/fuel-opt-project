from __future__ import annotations

import sys
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import installer_check
import refresh_scheduler_check
import windows_shutdown_check


def test_shutdown_absent_and_stale_contract() -> None:
    windows_shutdown_check.test_absent_and_stale_runtime_are_idempotent()


def test_shutdown_owned_process_contract() -> None:
    windows_shutdown_check.test_installed_process_is_signaled_and_stopped_cooperatively()


def test_shutdown_foreign_process_contract() -> None:
    windows_shutdown_check.test_development_and_portable_processes_are_foreign_and_untouched()


def test_shutdown_incoherent_runtime_contract() -> None:
    windows_shutdown_check.test_incoherent_or_invalid_live_runtime_fails_without_signaling()


def test_shutdown_timeout_contract() -> None:
    windows_shutdown_check.test_owned_process_timeout_remains_an_error()


def test_remove_refresh_task_identity_regression() -> None:
    refresh_scheduler_check.test_remove_refresh_task_identity_and_safety_regression()


def test_scheduler_task_ownership_contract() -> None:
    refresh_scheduler_check.test_scheduler_removes_only_managed_or_legacy_tasks()


def test_maintenance_cli_traceback_contract() -> None:
    refresh_scheduler_check.test_maintenance_cli_contains_unexpected_exceptions_without_traceback()


def test_installer_shutdown_exit_contract() -> None:
    installer_check._assert_uninstall_shutdown_exit_contract()
