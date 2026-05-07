"""Module 4 – LCA calculation (Deliverable 5).
TRACI-style inventory model for Module 1 and 2 alternatives.
Refs: EPA TRACI 2.1; ecoinvent/Wernet 2016; CRSI 2022.
"""
from __future__ import annotations

import csv
import json
import math
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EcoinventProcess:

    short_name: str
    activity_name: str
    geography: str
    unit: str
    note: str


@dataclass(frozen=True)
class FacilityLocation:

    short_name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class LCAUnitImpacts:

    # Screening factors mapped to TRACI 2.1 categories.
    # Sources: ecoinvent/APOS (Wernet 2016), CRSI 2022, EPA TRACI 2.1, Euclid 2026.
    concrete_kgco2e_per_cy: float = 355.0
    stone_57_kgco2e_per_ton: float = 5.0
    reinforcing_steel_kgco2e_per_ton: float = 774.736
    tufstrand_sf_kgco2e_per_kg: float = 3.08
    truck_transport_kgco2e_per_ton_mile: float = 0.17
    demolition_kgco2e_per_cy_concrete: float = 3.0
    concrete_crushing_kgco2e_per_ton: float = 1.5
    virgin_aggregate_credit_kgco2e_per_ton: float = 5.0

    # Additional TRACI categories retained as screening factors for Module 7 graphics.
    acidification_kgso2e_per_kgco2e: float = 0.0025
    eutrophication_kgn_per_kgco2e: float = 0.00018
    smog_kgo3e_per_kgco2e: float = 0.0040


@dataclass(frozen=True)
class LCAInputs:

    impact_methodology: str = "TRACI 2.1"  # EPA TRACI 2.1 / Deliverable 5
    impact_category: str = "Climate change, acidification, eutrophication, smog"
    impact_unit: str = "mixed TRACI units"

    concrete_ton_per_cy: float = 2.025  # normal-weight concrete, CY -> ton
    stone_ton_per_cy: float = 1.35  # CY -> ton

    fe3_to_tufstrand_dosage_lb_per_cy: dict[float, float] | None = None  # optional Euclid FiberCalc mapping

    # Material transport distances support the Deliverable 5 construction/EOL boundary.
    stone_to_project_miles: float = 16.0
    concrete_to_project_miles: float = 18.0
    crushed_concrete_to_reuse_miles: float = 16.0
    rebar_to_project_miles: float = 12.0
    nucor_to_hymmco_miles: float = 195.0

    construction_equipment_kgco2e_per_cy_concrete: float = 1.0  # equipment proxy; Deliverable 5 feedback

    include_virgin_aggregate_credit: bool = False

    def get_tufstrand_dosage_lb_per_cy(self, fe3_psi: float) -> float:

        if self.fe3_to_tufstrand_dosage_lb_per_cy is not None:
            if fe3_psi not in self.fe3_to_tufstrand_dosage_lb_per_cy:
                raise ValueError(
                    f"No TUF-STRAND dosage mapping provided for fe3={fe3_psi}. "
                    "Update LCAInputs.fe3_to_tufstrand_dosage_lb_per_cy."
                )
            return self.fe3_to_tufstrand_dosage_lb_per_cy[fe3_psi]

        return calculate_tufstrand_sf_dosage_lb_per_cy(fe3_psi)


# Process names document the ecoinvent/APOS proxies used in Deliverable 5.
def default_process_table() -> list[EcoinventProcess]:

    return [
        EcoinventProcess(
            short_name="ready_mix_concrete",
            activity_name="concrete production, 35MPa, for building construction",
            geography="US",
            unit="m3",
            note="Ready-mix concrete production; use closest strength class to project mix.",
        ),
        EcoinventProcess(
            short_name="crushed_stone",
            activity_name="market for gravel, crushed",
            geography="GLO",
            unit="kg",
            note="#57 stone represented as crushed gravel/stone aggregate.",
        ),
        EcoinventProcess(
            short_name="reinforcing_steel",
            activity_name="market for steel, low-alloyed",
            geography="GLO",
            unit="kg",
            note="Used for reinforcing bar production when Module 1 is evaluated.",
        ),
        EcoinventProcess(
            short_name="lorry_transport",
            activity_name="market for transport, freight, lorry, unspecified",
            geography="RoW",
            unit="tkm",
            note="Used for material hauling; inventory reports ton-mi and metric tonne-km.",
        ),
        EcoinventProcess(
            short_name="construction_equipment",
            activity_name="diesel, burned in building machine",
            geography="GLO",
            unit="MJ",
            note="Screening proxy for placement/finishing equipment in construction phase.",
        ),
        EcoinventProcess(
            short_name="demolition",
            activity_name="diesel, burned in building machine",
            geography="GLO",
            unit="MJ",
            note="Proxy for demolition equipment energy/emissions.",
        ),
        EcoinventProcess(
            short_name="concrete_crushing",
            activity_name="treatment of waste concrete, not reinforced, sorting plant",
            geography="RoW",
            unit="kg",
            note="Proxy for crushing demolished concrete into recycled concrete aggregate.",
        ),
        EcoinventProcess(
            short_name="tufstrand_sf",
            activity_name="TUF-STRAND SF synthetic macrofiber, Euclid Chemical EPD/TDS",
            geography="US",
            unit="kg",
            note="Product-specific GWP from Euclid TUF-STRAND SF technical data sheet.",
        ),
    ]


def calculate_haversine_distance_miles(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:

    radius_miles = 3958.7613  # haversine earth radius, miles

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )

    return 2.0 * radius_miles * math.asin(math.sqrt(a))


def geocode_address_nominatim(
    address: str,
    user_agent: str = "ce519_lca_program",
) -> tuple[float, float]:

    # Optional geocoding support for transport distances; not required for base run.
    query = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1})
    url = f"https://nominatim.openstreetmap.org/search?{query}"

    request = urllib.request.Request(url, headers={"User-Agent": user_agent})

    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    if not data:
        raise ValueError(f"No geocoding result found for address: {address}")

    return float(data[0]["lat"]), float(data[0]["lon"])


def route_distance_miles_osrm(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> float:

    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{origin_lon},{origin_lat};{destination_lon},{destination_lat}"
        "?overview=false"
    )

    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    if data.get("code") != "Ok":
        raise ValueError(f"OSRM route request failed: {data}")

    meters = data["routes"][0]["distance"]  # OSRM route distance

    return meters / 1609.344


def calculate_tufstrand_sf_dosage_lb_per_cy(fe3_psi: float) -> float:

    if fe3_psi < 0:
        raise ValueError("fe3 must be zero or greater.")

    # Project calibration for TUF-STRAND SF dosage; Euclid 2026 / Deliverable 3.
    calculated_dosage = 0.03 * fe3_psi - 1.1

    return min(20.0, max(3.0, calculated_dosage))


def get_required_float(candidate: dict[str, Any], key: str) -> float:

    if key not in candidate:
        raise KeyError(f"Candidate is missing required field: {key}")

    value = candidate[key]

    if value in ("", None):
        raise ValueError(f"Candidate field {key} is empty.")

    return float(value)


def calculate_material_inventory(
    candidate: dict[str, Any],
    inputs: LCAInputs,
) -> dict[str, float]:

    concrete_cy = get_required_float(candidate, "concrete_volume_cy_total")
    stone_cy = get_required_float(candidate, "subbase_volume_cy_total")

    # Inventory conversions for TRACI/ecoinvent-style quantities; Deliverable 5.
    concrete_m3 = concrete_cy * 0.764554858
    concrete_tons = concrete_cy * inputs.concrete_ton_per_cy
    stone_tons = stone_cy * inputs.stone_ton_per_cy

    steel_tons = 0.0
    fiber_lb = 0.0
    fiber_kg = 0.0
    fiber_dosage_lb_per_cy = 0.0

    module = str(candidate.get("module", "")).upper()

    if module == "SRC":
        steel_tons = get_required_float(candidate, "steel_weight_ton_total")

    elif module == "FRC":
        fe3_psi = get_required_float(candidate, "fe3_psi")
        # FRC inventory uses Module 2 dosage relationship; Euclid 2026.
        fiber_dosage_lb_per_cy = inputs.get_tufstrand_dosage_lb_per_cy(fe3_psi)
        fiber_lb = fiber_dosage_lb_per_cy * concrete_cy
        fiber_kg = fiber_lb * 0.45359237  # lb -> kg

    else:
        raise ValueError(f"Unsupported module type for LCA: {module}")

    return {
        "inventory_concrete_cy": concrete_cy,
        "inventory_concrete_m3": concrete_m3,
        "inventory_concrete_tons": concrete_tons,
        "inventory_57_stone_cy": stone_cy,
        "inventory_57_stone_tons": stone_tons,
        "inventory_reinforcing_steel_tons": steel_tons,
        "inventory_tufstrand_dosage_lb_per_cy": fiber_dosage_lb_per_cy,
        "inventory_tufstrand_lb": fiber_lb,
        "inventory_tufstrand_kg": fiber_kg,
    }


def calculate_transport_inventory(
    material_inventory: dict[str, float],
    inputs: LCAInputs,
) -> dict[str, float]:

    # Ton-mile inventory for lorry transport process; ecoinvent/APOS / Deliverable 5.
    concrete_ton_miles = (
        material_inventory["inventory_concrete_tons"]
        * inputs.concrete_to_project_miles
    )

    stone_ton_miles = (
        material_inventory["inventory_57_stone_tons"]
        * inputs.stone_to_project_miles
    )

    crushed_concrete_ton_miles = (
        material_inventory["inventory_concrete_tons"]
        * inputs.crushed_concrete_to_reuse_miles
    )

    rebar_nucor_to_hymmco_ton_miles = (
        material_inventory["inventory_reinforcing_steel_tons"]
        * inputs.nucor_to_hymmco_miles
    )

    rebar_hymmco_to_project_ton_miles = (
        material_inventory["inventory_reinforcing_steel_tons"]
        * inputs.rebar_to_project_miles
    )

    rebar_total_ton_miles = (
        rebar_nucor_to_hymmco_ton_miles
        + rebar_hymmco_to_project_ton_miles
    )

    ton_mile_to_tkm = 1.459972  # US ton-mile -> metric tonne-km

    return {
        "haul_concrete_miles": inputs.concrete_to_project_miles,
        "haul_57_stone_miles": inputs.stone_to_project_miles,
        "haul_crushed_concrete_miles": inputs.crushed_concrete_to_reuse_miles,
        "haul_rebar_nucor_to_hymmco_miles": inputs.nucor_to_hymmco_miles,
        "haul_rebar_hymmco_to_project_miles": inputs.rebar_to_project_miles,
        "haul_rebar_miles": inputs.nucor_to_hymmco_miles + inputs.rebar_to_project_miles,
        "haul_fiber_miles": 0.0,
        "haul_concrete_ton_miles": concrete_ton_miles,
        "haul_57_stone_ton_miles": stone_ton_miles,
        "haul_crushed_concrete_ton_miles": crushed_concrete_ton_miles,
        "haul_rebar_nucor_to_hymmco_ton_miles": rebar_nucor_to_hymmco_ton_miles,
        "haul_rebar_hymmco_to_project_ton_miles": rebar_hymmco_to_project_ton_miles,
        "haul_rebar_ton_miles": rebar_total_ton_miles,
        "haul_fiber_ton_miles": 0.0,
        "haul_total_ton_miles": (
            concrete_ton_miles
            + stone_ton_miles
            + crushed_concrete_ton_miles
            + rebar_total_ton_miles
        ),
        "haul_concrete_tkm": concrete_ton_miles * ton_mile_to_tkm,
        "haul_57_stone_tkm": stone_ton_miles * ton_mile_to_tkm,
        "haul_crushed_concrete_tkm": crushed_concrete_ton_miles * ton_mile_to_tkm,
        "haul_rebar_tkm": rebar_total_ton_miles * ton_mile_to_tkm,
        "haul_total_tkm": (
            concrete_ton_miles
            + stone_ton_miles
            + crushed_concrete_ton_miles
            + rebar_total_ton_miles
        ) * ton_mile_to_tkm,
    }


def calculate_impacts(
    material_inventory: dict[str, float],
    transport_inventory: dict[str, float],
    unit_impacts: LCAUnitImpacts,
    inputs: LCAInputs,
) -> dict[str, float]:

    # Impact = sum(Qi * EFi); EPA TRACI 2.1 / Deliverable 5.
    concrete_gwp = material_inventory["inventory_concrete_cy"] * unit_impacts.concrete_kgco2e_per_cy
    stone_gwp = material_inventory["inventory_57_stone_tons"] * unit_impacts.stone_57_kgco2e_per_ton
    reinforcing_steel_gwp = material_inventory["inventory_reinforcing_steel_tons"] * unit_impacts.reinforcing_steel_kgco2e_per_ton
    tufstrand_gwp = material_inventory["inventory_tufstrand_kg"] * unit_impacts.tufstrand_sf_kgco2e_per_kg

    # Ecoinvent lorry process is tkm; kg CO2e factor is retained as ton-mi equivalent.
    transport_gwp = transport_inventory["haul_total_ton_miles"] * unit_impacts.truck_transport_kgco2e_per_ton_mile

    construction_equipment_gwp = (
        material_inventory["inventory_concrete_cy"]
        * inputs.construction_equipment_kgco2e_per_cy_concrete
    )
    demolition_gwp = material_inventory["inventory_concrete_cy"] * unit_impacts.demolition_kgco2e_per_cy_concrete
    crushing_gwp = material_inventory["inventory_concrete_tons"] * unit_impacts.concrete_crushing_kgco2e_per_ton

    virgin_aggregate_credit = 0.0
    if inputs.include_virgin_aggregate_credit:
        virgin_aggregate_credit = material_inventory["inventory_concrete_tons"] * unit_impacts.virgin_aggregate_credit_kgco2e_per_ton

    total_gwp = (
        concrete_gwp
        + stone_gwp
        + reinforcing_steel_gwp
        + tufstrand_gwp
        + transport_gwp
        + construction_equipment_gwp
        + demolition_gwp
        + crushing_gwp
        - virgin_aggregate_credit
    )

    # Additional TRACI categories use screening multipliers for comparison graphics.
    acidification = total_gwp * unit_impacts.acidification_kgso2e_per_kgco2e
    eutrophication = total_gwp * unit_impacts.eutrophication_kgn_per_kgco2e
    smog = total_gwp * unit_impacts.smog_kgo3e_per_kgco2e

    return {
        "gwp_concrete_kgco2e": concrete_gwp,
        "gwp_57_stone_kgco2e": stone_gwp,
        "gwp_reinforcing_steel_kgco2e": reinforcing_steel_gwp,
        "gwp_tufstrand_sf_kgco2e": tufstrand_gwp,
        "gwp_transport_kgco2e": transport_gwp,
        "gwp_construction_equipment_kgco2e": construction_equipment_gwp,
        "gwp_demolition_kgco2e": demolition_gwp,
        "gwp_crushing_kgco2e": crushing_gwp,
        "gwp_virgin_aggregate_credit_kgco2e": virgin_aggregate_credit,
        "gwp_total_project_kgco2e": total_gwp,
        "acidification_total_kgso2e": acidification,
        "eutrophication_total_kgn": eutrophication,
        "smog_total_kgo3e": smog,
    }


def calculate_gwp(
    material_inventory: dict[str, float],
    transport_inventory: dict[str, float],
    unit_impacts: LCAUnitImpacts,
    inputs: LCAInputs,
) -> dict[str, float]:

    return calculate_impacts(material_inventory, transport_inventory, unit_impacts, inputs)

def evaluate_lca_candidate(
    candidate: dict[str, Any],
    unit_impacts: LCAUnitImpacts | None = None,
    inputs: LCAInputs | None = None,
) -> dict[str, Any]:

    unit_impacts = unit_impacts or LCAUnitImpacts()
    inputs = inputs or LCAInputs()

    material_inventory = calculate_material_inventory(candidate, inputs)
    transport_inventory = calculate_transport_inventory(material_inventory, inputs)
    gwp = calculate_impacts(material_inventory, transport_inventory, unit_impacts, inputs)

    return {
        **candidate,
        "lca_functional_unit": "one complete 86,000 SF pavement project meeting structural requirements",
        "lca_impact_methodology": inputs.impact_methodology,
        "lca_impact_category": inputs.impact_category,
        "lca_impact_unit": inputs.impact_unit,
        "include_virgin_aggregate_credit": inputs.include_virgin_aggregate_credit,
        **material_inventory,
        **transport_inventory,
        **gwp,
    }


def run_module_4_lca(
    module_1_results: list[dict[str, Any]] | None = None,
    module_2_results: list[dict[str, Any]] | None = None,
    unit_impacts: LCAUnitImpacts | None = None,
    inputs: LCAInputs | None = None,
) -> list[dict[str, Any]]:

    combined_candidates: list[dict[str, Any]] = []

    if module_1_results:
        combined_candidates.extend(module_1_results)

    if module_2_results:
        combined_candidates.extend(module_2_results)

    return [
        evaluate_lca_candidate(candidate, unit_impacts=unit_impacts, inputs=inputs)
        for candidate in combined_candidates
    ]


def write_results_csv(results: list[dict[str, Any]], output_path: str | Path) -> None:

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not results:
        output_path.write_text("")
        return

    fieldnames: list[str] = []
    for row in results:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
