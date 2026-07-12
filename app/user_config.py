from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path


class UserConfigError(ValueError):
    pass


class RefreshInterval(str, Enum):
    ONE_HOUR = "1h"
    TWO_HOURS = "2h"
    FOUR_HOURS = "4h"
    EIGHT_HOURS = "8h"
    TWELVE_HOURS = "12h"
    TWENTY_FOUR_HOURS = "24h"
    ON_OPEN = "on_open"
    MANUAL = "manual"


@dataclass(frozen=True)
class UserConfig:
    schema_version: int = 1
    refresh_interval: str = RefreshInterval.FOUR_HOURS.value
    ors_credential_migrated: bool = False

    def validate(self) -> "UserConfig":
        if self.schema_version != 1:
            raise UserConfigError(f"unsupported config schema_version: {self.schema_version}")
        try:
            RefreshInterval(self.refresh_interval)
        except ValueError as exc:
            raise UserConfigError(f"unsupported refresh_interval: {self.refresh_interval!r}") from exc
        if not isinstance(self.ors_credential_migrated, bool):
            raise UserConfigError("ors_credential_migrated must be a boolean")
        return self


def load_user_config(path: Path) -> UserConfig:
    if not path.exists():
        return UserConfig()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UserConfigError(f"could not read user config: {path}") from exc
    if not isinstance(payload, dict):
        raise UserConfigError("user config must be a JSON object")
    allowed = {"schema_version", "refresh_interval", "ors_credential_migrated"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise UserConfigError(f"unknown user config keys: {', '.join(unknown)}")
    try:
        config = UserConfig(**payload)
    except TypeError as exc:
        raise UserConfigError("invalid user config fields") from exc
    return config.validate()


def save_user_config(path: Path, config: UserConfig) -> None:
    validated = config.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(asdict(validated), ensure_ascii=False, indent=2) + "\n"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
