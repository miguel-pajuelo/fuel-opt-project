from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


CHECKSUM_LINE = re.compile(r"^([0-9a-fA-F]{64})  ([^\r\n]+)$")


class ReleaseAssetVerificationError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_asset_names(version: str) -> tuple[str, str, str]:
    return (
        f"FuelOpt-Setup-{version}.exe",
        f"FuelOpt-{version}-windows-x64.zip",
        "SHA256SUMS.txt",
    )


def canonical_release_body(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized[:-1] if normalized.endswith("\n") else normalized


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def flatten_paginated_items(value: Any, description: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ReleaseAssetVerificationError(f"{description} API response must be a paginated JSON array")
    items: list[dict[str, Any]] = []
    for page_number, page in enumerate(value, start=1):
        if not isinstance(page, list):
            raise ReleaseAssetVerificationError(f"{description} API page {page_number} is not a JSON array")
        for item in page:
            if not isinstance(item, dict):
                raise ReleaseAssetVerificationError(f"{description} API page {page_number} contains a malformed item")
            items.append(item)
    return items


def find_release_by_tag(release_pages: Any, expected_tag: str) -> dict[str, Any] | None:
    releases = flatten_paginated_items(release_pages, "release list")
    for release in releases:
        release_id = release.get("id")
        if isinstance(release_id, bool) or not isinstance(release_id, int) or release_id <= 0:
            raise ReleaseAssetVerificationError("release list contains an invalid release ID")
        if not isinstance(release.get("tag_name"), str):
            raise ReleaseAssetVerificationError("release list contains an invalid tag_name")
        if not isinstance(release.get("draft"), bool):
            raise ReleaseAssetVerificationError("release list contains an invalid draft state")
    matches = [item for item in releases if item["tag_name"] == expected_tag]
    if len(matches) > 1:
        raise ReleaseAssetVerificationError(f"multiple releases use the exact tag {expected_tag!r}")
    if not matches:
        return None
    release = matches[0]
    release_id = release["id"]
    return {"id": release_id, "draft": release["draft"], "tag_name": expected_tag}


def parse_checksum_file(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if len(lines) != 2:
        raise ReleaseAssetVerificationError(f"SHA256SUMS.txt must contain exactly two entries; found {len(lines)}")
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        match = CHECKSUM_LINE.fullmatch(line)
        if not match:
            raise ReleaseAssetVerificationError(f"invalid checksum line {line_number}: {line!r}")
        digest, name = match.groups()
        if name != name.strip() or name in {".", ".."} or "/" in name or "\\" in name:
            raise ReleaseAssetVerificationError(f"checksum entry must use an exact base filename: {name!r}")
        if Path(name).name != name:
            raise ReleaseAssetVerificationError(f"checksum entry contains a path: {name!r}")
        if name in checksums:
            raise ReleaseAssetVerificationError(f"duplicate checksum entry: {name}")
        checksums[name] = digest.lower()
    return checksums


def _verify_local_payload(release_dir: Path, version: str) -> tuple[tuple[str, str, str], dict[str, Path]]:
    names = expected_asset_names(version)
    local_files = {path.name: path for path in release_dir.iterdir() if path.is_file()}
    if set(local_files) != set(names):
        raise ReleaseAssetVerificationError(
            f"local release assets differ: expected {sorted(names)!r}, received {sorted(local_files)!r}"
        )
    checksums = parse_checksum_file(local_files["SHA256SUMS.txt"])
    binary_names = set(names[:2])
    if set(checksums) != binary_names:
        raise ReleaseAssetVerificationError(
            f"checksum entries differ: expected {sorted(binary_names)!r}, received {sorted(checksums)!r}"
        )
    for name in names[:2]:
        actual = sha256_file(local_files[name])
        if checksums[name] != actual:
            raise ReleaseAssetVerificationError(
                f"SHA256SUMS mismatch for {name}: declared {checksums[name]}, actual {actual}"
            )
    return names, local_files


def verify_release_snapshot(
    release: Any,
    asset_pages: Any,
    release_dir: Path,
    version: str,
    expected_tag: str,
    expected_commit: str,
    resolved_tag_commit: str,
    expected_title: str,
    expected_body: str,
    expected_draft: bool,
    expected_release_id: int | None = None,
) -> dict[str, Any]:
    if not isinstance(release, dict):
        raise ReleaseAssetVerificationError("release API response must contain an object")
    release_id = release.get("id")
    if isinstance(release_id, bool) or not isinstance(release_id, int) or release_id <= 0:
        raise ReleaseAssetVerificationError("release has an invalid ID")
    if expected_release_id is not None and release_id != expected_release_id:
        raise ReleaseAssetVerificationError(
            f"release ID differs: expected {expected_release_id}, received {release_id}"
        )
    if release.get("tag_name") != expected_tag:
        raise ReleaseAssetVerificationError("release tag differs from the expected tag")
    if resolved_tag_commit != expected_commit:
        raise ReleaseAssetVerificationError(
            f"release tag resolves to {resolved_tag_commit!r}, expected {expected_commit!r}"
        )
    target_commitish = release.get("target_commitish")
    if not isinstance(target_commitish, str) or not target_commitish:
        raise ReleaseAssetVerificationError("release has no target_commitish metadata")
    if release.get("name") != expected_title:
        raise ReleaseAssetVerificationError("release title differs from the deterministic title")
    body = release.get("body")
    if not isinstance(body, str) or canonical_release_body(body) != canonical_release_body(expected_body):
        raise ReleaseAssetVerificationError("release body differs from the deterministic notes")
    if release.get("draft") is not expected_draft:
        raise ReleaseAssetVerificationError(f"release draft state must be {expected_draft}")
    if release.get("prerelease") is not False:
        raise ReleaseAssetVerificationError("release must not be marked as a prerelease")
    updated_at = release.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at:
        raise ReleaseAssetVerificationError("release has no stable updated_at value")

    names, local_files = _verify_local_payload(release_dir, version)
    assets = flatten_paginated_items(asset_pages, "release assets")
    remote_assets: dict[str, dict[str, Any]] = {}
    asset_ids: set[int] = set()
    for asset in assets:
        asset_id = asset.get("id")
        name = asset.get("name")
        if isinstance(asset_id, bool) or not isinstance(asset_id, int) or asset_id <= 0:
            raise ReleaseAssetVerificationError("release contains an asset with an invalid ID")
        if asset_id in asset_ids:
            raise ReleaseAssetVerificationError(f"release contains duplicate asset ID: {asset_id}")
        asset_ids.add(asset_id)
        if not isinstance(name, str):
            raise ReleaseAssetVerificationError("release contains malformed asset metadata")
        if name in remote_assets:
            raise ReleaseAssetVerificationError(f"release contains duplicate asset: {name}")
        remote_assets[name] = asset
    if set(remote_assets) != set(names):
        raise ReleaseAssetVerificationError(
            f"remote release assets differ: expected {sorted(names)!r}, received {sorted(remote_assets)!r}"
        )

    normalized_assets: list[dict[str, Any]] = []
    for name in sorted(names):
        local = local_files[name]
        remote = remote_assets[name]
        if remote.get("state") != "uploaded":
            raise ReleaseAssetVerificationError(f"remote asset is not fully uploaded: {name}")
        if remote.get("size") != local.stat().st_size:
            raise ReleaseAssetVerificationError(
                f"remote size mismatch for {name}: expected {local.stat().st_size}, received {remote.get('size')}"
            )
        expected_digest = f"sha256:{sha256_file(local)}"
        remote_digest = str(remote.get("digest") or "").lower()
        if remote_digest != expected_digest:
            raise ReleaseAssetVerificationError(
                f"remote digest mismatch for {name}: expected {expected_digest}, received {remote_digest or '<missing>'}"
            )
        normalized_assets.append(
            {
                "id": remote["id"],
                "name": name,
                "state": "uploaded",
                "size": remote["size"],
                "digest": remote_digest,
            }
        )

    return {
        "id": release_id,
        "tag_name": expected_tag,
        "resolved_tag_commit": expected_commit,
        "target_commitish": target_commitish,
        "name": expected_title,
        "body": canonical_release_body(expected_body),
        "draft": expected_draft,
        "prerelease": False,
        "updated_at": updated_at,
        "assets": normalized_assets,
    }


def compare_snapshots(first: Any, second: Any) -> None:
    if not isinstance(first, dict) or not isinstance(second, dict):
        raise ReleaseAssetVerificationError("release snapshots must contain JSON objects")
    if first != second:
        raise ReleaseAssetVerificationError("release changed between verification snapshots")


def verify_published_transition(draft: Any, published: Any) -> None:
    if not isinstance(draft, dict) or not isinstance(published, dict):
        raise ReleaseAssetVerificationError("release snapshots must contain JSON objects")
    if draft.get("draft") is not True or published.get("draft") is not False:
        raise ReleaseAssetVerificationError("release did not transition from draft to published")
    stable_fields = {
        "id",
        "tag_name",
        "resolved_tag_commit",
        "target_commitish",
        "name",
        "body",
        "prerelease",
        "assets",
    }
    for field in stable_fields:
        if draft.get(field) != published.get(field):
            raise ReleaseAssetVerificationError(f"release field changed during publication: {field}")
    if not isinstance(published.get("updated_at"), str) or not published["updated_at"]:
        raise ReleaseAssetVerificationError("published release has no updated_at value")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify immutable GitHub Release metadata and assets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    find = subparsers.add_parser("find", help="Find one exact tag in a paginated release list.")
    find.add_argument("--releases-json", type=Path, required=True)
    find.add_argument("--expected-tag", required=True)
    find.add_argument("--output", type=Path, required=True)

    snapshot = subparsers.add_parser("snapshot", help="Validate and save a canonical release snapshot.")
    snapshot.add_argument("--release-json", type=Path, required=True)
    snapshot.add_argument("--assets-json", type=Path, required=True)
    snapshot.add_argument("--release-dir", type=Path, required=True)
    snapshot.add_argument("--version", required=True)
    snapshot.add_argument("--expected-tag", required=True)
    snapshot.add_argument("--expected-commit", required=True)
    snapshot.add_argument("--resolved-tag-commit", required=True)
    snapshot.add_argument("--expected-title", required=True)
    snapshot.add_argument("--expected-body-file", type=Path, required=True)
    snapshot.add_argument("--expected-draft", choices=("true", "false"), required=True)
    snapshot.add_argument("--expected-release-id", type=int, required=True)
    snapshot.add_argument("--output", type=Path, required=True)

    compare = subparsers.add_parser("compare", help="Require two pre-publication snapshots to be identical.")
    compare.add_argument("--first", type=Path, required=True)
    compare.add_argument("--second", type=Path, required=True)

    transition = subparsers.add_parser("transition", help="Verify an immutable draft-to-public transition.")
    transition.add_argument("--draft", type=Path, required=True)
    transition.add_argument("--published", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "find":
        release = find_release_by_tag(_read_json(args.releases_json), args.expected_tag)
        result = {"status": "absent"} if release is None else {"status": "found", **release}
        _write_json(args.output, result)
    elif args.command == "snapshot":
        snapshot = verify_release_snapshot(
            _read_json(args.release_json),
            _read_json(args.assets_json),
            args.release_dir,
            args.version,
            args.expected_tag,
            args.expected_commit,
            args.resolved_tag_commit,
            args.expected_title,
            args.expected_body_file.read_text(encoding="utf-8-sig"),
            args.expected_draft == "true",
            args.expected_release_id,
        )
        _write_json(args.output, snapshot)
    elif args.command == "compare":
        compare_snapshots(_read_json(args.first), _read_json(args.second))
    else:
        verify_published_transition(_read_json(args.draft), _read_json(args.published))
    print("OK: GitHub Release state matches the audited payload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
