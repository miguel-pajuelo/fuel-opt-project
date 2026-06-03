from __future__ import annotations

import re

from app.data_sources.adapters import BrandRegistry, MineturFilterAdapter, normalize_brand_label


# Values verified against docs/rotulos_catalog.txt generated from live MINETUR.
NORMALIZATION_VERSION = "brand-registry-v15"

REPSOL = MineturFilterAdapter("Repsol", ["REPSOL", "CAMPSA", "CAMPSA EXPRESS", "PETRONOR"])

CEPSA = MineturFilterAdapter("Cepsa", ["CEPSA", "MOEVE", "CEPSA-MOEVE", "MOEVE-CEPSA", "DISA"])

BP = MineturFilterAdapter("BP", ["BP", "B.P.", "BP OIL", "BP OIL ESPANA", "BP OIL ESPANA, S.A.U.", '"BP"'])

ANDAMUR = MineturFilterAdapter(
    "Andamur",
    [
        "ANDAMUR",
        'ANDAMUR "EL LIMITE"',
        'ANDAMUR "GUARROMAN"',
        'ANDAMUR "LA JONQUERA"',
        'ANDAMUR "LORCA"',
        'ANDAMUR "SAN ROMAN"',
    ],
)

AN_ENERGETICOS = MineturFilterAdapter("AN Energeticos", ["AN ENERGETICOS"])

AIRA_OIL = MineturFilterAdapter("Aira Oil", ["AIRA OIL"])

AIREMAR = MineturFilterAdapter("Airemar", ["AIREMAR"])

SHELL = MineturFilterAdapter("Shell", ["SHELL"])

GALP = MineturFilterAdapter("Galp", ["GALP", "GALP&GO"])

BALLENOIL = MineturFilterAdapter("Ballenoil", ["BALLENOIL"])

TOTAL = MineturFilterAdapter("TotalEnergies", ["TOTAL", "TOTALENERGIES", "ESSO"])

PLENERGY = MineturFilterAdapter("Plenergy", ["PLENERGY", "PLENOIL"])

PLENITUDE = MineturFilterAdapter("Plenitude", ["PLENITUDE"])

MEROIL = MineturFilterAdapter("Meroil", ["MEROIL", "MEROIL, S.L.", "MEROIL (FER PREU JUST)"])

Q8 = MineturFilterAdapter("Q8", ["Q8", "Q8 EASY", "Q8EASY", "KUWAIT PETROLEUM"])
QP = MineturFilterAdapter("QP", ["QP"])

PETROPRIX = MineturFilterAdapter("Petroprix", ["PETROPRIX"])

AVIA = MineturFilterAdapter("Avia", ["AVIA"])

BONAREA = MineturFilterAdapter("Bonarea", ["BONAREA"])

ALCAMPO = MineturFilterAdapter("Alcampo", ["ALCAMPO", "ALCAMPO S.A.", "ALCAMPO, S.A."])

CARREFOUR = MineturFilterAdapter("Carrefour", ["CARREFOUR"])

CARBUGAL = MineturFilterAdapter(
    "Carbugal",
    [
        "CARBUGAL",
        "CARBUGAL A BARCALA",
        "CARBUGAL A GRELA",
        "CARBUGAL ALVEDRO",
        "CARBUGAL CARBALLO",
        "CARBUGAL CEE",
        "CARBUGAL COLISEUM",
        "CARBUGAL CORISTANCO",
        "CARBUGAL CORTIÑAN",
        "CARBUGAL FUENLABRADA",
        "CARBUGAL LARAXE",
        "CARBUGAL LOS ROSALES",
        "CARBUGAL MEICENDE",
        "CARBUGAL SABÓN",
        "CARBUGAL SADA",
        "CARBUGAL SANTIAGO",
        "CARBUGAL TOMIÑO",
    ],
)

EROSKI = MineturFilterAdapter("Eroski", ["EROSKI"])

EL_CORTE_INGLES = MineturFilterAdapter("El Corte Ingles", ["EL CORTE INGLES", "ECI"])

LECLERC = MineturFilterAdapter("Leclerc", ["LECLERC", "E.LECLERC", "E. LECLERC"])

ESCLATOIL = MineturFilterAdapter("Esclatoil", ["ESCLATOIL"])
VALCARCE = MineturFilterAdapter("Valcarce", ["VALCARCE"])
VCC = MineturFilterAdapter("VCC", ["VCC"])
AGLA = MineturFilterAdapter("Agla", ["AGLA"])
EXOIL = MineturFilterAdapter("Exoil", ["EXOIL"])
GACOSUR = MineturFilterAdapter("Gacosur", ["GACOSUR"])
GV_OIL = MineturFilterAdapter("GV Oil", ["GV OIL", "GVOIL"])
H2EXAGON = MineturFilterAdapter("H2Exagon", ["H2EXAGON"])
H2GO = MineturFilterAdapter("H2Go", ["H2GO"])
HAM = MineturFilterAdapter("HAM", ["HAM"])
GASEXPRESS = MineturFilterAdapter("Gasexpress", ["GASEXPRESS", "GAS EXPRESS"])
BEROIL = MineturFilterAdapter("Beroil", ["BEROIL"])
ENI = MineturFilterAdapter("Eni", ["ENI", "ENI1"])
TAMOIL = MineturFilterAdapter("Tamoil", ["TAMOIL"])
MOLGAS = MineturFilterAdapter("Molgas", ["MOLGAS"])
IDS = MineturFilterAdapter("IDS", ["IDS"])
IBERDOEX = MineturFilterAdapter("Iberdoex", ["IBERDOEX"])
NATURGY = MineturFilterAdapter("Naturgy", ["NATURGY"])
ASC = MineturFilterAdapter("ASC Carburantes", ["ASC CARBURANTES"])
AUTONETOIL = MineturFilterAdapter("Autonetoil", ["AUTONETOIL", "AUTONET&OIL", "AUTONET OIL"])
EASYGAS = MineturFilterAdapter("Easygas", ["EASYGAS"])
PETROCAT = MineturFilterAdapter("Petrocat", ["PETROCAT", "PETROCAT DIRECTE"])
PETROMIRALLES = MineturFilterAdapter("Petromiralles", ["PETROMIRALLES"])
MASOIL = MineturFilterAdapter("Masoil", ["MASOIL"])
NORPETROL = MineturFilterAdapter("Norpetrol", ["NORPETROL"])
PETROCASH = MineturFilterAdapter("Petrocash", ["PETROCASH"])
PETRO_PINTO = MineturFilterAdapter("Petro Pinto", ["PETRO PINTO", "PETRO PINTO S.L.", "PETRO-PINTO,S.L."])
PETROIL_ENERGY = MineturFilterAdapter("Petroil Energy", ["PETROIL ENERGY"])
GM_OIL = MineturFilterAdapter("GM Oil", ["GM OIL", "GMOIL"])
PCAN = MineturFilterAdapter("Pcan", ["PCAN"])
CONFORT_AUTO = MineturFilterAdapter("Confort Auto", ["CONFORT AUTO"])
COMBUSTIBLES_LA_MURADA = MineturFilterAdapter(
    "Combustibles La Murada",
    ["COMBUSTIBLES LA MURADA", "COMBUSTIBLES LA MURADA,S.L."],
)
FAMILY_ENERGY = MineturFilterAdapter("Family Energy", ["FAMILY ENERGY"])
SUPECO = MineturFilterAdapter("Supeco", ["SUPECO"])
T9 = MineturFilterAdapter("T9", ["T9"])
BDMED = MineturFilterAdapter("BDMED", ["BDMED"])
DST = MineturFilterAdapter("DST", ["DST"])
STAROIL = MineturFilterAdapter("Staroil", ["STAROIL"])
FAST_FUEL = MineturFilterAdapter("Fast Fuel", ["FAST FUEL"])
PETREM = MineturFilterAdapter("Petrem", ["PETREM"])
ECONOIL = MineturFilterAdapter("Econoil", ["ECONOIL"])
HAFESA = MineturFilterAdapter("Hafesa", ["HAFESA OIL", "HAFESA"])
OILPRIX = MineturFilterAdapter("Oilprix", ["OILPRIX"])
COSTCO = MineturFilterAdapter("Costco", ["COSTCO"])
LOWCOSTFUEL = MineturFilterAdapter("Lowcostfuel", ["LOWCOSTFUEL", "LOW COST FUEL"])
SEROIL = MineturFilterAdapter("Seroil Energy", ["SEROIL ENERGY", "SEROIL"])
NIEVES = MineturFilterAdapter("Nieves", ["NIEVES"])
CEREALES_TERUEL = MineturFilterAdapter("Cereales Teruel", ["CEREALES TERUEL"])
FARRUCO = MineturFilterAdapter("Farruco", ["FARRUCO S.A.", "FARRUCO SA", "FARRUCO"])
ALSA = MineturFilterAdapter("Alsa", ["ALSA"])
SETTRAN = MineturFilterAdapter("Settran", ["SETTRAN"])
GASOLEOS_TERUEL = MineturFilterAdapter("Gasoleos Teruel", ["GASOLEOS TERUEL", "GASÓLEOS TERUEL"])
MLC = MineturFilterAdapter("MLC", ["MLC"])
GASOLWIN = MineturFilterAdapter("Gasolwin", ["GASOLWIN"])
GEDS = MineturFilterAdapter("Geds", ["GEDS"])
NAFTE = MineturFilterAdapter("Nafte", ["NAFTE"])
NUROIL = MineturFilterAdapter("Nuroil", ["NUROIL"])
AGROPAL = MineturFilterAdapter("Agropal", ["AGROPAL"])
ALAS = MineturFilterAdapter("Alas", ["ALAS"])
ENERGY_CARBURANTES = MineturFilterAdapter("Energy Carburantes", ["ENERGY CARBURANTES"])
EUSKADILOWCOST = MineturFilterAdapter("Euskadilowcost", ["EUSKADILOWCOST"])
LAS_PALMERAS = MineturFilterAdapter("Las Palmeras", ["LAS PALMERAS"])
V2_GASOLINERAS = MineturFilterAdapter("V2 Gasolineras", ["V2 GASOLINERAS"])
ADELFAS_OIL = MineturFilterAdapter("Adelfas Oil", ["ADELFAS OIL"])
ALIARA_ENERGIA = MineturFilterAdapter("Aliara Energia", ["ALIARA ENERGIA", "ALIARA ENERGÍA"])
ANEU_OIL = MineturFilterAdapter("Aneu Oil", ["ANEU OIL", "ANEUOIL"])
CAMPOASTUR = MineturFilterAdapter("Campoastur", ["CAMPOASTUR"])
DEOIL = MineturFilterAdapter("Deoil", ["DEOIL"])
ORTEGAL_OIL = MineturFilterAdapter("Ortegal Oil", ["ORTEGAL OIL"])
SBC = MineturFilterAdapter("SBC", ["SBC"])
SIS_CARBURANTES = MineturFilterAdapter("Sis Carburantes", ["SIS CARBURANTES"])
BENZOIL = MineturFilterAdapter("Benzoil", ["BENZOIL"])
EUROCAM = MineturFilterAdapter("Eurocam", ["EUROCAM"])
EVOLUTION = MineturFilterAdapter("Evolution", ["EVOLUTION"])
HEMEGAS = MineturFilterAdapter("Hemegas", ["HEMEGAS"])
IBESSA = MineturFilterAdapter("Ibessa", ["IBESSA"])
INPEALSA = MineturFilterAdapter("Inpealsa", ["INPEALSA"])
JAENCOOP = MineturFilterAdapter("Jaencoop", ["JAENCOOP", "JAENCOOP ENERGY"])
JUST_FUEL = MineturFilterAdapter("Just Fuel", ["JUST FUEL"])
MINIOIL = MineturFilterAdapter("Minioil", ["MINIOIL"])
OCEANO = MineturFilterAdapter("Oceano", ["OCEANO", "OCÉANO"])
PETROL_GO = MineturFilterAdapter("Petrol & Go", ["PETROL & GO", "PETROL&GO"])
PETROLOWCOST = MineturFilterAdapter("Petrolowcost", ["PETROLOWCOST"])
REPOSTANDO = MineturFilterAdapter("Repostando", ["REPOSTANDO"])
REPOSTAR = MineturFilterAdapter("Repostar", ["REPOSTAR"])
SAN_ISIDRO = MineturFilterAdapter("San Isidro", ["SAN ISIDRO"])
AUTOFUEL = MineturFilterAdapter("Autofuel", ["AUTOFUEL", "AUTOFUEL EXPRESS", "AUTOFUEL LOW COST"])
AUTOIL = MineturFilterAdapter(
    "Autoil",
    [
        "AUTOIL",
        "AUTOIL BENIFAIÓ",
        "AUTOIL FOIOS",
        "AUTOIL MASSANASSA",
        "AUTOIL MUSEROS",
        "AUTOIL OROPESA",
        "AUTOIL PAIPORTA",
        "AUTOIL PICASSENT",
        "AUTOIL PUZOL",
        "AUTOIL SEGORBE",
    ],
)
AVANZA = MineturFilterAdapter(
    "Avanza",
    [
        "AVANZA",
        "AVANZA OIL",
        "AVANZA ENERGY",
        "AVANZA LOW COST",
        "AVANZA OIL FIGUERES",
        "AVANZA OIL PAMPLONA",
    ],
)
BALLUS_BAIX_COST = MineturFilterAdapter("Ballus Baix Cost", ["BALLUS BAIX COST", "BALLUS BAIXCOST"])
BARATOIL = MineturFilterAdapter("Baratoil", ["BARATOIL"])
# "Benzina" is both the Valencian/Catalan word for gasoline AND a coherent small brand
# operating in the Valencian Community.  Exact BENZINA + compound BENZINA <loc> labels
# (all 5 stations in the DB are in Valencia/Alicante and clearly the same operator).
# BENZINERA / BENZINERES are the generic Catalan word for "gas station" and must NOT be
# merged here — they stay in manual-review territory.
BENZINA = MineturFilterAdapter("Benzina", ["BENZINA"])
BIESA = MineturFilterAdapter("Biesa", ["BIESA"])
CANARY_OIL = MineturFilterAdapter("Canary Oil", ["CANARY OIL", "CANARY OIL, S.L."])
ENERPLUS = MineturFilterAdapter("Enerplus", ["ENERPLUS"])
EURONOR_ENERGY = MineturFilterAdapter("Euronor Energy", ["EURONOR ENERGY"])
FULL_GO = MineturFilterAdapter("Full & Go", ["FULL & GO"])
GLOBAL_OIL = MineturFilterAdapter("Global Oil", ["GLOBAL OIL"])
GUGAS = MineturFilterAdapter("Gugas", ["GUGAS"])
ICOR_ENERGIA = MineturFilterAdapter("Icor Energia", ["ICOR ENERGIA"])
LABOIL = MineturFilterAdapter("Laboil", ["LABOIL", "LABOIL, S.L.", "LABOIL, S.L"])
MAXPETROL = MineturFilterAdapter("Maxpetrol", ["MAXPETROL"])
MOSCARDO = MineturFilterAdapter("Moscardo", ["MOSCARDO", "MOSCARDÓ"])
PARA_Y_SIGUE = MineturFilterAdapter("Para y Sigue", ["PARA Y SIGUE"])
PETRO_VALLES = MineturFilterAdapter("Petro Valles", ["PETRO VALLES"])
PETROLIS = MineturFilterAdapter("Petrolis", ["PETROLIS", "PETROLIS INDEPENDENTS", "PETROLIS INDEPENDENTS - PETRO7", "PETROLIS DE BARCELONA"])
RHR = MineturFilterAdapter("RHR", ["RHR"])
RENESUR = MineturFilterAdapter("Renesur", ["RENESUR"])
SPL = MineturFilterAdapter("SPL", ["SPL"])
STAR_PETROLEUM = MineturFilterAdapter("Star Petroleum", ["STAR PETROLEUM"])
TGAS = MineturFilterAdapter("Tgas", ["TGAS"])
URBAN_OIL = MineturFilterAdapter("Urban Oil", ["URBAN OIL"])
ZONA_DIESEL = MineturFilterAdapter("Zona Diesel", ["ZONA DIESEL"])

UNBRANDED_LABELS = {
    "",
    "(SIN ROTULO)",
    "-",
    "0",
    "BLANCA",
    "BLANCO",
    "LIBRE",
    "NINGUNO",
    "NO",
    "NO TIENE",
    "SIN ROTULO",
}


def build_default_registry() -> BrandRegistry:
    registry = BrandRegistry()
    for adapter in [
        REPSOL,
        CEPSA,
        BP,
        AN_ENERGETICOS,
        ANDAMUR,
        AIRA_OIL,
        AIREMAR,
        SHELL,
        GALP,
        BALLENOIL,
        TOTAL,
        PLENERGY,
        PLENITUDE,
        MEROIL,
        Q8,
        QP,
        PETROPRIX,
        AVIA,
        BONAREA,
        ALCAMPO,
        CARREFOUR,
        CARBUGAL,
        EROSKI,
        EL_CORTE_INGLES,
        LECLERC,
        ESCLATOIL,
        VALCARCE,
        VCC,
        AGLA,
        EXOIL,
        GACOSUR,
        GV_OIL,
        H2EXAGON,
        H2GO,
        HAM,
        GASEXPRESS,
        BEROIL,
        ENI,
        TAMOIL,
        MOLGAS,
        IDS,
        IBERDOEX,
        NATURGY,
        ASC,
        AUTONETOIL,
        EASYGAS,
        PETROCAT,
        PETROMIRALLES,
        MASOIL,
        NORPETROL,
        PETROCASH,
        PETRO_PINTO,
        PETROIL_ENERGY,
        GM_OIL,
        PCAN,
        CONFORT_AUTO,
        COMBUSTIBLES_LA_MURADA,
        FAMILY_ENERGY,
        SUPECO,
        T9,
        BDMED,
        DST,
        STAROIL,
        FAST_FUEL,
        PETREM,
        ECONOIL,
        HAFESA,
        OILPRIX,
        COSTCO,
        LOWCOSTFUEL,
        SEROIL,
        NIEVES,
        CEREALES_TERUEL,
        FARRUCO,
        ALSA,
        SETTRAN,
        GASOLEOS_TERUEL,
        MLC,
        GASOLWIN,
        GEDS,
        NAFTE,
        NUROIL,
        AGROPAL,
        ALAS,
        ENERGY_CARBURANTES,
        EUSKADILOWCOST,
        LAS_PALMERAS,
        V2_GASOLINERAS,
        ADELFAS_OIL,
        ALIARA_ENERGIA,
        ANEU_OIL,
        CAMPOASTUR,
        DEOIL,
        ORTEGAL_OIL,
        SBC,
        SIS_CARBURANTES,
        BENZOIL,
        EUROCAM,
        EVOLUTION,
        HEMEGAS,
        IBESSA,
        INPEALSA,
        JAENCOOP,
        JUST_FUEL,
        MINIOIL,
        OCEANO,
        PETROL_GO,
        PETROLOWCOST,
        REPOSTANDO,
        REPOSTAR,
        SAN_ISIDRO,
        AUTOFUEL,
        AUTOIL,
        AVANZA,
        BALLUS_BAIX_COST,
        BARATOIL,
        BENZINA,
        BIESA,
        CANARY_OIL,
        ENERPLUS,
        EURONOR_ENERGY,
        FULL_GO,
        GLOBAL_OIL,
        GUGAS,
        ICOR_ENERGIA,
        LABOIL,
        MAXPETROL,
        MOSCARDO,
        PARA_Y_SIGUE,
        PETRO_VALLES,
        PETROLIS,
        RHR,
        RENESUR,
        SPL,
        STAR_PETROLEUM,
        TGAS,
        URBAN_OIL,
        ZONA_DIESEL,
    ]:
        registry.register(adapter)
    return registry


def build_full_registry() -> BrandRegistry:
    """Registry with known MINETUR brands plus Ballenoil's legacy scraper adapter."""
    from app.data_sources.adapters_scraping import BallenoilAdapter

    registry = build_default_registry()
    registry.register(BallenoilAdapter())
    return registry


DEFAULT_REGISTRY = build_default_registry()


def canonical_brand_id(brand_name: str) -> str:
    label = normalize_brand_label(brand_name).lower()
    label = re.sub(r"[^a-z0-9]+", "-", label).strip("-")
    return label or "unknown"


# Prefix rules for compound raw labels created during brand transitions/rebranding.
# A raw label that begins with one of these prefixes is confidently mapped to the
# associated canonical even though the full compound string is not a registered alias.
# confidence=1.0 so these stations appear in /brands counts and brand filters.
# Only add entries here when the brand token unambiguously identifies the parent brand
# (e.g. "MOEVE VILANOVA" → CEPSA, "CEPSA LA GALIA" → CEPSA).
_BRAND_PREFIX_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    # BENZINA: small Valencian Community brand; compound labels follow "BENZINA <location>"
    # pattern.  BENZINERA / BENZINERES are NOT included — they're generic Catalan words.
    (("BENZINA ",), "BENZINA"),
    (("CEPSA ", "CEPSA-", "CEPSA/", "CEPSA("), "CEPSA"),
    (("DISA ", "DISA-", "DISA/", "DISA /"), "CEPSA"),
    (("DST ", "DST-", "DST/", "DST /"), "DST"),
    (("EXOIL ", "EXOIL-", "EXOIL/", "EXOIL /"), "EXOIL"),
    (("GACOSUR ", "GACOSUR-", "GACOSUR/", "GACOSUR /"), "GACOSUR"),
    (("H2EXAGON ", "H2EXAGON-", "H2EXAGON/", "H2EXAGON /"), "H2EXAGON"),
    (("H2GO ", "H2GO-", "H2GO/", "H2GO /"), "H2GO"),
    (("HAM ", "HAM-", "HAM/", "HAM /"), "HAM"),
    (("MASOIL ", "MASOIL-", "MASOIL/", "MASOIL /"), "MASOIL"),
    (("MOEVE ", "MOEVE-", "MOEVE/", "MOEVE("), "CEPSA"),
    (("NORPETROL ", "NORPETROL-", "NORPETROL/", "NORPETROL /"), "NORPETROL"),
    (("PETROL & GO ", "PETROL & GO-", "PETROL & GO/", "PETROL & GO /", "PETROL & GO("), "PETROL & GO"),
    (("PETROCASH ", "PETROCASH-", "PETROCASH/", "PETROCASH /"), "PETROCASH"),
    (("PETROIL ENERGY ", "PETROIL ENERGY-", "PETROIL ENERGY/", "PETROIL ENERGY /"), "PETROIL ENERGY"),
    (("Q8 ", "Q8-", "Q8/", "Q8 /"), "Q8"),
    (("QP ", "QP-", "QP/", "QP /"), "QP"),
    (("RENESUR ", "RENESUR-", "RENESUR/", "RENESUR /"), "RENESUR"),
    (("TGAS ", "TGAS-", "TGAS/", "TGAS /"), "TGAS"),
    (("VCC ", "VCC-", "VCC/", "VCC /"), "VCC"),
)

_BP_PREFIX_LABEL_RE = re.compile(r'^(?:BP(?:$|[\s\-\/.])|B\.P\.(?:$|[\s\-\/.])|["\u201c\u201d]BP["\u201c\u201d])')


def _is_bp_prefix_label(normalized_label: str) -> bool:
    """Match clear BP labels at the beginning without enabling BP token-anywhere matching."""
    return bool(_BP_PREFIX_LABEL_RE.search(normalized_label))


_TARGETED_LABEL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^A\.?N\.?\s+ENERGETICOS(?:$|[\s\-\/(),.;:])"), "AN ENERGETICOS"),
    (re.compile(r"^AIRA OIL(?:$|[\s\-\/(),.;:])"), "AIRA OIL"),
    (re.compile(r"^AIREMAR\s+(?:I|II)$"), "AIREMAR"),
)

_TOKEN_SEPARATOR_CHARS = r'\s\-\/(),.;:"'

_UNSAFE_BRAND_TOKEN_ALIASES = {
    # Short or abbreviation-like aliases are allowed only as exact labels.
    "BP",
    "B.P.",
    '"BP"',
    "Q8",
    "Q8 EASY",
    "Q8EASY",
    "QP",
    "T9",
    "IDS",
    "DST",
    "MLC",
    "SBC",
    "RHR",
    "SPL",
    "ENI",
    "GV OIL",
    "GVOIL",
    "EXOIL",
    "GACOSUR",
    "H2EXAGON",
    "H2GO",
    "HAM",
    "MASOIL",
    "NORPETROL",
    "PETROCASH",
    "PETRO PINTO",
    "PETRO-PINTO,S.L.",
    "PETROIL ENERGY",
    "PETROL & GO",
    "PETROL&GO",
    "RENESUR",
    "TGAS",
    # Generic words/phrases and common names are too broad for anywhere-token matching.
    "TOTAL",
    "ESSO",
    "DISA",
    "ALSA",
    "SAN ISIDRO",
    "LAS PALMERAS",
    "NIEVES",
    "ALAS",
    "STAR PETROLEUM",
    "AN ENERGETICOS",
    "AIRA OIL",
    "AIREMAR",
    "GM OIL",
    "HAFESA OIL",
    "ANEU OIL",
    "ANEUOIL",
    "ANDAMUR",
    'ANDAMUR "EL LIMITE"',
    'ANDAMUR "GUARROMAN"',
    'ANDAMUR "LA JONQUERA"',
    'ANDAMUR "LORCA"',
    'ANDAMUR "SAN ROMAN"',
    "AUTOFUEL",
    "AUTOFUEL EXPRESS",
    "AUTOFUEL LOW COST",
    "AUTOIL",
    "AUTOIL BENIFAIO",
    "AUTOIL FOIOS",
    "AUTOIL MASSANASSA",
    "AUTOIL MUSEROS",
    "AUTOIL OROPESA",
    "AUTOIL PAIPORTA",
    "AUTOIL PICASSENT",
    "AUTOIL PUZOL",
    "AUTOIL SEGORBE",
    "AVANZA",
    "AVANZA OIL",
    "AVANZA ENERGY",
    "AVANZA LOW COST",
    "AVANZA OIL FIGUERES",
    "AVANZA OIL PAMPLONA",
    "BALLUS BAIX COST",
    "BALLUS BAIXCOST",
    # BENZINA is the Valencian/Catalan generic word for gasoline; block token-anywhere matching
    # to avoid capturing unrelated cooperative/descriptive labels.
    "BENZINA",
    "CARBUGAL",
    "CARBUGAL A BARCALA",
    "CARBUGAL A GRELA",
    "CARBUGAL ALVEDRO",
    "CARBUGAL CARBALLO",
    "CARBUGAL CEE",
    "CARBUGAL COLISEUM",
    "CARBUGAL CORISTANCO",
    "CARBUGAL CORTINAN",
    "CARBUGAL FUENLABRADA",
    "CARBUGAL LARAXE",
    "CARBUGAL LOS ROSALES",
    "CARBUGAL MEICENDE",
    "CARBUGAL SABON",
    "CARBUGAL SADA",
    "CARBUGAL SANTIAGO",
    "CARBUGAL TOMINO",
    "COMBUSTIBLES LA MURADA",
    "COMBUSTIBLES LA MURADA,S.L.",
    "CANARY OIL",
    "GLOBAL OIL",
    "URBAN OIL",
    "ADELFAS OIL",
    "ORTEGAL OIL",
    "LOW COST FUEL",
    "ENERGY CARBURANTES",
    "PETROL",
    "VCC",
}

_GENERIC_BRAND_TOKEN_WORDS = {
    "OIL",
    "GAS",
    "ENERGY",
    "ENERGIA",
    "CARBURANTES",
    "FUEL",
    "LOW",
    "COST",
}


def _brand_token_regex(alias: str) -> re.Pattern[str]:
    return re.compile(
        rf'(?:^|(?<=[{_TOKEN_SEPARATOR_CHARS}])){re.escape(alias)}(?=[{_TOKEN_SEPARATOR_CHARS}]|$)'
    )


def _is_safe_brand_token_alias(alias: str) -> bool:
    alias = normalize_brand_label(alias)
    if alias in _UNSAFE_BRAND_TOKEN_ALIASES:
        return False
    if len(alias) < 4 and not any(char.isdigit() for char in alias):
        return False
    if not re.search(r"[A-Z]", alias):
        return False
    if set(alias.split()) <= _GENERIC_BRAND_TOKEN_WORDS:
        return False
    return True


def _build_safe_brand_token_rules() -> tuple[tuple[str, str, re.Pattern[str]], ...]:
    rules: list[tuple[str, str, re.Pattern[str]]] = []
    for adapter in DEFAULT_REGISTRY.adapters():
        canonical = adapter.brand_name.upper()
        for alias in adapter.aliases:
            normalized_alias = normalize_brand_label(alias)
            if _is_safe_brand_token_alias(normalized_alias):
                rules.append((normalized_alias, canonical, _brand_token_regex(normalized_alias)))
    return tuple(sorted(rules, key=lambda row: (-len(row[0]), row[1], row[0])))


_SAFE_BRAND_TOKEN_RULES = _build_safe_brand_token_rules()


def _match_known_brand_token(normalized_label: str) -> tuple[str, str] | None:
    matches = [
        (alias, canonical)
        for alias, canonical, regex in _SAFE_BRAND_TOKEN_RULES
        if regex.search(normalized_label)
    ]
    if not matches:
        return None
    canonicals = {canonical for _, canonical in matches}
    if len(canonicals) != 1:
        return None
    alias, canonical = matches[0]
    return canonical, alias


def canonicalize_brand_label(raw_label: str) -> tuple[str, str, float]:
    label = raw_label.upper().strip() or "UNKNOWN"
    normalized_label = normalize_brand_label(label)
    if normalized_label in UNBRANDED_LABELS:
        return "UNKNOWN", "UNKNOWN", 0.0
    for adapter in DEFAULT_REGISTRY.adapters():
        if normalized_label in adapter.aliases:
            canonical = adapter.brand_name.upper()
            return canonical, canonical, 1.0
    if _is_bp_prefix_label(normalized_label):
        return "BP", "BP", 1.0
    for regex, canonical in _TARGETED_LABEL_RULES:
        if regex.search(normalized_label):
            return canonical, canonical, 1.0
    # Fast-path: prefix rules for compound labels beginning with the brand token.
    for prefixes, canonical in _BRAND_PREFIX_RULES:
        if normalized_label.startswith(prefixes):
            return canonical, canonical, 1.0
    token_match = _match_known_brand_token(normalized_label)
    if token_match:
        canonical, _alias = token_match
        return canonical, canonical, 1.0
    return label, label, 0.0 if label == "UNKNOWN" else 0.5


def ui_brand_catalog() -> list[dict[str, object]]:
    return [
        {
            "id": canonical_brand_id(adapter.brand_name),
            "label": adapter.brand_name,
            "canonical": adapter.brand_name.upper(),
            "aliases": list(adapter.aliases),
        }
        for adapter in DEFAULT_REGISTRY.adapters()
    ]
