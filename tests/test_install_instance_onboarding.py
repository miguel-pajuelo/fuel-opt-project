from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fuelopt_launcher as launcher
from app.user_config import UserConfig


INSTALL_ONE = "11111111-1111-4111-8111-111111111111"
INSTALL_TWO = "22222222-2222-4222-8222-222222222222"


@contextmanager
def _frozen_executable(path: Path):
    with (
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "executable", str(path)),
    ):
        yield


def test_launcher_generates_valid_uuid_atomically_and_reuses_it(tmp_path: Path) -> None:
    executable = tmp_path / "portable" / "FuelOpt.exe"
    executable.parent.mkdir(parents=True)
    replacements: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def replace(source: str | Path, target: str | Path) -> None:
        source_path = Path(source)
        target_path = Path(target)
        assert source_path.exists()
        assert source_path.parent == target_path.parent == executable.parent
        replacements.append((source_path, target_path))
        real_replace(source_path, target_path)

    with (
        _frozen_executable(executable),
        patch.object(launcher.uuid, "uuid4", return_value=uuid.UUID(INSTALL_ONE)),
        patch.object(launcher.os, "replace", side_effect=replace),
    ):
        first = launcher.install_instance_id()
        second = launcher.install_instance_id()

    assert first == second == INSTALL_ONE
    assert uuid.UUID(first).version == 4
    marker = executable.parent / launcher.INSTALL_INSTANCE_MARKER
    assert marker.read_text(encoding="utf-8") == f"{INSTALL_ONE}\n"
    assert len(replacements) == 1
    assert replacements[0][0] != marker and replacements[0][1] == marker


def test_reinstall_or_new_portable_folder_gets_a_new_identifier(tmp_path: Path) -> None:
    executable = tmp_path / "installed" / "FuelOpt.exe"
    executable.parent.mkdir(parents=True)
    marker = executable.parent / launcher.INSTALL_INSTANCE_MARKER

    with _frozen_executable(executable), patch.object(
        launcher.uuid,
        "uuid4",
        side_effect=[uuid.UUID(INSTALL_ONE), uuid.UUID(INSTALL_TWO)],
    ):
        assert launcher.install_instance_id() == INSTALL_ONE
        marker.unlink()
        assert launcher.install_instance_id() == INSTALL_TWO
        assert launcher.install_instance_id() == INSTALL_TWO


def test_invalid_marker_is_replaced_and_portable_folders_are_independent(tmp_path: Path) -> None:
    first_executable = tmp_path / "portable-one" / "FuelOpt.exe"
    second_executable = tmp_path / "portable-two" / "FuelOpt.exe"
    first_executable.parent.mkdir(parents=True)
    second_executable.parent.mkdir(parents=True)
    (first_executable.parent / launcher.INSTALL_INSTANCE_MARKER).write_text("true\n", encoding="utf-8")

    with patch.object(
        launcher.uuid,
        "uuid4",
        side_effect=[uuid.UUID(INSTALL_ONE), uuid.UUID(INSTALL_TWO)],
    ):
        with _frozen_executable(first_executable):
            assert launcher.install_instance_id() == INSTALL_ONE
            assert launcher.install_instance_id() == INSTALL_ONE
        with _frozen_executable(second_executable):
            assert launcher.install_instance_id() == INSTALL_TWO
            assert launcher.install_instance_id() == INSTALL_TWO


def test_marker_failures_fall_back_without_blocking_and_source_creates_nothing(tmp_path: Path) -> None:
    executable = tmp_path / "FuelOpt.exe"
    marker = tmp_path / launcher.INSTALL_INSTANCE_MARKER

    with _frozen_executable(executable), patch.object(Path, "read_text", side_effect=PermissionError("denied")):
        assert launcher.install_instance_id() is None
    assert not marker.exists()

    with _frozen_executable(executable), patch.object(launcher.os, "replace", side_effect=PermissionError("denied")):
        assert launcher.install_instance_id() is None
    assert not marker.exists()
    assert not list(tmp_path.glob(f".{launcher.INSTALL_INSTANCE_MARKER}.*.tmp"))

    with patch.object(sys, "frozen", False, create=True), patch.object(launcher.uuid, "uuid4") as generated:
        assert launcher.install_instance_id() is None
        generated.assert_not_called()
    assert not marker.exists()


def test_launcher_uses_fragment_for_id_and_never_logs_identifier() -> None:
    opened: list[str] = []
    messages: list[str] = []

    @contextmanager
    def no_lock():
        yield

    args = type(
        "Args",
        (),
        {"port": 8001, "host": "127.0.0.1", "no_browser": False, "browser_host": "127.0.0.1", "no_refresh": True},
    )()
    with (
        patch.object(launcher, "launcher_start_lock", no_lock),
        patch.object(launcher, "install_instance_id", return_value=INSTALL_ONE),
        patch.object(launcher, "select_launcher_port", return_value=(8001, True)),
        patch.object(launcher.webbrowser, "open", side_effect=lambda url: opened.append(url) or True),
        patch.object(launcher, "load_user_config", return_value=UserConfig()),
        patch.object(launcher, "log", side_effect=messages.append),
    ):
        assert launcher.run_launcher(args) == 0

    assert opened == [
        f"http://127.0.0.1:8001?fuelopt-ui={launcher.UI_CACHE_REVISION}"
        f"#fuelopt-install={INSTALL_ONE}"
    ]
    assert "?fuelopt-install=" not in opened[0]
    assert f"fuelopt-install={INSTALL_ONE}" not in urllib.parse.urlsplit(opened[0]).query
    assert all(INSTALL_ONE not in message for message in messages)
    assert launcher.browser_url_with_install_instance("http://127.0.0.1:8001", None) == (
        f"http://127.0.0.1:8001?fuelopt-ui={launcher.UI_CACHE_REVISION}"
    )


def _run_onboarding(
    *,
    fragment: str,
    stored: str | None,
    actions: list[str] | None = None,
    storage_failure: str = "",
    search: str = "",
) -> dict[str, object]:
    config = {
        "fragment": fragment,
        "stored": stored,
        "actions": actions or [],
        "storageFailure": storage_failure,
        "search": search,
    }
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const config = JSON.parse(process.argv[1]);
const source = fs.readFileSync('static/app.js', 'utf8');
const prefix = source.slice(0, source.indexOf('let refreshMessageTimer'));
const state = { openCount: 0, writes: [], replacements: [] };

function element() {
  return {
    open: false,
    listeners: {},
    addEventListener(type, listener) { this.listeners[type] = listener; },
    focus() {},
    showModal() { this.open = true; state.openCount += 1; },
    close() { this.open = false; },
  };
}

const elements = {
  quick_help_dialog: element(),
  quick_help_trigger: element(),
  quick_help_close: element(),
  quick_help_start: element(),
};
let storedValue = config.stored;
const localStorage = {
  getItem() {
    if (config.storageFailure === 'read' || config.storageFailure === 'both') throw new Error('unavailable');
    return storedValue;
  },
  setItem(_key, value) {
    if (config.storageFailure === 'write' || config.storageFailure === 'both') throw new Error('unavailable');
    storedValue = value;
    state.writes.push(value);
  },
};
const history = {
  state: null,
  replaceState(nextState, _title, url) { this.state = nextState; state.replacements.push(url); },
};
const document = {
  body: element(),
  activeElement: null,
  getElementById(id) { return elements[id]; },
};
document.activeElement = document.body;
const context = {
  URLSearchParams,
  document,
  history,
  localStorage,
  location: { hash: config.fragment, pathname: '/app', search: config.search },
  requestAnimationFrame(callback) { callback(); },
};
context.window = context;
vm.createContext(context);
vm.runInContext(prefix, context);

for (const action of config.actions) {
  if (action === 'trigger') elements.quick_help_trigger.listeners.click();
  if (action === 'close') elements.quick_help_close.listeners.click();
  if (action === 'start') elements.quick_help_start.listeners.click();
  if (action === 'cancel') elements.quick_help_dialog.listeners.cancel({ preventDefault() {} });
}
process.stdout.write(JSON.stringify({
  openCount: state.openCount,
  dialogOpen: elements.quick_help_dialog.open,
  stored: storedValue,
  writes: state.writes,
  replacements: state.replacements,
}));
"""
    completed = subprocess.run(
        ["node", "-e", harness, json.dumps(config)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_first_install_then_same_install_then_reinstall_onboarding() -> None:
    first = _run_onboarding(fragment=f"#fuelopt-install={INSTALL_ONE}", stored=None, actions=["close"])
    assert first["openCount"] == 1 and first["stored"] == INSTALL_ONE

    second = _run_onboarding(fragment=f"#fuelopt-install={INSTALL_ONE}", stored=INSTALL_ONE)
    assert second["openCount"] == 0

    reinstalled = _run_onboarding(fragment=f"#fuelopt-install={INSTALL_TWO}", stored=INSTALL_ONE)
    assert reinstalled["openCount"] == 1


def test_legacy_true_does_not_hide_current_install_and_automatic_close_saves_id() -> None:
    result = _run_onboarding(fragment=f"#fuelopt-install={INSTALL_ONE}", stored="true", actions=["start"])
    assert result["openCount"] == 1
    assert result["writes"] == [INSTALL_ONE]
    assert result["stored"] == INSTALL_ONE


def test_manual_quick_help_does_not_change_preference() -> None:
    result = _run_onboarding(
        fragment=f"#fuelopt-install={INSTALL_ONE}",
        stored=INSTALL_ONE,
        actions=["trigger", "close"],
    )
    assert result["openCount"] == 1
    assert result["writes"] == []
    assert result["stored"] == INSTALL_ONE


def test_fragment_is_removed_without_placing_identifier_in_query() -> None:
    result = _run_onboarding(
        fragment=f"#fuelopt-install={INSTALL_ONE}",
        stored=INSTALL_ONE,
        search="?existing=1",
    )
    assert result["replacements"] == ["/app?existing=1"]
    assert INSTALL_ONE not in str(result["replacements"])


def test_source_fallback_keeps_true_and_storage_failures_do_not_block() -> None:
    dismissed_source = _run_onboarding(fragment="", stored="true")
    assert dismissed_source["openCount"] == 0

    first_source = _run_onboarding(fragment="", stored=None, actions=["close"])
    assert first_source["openCount"] == 1 and first_source["stored"] == "true"

    unavailable = _run_onboarding(fragment=f"#fuelopt-install={INSTALL_ONE}", stored=None, actions=["close"], storage_failure="both")
    assert unavailable["openCount"] == 1
