from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_release_assets import (
    ReleaseAssetVerificationError,
    canonical_release_body,
    compare_snapshots,
    expected_asset_names,
    find_release_by_tag,
    sha256_file,
    verify_published_transition,
    verify_release_snapshot,
)


VERSION = "0.1.2"
TAG = "v0.1.2"
COMMIT = "a" * 40
TITLE = "FuelOpt 0.1.2"
BODY = (
    "FuelOpt 0.1.2\n\n"
    "Artefactos generados para la etiqueta v0.1.2. "
    "Verifica el instalador y el ZIP portable con SHA256SUMS.txt antes de utilizarlos.\n"
)


def _fixture(tmp_path: Path, *, draft: bool = True) -> tuple[Path, dict[str, object], list[list[dict[str, object]]]]:
    setup_name, zip_name, checksum_name = expected_asset_names(VERSION)
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    (release_dir / setup_name).write_bytes(b"installer payload\n")
    (release_dir / zip_name).write_bytes(b"portable payload\n")
    _write_valid_checksums(release_dir)
    assets = [
        {
            "id": index,
            "name": name,
            "size": (release_dir / name).stat().st_size,
            "digest": f"sha256:{sha256_file(release_dir / name)}",
            "state": "uploaded",
        }
        for index, name in enumerate((setup_name, zip_name, checksum_name), start=101)
    ]
    release: dict[str, object] = {
        "id": 42,
        "tag_name": TAG,
        "target_commitish": COMMIT,
        "name": TITLE,
        "body": BODY,
        "draft": draft,
        "prerelease": False,
        "updated_at": "2026-07-15T10:00:00Z",
    }
    return release_dir, release, [assets]


def _write_valid_checksums(release_dir: Path, *, upper: bool = False) -> None:
    setup_name, zip_name, checksum_name = expected_asset_names(VERSION)
    entries = []
    for name in (setup_name, zip_name):
        digest = sha256_file(release_dir / name)
        entries.append(f"{digest.upper() if upper else digest}  {name}")
    (release_dir / checksum_name).write_text("\n".join(entries) + "\n", encoding="utf-8")


def _snapshot(
    release_dir: Path,
    release: dict[str, object],
    assets: list[list[dict[str, object]]],
    *,
    expected_draft: bool | None = None,
) -> dict[str, object]:
    return verify_release_snapshot(
        release,
        assets,
        release_dir,
        VERSION,
        TAG,
        COMMIT,
        COMMIT,
        TITLE,
        BODY,
        bool(release["draft"]) if expected_draft is None else expected_draft,
        42,
    )


def test_release_absence_is_decided_from_paginated_json() -> None:
    assert find_release_by_tag([[{"id": 1, "tag_name": "v0.1.0", "draft": False}], []], TAG) is None


def test_release_is_found_on_a_later_page() -> None:
    result = find_release_by_tag(
        [[{"id": 1, "tag_name": "v0.1.0", "draft": False}], [{"id": 42, "tag_name": TAG, "draft": True}]],
        TAG,
    )
    assert result == {"id": 42, "draft": True, "tag_name": TAG}


def test_duplicate_tag_matches_are_rejected() -> None:
    with pytest.raises(ReleaseAssetVerificationError, match="multiple releases"):
        find_release_by_tag([[{"id": 41, "tag_name": TAG, "draft": True}], [{"id": 42, "tag_name": TAG, "draft": False}]], TAG)


@pytest.mark.parametrize(
    "malformed",
    [
        {"message": "Bad credentials"},
        [[{"message": "not found"}]],
        [[{"id": 1, "tag_name": TAG}]],
    ],
)
def test_api_failure_payload_is_never_interpreted_as_absence(malformed: object) -> None:
    with pytest.raises(ReleaseAssetVerificationError):
        find_release_by_tag(malformed, TAG)


@pytest.mark.parametrize("draft", [True, False])
def test_identical_draft_and_published_release_are_accepted(tmp_path: Path, draft: bool) -> None:
    release_dir, release, assets = _fixture(tmp_path, draft=draft)
    snapshot = _snapshot(release_dir, release, assets)
    assert snapshot["draft"] is draft
    assert snapshot["id"] == 42
    assert len(snapshot["assets"]) == 3


def test_body_normalization_is_limited_to_line_endings_and_one_final_newline(tmp_path: Path) -> None:
    release_dir, release, assets = _fixture(tmp_path)
    release["body"] = canonical_release_body(BODY).replace("\n", "\r\n")
    _snapshot(release_dir, release, assets)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "FuelOpt altered", "title"),
        ("body", BODY.replace("Verifica", "Ignora"), "body"),
        ("prerelease", True, "prerelease"),
        ("target_commitish", "", "target_commitish"),
        ("tag_name", "v9.9.9", "tag"),
    ],
)
def test_divergent_release_metadata_is_rejected(tmp_path: Path, field: str, value: object, message: str) -> None:
    release_dir, release, assets = _fixture(tmp_path)
    release[field] = value
    with pytest.raises(ReleaseAssetVerificationError, match=message):
        _snapshot(release_dir, release, assets)


def test_tag_resolving_to_another_commit_is_rejected(tmp_path: Path) -> None:
    release_dir, release, assets = _fixture(tmp_path)
    with pytest.raises(ReleaseAssetVerificationError, match="tag resolves"):
        verify_release_snapshot(release, assets, release_dir, VERSION, TAG, COMMIT, "b" * 40, TITLE, BODY, True)


def test_release_response_id_must_match_the_lookup_id(tmp_path: Path) -> None:
    release_dir, release, assets = _fixture(tmp_path)
    release["id"] = 43
    with pytest.raises(ReleaseAssetVerificationError, match="release ID differs"):
        _snapshot(release_dir, release, assets)


@pytest.mark.parametrize("change", ["id", "extra", "missing", "duplicate-name", "duplicate-id", "state", "size", "digest"])
def test_remote_asset_divergences_are_rejected(tmp_path: Path, change: str) -> None:
    release_dir, release, asset_pages = _fixture(tmp_path)
    assets = asset_pages[0]
    if change == "id":
        assets[0]["id"] = 0
    elif change == "extra":
        assets.append({"id": 999, "name": "extra.bin", "size": 1, "digest": "sha256:" + "0" * 64, "state": "uploaded"})
    elif change == "missing":
        assets.pop()
    elif change == "duplicate-name":
        duplicate = copy.deepcopy(assets[0])
        duplicate["id"] = 999
        assets.append(duplicate)
    elif change == "duplicate-id":
        assets[1]["id"] = assets[0]["id"]
    elif change == "state":
        assets[0]["state"] = "new"
    elif change == "size":
        assets[0]["size"] = int(assets[0]["size"]) + 1
    else:
        assets[0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ReleaseAssetVerificationError):
        _snapshot(release_dir, release, asset_pages)


def test_uppercase_hexadecimal_checksums_are_accepted(tmp_path: Path) -> None:
    release_dir, release, _ = _fixture(tmp_path)
    _write_valid_checksums(release_dir, upper=True)
    _, _, checksum_name = expected_asset_names(VERSION)
    assets = [[
        {
            "id": index,
            "name": name,
            "size": (release_dir / name).stat().st_size,
            "digest": f"sha256:{sha256_file(release_dir / name)}",
            "state": "uploaded",
        }
        for index, name in enumerate(expected_asset_names(VERSION), start=101)
    ]]
    _snapshot(release_dir, release, assets)
    assert (release_dir / checksum_name).is_file()


@pytest.mark.parametrize(
    "invalid_lines",
    [
        lambda setup, zip_name, setup_hash, zip_hash: [f"{'0' * 64}  {setup}", f"{zip_hash}  {zip_name}"],
        lambda setup, zip_name, setup_hash, zip_hash: [f"{setup_hash}  {setup}", f"{setup_hash}  {setup}"],
        lambda setup, zip_name, setup_hash, zip_hash: [f"{setup_hash}  nested/{setup}", f"{zip_hash}  {zip_name}"],
        lambda setup, zip_name, setup_hash, zip_hash: [f"{setup_hash}  ./{setup}", f"{zip_hash}  {zip_name}"],
        lambda setup, zip_name, setup_hash, zip_hash: [f"{setup_hash}  folder\\{setup}", f"{zip_hash}  {zip_name}"],
        lambda setup, zip_name, setup_hash, zip_hash: [f"{setup_hash} {setup}", f"{zip_hash}  {zip_name}"],
        lambda setup, zip_name, setup_hash, zip_hash: [f"{setup_hash}   {setup}", f"{zip_hash}  {zip_name}"],
        lambda setup, zip_name, setup_hash, zip_hash: [f"{setup_hash}  other.exe", f"{zip_hash}  {zip_name}"],
        lambda setup, zip_name, setup_hash, zip_hash: [f"{zip_hash}  {setup}", f"{setup_hash}  {zip_name}"],
        lambda setup, zip_name, setup_hash, zip_hash: [f"{setup_hash}  {setup.upper()}", f"{zip_hash}  {zip_name}"],
    ],
    ids=["wrong-hash", "duplicate", "path", "dot-path", "windows-path", "one-space", "three-spaces", "other-file", "swapped-hashes", "filename-case"],
)
def test_invalid_checksum_payloads_are_rejected(tmp_path: Path, invalid_lines: object) -> None:
    release_dir, release, assets = _fixture(tmp_path)
    setup, zip_name, checksum_name = expected_asset_names(VERSION)
    setup_hash = sha256_file(release_dir / setup)
    zip_hash = sha256_file(release_dir / zip_name)
    lines = invalid_lines(setup, zip_name, setup_hash, zip_hash)
    (release_dir / checksum_name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseAssetVerificationError):
        _snapshot(release_dir, release, assets)


@pytest.mark.parametrize("entry_count", [1, 3])
def test_checksum_file_requires_exactly_two_entries(tmp_path: Path, entry_count: int) -> None:
    release_dir, release, assets = _fixture(tmp_path)
    setup, zip_name, checksum_name = expected_asset_names(VERSION)
    valid = [f"{sha256_file(release_dir / setup)}  {setup}", f"{sha256_file(release_dir / zip_name)}  {zip_name}"]
    lines = valid[:entry_count] if entry_count == 1 else valid + [f"{'0' * 64}  extra.bin"]
    (release_dir / checksum_name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseAssetVerificationError, match="exactly two"):
        _snapshot(release_dir, release, assets)


def test_two_identical_prepublication_snapshots_are_accepted(tmp_path: Path) -> None:
    release_dir, release, assets = _fixture(tmp_path)
    snapshot = _snapshot(release_dir, release, assets)
    compare_snapshots(snapshot, copy.deepcopy(snapshot))


@pytest.mark.parametrize("change", ["release-id", "updated-at", "target-commitish", "asset-id"])
def test_prepublication_snapshot_changes_are_rejected(tmp_path: Path, change: str) -> None:
    release_dir, release, assets = _fixture(tmp_path)
    first = _snapshot(release_dir, release, assets)
    second = copy.deepcopy(first)
    if change == "release-id":
        second["id"] = 43
    elif change == "updated-at":
        second["updated_at"] = "2026-07-15T10:01:00Z"
    elif change == "target-commitish":
        second["target_commitish"] = "main"
    else:
        second["assets"][0]["id"] = 999
    with pytest.raises(ReleaseAssetVerificationError, match="changed"):
        compare_snapshots(first, second)


def test_postpublication_snapshot_preserves_all_stable_fields(tmp_path: Path) -> None:
    release_dir, release, assets = _fixture(tmp_path)
    draft = _snapshot(release_dir, release, assets)
    release["draft"] = False
    release["updated_at"] = "2026-07-15T10:02:00Z"
    published = _snapshot(release_dir, release, assets)
    verify_published_transition(draft, published)


@pytest.mark.parametrize("change", ["release-id", "title", "body", "asset-id", "prerelease"])
def test_postpublication_divergence_is_rejected(tmp_path: Path, change: str) -> None:
    release_dir, release, assets = _fixture(tmp_path)
    draft = _snapshot(release_dir, release, assets)
    published = copy.deepcopy(draft)
    published["draft"] = False
    published["updated_at"] = "2026-07-15T10:02:00Z"
    if change == "release-id":
        published["id"] = 43
    elif change == "title":
        published["name"] = "FuelOpt altered"
    elif change == "body":
        published["body"] += " altered"
    elif change == "asset-id":
        published["assets"][0]["id"] = 999
    else:
        published["prerelease"] = True
    with pytest.raises(ReleaseAssetVerificationError):
        verify_published_transition(draft, published)


def test_cli_find_and_snapshot_commands_use_json_files(tmp_path: Path) -> None:
    release_dir, release, assets = _fixture(tmp_path)
    script = ROOT / "scripts" / "verify_release_assets.py"
    pages_path = tmp_path / "release-pages.json"
    lookup_path = tmp_path / "lookup.json"
    release_path = tmp_path / "release.json"
    assets_path = tmp_path / "assets.json"
    body_path = tmp_path / "body.txt"
    snapshot_path = tmp_path / "snapshot.json"
    pages_path.write_text(json.dumps([[{"id": 42, "tag_name": TAG, "draft": True}]]), encoding="utf-8")
    release_path.write_text(json.dumps(release), encoding="utf-8")
    assets_path.write_text(json.dumps(assets), encoding="utf-8")
    body_path.write_text(BODY, encoding="utf-8")
    subprocess.run(
        [sys.executable, str(script), "find", "--releases-json", str(pages_path), "--expected-tag", TAG, "--output", str(lookup_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(lookup_path.read_text(encoding="utf-8"))["id"] == 42
    subprocess.run(
        [
            sys.executable,
            str(script),
            "snapshot",
            "--release-json",
            str(release_path),
            "--assets-json",
            str(assets_path),
            "--release-dir",
            str(release_dir),
            "--version",
            VERSION,
            "--expected-tag",
            TAG,
            "--expected-commit",
            COMMIT,
            "--resolved-tag-commit",
            COMMIT,
            "--expected-title",
            TITLE,
            "--expected-body-file",
            str(body_path),
            "--expected-draft",
            "true",
            "--expected-release-id",
            "42",
            "--output",
            str(snapshot_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(snapshot_path.read_text(encoding="utf-8"))["assets"][0]["id"] > 0
