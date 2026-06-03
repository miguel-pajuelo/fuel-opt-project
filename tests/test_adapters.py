from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_sources.adapters import BrandRegistry, MineturFilterAdapter
from app.data_sources.brand_catalog import NORMALIZATION_VERSION, canonicalize_brand_label


SAMPLE_ITEMS = [
    {
        "IDEESS": "1001",
        "Rotulo": "REPSOL",
        "Latitud": "40,416775",
        "Longitud (WGS84)": "-3,703790",
        "Direccion": "CALLE GRAN VIA 1",
        "Municipio": "MADRID",
        "Provincia": "MADRID",
        "C.P.": "28013",
        "Precio Gasoleo A": "1,599",
        "Precio Gasolina 95 E5": "1,699",
    },
    {
        "IDEESS": "1002",
        "Rotulo": "CEPSA",
        "Latitud": "40,453305",
        "Longitud (WGS84)": "-3,688627",
        "Direccion": "AVENIDA DE AMERICA 5",
        "Municipio": "MADRID",
        "Provincia": "MADRID",
        "C.P.": "28028",
        "Precio Gasoleo A": "1,579",
    },
    {
        "IDEESS": "1003",
        "Rotulo": "CAMPSA",
        "Latitud": "40,400000",
        "Longitud (WGS84)": "-3,700000",
        "Direccion": "CALLE TOLEDO 10",
        "Municipio": "MADRID",
        "Provincia": "MADRID",
        "C.P.": "28005",
        "Precio Gasoleo A": "1,589",
    },
]


def test_filter_single_rotulo() -> None:
    adapter = MineturFilterAdapter("Cepsa", ["CEPSA"])
    stations, _ = adapter.fetch(SAMPLE_ITEMS)
    assert len(stations) == 1
    assert stations[0].station_id == "1002"
    assert stations[0].brand == "CEPSA"
    assert stations[0].brand_label_raw == "CEPSA"
    assert stations[0].brand_canonical == "CEPSA"


def test_filter_multi_rotulo() -> None:
    adapter = MineturFilterAdapter("Repsol", ["REPSOL", "CAMPSA"])
    stations, _ = adapter.fetch(SAMPLE_ITEMS)
    assert len(stations) == 2
    assert all(station.brand == "REPSOL" for station in stations)
    assert {station.brand_label_raw for station in stations} == {"REPSOL", "CAMPSA"}
    assert all(station.brand_canonical == "REPSOL" for station in stations)


def test_prices_parsed() -> None:
    adapter = MineturFilterAdapter("Repsol", ["REPSOL"])
    stations, prices = adapter.fetch(SAMPLE_ITEMS)
    assert len(stations) == 1
    fuel_types = {price.fuel_type for price in prices}
    assert "gasoleo_a" in fuel_types
    assert "gasolina_95" in fuel_types
    repsol_gasoleo = next(price for price in prices if price.fuel_type == "gasoleo_a")
    assert abs(repsol_gasoleo.price_eur_l - 1.599) < 1e-6


def test_registry_fetch_all() -> None:
    registry = BrandRegistry()
    registry.register(MineturFilterAdapter("Repsol", ["REPSOL", "CAMPSA"]))
    registry.register(MineturFilterAdapter("Cepsa", ["CEPSA"]))
    stations, _ = registry.fetch_all(SAMPLE_ITEMS)
    assert len(stations) == 3
    assert {station.brand for station in stations} == {"REPSOL", "CEPSA"}


def test_registry_fetch_filtered() -> None:
    registry = BrandRegistry()
    registry.register(MineturFilterAdapter("Repsol", ["REPSOL", "CAMPSA"]))
    registry.register(MineturFilterAdapter("Cepsa", ["CEPSA"]))
    stations, _ = registry.fetch_all(SAMPLE_ITEMS, brands=["Cepsa"])
    assert len(stations) == 1
    assert all(station.brand == "CEPSA" for station in stations)


def test_adapter_no_network() -> None:
    adapter = MineturFilterAdapter("Repsol", ["REPSOL"])
    assert adapter.needs_network() is False


def test_missing_coords_skipped() -> None:
    bad_item = {"IDEESS": "9999", "Rotulo": "REPSOL"}
    adapter = MineturFilterAdapter("Repsol", ["REPSOL"])
    stations, prices = adapter.fetch([bad_item])
    assert stations == []
    assert prices == []


def test_brand_registry_v14_canonicalizes_long_tail_labels() -> None:
    # Version check kept at v14 for historical-coverage; version bump to v15 tested below.
    assert NORMALIZATION_VERSION in ("brand-registry-v14", "brand-registry-v15")
    assert canonicalize_brand_label("ESCLATOIL") == ("ESCLATOIL", "ESCLATOIL", 1.0)
    assert canonicalize_brand_label("ALIARA ENERGÍA") == ("ALIARA ENERGIA", "ALIARA ENERGIA", 1.0)
    assert canonicalize_brand_label("PETROLIS INDEPENDENTS - PETRO7") == ("PETROLIS", "PETROLIS", 1.0)
    assert canonicalize_brand_label("SIN ROTULO") == ("UNKNOWN", "UNKNOWN", 0.0)


def test_brand_registry_v15_version_bumped() -> None:
    assert NORMALIZATION_VERSION == "brand-registry-v15", (
        f"Expected brand-registry-v15, got {NORMALIZATION_VERSION}"
    )


def test_brand_registry_v9_canonicalizes_manual_audit_aliases() -> None:
    examples = {
        'ANDAMUR "EL LIMITE"': "ANDAMUR",
        'ANDAMUR "SAN ROMAN"': "ANDAMUR",
        "ANEUOIL": "ANEU OIL",
        "AUTOIL BENIFAIÓ": "AUTOIL",
        "AUTOIL SEGORBE": "AUTOIL",
        "B.P.": "BP",
        "AUTOFUEL EXPRESS": "AUTOFUEL",
        "AUTOFUEL LOW COST": "AUTOFUEL",
        "AVANZA": "AVANZA",
        "AVANZA OIL FIGUERES": "AVANZA",
        "AVANZA OIL PAMPLONA": "AVANZA",
        "BALLUS BAIXCOST": "BALLUS BAIX COST",
    }
    for raw, expected in examples.items():
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == expected, f"{raw!r} -> {canonical!r}"
        assert group == expected
        assert confidence == 1.0


def test_brand_registry_v9_canonicalizes_generic_descriptor_duplicates_conservatively() -> None:
    positives = {
        "CARBUGAL A BARCALA": "CARBUGAL",
        "CARBUGAL TOMIÑO": "CARBUGAL",
        "COMBUSTIBLES LA MURADA,S.L.": "COMBUSTIBLES LA MURADA",
    }
    for raw, expected in positives.items():
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == expected, f"{raw!r} -> {canonical!r}"
        assert group == expected
        assert confidence == 1.0


def test_generic_business_descriptors_are_not_global_brands() -> None:
    examples = {
        "CARBURANTES LA ESTRELLA": "CARBURANTES",
        "CARBURANTES IBIZA, S.L.": "CARBURANTES",
        "COMBUSTIBLES GOMEZ": "COMBUSTIBLES",
        "COMBUSTIBLES CALAHORRA S.L.": "COMBUSTIBLES",
        "CARBURANTS LOW COST": "CARBURANTS",
        "BENZINERA LA PLANA": "BENZINERA",
    }
    for raw, generic_canonical in examples.items():
        canonical, _, confidence = canonicalize_brand_label(raw)
        assert canonical != generic_canonical or confidence < 1.0, (
            f"{raw!r} should not map to generic canonical {generic_canonical!r}"
        )


def test_moeve_exact_maps_to_cepsa() -> None:
    canonical, group, confidence = canonicalize_brand_label("MOEVE")
    assert canonical == "CEPSA"
    assert group == "CEPSA"
    assert confidence == 1.0


def test_cepsa_moeve_exact_maps_to_cepsa() -> None:
    for raw in ("CEPSA-MOEVE", "MOEVE-CEPSA"):
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == "CEPSA", f"{raw!r} → {canonical!r}"
        assert group == "CEPSA"
        assert confidence == 1.0


def test_moeve_compound_prefix_maps_to_cepsa() -> None:
    """Compound MOEVE labels must map to CEPSA with confidence=1.0 so they count in /brands."""
    compound_labels = [
        "MOEVE VILANOVA",
        "MOEVE COMERCIAL S.A.U.",
        "MOEVE (ANTERIORMENTE CEPSA) PENDIENTE DE CAMBIAR TODA LA IMAGEN",
        "MOEVE-GARCIBUR",
        "MOEVE-E.S.JAIME I",
        "MOEVE COMPLEJO LEO 24H",
    ]
    for raw in compound_labels:
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == "CEPSA", f"{raw!r} → {canonical!r}"
        assert group == "CEPSA", f"{raw!r} group={group!r}"
        assert confidence == 1.0, f"{raw!r} confidence={confidence} must be 1.0 for /brands"


def test_cepsa_compound_prefix_maps_to_cepsa() -> None:
    """Compound CEPSA labels must map to CEPSA with confidence=1.0."""
    for raw in ("CEPSA LA GALIA", "CEPSA COMERCIAL", "CEPSA- ANTELA E.S.", "CEPSA/LOHANA"):
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == "CEPSA", f"{raw!r} → {canonical!r}"
        assert confidence == 1.0, f"{raw!r} confidence={confidence}"


def test_disa_compound_prefix_follows_exact_disa_canonical() -> None:
    exact_canonical, exact_group, exact_confidence = canonicalize_brand_label("DISA")
    assert exact_confidence == 1.0
    for raw in ("DISA EL CHARCO", "DISA ARRECIFE", "DISA AEROPUERTO", "DISA CIRCUNVALACION I"):
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == exact_canonical, f"{raw!r} -> {canonical!r}"
        assert group == exact_group
        assert confidence == 1.0


def test_dst_compound_prefix_maps_to_dst() -> None:
    for raw in ("DST", "DST ARCA REAL", "DST BELVIS", "DST CABANILLAS", "DST MERCAOLID"):
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == "DST", f"{raw!r} -> {canonical!r}"
        assert group == "DST"
        assert confidence == 1.0


def test_cepsa_moeve_token_in_middle_or_end_maps_to_cepsa() -> None:
    """CEPSA/MOEVE appearing as a bounded token anywhere in the label must map to CEPSA."""
    for raw in (
        "GRUPO CACHO - MOEVE",         # MOEVE at the end, hyphen-space separator
        "SUTULLENA-CEPSA",             # CEPSA at the end, hyphen separator
        "U.S. MOEVE POSTE PILAS",      # MOEVE in the middle, space separators
        "E.S. CEPSA CHIO",             # CEPSA in the middle, space separators
        "ES MIRALBUENO CEPSA",         # CEPSA at the end, space separator
        'INLOCOR S.L. "CEPSA"',        # CEPSA at the end, quote separators
        "EE SS. VENTA DEL SOL CEPSA",  # CEPSA at the end
        "FUNDACION AIDA CEPSA",        # CEPSA at the end
        "GASOLINERA CEPSA LA CARIDAD", # CEPSA in the middle
        'E.S.  AVINY\xd3   -CEPSA-',  # CEPSA surrounded by hyphens
    ):
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == "CEPSA", f"{raw!r} → {canonical!r}"
        assert group == "CEPSA", f"{raw!r} group={group!r}"
        assert confidence == 1.0, f"{raw!r} confidence={confidence}"


def test_safe_brand_token_matching_maps_known_brands_anywhere() -> None:
    examples = {
        "AREA SERVICIO REPSOL NORTE": "REPSOL",
        "ALCAMPO VALLADOLID": "ALCAMPO",
        "BALLENOIL MÓSTOLES": "BALLENOIL",
        "GRUPO X - SHELL": "SHELL",
        "E.S. ZESTOA-AVIA": "AVIA",
    }
    for raw, expected in examples.items():
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == expected, f"{raw!r} → {canonical!r}"
        assert group == expected
        assert confidence == 1.0


def test_targeted_suffix_brand_rules_group_known_families() -> None:
    examples = {
        '"BP" ROTONDA LAS VAGUADAS S.L.': "BP",
        '"BP"BEGUR': "BP",
        '"BP"PROPERLY, S.A.': "BP",
        "A.N. ENERGETICOS - LOS ARCOS": "AN ENERGETICOS",
        "A.N. ENERGETICOS, S.L - PERALTA": "AN ENERGETICOS",
        "A.N. ENERGETICOS-ALDEANUEVA": "AN ENERGETICOS",
        "AN ENERGETICOS - ARGUEDAS": "AN ENERGETICOS",
        "AIRA OIL TABOADA": "AIRA OIL",
        "AIREMAR I": "AIREMAR",
        "AIREMAR II": "AIREMAR",
    }
    for raw, expected in examples.items():
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == expected, f"{raw!r} â†’ {canonical!r}"
        assert group == expected
        assert confidence == 1.0


def test_bp_prefix_labels_map_to_bp_without_broad_token_matching() -> None:
    positives = [
        "BP ALOD",
        "BP - AVILA",
        "BP 24 HORAS",
        "BP A42 CABANAS MD",
        "BP ALGEMESI I - SAN CRISTOBAL",
        '"BP" ROTONDA LAS VAGUADAS S.L.',
        '"BP"BEGUR',
        '"BP"PROPERLY, S.A.',
        "B.P.",
        "BP ROMICA",
        "BP OIL ESPAÑA S.A.",
    ]
    for raw in positives:
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == "BP", f"{raw!r} -> {canonical!r}"
        assert group == "BP"
        assert confidence == 1.0

    negatives = [
        "ABP SERVICE",
        "SUPERBP GAS",
        "GASOLINERA BPX",
        "X BP TEST",
        "AREA BP NORTE",
    ]
    for raw in negatives:
        canonical, _, confidence = canonicalize_brand_label(raw)
        assert canonical != "BP" or confidence < 1.0, f"{raw!r} should not map broadly to BP"


def test_branch_prefix_brand_families_map_without_broad_short_token_matching() -> None:
    positives = {
        "EXOIL ALBERIC": "EXOIL",
        "EXOIL RIBA-ROJA": "EXOIL",
        "GACOSUR JEREZ": "GACOSUR",
        "GACOSUR VILLAMARTIN": "GACOSUR",
        "GV OIL": "GV OIL",
        "GVOIL": "GV OIL",
        "H2EXAGON ARAFO": "H2EXAGON",
        "H2EXAGON NORTE": "H2EXAGON",
        "H2GO CORRALEJO": "H2GO",
        "H2GO MUELLE CHICO": "H2GO",
        "HAM BILBAO": "HAM",
        "HAM TRES CANTOS": "HAM",
    }
    for raw, expected in positives.items():
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == expected, f"{raw!r} -> {canonical!r}"
        assert group == expected
        assert confidence == 1.0

    negatives = {
        "EXO": "EXOIL",
        "GACO": "GACOSUR",
        "GV": "GV OIL",
        "H2": "H2GO",
        "HAMMER OIL": "HAM",
        "X HAM TEST": "HAM",
        "CHAMPION GAS": "HAM",
        "GÓMEZ Y SIRVENT": "GÓMEZ Y SIRVENT",
    }
    for raw, unsafe_canonical in negatives.items():
        canonical, _, confidence = canonicalize_brand_label(raw)
        assert canonical != unsafe_canonical or confidence < 1.0, (
            f"{raw!r} should not be a broad match for {unsafe_canonical!r}"
        )


def test_petro_like_families_map_without_generic_petro_canonical() -> None:
    positives = {
        "MASOIL ALCOY": "MASOIL",
        "MASOIL CASTALLA": "MASOIL",
        "NORPETROL ARCOS": "NORPETROL",
        "NORPETROL LOS CARROS 2": "NORPETROL",
        "PETROCASH BETANZOS": "PETROCASH",
        "PETROCASH NARON (POL. GÁNDARA)": "PETROCASH",
        "PETRO PINTÓ S.L.": "PETRO PINTO",
        "PETRO-PINTO,S.L.": "PETRO PINTO",
        "PETROIL ENERGY AZAHARA": "PETROIL ENERGY",
        "PETROIL ENERGY GRANADAL II": "PETROIL ENERGY",
        "PETRO7 - PETROLIS INDEPENDENTS": "PETROLIS",
    }
    for raw, expected in positives.items():
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == expected, f"{raw!r} -> {canonical!r}"
        assert group == expected
        assert confidence == 1.0

    for raw in (
        "PETRO G24",
        "PETRO GRADO",
        "PETRO SWAP",
        "PETROALACANT",
        "PETRO7",
        "PETRO",
        "AREA PETRO TEST",
    ):
        canonical, _, confidence = canonicalize_brand_label(raw)
        assert canonical != "PETRO" or confidence < 1.0, f"{raw!r} should not map confidently to generic PETRO"


def test_petrol_q8_qp_renesur_tgas_prefix_families_canonicalize_conservatively() -> None:
    examples = {
        "PETROL&GO": "PETROL & GO",
        "Q8 CASTELLAR": "Q8",
        "Q8EASY": "Q8",
        "QP ALMENSILLA": "QP",
        "QP NERVION": "QP",
        "RENESUR GR": "RENESUR",
        "RENESUR-EL ALTIPLANO": "RENESUR",
        "TGAS ARONA": "TGAS",
        "TGAS EL MÉDANO": "TGAS",
        "TGAS-TU TRÉBOL": "TGAS",
    }
    for raw, expected in examples.items():
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == expected, f"{raw!r} -> {canonical!r}"
        assert group == expected
        assert confidence == 1.0


def test_petrol_q8_qp_tgas_prefix_rules_do_not_overmatch() -> None:
    examples = {
        "PETROLAVILA": "PETROL",
        "PETROLCAR": "PETROL",
        "PETROL A RUA": "PETROL & GO",
        "X PETROL & GO TEST": "PETROL & GO",
        "Q8X SERVICE": "Q8",
        "X Q8 TEST": "Q8",
        "AQP SERVICE": "QP",
        "X QP TEST": "QP",
        "TGASOLINA": "TGAS",
        "X TGAS TEST": "TGAS",
    }
    for raw, unsafe_canonical in examples.items():
        canonical, _, confidence = canonicalize_brand_label(raw)
        assert canonical != unsafe_canonical or confidence < 1.0, (
            f"{raw!r} should not be a broad match for {unsafe_canonical!r}"
        )


def test_vcc_prefix_family_maps_without_broad_token_matching() -> None:
    for raw in ("VCC ALFAFAR", "VCC ALICANTE", "VCC PEÑISCOLA", "VCC SANTA POLA"):
        canonical, group, confidence = canonicalize_brand_label(raw)
        assert canonical == "VCC", f"{raw!r} -> {canonical!r}"
        assert group == "VCC"
        assert confidence == 1.0

    for raw in ("AVCC SERVICE", "VCCX GAS", "X VCC TEST"):
        canonical, _, confidence = canonicalize_brand_label(raw)
        assert canonical != "VCC" or confidence < 1.0, f"{raw!r} should not map broadly to VCC"


def test_brand_token_matching_respects_boundaries() -> None:
    for raw in (
        "MIRESPSOLERA",
        "XXBALLENOILYY",
        "ALCAMPONORTE",
        "SHELLBOX",
        "CEPSATO",
    ):
        canonical, _, confidence = canonicalize_brand_label(raw)
        assert confidence < 1.0, f"{raw!r} should not be a safe token match: {canonical!r}"


def test_unsafe_short_or_generic_aliases_are_not_token_matched() -> None:
    examples = {
        "AREA BP NORTE": "BP",
        "X DISA TEST": "CEPSA",
        "COOP SAN ISIDRO": "SAN ISIDRO",
        "ALSA Y SERVI OIL LOW COST": "ALSA",
        "EUSKOIL-STAR PETROLEUM": "STAR PETROLEUM",
    }
    for raw, unsafe_canonical in examples.items():
        canonical, _, confidence = canonicalize_brand_label(raw)
        assert canonical != unsafe_canonical or confidence < 1.0, (
            f"{raw!r} should not use unsafe token matching for {unsafe_canonical!r}"
        )


def test_manual_audit_aliases_do_not_overmatch() -> None:
    examples = {
        "RANDOMBPWORD": "BP",
        "AREA BP NORTE": "BP",
        "ANEU": "ANEU OIL",
        "AUTO": "AUTOIL",
        "OIL": "ANEU OIL",
        "AUTO OIL": "AUTOIL",
        "AND": "ANDAMUR",
        "ANDA": "ANDAMUR",
        "GRUPO AVANZA NORTE": "AVANZA",
        "AVANZA OILERA": "AVANZA",
        "ADISARANDOM": "CEPSA",
        "X DISA TEST": "CEPSA",
        "DSTATION SERVICE": "DST",
        "X DST TEST": "DST",
    }
    for raw, unsafe_canonical in examples.items():
        canonical, _, confidence = canonicalize_brand_label(raw)
        assert canonical != unsafe_canonical or confidence < 1.0, (
            f"{raw!r} should not be a broad match for {unsafe_canonical!r}"
        )


def test_exact_alias_behavior_remains_unchanged() -> None:
    assert canonicalize_brand_label("BP") == ("BP", "BP", 1.0)
    assert canonicalize_brand_label("DISA") == ("CEPSA", "CEPSA", 1.0)
    assert canonicalize_brand_label("SAN ISIDRO") == ("SAN ISIDRO", "SAN ISIDRO", 1.0)
    assert canonicalize_brand_label("ALSA") == ("ALSA", "ALSA", 1.0)
    assert canonicalize_brand_label("STAR PETROLEUM") == ("STAR PETROLEUM", "STAR PETROLEUM", 1.0)
    assert canonicalize_brand_label("AN ENERGETICOS") == ("AN ENERGETICOS", "AN ENERGETICOS", 1.0)
    assert canonicalize_brand_label("AIRA OIL") == ("AIRA OIL", "AIRA OIL", 1.0)
    assert canonicalize_brand_label("AIREMAR") == ("AIREMAR", "AIREMAR", 1.0)


def test_targeted_suffix_brand_rules_do_not_overmatch() -> None:
    examples = {
        "AREA BP NORTE": "BP",
        "INBPENERGY": "BP",
        "AN": "AN ENERGETICOS",
        "AIRA": "AIRA OIL",
        "AIREMARINE": "AIREMAR",
    }
    for raw, unsafe_canonical in examples.items():
        canonical, _, confidence = canonicalize_brand_label(raw)
        assert canonical != unsafe_canonical or confidence < 1.0, (
            f"{raw!r} should not be a broad match for {unsafe_canonical!r}"
        )


def test_unrelated_label_not_mapped_to_cepsa() -> None:
    """Labels containing neither CEPSA nor MOEVE as a standalone token must not map to CEPSA."""
    for raw in (
        "GASOLINERA INDEPENDIENTE",  # no CEPSA/MOEVE at all
        "REPSOL",
        "BALLENOIL",
        "ACADEMIA DE CONDUCCION",    # no CEPSA/MOEVE
        "CEPSATO",                   # CEPSA substring without right separator
    ):
        canonical, _, _ = canonicalize_brand_label(raw)
        assert canonical != "CEPSA", f"{raw!r} should NOT map to CEPSA"


def test_benzina_prefix_family_canonicalizes_to_benzina() -> None:
    """BENZINA is a small Valencian Community brand (5 stations); its compound labels
    must map to the BENZINA canonical.  BENZINERA / BENZINERES (generic Catalan word for
    'gas station') must NOT be merged into BENZINA."""
    # Positive: all known BENZINA labels
    for label in (
        "BENZINA",
        "BENZINA ALAQUAS",
        "BENZINA CARBURANTES",
        "BENZINA CARBURANTES PEGO",
    ):
        canonical, _, conf = canonicalize_brand_label(label)
        assert canonical == "BENZINA" and conf == 1.0, (
            f"Expected BENZINA@1.0, got {canonical!r}@{conf} for {label!r}"
        )
    # Negative: BENZINERA / BENZINERES must NOT merge with BENZINA
    for label in (
        "BENZINERA CASTELLBISBAL",
        "BENZINERA GRANOLLERS",
        "BENZINERA LA GARRIGA",
        "BENZINERA MARTINET",
        "BENZINERA SANTA SUSANNA",
        "BENZINERA VILAMARXANT",
        'BENZINERA  " 38 "',
        "BENZINERES MONTOIL",
    ):
        canonical, _, conf = canonicalize_brand_label(label)
        assert canonical != "BENZINA", (
            f"BENZINERA/BENZINERES must not map to BENZINA, got {canonical!r} for {label!r}"
        )
    # Negative: token-anywhere matching must be blocked for BENZINA
    canonical, _, conf = canonicalize_brand_label("X BENZINA Y")
    assert canonical != "BENZINA", (
        f"'X BENZINA Y' must not token-match BENZINA, got {canonical!r}"
    )


def test_brand_normalization_v15_negative_guard_overmatching() -> None:
    """Regression guards — none of these labels must be over-merged into a short canonical.
    Sourced from task spec 'negative tests protecting against overmatching'."""
    # BP: only prefix / B.P. / quoted-BP are safe; internal-token BP must NOT match
    canonical, _, _ = canonicalize_brand_label("ABP SERVICE")
    assert canonical != "BP", f"ABP SERVICE must not map to BP, got {canonical!r}"
    canonical, _, _ = canonicalize_brand_label("X BP TEST")
    assert canonical != "BP", f"X BP TEST must not map to BP, got {canonical!r}"

    # DST: prefix-only; internal DST must not match
    canonical, _, _ = canonicalize_brand_label("DSTATION SERVICE")
    assert canonical != "DST", f"DSTATION SERVICE must not map to DST, got {canonical!r}"
    canonical, _, _ = canonicalize_brand_label("X DST TEST")
    assert canonical != "DST", f"X DST TEST must not map to DST, got {canonical!r}"

    # VCC: prefix-only; prefix-mismatch and suffix-only must not match
    canonical, _, _ = canonicalize_brand_label("AVCC SERVICE")
    assert canonical != "VCC", f"AVCC SERVICE must not map to VCC, got {canonical!r}"
    canonical, _, _ = canonicalize_brand_label("VCCX GAS")
    assert canonical != "VCC", f"VCCX GAS must not map to VCC, got {canonical!r}"

    # PETRO*: no generic PETRO canonical
    for label, forbidden in (
        ("PETRO G24", "PETRO"),
        ("PETROALACANT", "PETRO"),
        ("PETRO GRADO", "PETRO"),
        ("PETRO SWAP", "PETRO"),
        ("PETRO7", "PETRO"),
    ):
        canonical, _, _ = canonicalize_brand_label(label)
        assert canonical != forbidden, (
            f"{label!r} must not map to generic {forbidden!r}, got {canonical!r}"
        )

    # PETROL*: no generic PETROL canonical
    for label in ("PETROLAVILA", "PETROL A RUA", "PETROL MOSTOLES", "PETROL RED", "PETROLCAR"):
        canonical, _, _ = canonicalize_brand_label(label)
        assert canonical != "PETROL", (
            f"{label!r} must not map to generic PETROL, got {canonical!r}"
        )

    # Generic words must not produce canonical brand labels
    canonical, _, _ = canonicalize_brand_label("CARBURANTES LA ESTRELLA")
    assert canonical != "CARBURANTES", (
        f"'CARBURANTES LA ESTRELLA' must not map to CARBURANTES, got {canonical!r}"
    )
    canonical, _, _ = canonicalize_brand_label("COMBUSTIBLES GOMEZ")
    assert canonical != "COMBUSTIBLES", (
        f"'COMBUSTIBLES GOMEZ' must not map to COMBUSTIBLES, got {canonical!r}"
    )

    # BENZINERA: must not map to BENZINA
    canonical, _, _ = canonicalize_brand_label("BENZINERA RANDOM TOWN")
    assert canonical != "BENZINA", (
        f"'BENZINERA RANDOM TOWN' must not map to BENZINA, got {canonical!r}"
    )

    # HAM: prefix-only; internal-token must not match
    canonical, _, _ = canonicalize_brand_label("HAMMER OIL")
    assert canonical != "HAM", f"HAMMER OIL must not map to HAM, got {canonical!r}"

    # Q8/QP: prefix-only; internal-token must not match
    canonical, _, _ = canonicalize_brand_label("X Q8 TEST")
    assert canonical != "Q8", f"X Q8 TEST must not map to Q8, got {canonical!r}"
    canonical, _, _ = canonicalize_brand_label("X QP TEST")
    assert canonical != "QP", f"X QP TEST must not map to QP, got {canonical!r}"

    # TGAS: prefix-only; prefix-mismatch must not match
    canonical, _, _ = canonicalize_brand_label("TGASOLINA")
    assert canonical != "TGAS", f"TGASOLINA must not map to TGAS, got {canonical!r}"


def run() -> None:
    test_filter_single_rotulo()
    test_filter_multi_rotulo()
    test_prices_parsed()
    test_registry_fetch_all()
    test_registry_fetch_filtered()
    test_adapter_no_network()
    test_missing_coords_skipped()
    test_brand_registry_v14_canonicalizes_long_tail_labels()
    test_brand_registry_v9_canonicalizes_manual_audit_aliases()
    test_brand_registry_v9_canonicalizes_generic_descriptor_duplicates_conservatively()
    test_generic_business_descriptors_are_not_global_brands()
    test_moeve_exact_maps_to_cepsa()
    test_cepsa_moeve_exact_maps_to_cepsa()
    test_moeve_compound_prefix_maps_to_cepsa()
    test_cepsa_compound_prefix_maps_to_cepsa()
    test_disa_compound_prefix_follows_exact_disa_canonical()
    test_dst_compound_prefix_maps_to_dst()
    test_cepsa_moeve_token_in_middle_or_end_maps_to_cepsa()
    test_safe_brand_token_matching_maps_known_brands_anywhere()
    test_targeted_suffix_brand_rules_group_known_families()
    test_bp_prefix_labels_map_to_bp_without_broad_token_matching()
    test_branch_prefix_brand_families_map_without_broad_short_token_matching()
    test_petro_like_families_map_without_generic_petro_canonical()
    test_petrol_q8_qp_renesur_tgas_prefix_families_canonicalize_conservatively()
    test_petrol_q8_qp_tgas_prefix_rules_do_not_overmatch()
    test_vcc_prefix_family_maps_without_broad_token_matching()
    test_brand_token_matching_respects_boundaries()
    test_unsafe_short_or_generic_aliases_are_not_token_matched()
    test_manual_audit_aliases_do_not_overmatch()
    test_exact_alias_behavior_remains_unchanged()
    test_targeted_suffix_brand_rules_do_not_overmatch()
    test_unrelated_label_not_mapped_to_cepsa()
    test_brand_registry_v15_version_bumped()
    test_benzina_prefix_family_canonicalizes_to_benzina()
    test_brand_normalization_v15_negative_guard_overmatching()
    print("OK: adapter checks passed")


if __name__ == "__main__":
    run()
