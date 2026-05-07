"""Module 3 – LCC calculation (Deliverable 4).
Present-worth cost model for Module 1 and 2 alternatives.
Refs: FHWA 2002; RSMeans/Gordian 2026; Parsons/Euclid 2026.
"""
from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from module_2 import calculate_tufstrand_sf_dosage_lb_per_cy


@dataclass(frozen=True)
class RSMeansUnitCosts:

    # Baseline cost sources: RSMeans/Gordian 2026 and Parsons/Euclid 2026 pricing.
    concrete_cost_per_cy: float = 185.00
    stone_57_cost_per_cy: float = 58.00
    reinforcing_steel_cost_per_ton: float = 3200.00

    tufstrand_sf_cost_per_lb: float = 1.47  # Parsons/Euclid 2026 max baseline; discount sampled in Module 5

    concrete_demolition_cost_per_cy: float = 42.00
    concrete_crushing_cost_per_ton: float = 9.00
    subbase_removal_cost_per_cy: float = 18.00

    recycled_concrete_aggregate_credit_per_ton: float = 6.00


@dataclass(frozen=True)
class LCCInputs:

    analysis_period_yr: int = 50  # Deliverable 4 service-life basis
    end_of_service_life_yr: int = 50
    real_discount_rate: float = 0.03  # FHWA LCCA primer / Deliverable 4 baseline

    saginaw_county_location_factor: float = 1.00

    concrete_ton_per_cy: float = 2.025  # normal-weight concrete, CY -> ton

    maintenance_cost_present_worth: float = 0.0

    contractor_markup_factor: float = 1.00
    contingency_factor: float = 1.00



def build_unit_cost_table(costs: RSMeansUnitCosts | None = None) -> list[dict[str, Any]]:

    costs = costs or RSMeansUnitCosts()

    # Unit-cost table required by Deliverable 4 feedback; ranges align with Module 5.
    return [
        {"name": "c_conc", "description": "concrete", "baseline": costs.concrete_cost_per_cy, "low": 150.0, "high": 230.0, "units": "$/cy", "reference": "RSMeans/Gordian 2026"},
        {"name": "c_base", "description": "#57 stone", "baseline": costs.stone_57_cost_per_cy, "low": 45.0, "high": 75.0, "units": "$/cy", "reference": "RSMeans/Gordian 2026"},
        {"name": "c_rebar", "description": "reinforcing steel", "baseline": costs.reinforcing_steel_cost_per_ton, "low": 2600.0, "high": 3900.0, "units": "$/ton", "reference": "RSMeans/Gordian 2026"},
        {"name": "c_fiber", "description": "TUF-STRAND SF", "baseline": costs.tufstrand_sf_cost_per_lb, "low": 1.323, "high": 1.47, "units": "$/lb", "reference": "Parsons/Euclid 2026"},
        {"name": "c_demo", "description": "concrete demolition", "baseline": costs.concrete_demolition_cost_per_cy, "low": 32.0, "high": 55.0, "units": "$/cy", "reference": "RSMeans/Gordian 2026"},
        {"name": "c_crush", "description": "concrete crushing", "baseline": costs.concrete_crushing_cost_per_ton, "low": 6.0, "high": 13.0, "units": "$/ton", "reference": "RSMeans/local recycler"},
        {"name": "c_subbase_remove", "description": "subbase removal", "baseline": costs.subbase_removal_cost_per_cy, "low": 15.0, "high": 22.0, "units": "$/cy", "reference": "RSMeans/Gordian 2026"},
        {"name": "c_credit", "description": "recycled aggregate credit", "baseline": costs.recycled_concrete_aggregate_credit_per_ton, "low": 3.0, "high": 9.0, "units": "$/ton", "reference": "local recycled aggregate value"},
    ]

def calculate_present_value_factor(
    real_discount_rate: float,
    year: int,
) -> float:

    if year < 0:
        raise ValueError("Year must be zero or greater.")
    if real_discount_rate <= -1.0:
        raise ValueError("Discount rate must be greater than -100%.")

    # Present-worth factor: FHWA LCCA primer / Deliverable 4.
    return 1.0 / ((1.0 + real_discount_rate) ** year)


def localize_cost(
    national_average_cost: float,
    inputs: LCCInputs,
) -> float:

    if national_average_cost < 0:
        raise ValueError("National average cost must be zero or greater.")
    if inputs.saginaw_county_location_factor <= 0:
        raise ValueError("Location factor must be greater than zero.")

    return (
        national_average_cost
        * inputs.saginaw_county_location_factor
        * inputs.contractor_markup_factor
        * inputs.contingency_factor
    )


def get_required_float(
    candidate: dict[str, Any],
    key: str,
) -> float:

    if key not in candidate:
        raise KeyError(f"Candidate is missing required field: {key}")

    value = candidate[key]

    if value in ("", None):
        raise ValueError(f"Candidate field {key} is empty.")

    return float(value)


def calculate_initial_construction_cost(
    candidate: dict[str, Any],
    costs: RSMeansUnitCosts,
    inputs: LCCInputs,
) -> dict[str, float]:

    concrete_cy = get_required_float(candidate, "concrete_volume_cy_total")
    stone_cy = get_required_float(candidate, "subbase_volume_cy_total")

    # Initial construction cost components from Deliverable 4.
    concrete_cost = localize_cost(concrete_cy * costs.concrete_cost_per_cy, inputs)
    stone_cost = localize_cost(stone_cy * costs.stone_57_cost_per_cy, inputs)

    steel_cost = 0.0
    fiber_cost = 0.0

    module = str(candidate.get("module", "")).upper()

    if module == "SRC":
        steel_ton = get_required_float(candidate, "steel_weight_ton_total")
        steel_cost = localize_cost(steel_ton * costs.reinforcing_steel_cost_per_ton, inputs)

    elif module == "FRC":
        fe3_psi = get_required_float(candidate, "fe3_psi")

        # Fiber dosage relation from Module 2 / Euclid 2026 calibration.
        tufstrand_dosage_lb_per_cy = calculate_tufstrand_sf_dosage_lb_per_cy(fe3_psi)
        fiber_cost = localize_cost(
            concrete_cy * tufstrand_dosage_lb_per_cy * costs.tufstrand_sf_cost_per_lb,  # CY * lb/CY * $/lb
            inputs,
        )

    else:
        raise ValueError(f"Unsupported module type for LCC: {module}")

    initial_cost = concrete_cost + stone_cost + steel_cost + fiber_cost

    return {
        "initial_concrete_cost": concrete_cost,
        "initial_57_stone_cost": stone_cost,
        "initial_reinforcing_steel_cost": steel_cost,
        "initial_fiber_cost": fiber_cost,
        "initial_construction_cost": initial_cost,
    }


def calculate_end_of_life_cost(
    candidate: dict[str, Any],
    costs: RSMeansUnitCosts,
    inputs: LCCInputs,
) -> dict[str, float]:

    concrete_cy = get_required_float(candidate, "concrete_volume_cy_total")
    stone_cy = get_required_float(candidate, "subbase_volume_cy_total")

    concrete_tons = concrete_cy * inputs.concrete_ton_per_cy  # CY -> ton

    # End-of-life terms: demolition, crushing, subbase removal, reuse credit; Deliverable 4.
    demo_cost = localize_cost(concrete_cy * costs.concrete_demolition_cost_per_cy, inputs)
    crushing_cost = localize_cost(concrete_tons * costs.concrete_crushing_cost_per_ton, inputs)
    subbase_removal_cost = localize_cost(stone_cy * costs.subbase_removal_cost_per_cy, inputs)

    recycled_aggregate_credit = localize_cost(
        concrete_tons * costs.recycled_concrete_aggregate_credit_per_ton,
        inputs,
    )

    end_of_life_net_future_cost = (
        demo_cost
        + crushing_cost
        + subbase_removal_cost
        - recycled_aggregate_credit
    )

    pv_factor = calculate_present_value_factor(
        inputs.real_discount_rate,
        inputs.end_of_service_life_yr,
    )

    end_of_life_present_worth = end_of_life_net_future_cost * pv_factor

    return {
        "end_of_life_concrete_tons": concrete_tons,
        "end_of_life_demo_cost_future": demo_cost,
        "end_of_life_crushing_cost_future": crushing_cost,
        "end_of_life_subbase_removal_cost_future": subbase_removal_cost,
        "end_of_life_recycled_aggregate_credit_future": recycled_aggregate_credit,
        "end_of_life_net_future_cost": end_of_life_net_future_cost,
        "end_of_life_pv_factor": pv_factor,
        "end_of_life_present_worth": end_of_life_present_worth,
    }


def evaluate_lcc_candidate(
    candidate: dict[str, Any],
    costs: RSMeansUnitCosts | None = None,
    inputs: LCCInputs | None = None,
) -> dict[str, Any]:

    costs = costs or RSMeansUnitCosts()
    inputs = inputs or LCCInputs()

    initial = calculate_initial_construction_cost(candidate, costs, inputs)
    end_of_life = calculate_end_of_life_cost(candidate, costs, inputs)

    # PW = initial + maintenance + PV(EOL); FHWA / Deliverable 4.
    total_present_worth = (
        initial["initial_construction_cost"]
        + inputs.maintenance_cost_present_worth
        + end_of_life["end_of_life_present_worth"]
    )

    total_area_sf = get_required_float(candidate, "total_area_sf")

    result = {
        **candidate,
        "lcc_analysis_period_yr": inputs.analysis_period_yr,
        "lcc_end_of_service_life_yr": inputs.end_of_service_life_yr,
        "lcc_real_discount_rate": inputs.real_discount_rate,
        "rsmeans_saginaw_county_location_factor": inputs.saginaw_county_location_factor,
        "maintenance_present_worth": inputs.maintenance_cost_present_worth,
        **initial,
        **end_of_life,
        "total_present_worth": total_present_worth,
        "present_worth_per_sf": total_present_worth / total_area_sf,
    }

    return result


def run_module_3_lcc(
    module_1_results: list[dict[str, Any]] | None = None,
    module_2_results: list[dict[str, Any]] | None = None,
    costs: RSMeansUnitCosts | None = None,
    inputs: LCCInputs | None = None,
) -> list[dict[str, Any]]:

    costs = costs or RSMeansUnitCosts()
    inputs = inputs or LCCInputs()

    combined_candidates: list[dict[str, Any]] = []

    if module_1_results:
        combined_candidates.extend(module_1_results)

    if module_2_results:
        combined_candidates.extend(module_2_results)

    return [
        evaluate_lcc_candidate(candidate, costs=costs, inputs=inputs)
        for candidate in combined_candidates
    ]


def read_results_csv(path: str | Path) -> list[dict[str, Any]]:

    path = Path(path)

    if not path.exists():
        return []

    with path.open("r", newline="") as f:
        return list(csv.DictReader(f))


def write_results_csv(
    results: list[dict[str, Any]],
    output_path: str | Path,
) -> None:

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
