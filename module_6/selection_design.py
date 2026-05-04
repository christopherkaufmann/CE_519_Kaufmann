"""Module 6 – optimization and selection.
Combines design, LCC, LCA, and uncertainty results for final screening.
Refs: Deliverables 3–6.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class SelectionInputs:

    cost_threshold_multiplier: float = 1.20  # project screening rule for LCC/LCA selection
    lcc_column: str = "total_present_worth"
    lca_column: str = "gwp_total_project_kgco2e"


# Common key ties Module 1/2 design alternatives to Module 3/4/5 results.
def build_alternative_key(df: pd.DataFrame) -> pd.Series:

    key_columns = [
        "module",
        "subbase_thickness_in",
        "pavement_thickness_in",
        "bar_size",
        "bar_spacing_in",
        "fe3_psi",
    ]

    working = df.copy()

    for column in key_columns:
        if column not in working.columns:
            working[column] = ""

    return working[key_columns].fillna("").astype(str).agg("|".join, axis=1)


def merge_lcc_lca_results(
    lcc_results: list[dict[str, Any]],
    lca_results: list[dict[str, Any]],
) -> pd.DataFrame:

    lcc_df = pd.DataFrame(lcc_results)
    lca_df = pd.DataFrame(lca_results)

    if lcc_df.empty:
        raise ValueError("Module 6 received no LCC results.")
    if lca_df.empty:
        raise ValueError("Module 6 received no LCA results.")

    lcc_df["_alternative_key"] = build_alternative_key(lcc_df)
    lca_df["_alternative_key"] = build_alternative_key(lca_df)

    merged = lcc_df.merge(
        lca_df,
        on="_alternative_key",
        suffixes=("", "_lca"),
    )

    if merged.empty:
        raise ValueError("No matching alternatives were found between LCC and LCA results.")

    return merged


def attach_uncertainty_summary(
    selected_df: pd.DataFrame,
    uncertainty_summary: list[dict[str, Any]] | None,
) -> pd.DataFrame:

    if not uncertainty_summary:
        return selected_df

    uncertainty_df = pd.DataFrame(uncertainty_summary)

    if uncertainty_df.empty:
        return selected_df

    uncertainty_df["_alternative_key"] = build_alternative_key(uncertainty_df)

    keep_columns = [
        "_alternative_key",
        "total_present_worth_mean",
        "total_present_worth_std",
        "total_present_worth_p05",
        "total_present_worth_p50",
        "total_present_worth_p95",
        "gwp_total_project_kgco2e_mean",
        "gwp_total_project_kgco2e_std",
        "gwp_total_project_kgco2e_p05",
        "gwp_total_project_kgco2e_p50",
        "gwp_total_project_kgco2e_p95",
        "n_simulations",
        "random_seed",
    ]

    keep_columns = [column for column in keep_columns if column in uncertainty_df.columns]

    return selected_df.merge(
        uncertainty_df[keep_columns],
        on="_alternative_key",
        how="left",
    )


def filter_sensitivity_for_selected(
    selected_df: pd.DataFrame,
    uncertainty_summary: list[dict[str, Any]] | None,
    sensitivity_results: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:

    if not uncertainty_summary or not sensitivity_results:
        return []

    uncertainty_df = pd.DataFrame(uncertainty_summary)
    sensitivity_df = pd.DataFrame(sensitivity_results)

    if uncertainty_df.empty or sensitivity_df.empty:
        return []

    uncertainty_df["_alternative_key"] = build_alternative_key(uncertainty_df)

    selected_keys = set(selected_df["_alternative_key"].tolist())

    selected_alt_ids = uncertainty_df.loc[
        uncertainty_df["_alternative_key"].isin(selected_keys),
        "alternative_id",
    ].tolist()

    filtered = sensitivity_df.loc[
        sensitivity_df["alternative_id"].isin(selected_alt_ids)
    ].copy()

    if filtered.empty:
        return []

    filtered["sensitivity_rank"] = (
        filtered.groupby(["alternative_id", "output"])["abs_spearman_rho"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    return filtered.sort_values(
        by=["alternative_id", "output", "sensitivity_rank"]
    ).to_dict(orient="records")


def select_lowest_lca_by_module(
    eligible_df: pd.DataFrame,
    module_name: str,
    lca_column: str,
) -> pd.DataFrame:

    module_df = eligible_df.loc[
        eligible_df["module"].astype(str).str.upper() == module_name.upper()
    ].copy()

    if module_df.empty:
        return module_df

    return module_df.sort_values(
        by=[lca_column, "total_present_worth"]
    ).head(1)


def select_best_lca_by_module_any_cost(
    merged_df: pd.DataFrame,
    module_name: str,
    lca_column: str,
) -> pd.DataFrame:

    module_df = merged_df.loc[
        merged_df["module"].astype(str).str.upper() == module_name.upper()
    ].copy()

    if module_df.empty:
        return module_df

    return module_df.sort_values(
        by=[lca_column, "total_present_worth"]
    ).head(1)


def run_module_6_selection(
    lcc_results: list[dict[str, Any]],
    lca_results: list[dict[str, Any]],
    uncertainty_summary: list[dict[str, Any]] | None = None,
    sensitivity_results: list[dict[str, Any]] | None = None,
    inputs: SelectionInputs | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:

    inputs = inputs or SelectionInputs()

    merged = merge_lcc_lca_results(lcc_results, lca_results)

    merged[inputs.lcc_column] = pd.to_numeric(merged[inputs.lcc_column])
    merged[inputs.lca_column] = pd.to_numeric(merged[inputs.lca_column])

    # Benchmark = lowest LCC alternative; selection follows Deliverables 3–6 workflow.
    benchmark = merged.sort_values(
        by=[inputs.lcc_column, inputs.lca_column]
    ).head(1).copy()

    benchmark_lcc = float(benchmark.iloc[0][inputs.lcc_column])
    cost_threshold = benchmark_lcc * inputs.cost_threshold_multiplier

    eligible = merged.loc[
        merged[inputs.lcc_column] <= cost_threshold
    ].copy()

    eligible["selection_cost_threshold"] = cost_threshold
    eligible["selection_cost_threshold_multiplier"] = inputs.cost_threshold_multiplier
    eligible["selection_lcc_benchmark"] = benchmark_lcc
    eligible["lcc_percent_of_benchmark"] = (
        eligible[inputs.lcc_column] / benchmark_lcc * 100.0
    )

    selected_src = select_lowest_lca_by_module(
        eligible,
        "SRC",
        inputs.lca_column,
    )

    selected_frc = select_lowest_lca_by_module(
        eligible,
        "FRC",
        inputs.lca_column,
    )

    benchmark = benchmark.copy()
    benchmark["selection_role"] = "Benchmark - lowest deterministic LCC"
    benchmark["selection_status"] = "Within 120% LCC threshold"
    benchmark["selection_cost_threshold"] = cost_threshold
    benchmark["selection_cost_threshold_multiplier"] = inputs.cost_threshold_multiplier
    benchmark["selection_lcc_benchmark"] = benchmark_lcc
    benchmark["lcc_percent_of_benchmark"] = 100.0

    selected_frames: list[pd.DataFrame] = [benchmark]

    if not selected_src.empty:
        selected_src = selected_src.copy()
        selected_src["selection_role"] = "Selected SRC - lowest LCA within 120% LCC"
        selected_src["selection_status"] = "Within 120% LCC threshold"
        selected_frames.append(selected_src)
    else:
        selected_src = select_best_lca_by_module_any_cost(
            merged,
            "SRC",
            inputs.lca_column,
        )
        if not selected_src.empty:
            selected_src = selected_src.copy()
            selected_src["selection_role"] = "Override SRC - best LCA outside 120% LCC"
            selected_src["selection_status"] = "Outside 120% LCC threshold; shown for SRC comparison"
            selected_src["selection_cost_threshold"] = cost_threshold
            selected_src["selection_cost_threshold_multiplier"] = inputs.cost_threshold_multiplier
            selected_src["selection_lcc_benchmark"] = benchmark_lcc
            selected_src["lcc_percent_of_benchmark"] = (
                selected_src[inputs.lcc_column] / benchmark_lcc * 100.0
            )
            selected_frames.append(selected_src)

    if not selected_frc.empty:
        selected_frc = selected_frc.copy()
        selected_frc["selection_role"] = "Selected FRC - lowest LCA within 120% LCC"
        selected_frc["selection_status"] = "Within 120% LCC threshold"
        selected_frames.append(selected_frc)
    else:
        selected_frc = select_best_lca_by_module_any_cost(
            merged,
            "FRC",
            inputs.lca_column,
        )
        if not selected_frc.empty:
            selected_frc = selected_frc.copy()
            selected_frc["selection_role"] = "Override FRC - best LCA outside 120% LCC"
            selected_frc["selection_status"] = "Outside 120% LCC threshold; shown for FRC comparison"
            selected_frc["selection_cost_threshold"] = cost_threshold
            selected_frc["selection_cost_threshold_multiplier"] = inputs.cost_threshold_multiplier
            selected_frc["selection_lcc_benchmark"] = benchmark_lcc
            selected_frc["lcc_percent_of_benchmark"] = (
                selected_frc[inputs.lcc_column] / benchmark_lcc * 100.0
            )
            selected_frames.append(selected_frc)

    selected = pd.concat(selected_frames, ignore_index=True)

    selected["_alternative_key"] = build_alternative_key(selected)
    selected["selection_duplicate_note"] = ""

    duplicate_keys = selected["_alternative_key"].duplicated(keep=False)

    if duplicate_keys.any():
        for key in selected.loc[duplicate_keys, "_alternative_key"].unique():
            roles = selected.loc[selected["_alternative_key"] == key, "selection_role"].tolist()
            selected.loc[selected["_alternative_key"] == key, "selection_duplicate_note"] = " | ".join(roles)

        selected = selected.drop_duplicates(
            subset=["_alternative_key"],
            keep="first",
        ).copy()

    selected = attach_uncertainty_summary(selected, uncertainty_summary)

    selected_sensitivity = filter_sensitivity_for_selected(
        selected,
        uncertainty_summary,
        sensitivity_results,
    )

    return (
        benchmark.to_dict(orient="records"),
        selected.to_dict(orient="records"),
        eligible.to_dict(orient="records"),
        selected_sensitivity,
    )


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
