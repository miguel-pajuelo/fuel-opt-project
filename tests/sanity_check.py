from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_sources.ballenoil import parse_station_detail
from app.data_sources.minetur import to_float_es


def _assert_close(value: float, expected: float, name: str) -> None:
    if not math.isclose(value, expected, rel_tol=0.0, abs_tol=1e-12):
        raise AssertionError(f"{name}: esperado {expected}, obtenido {value}")


def run() -> None:
    fixture_path = ROOT / "tests" / "fixtures" / "ballenoil_detail_sample.html"
    html = fixture_path.read_text(encoding="utf-8")

    detail = parse_station_detail(html)
    tokens = detail.get("tokens") or []

    if "ALBASANZ" not in tokens or "ESCOFINA" not in tokens:
        raise AssertionError(f"Tokens no extraidos correctamente: {tokens}")

    v1 = to_float_es("40.123456")
    v2 = to_float_es("1.249,50")
    if v1 is None or v2 is None:
        raise AssertionError(f"Conversion devolvio None: {v1=}, {v2=}")

    _assert_close(v1, 40.123456, "to_float_es('40.123456')")
    _assert_close(v2, 1249.5, "to_float_es('1.249,50')")

    print("OK: tokens y conversiones numericas validados")


if __name__ == "__main__":
    run()
