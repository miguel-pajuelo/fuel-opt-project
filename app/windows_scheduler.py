from __future__ import annotations

import ctypes
import html
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from app.paths import APP_PATHS, AppPaths
from app.user_config import RefreshInterval


TASK_NAME = "FuelOpt Catalog Refresh"
TASK_URI = rf"\{TASK_NAME}"
INTERVAL_DURATIONS = {
    RefreshInterval.ONE_HOUR.value: "PT1H",
    RefreshInterval.TWO_HOURS.value: "PT2H",
    RefreshInterval.FOUR_HOURS.value: "PT4H",
    RefreshInterval.EIGHT_HOURS.value: "PT8H",
    RefreshInterval.TWELVE_HOURS.value: "PT12H",
    RefreshInterval.TWENTY_FOUR_HOURS.value: "PT24H",
}
INTERVAL_DELTAS = {
    RefreshInterval.ONE_HOUR.value: timedelta(hours=1),
    RefreshInterval.TWO_HOURS.value: timedelta(hours=2),
    RefreshInterval.FOUR_HOURS.value: timedelta(hours=4),
    RefreshInterval.EIGHT_HOURS.value: timedelta(hours=8),
    RefreshInterval.TWELVE_HOURS.value: timedelta(hours=12),
    RefreshInterval.TWENTY_FOUR_HOURS.value: timedelta(hours=24),
}


class SchedulerError(RuntimeError):
    pass


@dataclass(frozen=True)
class SchedulerResult:
    action: str
    task_name: str = TASK_NAME


@dataclass(frozen=True)
class TaskAction:
    command: str
    arguments: str


def _task_action(xml: str) -> TaskAction:
    try:
        root = ET.fromstring(xml.lstrip("\ufeff\x00 \t\r\n"))
    except ET.ParseError as exc:
        raise SchedulerError("the existing FuelOpt task has invalid XML") from exc

    def value(name: str) -> str:
        node = root.find(f".//{{*}}{name}")
        return (node.text or "").strip() if node is not None else ""

    return TaskAction(command=value("Command"), arguments=value("Arguments"))


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left).strip().strip('"'))) == os.path.normcase(
        os.path.abspath(str(right).strip().strip('"'))
    )


def _is_managed_task(xml: str, command: Path, arguments: str) -> bool:
    action = _task_action(xml)
    return _same_path(action.command, command) and action.arguments == arguments


def _is_legacy_task(xml: str) -> bool:
    action = _task_action(xml)
    command_name = Path(action.command.strip().strip('"')).name.casefold()
    normalized_arguments = action.arguments.casefold().replace("/", "\\")
    return command_name in {"cmd.exe", "cmd", "run_refresh_catalog.cmd"} and (
        command_name == "run_refresh_catalog.cmd" or "run_refresh_catalog.cmd" in normalized_arguments
    )


def _current_user_sid() -> str:
    if sys.platform != "win32":
        raise SchedulerError("Task Scheduler is only available on Windows")

    token_query = 0x0008
    token_user_class = 1
    error_insufficient_buffer = 122
    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]

    class TOKEN_USER(ctypes.Structure):
        _fields_ = [("User", SID_AND_ATTRIBUTES)]

    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), token_query, ctypes.byref(token)):
        raise SchedulerError(f"OpenProcessToken failed: {ctypes.get_last_error()}")
    try:
        required = wintypes.DWORD()
        advapi32.GetTokenInformation(token, token_user_class, None, 0, ctypes.byref(required))
        if ctypes.get_last_error() != error_insufficient_buffer or required.value <= 0:
            raise SchedulerError(f"GetTokenInformation size failed: {ctypes.get_last_error()}")
        buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token,
            token_user_class,
            buffer,
            required,
            ctypes.byref(required),
        ):
            raise SchedulerError(f"GetTokenInformation failed: {ctypes.get_last_error()}")
        token_user = ctypes.cast(buffer, ctypes.POINTER(TOKEN_USER)).contents
        sid_text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(token_user.User.Sid, ctypes.byref(sid_text)):
            raise SchedulerError(f"ConvertSidToStringSidW failed: {ctypes.get_last_error()}")
        try:
            return str(sid_text.value)
        finally:
            kernel32.LocalFree(sid_text)
    finally:
        kernel32.CloseHandle(token)


def task_start_boundary(interval: str, now: datetime | None = None) -> str:
    if interval not in INTERVAL_DELTAS:
        raise ValueError(f"interval does not create a scheduled task: {interval}")
    current = (now or datetime.now().astimezone()).astimezone()
    start = (current + INTERVAL_DELTAS[interval]).replace(microsecond=0)
    return start.isoformat()


def render_task_xml(
    *,
    interval: str,
    user_sid: str,
    command: Path,
    arguments: str,
    working_directory: Path,
    now: datetime | None = None,
) -> str:
    duration = INTERVAL_DURATIONS.get(interval)
    if duration is None:
        raise ValueError(f"interval does not create a scheduled task: {interval}")
    start_boundary = task_start_boundary(interval, now=now)
    esc = lambda value: html.escape(str(value), quote=True)
    return f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Actualiza de forma segura el catálogo local de FuelOpt.</Description>
    <URI>{esc(TASK_URI)}</URI>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>{duration}</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>{esc(start_boundary)}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="CurrentUser">
      <UserId>{esc(user_sid)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT45M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="CurrentUser">
    <Exec>
      <Command>{esc(command)}</Command>
      <Arguments>{esc(arguments)}</Arguments>
      <WorkingDirectory>{esc(working_directory)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
'''


Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _default_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, errors="replace")


class TaskScheduler:
    def __init__(self, *, paths: AppPaths = APP_PATHS, runner: Runner | None = None) -> None:
        self.paths = paths
        self.runner = runner or _default_runner

    def _query_xml(self) -> str | None:
        completed = self.runner(["schtasks.exe", "/Query", "/TN", TASK_NAME, "/XML"])
        return completed.stdout if completed.returncode == 0 and completed.stdout.strip() else None

    def _write_temp_xml(self, xml: str, name: str) -> Path:
        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.paths.cache_dir / name
        path.write_text(xml, encoding="utf-16")
        return path

    def remove(self, *, command: Path, arguments: str) -> SchedulerResult:
        old_xml = self._query_xml()
        if old_xml is None:
            return SchedulerResult("absent")
        if not (_is_managed_task(old_xml, command, arguments) or _is_legacy_task(old_xml)):
            raise SchedulerError("refusing to remove an unrecognized task with the FuelOpt task name")
        completed = self.runner(["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"])
        if completed.returncode != 0:
            raise SchedulerError(completed.stderr.strip() or completed.stdout.strip() or "could not delete task")
        return SchedulerResult("removed")

    def configure(
        self,
        *,
        interval: str,
        command: Path,
        arguments: str,
        working_directory: Path,
        user_sid: str | None = None,
        now: datetime | None = None,
    ) -> SchedulerResult:
        if interval in {RefreshInterval.ON_OPEN.value, RefreshInterval.MANUAL.value}:
            return self.remove(command=command, arguments=arguments)

        old_xml = self._query_xml()
        if old_xml and not (_is_managed_task(old_xml, command, arguments) or _is_legacy_task(old_xml)):
            raise SchedulerError("refusing to replace an unrecognized task with the FuelOpt task name")

        xml = render_task_xml(
            interval=interval,
            user_sid=user_sid or _current_user_sid(),
            command=command,
            arguments=arguments,
            working_directory=working_directory,
            now=now,
        )
        temp_xml = self._write_temp_xml(xml, "fuelopt-refresh-task.xml")
        try:
            completed = self.runner(["schtasks.exe", "/Create", "/TN", TASK_NAME, "/XML", str(temp_xml), "/F"])
            error = completed.stderr.strip() or completed.stdout.strip() or "could not create task"
            installed_xml = self._query_xml() if completed.returncode == 0 else None
            if installed_xml and _is_managed_task(installed_xml, command, arguments):
                return SchedulerResult("updated" if old_xml else "created")

            if old_xml is not None:
                restore_xml = self._write_temp_xml(old_xml, "fuelopt-refresh-task-restore.xml")
                try:
                    restored = self.runner(["schtasks.exe", "/Create", "/TN", TASK_NAME, "/XML", str(restore_xml), "/F"])
                    if restored.returncode != 0:
                        raise SchedulerError("new task failed and the previous task could not be restored")
                finally:
                    restore_xml.unlink(missing_ok=True)
            elif installed_xml is not None:
                self.runner(["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"])
            raise SchedulerError(error if completed.returncode else "created task failed verification")
        finally:
            temp_xml.unlink(missing_ok=True)
