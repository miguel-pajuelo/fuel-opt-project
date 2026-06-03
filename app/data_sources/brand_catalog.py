from __future__ import annotations

import re

from app.data_sources.adapters import BrandRegistry, MineturFilterAdapter, normalize_brand_label


# Values verified against docs/rotulos_catalog.txt generated from live MINETUR.
NORMALIZATION_VERSION = "brand-registry-v3"

REPSOL = MineturFilterAdapter("Repsol", ["REPSOL", "CAMPSA", "CAMPSA EXPRESS", "PETRONOR"])

CEPSA = MineturFilterAdapter("Cepsa", ["CEPSA", "MOEVE", "CEPSA-MOEVE", "MOEVE-CEPSA", "DISA"])

BP = MineturFilterAdapter("BP", ["BP", "BP OIL", "BP OIL ESPANA", "BP OIL ESPANA, S.A.U.", '"BP"'])

SHELL = MineturFilterAdapter("Shell", ["SHELL"])

GALP = MineturFilterAdapter("Galp", ["GALP", "GALP&GO"])

BALLENOIL = MineturFilterAdapter("Ballenoil", ["BALLENOIL"])

TOTAL = MineturFilterAdapter("TotalEnergies", ["TOTAL", "TOTALENERGIES", "ESSO"])

PLENERGY = MineturFilterAdapter("Plenergy", ["PLENERGY", "PLENOIL"])

PLENITUDE = MineturFilterAdapter("Plenitude", ["PLENITUDE"])

MEROIL = MineturFilterAdapter("Meroil", ["MEROIL", "MEROIL, S.L.", "MEROIL (FER PREU JUST)"])

Q8 = MineturFilterAdapter("Q8", ["Q8", "Q8 EASY", "KUWAIT PETROLEUM"])

PETROPRIX = MineturFilterAdapter("Petroprix", ["PETROPRIX"])

AVIA = MineturFilterAdapter("Avia", ["AVIA"])

BONAREA = MineturFilterAdapter("Bonarea", ["BONAREA"])

ALCAMPO = MineturFilterAdapter("Alcampo", ["ALCAMPO", "ALCAMPO S.A.", "ALCAMPO, S.A."])

CARREFOUR = MineturFilterAdapter("Carrefour", ["CARREFOUR"])

EROSKI = MineturFilterAdapter("Eroski", ["EROSKI"])

EL_CORTE_INGLES = MineturFilterAdapter("El Corte Ingles", ["EL CORTE INGLES", "ECI"])

LECLERC = MineturFilterAdapter("Leclerc", ["LECLERC", "E.LECLERC", "E. LECLERC"])

ESCLATOIL = MineturFilterAdapter("Esclatoil", ["ESCLATOIL"])
VALCARCE = MineturFilterAdapter("Valcarce", ["VALCARCE"])
AGLA = MineturFilterAdapter("Agla", ["AGLA"])
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
GM_OIL = MineturFilterAdapter("GM Oil", ["GM OIL", "GMOIL"])
PCAN = MineturFilterAdapter("Pcan", ["PCAN"])
CONFORT_AUTO = MineturFilterAdapter("Confort Auto", ["CONFORT AUTO"])
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
ANEU_OIL = MineturFilterAdapter("Aneu Oil", ["ANEU OIL"])
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
PETROL_GO = MineturFilterAdapter("Petrol & Go", ["PETROL & GO"])
PETROLOWCOST = MineturFilterAdapter("Petrolowcost", ["PETROLOWCOST"])
REPOSTANDO = MineturFilterAdapter("Repostando", ["REPOSTANDO"])
REPOSTAR = MineturFilterAdapter("Repostar", ["REPOSTAR"])
SAN_ISIDRO = MineturFilterAdapter("San Isidro", ["SAN ISIDRO"])
AVANZA = MineturFilterAdapter("Avanza", ["AVANZA OIL", "AVANZA ENERGY", "AVANZA LOW COST"])
BARATOIL = MineturFilterAdapter("Baratoil", ["BARATOIL"])
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
SPL = MineturFilterAdapter("SPL", ["SPL"])
STAR_PETROLEUM = MineturFilterAdapter("Star Petroleum", ["STAR PETROLEUM"])
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
        SHELL,
        GALP,
        BALLENOIL,
        TOTAL,
        PLENERGY,
        PLENITUDE,
        MEROIL,
        Q8,
        PETROPRIX,
        AVIA,
        BONAREA,
        ALCAMPO,
        CARREFOUR,
        EROSKI,
        EL_CORTE_INGLES,
        LECLERC,
        ESCLATOIL,
        VALCARCE,
        AGLA,
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
        GM_OIL,
        PCAN,
        CONFORT_AUTO,
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
        AVANZA,
        BARATOIL,
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
        SPL,
        STAR_PETROLEUM,
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


def canonicalize_brand_label(raw_label: str) -> tuple[str, str, float]:
    label = raw_label.upper().strip() or "UNKNOWN"
    normalized_label = normalize_brand_label(label)
    if normalized_label in UNBRANDED_LABELS:
        return "UNKNOWN", "UNKNOWN", 0.0
    for adapter in DEFAULT_REGISTRY.adapters():
        if normalized_label in adapter.aliases:
            canonical = adapter.brand_name.upper()
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
