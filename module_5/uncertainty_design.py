"""Module 5 – uncertainty and sensitivity (Deliverable 6).
Monte Carlo sampling and Spearman rank sensitivity.
Refs: FHWA 2002; RSMeans/Gordian 2026; ecoinvent/Wernet 2016; PCA 1984.
"""
from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from module_2 import calculate_tufstrand_sf_dosage_lb_per_cy


@dataclass(frozen=True)
class UncertainParameter:

    name: str
    distribution: str
    low: float
    high: float
    mean: float | None = None
    std: float | None = None
    alpha: float | None = None
    beta: float | None = None
    units: str = ""
    reference: str = ""
    description: str = ""


@dataclass(frozen=True)
class UncertaintyInputs:

    n_simulations: int = 50_000  # Deliverable 6 Monte Carlo plan
    random_seed: int = 42  # reproducibility basis in Deliverable 6

    end_of_service_life_yr: int = 50
    concrete_ton_per_cy: float = 2.025
    stone_ton_per_cy: float = 1.35

    truck_transport_kgco2e_per_ton_mile_nominal: float = 0.17
    tufstrand_sf_kgco2e_per_kg: float = 3.08

    base_subgrade_k_pci: float = 100.0  # Module 1 baseline k before subbase improvement
    concrete_Ec_psi: float = 57000.0 * math.sqrt(4500.0)  # ACI 318-19 normal-weight Ec
    poisson_ratio: float = 0.15

    include_virgin_aggregate_credit_lca: bool = False


def build_default_uncertain_parameters() -> list[UncertainParameter]:

    # Parameter/distribution table required by Deliverable 6.
    return [
        UncertainParameter(
            name="concrete_unit_cost",
            distribution="uniform",
            low=150.0,
            high=230.0,
            units="$/cy",
            reference="RSMeans line item, user-selected edition; range for uncertainty screening.",
            description="Ready-mix concrete unit cost.",
        ),
        UncertainParameter(
            name="stone_57_unit_cost",
            distribution="uniform",
            low=45.0,
            high=75.0,
            units="$/cy",
            reference="RSMeans line item, user-selected edition; range for uncertainty screening.",
            description="#57 stone unit cost.",
        ),
        UncertainParameter(
            name="rebar_unit_cost",
            distribution="uniform",
            low=2600.0,
            high=3900.0,
            units="$/ton",
            reference="RSMeans line item, user-selected edition; range for uncertainty screening.",
            description="Reinforcing steel unit cost.",
        ),
        UncertainParameter(
            name="fiber_unit_cost",
            distribution="uniform",
            low=1.323,
            high=1.47,
            units="$/lb",
            reference="Parsons Corporation Euclid Chemical Pricing Agreement, February 2026; lower bound represents 90% contract price with volume discount.",
            description="TUF-STRAND SF unit cost with volume-discount uncertainty.",
        ),
        UncertainParameter(
            name="demolition_cost",
            distribution="uniform",
            low=32.0,
            high=55.0,
            units="$/cy",
            reference="RSMeans demolition line item, user-selected edition; range for uncertainty screening.",
            description="End-of-life concrete demolition cost.",
        ),
        UncertainParameter(
            name="crushing_cost",
            distribution="uniform",
            low=6.0,
            high=13.0,
            units="$/ton",
            reference="RSMeans crushing/recycling line item or local recycler quote; range for uncertainty screening.",
            description="End-of-life concrete crushing cost.",
        ),
        UncertainParameter(
            name="recycled_aggregate_credit",
            distribution="uniform",
            low=3.0,
            high=9.0,
            units="$/ton",
            reference="Local recycled aggregate value; range for uncertainty screening.",
            description="Credit for demolished concrete reused as crushed concrete aggregate.",
        ),
        UncertainParameter(
            name="discount_rate",
            distribution="normal_trunc",
            low=0.0,
            high=0.08,
            mean=0.03,
            std=0.01,
            units="decimal",
            reference="FHWA LCCA practice; bounded real discount-rate screening assumption.",
            description="Real discount rate used for end-of-life present value.",
        ),
        UncertainParameter(
            name="subgrade_k_pci",
            distribution="uniform",
            low=75.0,
            high=150.0,
            units="pci",
            reference="PCA rigid pavement design guidance; conservative screening range around project baseline k.",
            description="Subgrade modulus used to screen design-demand uncertainty only.",
        ),
        UncertainParameter(
            name="concrete_gwp_factor",
            distribution="beta_scaled",
            low=0.80,
            high=1.25,
            alpha=2.0,
            beta=3.0,
            units="multiplier",
            reference="ecoinvent/APOS concrete process factor uncertainty screening.",
            description="Multiplier on concrete production GWP factor.",
        ),
        UncertainParameter(
            name="stone_57_gwp_factor",
            distribution="beta_scaled",
            low=0.75,
            high=1.35,
            alpha=2.0,
            beta=3.0,
            units="multiplier",
            reference="ecoinvent/APOS crushed aggregate process factor uncertainty screening.",
            description="Multiplier on #57 stone production GWP factor.",
        ),
        UncertainParameter(
            name="rebar_gwp_factor",
            distribution="beta_scaled",
            low=0.75,
            high=1.35,
            alpha=2.0,
            beta=3.0,
            units="multiplier",
            reference="CRSI fabricated rebar EPD A1-A3 GWP uncertainty screening.",
            description="Multiplier on reinforcing steel production GWP factor.",
        ),
        UncertainParameter(
            name="trucking_gwp_factor",
            distribution="beta_scaled",
            low=0.80,
            high=1.30,
            alpha=2.0,
            beta=3.0,
            units="multiplier",
            reference="ecoinvent/APOS lorry transport process factor uncertainty screening.",
            description="Multiplier on trucking/hauling GWP factor.",
        ),
        UncertainParameter(
            name="demolition_gwp_factor",
            distribution="beta_scaled",
            low=0.70,
            high=1.50,
            alpha=2.0,
            beta=3.0,
            units="multiplier",
            reference="ecoinvent/APOS diesel equipment proxy uncertainty screening.",
            description="Multiplier on demolition GWP factor.",
        ),
        UncertainParameter(
            name="crushing_gwp_factor",
            distribution="beta_scaled",
            low=0.70,
            high=1.50,
            alpha=2.0,
            beta=3.0,
            units="multiplier",
            reference="ecoinvent/APOS concrete crushing/recycling proxy uncertainty screening.",
            description="Multiplier on concrete crushing GWP factor.",
        ),
    ]


def sample_uncertain_parameters(
    parameters: list[UncertainParameter],
    inputs: UncertaintyInputs,
) -> pd.DataFrame:

    rng = np.random.default_rng(inputs.random_seed)
    samples: dict[str, np.ndarray] = {}

    for parameter in parameters:
        # Uniform = bounded uncertainty; ranges intentionally conservative unless project data are available.
        if parameter.distribution == "uniform":
            values = rng.uniform(parameter.low, parameter.high, inputs.n_simulations)

        # Truncated normal = discount-rate uncertainty; FHWA / Deliverable 6.
        elif parameter.distribution == "normal_trunc":
            if parameter.mean is None or parameter.std is None:
                raise ValueError(f"Normal parameter {parameter.name} requires mean and std.")

            values = rng.normal(parameter.mean, parameter.std, inputs.n_simulations)
            values = np.clip(values, parameter.low, parameter.high)

        # Scaled beta = bounded environmental-factor uncertainty; ecoinvent/Wernet basis.
        elif parameter.distribution == "beta_scaled":
            if parameter.alpha is None or parameter.beta is None:
                raise ValueError(f"Beta parameter {parameter.name} requires alpha and beta.")

            beta_values = rng.beta(parameter.alpha, parameter.beta, inputs.n_simulations)
            values = parameter.low + beta_values * (parameter.high - parameter.low)

        else:
            raise ValueError(f"Unsupported distribution: {parameter.distribution}")

        samples[parameter.name] = values

    return pd.DataFrame(samples)


def build_parameter_table(parameters: list[UncertainParameter]) -> list[dict[str, Any]]:

    return [asdict(parameter) for parameter in parameters]


def get_float(row: pd.Series | dict[str, Any], key: str, default: float = 0.0) -> float:

    value = row.get(key, default)

    if value in ("", None):
        return default

    try:
        if math.isnan(float(value)):
            return default
    except (TypeError, ValueError):
        return default

    return float(value)


def calculate_lcc_simulation(
    row: pd.Series,
    samples: pd.DataFrame,
    inputs: UncertaintyInputs,
) -> np.ndarray:

    concrete_cy = get_float(row, "concrete_volume_cy_total")
    stone_cy = get_float(row, "subbase_volume_cy_total")
    steel_ton = get_float(row, "steel_weight_ton_total")
    fe3_psi = get_float(row, "fe3_psi")

    module = str(row.get("module", "")).upper()

    initial_concrete = concrete_cy * samples["concrete_unit_cost"].to_numpy()
    initial_stone = stone_cy * samples["stone_57_unit_cost"].to_numpy()

    initial_steel = np.zeros(inputs.n_simulations)
    initial_fiber = np.zeros(inputs.n_simulations)

    if module == "SRC":
        initial_steel = steel_ton * samples["rebar_unit_cost"].to_numpy()

    elif module == "FRC":
        tufstrand_dosage_lb_per_cy = calculate_tufstrand_sf_dosage_lb_per_cy(fe3_psi)
        initial_fiber = (
            concrete_cy
            * tufstrand_dosage_lb_per_cy
            * samples["fiber_unit_cost"].to_numpy()
        )

    concrete_tons = concrete_cy * inputs.concrete_ton_per_cy  # CY -> ton

    # EOL cost uncertainty follows Module 3 present-worth structure; FHWA / Deliverable 4.
    future_demo = concrete_cy * samples["demolition_cost"].to_numpy()
    future_crushing = concrete_tons * samples["crushing_cost"].to_numpy()
    future_credit = concrete_tons * samples["recycled_aggregate_credit"].to_numpy()

    discount_rate = samples["discount_rate"].to_numpy()
    pv_factor = 1.0 / ((1.0 + discount_rate) ** inputs.end_of_service_life_yr)

    end_of_life_pw = (future_demo + future_crushing - future_credit) * pv_factor

    return initial_concrete + initial_stone + initial_steel + initial_fiber + end_of_life_pw


def calculate_lca_simulation(
    row: pd.Series,
    samples: pd.DataFrame,
    inputs: UncertaintyInputs,
) -> np.ndarray:

    concrete_gwp_base = get_float(row, "gwp_concrete_kgco2e")
    stone_gwp_base = get_float(row, "gwp_57_stone_kgco2e")
    rebar_gwp_base = get_float(row, "gwp_reinforcing_steel_kgco2e")
    transport_gwp_base = get_float(row, "gwp_transport_kgco2e")
    construction_equipment_gwp_base = get_float(row, "gwp_construction_equipment_kgco2e")
    demolition_gwp_base = get_float(row, "gwp_demolition_kgco2e")
    crushing_gwp_base = get_float(row, "gwp_crushing_kgco2e")

    tufstrand_gwp = get_float(row, "gwp_tufstrand_sf_kgco2e")

    # LCA uncertainty applies multipliers to Module 4 GWP components; Deliverable 5/6.
    total = (
        concrete_gwp_base * samples["concrete_gwp_factor"].to_numpy()
        + stone_gwp_base * samples["stone_57_gwp_factor"].to_numpy()
        + rebar_gwp_base * samples["rebar_gwp_factor"].to_numpy()
        + transport_gwp_base * samples["trucking_gwp_factor"].to_numpy()
        + construction_equipment_gwp_base * samples["demolition_gwp_factor"].to_numpy()
        + demolition_gwp_base * samples["demolition_gwp_factor"].to_numpy()
        + crushing_gwp_base * samples["crushing_gwp_factor"].to_numpy()
        + tufstrand_gwp
    )

    return total


def calculate_design_k_simulation(
    row: pd.Series,
    samples: pd.DataFrame,
    inputs: UncertaintyInputs,
) -> np.ndarray:

    if "subgrade_k_pci" not in samples.columns:
        return np.full(inputs.n_simulations, get_float(row, "demand_capacity_ratio", math.nan))

    h_in = get_float(row, "pavement_thickness_in")
    phi_mn = get_float(row, "phi_Mn_kip_in_per_ft")
    if phi_mn <= 0:
        phi_mn = get_float(row, "phi_Mtotal_FRC_kip_in_per_ft")

    wheel_load_lb = get_float(row, "wheel_load_kip") * 1000.0
    tire_pressure = get_float(row, "tire_pressure_psi")

    if h_in <= 0 or phi_mn <= 0 or wheel_load_lb <= 0 or tire_pressure <= 0:
        return np.full(inputs.n_simulations, math.nan)

    k_base_eff = get_float(row, "k_eff_pci")
    if k_base_eff <= 0:
        k_base_eff = inputs.base_subgrade_k_pci

    subgrade_factor = k_base_eff / inputs.base_subgrade_k_pci
    k_eff = samples["subgrade_k_pci"].to_numpy() * subgrade_factor

    # Westergaard/PCA sensitivity to k only; other Module 1 inputs held fixed.
    l_in = ((inputs.concrete_Ec_psi * h_in**3) / (12.0 * k_eff * (1.0 - inputs.poisson_ratio**2))) ** 0.25
    contact_radius = np.sqrt((wheel_load_lb / tire_pressure) / math.pi)

    if contact_radius < 1.724 * h_in:
        b_in = math.sqrt(1.6 * contact_radius**2 + h_in**2) - 0.675 * h_in
    else:
        b_in = contact_radius

    edge_stress = (0.572 * wheel_load_lb / h_in**2) * (4.0 * np.log10(l_in / b_in) + 0.359)
    mu = (edge_stress * 12.0 * h_in**2 / 6.0) / 1000.0

    return mu / phi_mn


def summarize_simulation(values: np.ndarray, prefix: str) -> dict[str, float]:

    return {
        f"{prefix}_mean": float(np.mean(values)),
        f"{prefix}_std": float(np.std(values, ddof=1)),
        f"{prefix}_p05": float(np.percentile(values, 5)),
        f"{prefix}_p50": float(np.percentile(values, 50)),
        f"{prefix}_p95": float(np.percentile(values, 95)),
        f"{prefix}_min": float(np.min(values)),
        f"{prefix}_max": float(np.max(values)),
    }


# Output-specific parameter groups keep the Spearman plots tied to the physics/economics
# of each result. Cost variables belong on LCC sensitivity; environmental multiplier
# variables belong on LCA sensitivity. This avoids showing cost-only variables such as
# fiber_unit_cost or crushing_cost on the LCA Spearman chart.
# Refs: FHWA LCCA present-worth framework; ISO 14040/14044 LCA inventory-to-impact method.
LCC_SENSITIVITY_PARAMETERS = [
    "concrete_unit_cost",
    "stone_57_unit_cost",
    "rebar_unit_cost",
    "fiber_unit_cost",
    "demolition_cost",
    "crushing_cost",
    "recycled_aggregate_credit",
    "discount_rate",
]

LCA_SENSITIVITY_PARAMETERS = [
    "concrete_gwp_factor",
    "stone_57_gwp_factor",
    "rebar_gwp_factor",
    "trucking_gwp_factor",
    "demolition_gwp_factor",
    "crushing_gwp_factor",
]

DESIGN_K_SENSITIVITY_PARAMETERS = [
    "subgrade_k_pci",
]


# Spearman rank sensitivity; Deliverable 6 selected method for nonlinear screening.
def calculate_spearman_sensitivity(
    samples: pd.DataFrame,
    output_values: np.ndarray,
    output_name: str,
    alternative_id: int,
    ranked_samples: pd.DataFrame | None = None,
    parameter_names: list[str] | None = None,
) -> list[dict[str, Any]]:

    ranked_samples = ranked_samples if ranked_samples is not None else samples.rank(method="average")
    ranked_output = pd.Series(output_values).rank(method="average")

    sensitivity_rows: list[dict[str, Any]] = []
    parameters_to_evaluate = parameter_names or list(samples.columns)

    for parameter_name in parameters_to_evaluate:
        if parameter_name not in ranked_samples.columns:
            continue

        rho = ranked_samples[parameter_name].corr(ranked_output, method="pearson")

        sensitivity_rows.append(
            {
                "alternative_id": alternative_id,
                "output": output_name,
                "parameter": parameter_name,
                "spearman_rho": float(rho),
                "abs_spearman_rho": float(abs(rho)),
            }
        )

    return sensitivity_rows


def run_module_5_uncertainty(
    lcc_results: list[dict[str, Any]],
    lca_results: list[dict[str, Any]],
    parameters: list[UncertainParameter] | None = None,
    inputs: UncertaintyInputs | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:

    parameters = parameters or build_default_uncertain_parameters()
    inputs = inputs or UncertaintyInputs()

    samples = sample_uncertain_parameters(parameters, inputs)
    ranked_samples = samples.rank(method="average")

    lcc_df = pd.DataFrame(lcc_results)
    lca_df = pd.DataFrame(lca_results)

    if "module" not in lcc_df.columns or "module" not in lca_df.columns:
        raise ValueError("LCC and LCA results must include a module column.")

    key_columns = [
        "module",
        "subbase_thickness_in",
        "pavement_thickness_in",
        "bar_size",
        "bar_spacing_in",
        "fe3_psi",
    ]

    for df in (lcc_df, lca_df):
        for column in key_columns:
            if column not in df.columns:
                df[column] = ""

        df["_alternative_key"] = df[key_columns].astype(str).agg("|".join, axis=1)

    merged = lcc_df.merge(
        lca_df,
        on="_alternative_key",
        suffixes=("", "_lca"),
    )

    parameter_table = build_parameter_table(parameters)
    summary_results: list[dict[str, Any]] = []
    sensitivity_results: list[dict[str, Any]] = []

    for alternative_id, (_, row) in enumerate(merged.iterrows(), start=1):
        lcc_values = calculate_lcc_simulation(row, samples, inputs)
        lca_values = calculate_lca_simulation(row, samples, inputs)

        summary = {
            "alternative_id": alternative_id,
            "module": row.get("module", ""),
            "subbase_thickness_in": row.get("subbase_thickness_in", ""),
            "pavement_thickness_in": row.get("pavement_thickness_in", ""),
            "bar_size": row.get("bar_size", ""),
            "bar_spacing_in": row.get("bar_spacing_in", ""),
            "fe3_psi": row.get("fe3_psi", ""),
            "n_simulations": inputs.n_simulations,
            "random_seed": inputs.random_seed,
        }

        design_k_values = calculate_design_k_simulation(row, samples, inputs)

        summary.update(summarize_simulation(lcc_values, "total_present_worth"))
        summary.update(summarize_simulation(lca_values, "gwp_total_project_kgco2e"))
        summary.update(summarize_simulation(design_k_values, "demand_capacity_ratio_k"))

        summary_results.append(summary)

        sensitivity_results.extend(
            calculate_spearman_sensitivity(
                samples,
                lcc_values,
                "total_present_worth",
                alternative_id,
                ranked_samples=ranked_samples,
                parameter_names=LCC_SENSITIVITY_PARAMETERS,
            )
        )

        sensitivity_results.extend(
            calculate_spearman_sensitivity(
                samples,
                lca_values,
                "gwp_total_project_kgco2e",
                alternative_id,
                ranked_samples=ranked_samples,
                parameter_names=LCA_SENSITIVITY_PARAMETERS,
            )
        )

        sensitivity_results.extend(
            calculate_spearman_sensitivity(
                samples,
                design_k_values,
                "demand_capacity_ratio_k",
                alternative_id,
                ranked_samples=ranked_samples,
                parameter_names=DESIGN_K_SENSITIVITY_PARAMETERS,
            )
        )

    return parameter_table, summary_results, sensitivity_results


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
