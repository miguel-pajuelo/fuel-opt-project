"""Static contract checks for the tag-driven Windows release workflow."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-release.yml"
sys.path.insert(0, str(ROOT))

from scripts.check_release_license import evaluate_gate, validate_license
from scripts.generate_version_info import DEFAULT_VERSION


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    lowered = text.lower()

    _assert(re.search(r"(?m)^\s*tags:\s*$", text), "workflow must filter pushed tags")
    _assert('      - "v*"' in text, "workflow must trigger on v* tags")
    _assert("workflow_dispatch:" in text, "dry-run dispatch contract is missing")
    _assert("windows-latest" in lowered, "Windows runner is required")
    _assert(lowered.count("contents: write") == 1, "write permission must exist only on the publish job")
    _assert("github.ref_type == 'tag'" in text, "release publication must be tag-only")
    _assert("id: license" in text, "LICENSE gate step is missing")
    _assert("license-approved: ${{ steps.license.outputs.license-approved }}" in text, "LICENSE approval is not exported")
    _assert("needs.build.outputs.license-approved == 'true'" in text, "publish job can bypass LICENSE approval")
    _assert(r"scripts\check_release_license.py --mode $mode" in text, "workflow does not execute the LICENSE validator")
    _assert(text.index("Enforce release LICENSE gate") < text.index("Install pinned dependencies"), "tag guard must run before build setup")
    _assert("cancel-in-progress: false" in lowered, "release builds must not cancel one another")
    _assert(r"^v(?<version>\d+\.\d+\.\d+)$" in text, "release tags must be validated strictly")
    _assert("id: version" in text and "GITHUB_OUTPUT" in text, "derived version must be available to action inputs")
    _assert("python-version: ${{ env.PYTHON_VERSION }}" in text, "Python version must be explicit")
    _assert("requirements-web.txt" in text and "requirements-build.txt" in text, "pinned dependencies are incomplete")
    _assert(r"scripts\release_check.cmd" in text, "release checks must run before packaging")
    _assert(r"scripts\clean_release_artifacts.ps1" in text, "release outputs must start clean")
    _assert(r"scripts\build_onedir.cmd" in text, "PyInstaller build is missing")
    _assert(r"scripts\build_installer.cmd" in text, "Inno Setup build is missing")
    _assert("INNO_INSTALLER_SHA256" in text, "Inno Setup download must be hash-pinned")
    _assert("Get-AuthenticodeSignature" in text and "Pyrsys B\\.V\\." in text, "Inno publisher verification is missing")
    _assert("SHA256SUMS.txt" in text and "Get-FileHash" in text, "release checksums are missing")
    action_uses = re.findall(r"uses:\s+actions/[^@\s]+@([^\s#]+)", text)
    _assert(len(action_uses) == 4, "unexpected number of first-party actions")
    _assert(all(re.fullmatch(r"[0-9a-f]{40}", revision) for revision in action_uses), "actions must be commit-pinned")
    _assert(text.count("# v7") == 2, "artifact upload and download actions must use the Node 24 release")
    _assert("overwrite: true" in text, "workflow reruns must replace their existing artifact safely")
    _assert("gh release create" in text and "gh release upload" in text, "idempotent GitHub Release publication is missing")
    _assert("GH_TOKEN: ${{ github.token }}" in text, "GitHub CLI must use the scoped workflow token")
    _assert("--verify-tag" in text, "release publication must verify the tag")
    _assert(".env" not in lowered and "ors_api_key" not in lowered, "workflow references private configuration")
    _assert("pull_request_target" not in lowered, "privileged pull_request_target execution is forbidden")
    _assert("workflow_run" not in lowered, "release must not accept untrusted workflow artifacts")
    _assert("branches:" not in text and "codex/patch-7a" not in text, "temporary branch triggers must not remain")
    _assert("fail_before_build" not in text, "temporary failure simulation must not remain")

    with tempfile.TemporaryDirectory(prefix="fuelopt-license-gate-") as temp_dir:
        license_path = Path(temp_dir) / "LICENSE"
        approved, blocked, problems = evaluate_gate("dry-run", license_path)
        _assert(not approved and not blocked and problems, "dry-run without LICENSE must continue but remain unapproved")
        approved, blocked, problems = evaluate_gate("tag", license_path)
        _assert(not approved and blocked and problems, "tag without LICENSE must be blocked")
        for placeholder in ("TODO", "CHOOSE LICENSE", "LICENSE PENDING", "TBD"):
            license_path.write_text(placeholder, encoding="utf-8")
            _assert(validate_license(license_path), f"LICENSE placeholder was accepted: {placeholder}")
        license_path.write_text("Approved fixture license text for gate testing.\n", encoding="utf-8")
        approved, blocked, problems = evaluate_gate("tag", license_path)
        _assert(approved and not blocked and not problems, "valid fixture should pass the future tag gate")

    dispatch_default = re.search(r'(?ms)workflow_dispatch:.*?default:\s*"(\d+\.\d+\.\d+)"', text)
    _assert(dispatch_default and dispatch_default.group(1) == DEFAULT_VERSION, "workflow dry-run default diverges from local build default")
    print("OK: Windows GitHub Release workflow checks passed")


if __name__ == "__main__":
    run()
