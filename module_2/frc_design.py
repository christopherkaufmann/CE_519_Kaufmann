"""Module 2 – FRC design (Deliverable 3).
Westergaard demand, residual strength capacity, and project quantities.
Refs: ACI 544.4R-18; ASTM C1609; Euclid 2026.
"""
from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FRCInputs:

    parking_lot_length_ft: float = 300.0
    parking_lot_width_ft: float = 150.0
    roadway_length_ft: float = 2050.0
    roadway_width_ft: float = 20.0

    axle_load_kip: float = 19.0
    tire_pressure_psi: float = 100.0

    concrete_fpc_psi: float = 4500.0
    concrete_MR_psi: float = 650.0
    concrete_Ec_psi: float = 57000.0 * math.sqrt(4500.0)  # ACI 318-19 normal-weight Ec
    poisson_ratio: float = 0.15

    subgrade_k_pci: float = 100.0

    design_strip_width_in: float = 12.0

    phi_frc: float = 1.0  # project screening factor for residual-capacity comparison

    @property
    def parking_lot_area_sf(self) -> float:
        return self.parking_lot_length_ft * self.parking_lot_width_ft

    @property
    def roadway_area_sf(self) -> float:
        return self.roadway_length_ft * self.roadway_width_ft

    @property
    def total_area_sf(self) -> float:
        return self.parking_lot_area_sf + self.roadway_area_sf

    @property
    def wheel_load_lb(self) -> float:
        return self.axle_load_kip * 1000.0 / 2.0


@dataclass(frozen=True)
class FRCCandidate:

    subbase_thickness_in: float
    pavement_thickness_in: float
    fe3_psi: float


def generate_frc_candidates(
    subbase_thicknesses_in: list[float] | None = None,
    pavement_thicknesses_in: list[float] | None = None,
    fe3_values_psi: list[float] | None = None,
) -> list[FRCCandidate]:

    # Candidate ranges match Deliverable 3 FRC design-variable screening.
    subbase_thicknesses_in = subbase_thicknesses_in or [4, 6, 8, 10, 12]
    pavement_thicknesses_in = pavement_thicknesses_in or [6, 8, 10, 12]
    fe3_values_psi = fe3_values_psi or [100, 150, 200, 250, 300, 350, 400]

    return [
        FRCCandidate(
            subbase_thickness_in=subbase_t,
            pavement_thickness_in=slab_t,
            fe3_psi=fe3,
        )
        for subbase_t, slab_t, fe3 in product(
            subbase_thicknesses_in,
            pavement_thicknesses_in,
            fe3_values_psi,
        )
    ]


def calculate_effective_k(subgrade_k_pci: float, subbase_thickness_in: float) -> float:

    # Effective k multiplier: pavement design screening assumption; PCA/ACI basis.
    subbase_factor_by_thickness = {
        4: 1.10,
        6: 1.20,
        8: 1.30,
        10: 1.40,
        12: 1.50,
    }

    if subbase_thickness_in not in subbase_factor_by_thickness:
        raise ValueError(
            f"Unsupported #57 stone thickness: {subbase_thickness_in}. "
            f"Allowed values are {list(subbase_factor_by_thickness)}."
        )

    return subgrade_k_pci * subbase_factor_by_thickness[subbase_thickness_in]


def calculate_radius_relative_stiffness(
    Ec_psi: float,
    h_in: float,
    k_eff_pci: float,
    poisson_ratio: float,
) -> float:

    if h_in <= 0:
        raise ValueError("Slab thickness must be greater than zero.")
    if k_eff_pci <= 0:
        raise ValueError("Effective k must be greater than zero.")

    # Radius of relative stiffness, Westergaard/PCA rigid pavement formulation.
    return ((Ec_psi * h_in**3) / (12.0 * k_eff_pci * (1.0 - poisson_ratio**2))) ** 0.25


def calculate_contact_radius(wheel_load_lb: float, tire_pressure_psi: float) -> float:

    if wheel_load_lb <= 0:
        raise ValueError("Wheel load must be greater than zero.")
    if tire_pressure_psi <= 0:
        raise ValueError("Tire pressure must be greater than zero.")

    # Circular tire contact area from wheel load and tire pressure; Westergaard input.
    return math.sqrt((wheel_load_lb / tire_pressure_psi) / math.pi)


def calculate_equivalent_resisting_radius(
    contact_radius_in: float,
    h_in: float,
) -> float:

    if contact_radius_in <= 0:
        raise ValueError("Contact radius must be greater than zero.")
    if h_in <= 0:
        raise ValueError("Slab thickness must be greater than zero.")

    if contact_radius_in < 1.724 * h_in:
        # Equivalent resisting radius for interior contact condition; Westergaard/PCA.
        return math.sqrt(1.6 * contact_radius_in**2 + h_in**2) - 0.675 * h_in

    return contact_radius_in


def calculate_edge_stress_psi(
    wheel_load_lb: float,
    h_in: float,
    l_in: float,
    contact_radius_in: float,
) -> float:

    if wheel_load_lb <= 0:
        raise ValueError("Wheel load must be greater than zero.")
    if h_in <= 0:
        raise ValueError("Slab thickness must be greater than zero.")
    if l_in <= 0:
        raise ValueError("Radius of relative stiffness must be greater than zero.")

    b_in = calculate_equivalent_resisting_radius(contact_radius_in, h_in)

    if l_in <= b_in:
        raise ValueError(
            f"Westergaard input check failed: l ({l_in:.3f} in.) must be greater "
            f"than b ({b_in:.3f} in.) for this equation."
        )

    # Westergaard edge stress equation used in Deliverable 3.
    return (0.572 * wheel_load_lb / h_in**2) * (4.0 * math.log10(l_in / b_in) + 0.359)


def convert_stress_to_moment_per_ft(
    stress_psi: float,
    b_in: float,
    h_in: float,
) -> float:

    # Elastic section modulus conversion: stress * b*h^2/6 -> kip-in/ft.
    return (stress_psi * b_in * h_in**2 / 6.0) / 1000.0


def calculate_re3(
    fe3_psi: float,
    fr_psi: float,
) -> dict[str, float]:

    if fe3_psi < 0:
        raise ValueError("fe3 must be zero or greater.")
    if fr_psi <= 0:
        raise ValueError("fr / MR must be greater than zero.")

    # Re3 = residual strength ratio; ACI 544.4R / ASTM C1609 terminology.
    re3_decimal = fe3_psi / fr_psi

    return {
        "Re3_decimal": re3_decimal,
        "Re3_percent": re3_decimal * 100.0,
    }


def calculate_tufstrand_sf_dosage_lb_per_cy(fe3_psi: float) -> float:

    if fe3_psi < 0:
        raise ValueError("fe3 must be zero or greater.")

    # Project calibration for TUF-STRAND SF dosage; Euclid 2026 / Deliverable 3.
    calculated_dosage = 0.03 * fe3_psi - 1.1

    return min(20.0, max(3.0, calculated_dosage))


def calculate_frc_nominal_moment_capacity(
    fe3_psi: float,
    b_in: float,
    h_in: float,
) -> float:

    if fe3_psi < 0:
        raise ValueError("fe3 must be zero or greater.")
    if b_in <= 0:
        raise ValueError("Design strip width must be greater than zero.")
    if h_in <= 0:
        raise ValueError("Slab thickness must be greater than zero.")

    # Residual FRC moment, fe3*b*h^2/6; ACI 544.4R / Deliverable 3.
    return (fe3_psi * b_in * h_in**2 / 6.0) / 1000.0


def calculate_plain_cracking_moment(
    MR_psi: float,
    b_in: float,
    h_in: float,
) -> float:

    if MR_psi <= 0:
        raise ValueError("MR must be greater than zero.")

    # Plain concrete cracking moment using MR and gross section modulus; PCA/ACI.
    return (MR_psi * b_in * h_in**2 / 6.0) / 1000.0


def calculate_material_quantities(
    inputs: FRCInputs,
    h_in: float,
    subbase_thickness_in: float,
    fe3_psi: float,
) -> dict[str, float | str]:

    total_area_sf = inputs.total_area_sf

    # SF * in -> CY
    concrete_volume_cy = total_area_sf * (h_in / 12.0) / 27.0
    subbase_volume_cy = total_area_sf * (subbase_thickness_in / 12.0) / 27.0

    return {
        "parking_lot_area_sf": inputs.parking_lot_area_sf,
        "roadway_area_sf": inputs.roadway_area_sf,
        "total_area_sf": total_area_sf,
        "concrete_volume_cy_total": concrete_volume_cy,
        "subbase_volume_cy_total": subbase_volume_cy,
        "fe3_psi_for_lcc_lca_mapping": fe3_psi,
        "fiber_quantity_note": "Fiber dosage is calculated in Module 2; total fiber mass is calculated in Module 4 LCA.",
    }


def check_constructability(candidate: FRCCandidate) -> list[str]:

    warnings: list[str] = []

    if candidate.pavement_thickness_in < 5:
        warnings.append("Very thin FRC pavement section should be reviewed.")

    if candidate.fe3_psi <= 0:
        warnings.append("fe3 is zero or negative; FRC residual contribution is not active.")

    if candidate.fe3_psi > 500:
        warnings.append("High fe3 value; confirm with ASTM C1609 test data or supplier data.")

    return warnings


def evaluate_frc_candidate(
    inputs: FRCInputs,
    candidate: FRCCandidate,
) -> dict[str, Any]:

    h = candidate.pavement_thickness_in
    b = inputs.design_strip_width_in

    k_eff = calculate_effective_k(inputs.subgrade_k_pci, candidate.subbase_thickness_in)

    l_in = calculate_radius_relative_stiffness(
        inputs.concrete_Ec_psi,
        h,
        k_eff,
        inputs.poisson_ratio,
    )

    contact_radius = calculate_contact_radius(inputs.wheel_load_lb, inputs.tire_pressure_psi)

    equivalent_radius = calculate_equivalent_resisting_radius(contact_radius, h)

    edge_stress = calculate_edge_stress_psi(
        inputs.wheel_load_lb,
        h,
        l_in,
        contact_radius,
    )

    Mu = convert_stress_to_moment_per_ft(edge_stress, b, h)

    re3 = calculate_re3(candidate.fe3_psi, inputs.concrete_MR_psi)

    tufstrand_dosage = calculate_tufstrand_sf_dosage_lb_per_cy(candidate.fe3_psi)

    Mn_frc = calculate_frc_nominal_moment_capacity(candidate.fe3_psi, b, h)
    Mcr = calculate_plain_cracking_moment(inputs.concrete_MR_psi, b, h)
    Mtotal = Mcr + Mn_frc
    phi_Mtotal = inputs.phi_frc * Mtotal

    demand_capacity_ratio = Mu / phi_Mtotal if phi_Mtotal > 0 else math.inf
    cracking_ratio = Mu / Mcr if Mcr > 0 else math.inf

    quantities = calculate_material_quantities(
        inputs,
        h,
        candidate.subbase_thickness_in,
        candidate.fe3_psi,
    )

    warnings = check_constructability(candidate)

    if cracking_ratio <= 1.0:
        warnings.append("Wheel-load demand is below plain concrete cracking moment; fiber residual capacity provides additional reserve.")
    else:
        warnings.append("Wheel-load demand exceeds plain concrete cracking moment; combined concrete plus fiber capacity is active.")

    feasible = demand_capacity_ratio <= 1.0

    return {
        "module": "FRC",
        **asdict(candidate),
        "axle_load_kip": inputs.axle_load_kip,
        "wheel_load_kip": inputs.wheel_load_lb / 1000.0,
        "tire_pressure_psi": inputs.tire_pressure_psi,
        "subbase_material": "#57 stone",
        "k_eff_pci": k_eff,
        "radius_relative_stiffness_in": l_in,
        "contact_radius_in": contact_radius,
        "equivalent_resisting_radius_b_in": equivalent_radius,
        "edge_stress_psi": edge_stress,
        "Mu_kip_in_per_ft": Mu,
        "concrete_MR_psi": inputs.concrete_MR_psi,
        "fe3_psi": candidate.fe3_psi,
        "Re3_decimal": re3["Re3_decimal"],
        "Re3_percent": re3["Re3_percent"],
        "tufstrand_dosage_lb_per_cy": tufstrand_dosage,
        "Mcr_kip_in_per_ft": Mcr,
        "Mn_FRC_kip_in_per_ft": Mn_frc,
        "Mtotal_FRC_kip_in_per_ft": Mtotal,
        "phi_FRC": inputs.phi_frc,
        "phi_Mtotal_FRC_kip_in_per_ft": phi_Mtotal,
        "demand_capacity_ratio": demand_capacity_ratio,
        "cracking_ratio": cracking_ratio,
        **quantities,
        "feasible": feasible,
        "warnings": "; ".join(warnings),
    }


def run_module_2_frc(
    inputs: FRCInputs | None = None,
    candidates: list[FRCCandidate] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:

    inputs = inputs or FRCInputs()
    candidates = candidates or generate_frc_candidates()

    all_results = [evaluate_frc_candidate(inputs, candidate) for candidate in candidates]
    feasible_results = [result for result in all_results if result["feasible"]]

    return all_results, feasible_results


def write_results_csv(
    results: list[dict[str, Any]],
    output_path: str | Path,
) -> None:

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not results:
        output_path.write_text("")
        return

    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
