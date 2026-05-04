"""Module 1 – SRC design (Deliverable 3).
Westergaard demand, ACI flexure, and project quantities.
Refs: ACI 318-19; PCA 1984; Westergaard 1926.
"""
from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Any


# ASTM/AASHTO standard U.S. bar geometry used for detailing and weight takeoff.
BAR_DATABASE: dict[str, dict[str, float]] = {
    "#3": {"diameter_in": 0.375, "area_in2": 0.11},
    "#4": {"diameter_in": 0.500, "area_in2": 0.20},
    "#5": {"diameter_in": 0.625, "area_in2": 0.31},
    "#6": {"diameter_in": 0.750, "area_in2": 0.44},
}


@dataclass(frozen=True)
class SRCInputs:

    parking_lot_length_ft: float = 300.0
    parking_lot_width_ft: float = 150.0
    roadway_length_ft: float = 2050.0
    roadway_width_ft: float = 20.0

    rebar_stock_length_ft: float = 40.0
    class_a_splice_multiplier: float = 1.0

    axle_load_kip: float = 19.0
    tire_pressure_psi: float = 100.0

    concrete_fpc_psi: float = 4500.0
    concrete_MR_psi: float = 650.0
    concrete_Ec_psi: float = 57000.0 * math.sqrt(4500.0)  # ACI 318-19 normal-weight Ec
    poisson_ratio: float = 0.15

    steel_fy_psi: float = 60000.0  # ASTM Grade 60 reinforcing steel
    steel_Es_psi: float = 29000000.0  # ACI 318-19 steel modulus

    subgrade_k_pci: float = 100.0

    clear_cover_bottom_in: float = 3.0
    phi_flexure: float = 0.90  # ACI 318-19 tension-controlled flexure

    design_strip_width_in: float = 12.0

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
class SRCCandidate:

    subbase_thickness_in: float
    pavement_thickness_in: float
    bar_size: str
    bar_spacing_in: float


def generate_src_candidates(
    subbase_thicknesses_in: list[float] | None = None,
    pavement_thicknesses_in: list[float] | None = None,
    bar_sizes: list[str] | None = None,
    bar_spacings_in: list[float] | None = None,
) -> list[SRCCandidate]:

    # Candidate ranges match Deliverable 3 design-variable screening.
    subbase_thicknesses_in = subbase_thicknesses_in or [4, 6, 8, 10, 12]
    pavement_thicknesses_in = pavement_thicknesses_in or [6, 8, 10, 12]
    bar_sizes = bar_sizes or ["#3", "#4", "#5", "#6"]
    bar_spacings_in = bar_spacings_in or [6, 8, 10, 12, 15, 18, 24]

    return [
        SRCCandidate(
            subbase_thickness_in=subbase_t,
            pavement_thickness_in=slab_t,
            bar_size=bar,
            bar_spacing_in=spacing,
        )
        for subbase_t, slab_t, bar, spacing in product(
            subbase_thicknesses_in,
            pavement_thicknesses_in,
            bar_sizes,
            bar_spacings_in,
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


def calculate_As_per_ft(bar_size: str, spacing_in: float) -> float:

    if bar_size not in BAR_DATABASE:
        raise ValueError(f"Unsupported bar size: {bar_size}")
    if spacing_in <= 0:
        raise ValueError("Bar spacing must be greater than zero.")

    # Distributed steel area per foot from selected bar size/spacing; ACI 318 detailing basis.
    return BAR_DATABASE[bar_size]["area_in2"] * 12.0 / spacing_in


def calculate_effective_depth(
    h_in: float,
    clear_cover_bottom_in: float,
    bar_size: str,
) -> float:

    if bar_size not in BAR_DATABASE:
        raise ValueError(f"Unsupported bar size: {bar_size}")

    # Effective depth to bar centroid using cover assumption from Deliverable 3.
    return h_in - clear_cover_bottom_in - BAR_DATABASE[bar_size]["diameter_in"] / 2.0


# ACI 318-19 equivalent rectangular stress block factor.
def calculate_beta1(fpc_psi: float) -> float:

    if fpc_psi <= 4000.0:
        return 0.85

    return max(0.85 - 0.05 * ((fpc_psi - 4000.0) / 1000.0), 0.65)


def calculate_flexural_capacity(
    As_in2_per_ft: float,
    fy_psi: float,
    fpc_psi: float,
    b_in: float,
    d_in: float,
    phi: float,
) -> dict[str, float]:

    if d_in <= 0:
        return {
            "a_in": math.nan,
            "Mn_kip_in_per_ft": math.nan,
            "phi_Mn_kip_in_per_ft": math.nan,
        }

    # ACI 318-19 singly reinforced rectangular section.
    a_in = As_in2_per_ft * fy_psi / (0.85 * fpc_psi * b_in)
    Mn_lb_in_per_ft = As_in2_per_ft * fy_psi * (d_in - a_in / 2.0)

    return {
        "a_in": a_in,
        "Mn_kip_in_per_ft": Mn_lb_in_per_ft / 1000.0,
        "phi_Mn_kip_in_per_ft": phi * Mn_lb_in_per_ft / 1000.0,
    }


def calculate_cracking_moment(
    MR_psi: float,
    b_in: float,
    h_in: float,
) -> float:

    # Cracking moment using modulus of rupture and gross section modulus; ACI/PCA.
    return (MR_psi * b_in * h_in**2 / 6.0) / 1000.0


def calculate_tension_strain(
    a_in: float,
    d_in: float,
    fpc_psi: float,
) -> float:

    if math.isnan(a_in) or d_in <= 0:
        return math.nan

    c_in = a_in / calculate_beta1(fpc_psi)

    if c_in <= 0:
        return math.nan

    return 0.003 * (d_in - c_in) / c_in


def calculate_tension_development_length_in(
    bar_size: str,
    fy_psi: float,
    fpc_psi: float,
    lambda_concrete: float = 1.0,
    psi_t: float = 1.0,
    psi_e: float = 1.0,
    psi_s: float = 0.8,
) -> float:

    if bar_size not in BAR_DATABASE:
        raise ValueError(f"Unsupported bar size: {bar_size}")
    if fpc_psi <= 0:
        raise ValueError("Concrete compressive strength must be greater than zero.")

    db = BAR_DATABASE[bar_size]["diameter_in"]
    # Tension development length expression; ACI 318-19, simplified for project assumptions.
    ld = (3.0 / 40.0) * (fy_psi / (lambda_concrete * math.sqrt(fpc_psi))) * psi_t * psi_e * psi_s * db

    return max(ld, 12.0)


def calculate_class_a_lap_length_in(
    bar_size: str,
    fy_psi: float,
    fpc_psi: float,
    class_a_splice_multiplier: float = 1.0,
) -> float:

    ld = calculate_tension_development_length_in(bar_size, fy_psi, fpc_psi)

    return class_a_splice_multiplier * ld


def calculate_bars_required(perpendicular_width_ft: float, spacing_in: float) -> int:

    if perpendicular_width_ft <= 0:
        raise ValueError("Width must be greater than zero.")
    if spacing_in <= 0:
        raise ValueError("Spacing must be greater than zero.")

    return math.ceil(perpendicular_width_ft * 12.0 / spacing_in) + 1


def calculate_spliced_bar_run_length_ft(
    run_length_ft: float,
    stock_length_ft: float,
    lap_length_ft: float,
) -> tuple[float, int, int, float]:

    if run_length_ft <= 0:
        raise ValueError("Run length must be greater than zero.")
    if stock_length_ft <= 0:
        raise ValueError("Stock length must be greater than zero.")

    pieces = math.ceil(run_length_ft / stock_length_ft)
    splices = max(0, pieces - 1)
    lap_added_ft = splices * lap_length_ft
    total_run_length_ft = run_length_ft + lap_added_ft

    return total_run_length_ft, pieces, splices, lap_added_ft


def calculate_rebar_length_ft(
    inputs: SRCInputs,
    candidate: SRCCandidate,
    lap_length_in: float,
) -> dict[str, float]:

    spacing = candidate.bar_spacing_in
    stock_length_ft = inputs.rebar_stock_length_ft
    lap_length_ft = lap_length_in / 12.0

    def two_way_area_lengths(area_length_ft: float, area_width_ft: float) -> dict[str, float]:
        n_longitudinal = calculate_bars_required(area_width_ft, spacing)
        long_run, long_pieces, long_splices, long_lap_ft = calculate_spliced_bar_run_length_ft(
            area_length_ft, stock_length_ft, lap_length_ft
        )

        n_transverse = calculate_bars_required(area_length_ft, spacing)
        trans_run, trans_pieces, trans_splices, trans_lap_ft = calculate_spliced_bar_run_length_ft(
            area_width_ft, stock_length_ft, lap_length_ft
        )

        total_longitudinal_ft = n_longitudinal * long_run
        total_transverse_ft = n_transverse * trans_run

        return {
            "longitudinal_bar_count": float(n_longitudinal),
            "transverse_bar_count": float(n_transverse),
            "longitudinal_pieces_per_bar": float(long_pieces),
            "transverse_pieces_per_bar": float(trans_pieces),
            "longitudinal_splices_per_bar": float(long_splices),
            "transverse_splices_per_bar": float(trans_splices),
            "longitudinal_lap_added_ft_per_bar": long_lap_ft,
            "transverse_lap_added_ft_per_bar": trans_lap_ft,
            "longitudinal_rebar_length_ft": total_longitudinal_ft,
            "transverse_rebar_length_ft": total_transverse_ft,
            "total_rebar_length_ft": total_longitudinal_ft + total_transverse_ft,
        }

    def one_way_longitudinal_area_lengths(area_length_ft: float, area_width_ft: float) -> dict[str, float]:
        n_longitudinal = calculate_bars_required(area_width_ft, spacing)
        long_run, long_pieces, long_splices, long_lap_ft = calculate_spliced_bar_run_length_ft(
            area_length_ft, stock_length_ft, lap_length_ft
        )

        total_longitudinal_ft = n_longitudinal * long_run

        return {
            "longitudinal_bar_count": float(n_longitudinal),
            "transverse_bar_count": 0.0,
            "longitudinal_pieces_per_bar": float(long_pieces),
            "transverse_pieces_per_bar": 0.0,
            "longitudinal_splices_per_bar": float(long_splices),
            "transverse_splices_per_bar": 0.0,
            "longitudinal_lap_added_ft_per_bar": long_lap_ft,
            "transverse_lap_added_ft_per_bar": 0.0,
            "longitudinal_rebar_length_ft": total_longitudinal_ft,
            "transverse_rebar_length_ft": 0.0,
            "total_rebar_length_ft": total_longitudinal_ft,
        }

    parking = two_way_area_lengths(inputs.parking_lot_length_ft, inputs.parking_lot_width_ft)
    roadway = one_way_longitudinal_area_lengths(inputs.roadway_length_ft, inputs.roadway_width_ft)

    return {
        "class_a_lap_length_in": lap_length_in,
        "rebar_stock_length_ft": stock_length_ft,
        "parking_lot_reinforcement_directions": 2.0,
        "roadway_reinforcement_directions": 1.0,
        "parking_lot_rebar_length_ft": parking["total_rebar_length_ft"],
        "roadway_rebar_length_ft": roadway["total_rebar_length_ft"],
        "total_rebar_length_ft_with_laps": parking["total_rebar_length_ft"] + roadway["total_rebar_length_ft"],
        "parking_lot_longitudinal_bar_count": parking["longitudinal_bar_count"],
        "parking_lot_transverse_bar_count": parking["transverse_bar_count"],
        "roadway_longitudinal_bar_count": roadway["longitudinal_bar_count"],
        "roadway_transverse_bar_count": roadway["transverse_bar_count"],
        "roadway_longitudinal_splices_per_bar": roadway["longitudinal_splices_per_bar"],
        "roadway_transverse_splices_per_bar": roadway["transverse_splices_per_bar"],
        "parking_lot_longitudinal_splices_per_bar": parking["longitudinal_splices_per_bar"],
        "parking_lot_transverse_splices_per_bar": parking["transverse_splices_per_bar"],
    }

def calculate_material_quantities(
    inputs: SRCInputs,
    h_in: float,
    subbase_thickness_in: float,
    As_in2_per_ft: float,
    candidate: SRCCandidate | None = None,
    reinforcement_directions: int = 2,
) -> dict[str, float]:

    total_area_sf = inputs.total_area_sf

    # SF * in -> CY
    concrete_volume_cy = total_area_sf * (h_in / 12.0) / 27.0
    subbase_volume_cy = total_area_sf * (subbase_thickness_in / 12.0) / 27.0

    steel_density_lb_per_in3 = 490.0 / 1728.0  # steel unit weight, lb/ft^3 -> lb/in^3

    quantity_result: dict[str, float] = {
        "parking_lot_area_sf": inputs.parking_lot_area_sf,
        "roadway_area_sf": inputs.roadway_area_sf,
        "total_area_sf": total_area_sf,
        "concrete_volume_cy_total": concrete_volume_cy,
        "subbase_volume_cy_total": subbase_volume_cy,
    }

    if candidate is not None:
        bar_area_in2 = BAR_DATABASE[candidate.bar_size]["area_in2"]
        lap_length_in = calculate_class_a_lap_length_in(
            candidate.bar_size,
            inputs.steel_fy_psi,
            inputs.concrete_fpc_psi,
            inputs.class_a_splice_multiplier,
        )

        rebar_layout = calculate_rebar_length_ft(inputs, candidate, lap_length_in)
        total_rebar_length_ft = rebar_layout["total_rebar_length_ft_with_laps"]

        steel_volume_in3_total = total_rebar_length_ft * 12.0 * bar_area_in2
        steel_weight_lb_total = steel_volume_in3_total * steel_density_lb_per_in3

        quantity_result.update(rebar_layout)
        quantity_result.update(
            {
                "reinforcement_directions": 2.0,
                "steel_weight_lb_total": steel_weight_lb_total,
                "steel_weight_ton_total": steel_weight_lb_total / 2000.0,  # lb -> ton
            }
        )

        return quantity_result

    steel_volume_in3_per_sf = As_in2_per_ft * 12.0 * reinforcement_directions
    # in^3/SF * lb/in^3 * SF -> lb
    steel_weight_lb_total = steel_volume_in3_per_sf * steel_density_lb_per_in3 * total_area_sf

    quantity_result.update(
        {
            "reinforcement_directions": float(reinforcement_directions),
            "steel_weight_lb_total": steel_weight_lb_total,
            "steel_weight_ton_total": steel_weight_lb_total / 2000.0,  # lb -> ton
        }
    )

    return quantity_result


def check_constructability(candidate: SRCCandidate, d_in: float) -> list[str]:

    warnings: list[str] = []

    if d_in <= 0:
        warnings.append("Effective depth is less than or equal to zero.")

    if candidate.pavement_thickness_in < 6 and candidate.bar_size in ["#5", "#6"]:
        warnings.append("Large bar in thin slab may be impractical.")

    if candidate.bar_spacing_in < 6:
        warnings.append("Bar spacing below 6 in may be difficult to place.")

    if candidate.bar_spacing_in > 24:
        warnings.append("Bar spacing above 24 in may not provide good crack control.")

    return warnings


def evaluate_src_candidate(
    inputs: SRCInputs,
    candidate: SRCCandidate,
    reinforcement_directions: int = 1,
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

    As = calculate_As_per_ft(candidate.bar_size, candidate.bar_spacing_in)

    d = calculate_effective_depth(h, inputs.clear_cover_bottom_in, candidate.bar_size)

    capacity = calculate_flexural_capacity(
        As,
        inputs.steel_fy_psi,
        inputs.concrete_fpc_psi,
        b,
        d,
        inputs.phi_flexure,
    )

    Mcr = calculate_cracking_moment(inputs.concrete_MR_psi, b, h)

    epsilon_t = calculate_tension_strain(
        capacity["a_in"],
        d,
        inputs.concrete_fpc_psi,
    )

    phi_Mn = capacity["phi_Mn_kip_in_per_ft"]
    dcr = Mu / phi_Mn if phi_Mn and not math.isnan(phi_Mn) else math.inf
    cracking_ratio = Mu / Mcr if Mcr else math.inf

    quantities = calculate_material_quantities(
        inputs,
        h,
        candidate.subbase_thickness_in,
        As,
        candidate=candidate,
        reinforcement_directions=2,
    )

    warnings = check_constructability(candidate, d)

    if not math.isnan(epsilon_t) and epsilon_t < 0.005:
        warnings.append("Section may not be tension-controlled; phi = 0.90 should be reviewed.")

    feasible = dcr <= 1.0 and d > 0

    return {
        "module": "SRC",
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
        "As_per_ft_in2": As,
        "effective_depth_in": d,
        "a_in": capacity["a_in"],
        "Mn_kip_in_per_ft": capacity["Mn_kip_in_per_ft"],
        "phi_Mn_kip_in_per_ft": capacity["phi_Mn_kip_in_per_ft"],
        "Mcr_kip_in_per_ft": Mcr,
        "demand_capacity_ratio": dcr,
        "cracking_ratio": cracking_ratio,
        "epsilon_t": epsilon_t,
        "reinforcement_directions": 2,
        **quantities,
        "feasible": feasible,
        "warnings": "; ".join(warnings),
    }


def run_module_1_src(
    inputs: SRCInputs | None = None,
    reinforcement_directions: int = 1,
    candidates: list[SRCCandidate] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:

    inputs = inputs or SRCInputs()
    candidates = candidates or generate_src_candidates()

    all_results = [
        evaluate_src_candidate(inputs, candidate, reinforcement_directions=reinforcement_directions)
        for candidate in candidates
    ]

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
