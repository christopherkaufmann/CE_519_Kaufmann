"""Module 7 – summary output graphics.
Reads Modules 1–6 CSV outputs and writes presentation-ready PNGs.
Refs: Deliverables 3–6; EPA TRACI 2.1; FHWA LCCA.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


@dataclass(frozen=True)
class SummaryOutputInputs:

    output_dir: Path = Path("outputs")
    figure_dir_name: str = "figures"
    dpi: int = 300
    max_tradeoff_points: int = 400
    max_sensitivity_parameters: int = 10


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _figure_path(inputs: SummaryOutputInputs, name: str) -> Path:
    figure_dir = inputs.output_dir / inputs.figure_dir_name
    figure_dir.mkdir(parents=True, exist_ok=True)
    return figure_dir / name


def _save(fig: plt.Figure, path: Path, inputs: SummaryOutputInputs) -> str:
    fig.tight_layout()
    fig.savefig(path, dpi=inputs.dpi, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def _clean(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _label(row: pd.Series) -> str:
    # Build labels from row-level data. Do not reuse/broadcast loop variables.
    module = _clean(row.get("module", "ALT")).upper() or "ALT"
    h = _clean(row.get("pavement_thickness_in", ""))
    subbase = _clean(row.get("subbase_thickness_in", ""))
    prefix = f"{module} | h={h} in" if h else module
    if subbase:
        prefix += f" | base={subbase} in"

    if module == "SRC":
        bar = _clean(row.get("bar_size", ""))
        spacing = _clean(row.get("bar_spacing_in", ""))
        steel = f" | {bar}@{spacing} in" if bar and spacing else ""
        return prefix + steel

    if module == "FRC":
        fe3 = _clean(row.get("fe3_psi", ""))
        return prefix + (f" | fe3={fe3} psi" if fe3 else "")

    return prefix


def _plot_feasible_by_thickness(inputs: SummaryOutputInputs) -> dict[str, Any]:
    frames = []
    for filename in ["module_1_all_results.csv", "module_2_all_results.csv"]:
        df = _read_csv(inputs.output_dir / filename)
        if not df.empty and {"module", "pavement_thickness_in", "feasible"}.issubset(df.columns):
            frames.append(df[["module", "pavement_thickness_in", "feasible"]].copy())

    if not frames:
        return {"figure": "feasible_by_thickness", "status": "skipped", "reason": "Module 1/2 result CSVs were not available."}

    df = pd.concat(frames, ignore_index=True)
    df["feasible"] = df["feasible"].astype(str).str.lower().isin(["true", "1", "yes"])
    grouped = (
        df.groupby(["module", "pavement_thickness_in"], dropna=False)
        .agg(total_alternatives=("feasible", "size"), feasible_alternatives=("feasible", "sum"))
        .reset_index()
    )
    grouped["label"] = grouped["module"].astype(str) + " - " + grouped["pavement_thickness_in"].astype(str) + " in"

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(grouped["label"], grouped["feasible_alternatives"])
    ax.set_title("Feasible Alternatives by Pavement Thickness")
    ax.set_xlabel("Alternative group")
    ax.set_ylabel("Feasible alternatives")
    ax.tick_params(axis="x", rotation=45)
    path = _figure_path(inputs, "module_7_01_feasible_by_thickness.png")
    return {"figure": "feasible_by_thickness", "status": "created", "path": _save(fig, path, inputs), "rows_used": int(len(grouped))}


def _selected_source(inputs: SummaryOutputInputs) -> pd.DataFrame:
    # Selected plots should use the final Module 6 selections, not all eligible options.
    preferred = _read_csv(inputs.output_dir / "module_6_selected_solutions.csv")
    if not preferred.empty:
        return preferred
    return _read_csv(inputs.output_dir / "module_6_eligible_solutions.csv")


def _eligible_source(inputs: SummaryOutputInputs) -> pd.DataFrame:
    preferred = _read_csv(inputs.output_dir / "module_6_eligible_solutions.csv")
    if not preferred.empty:
        return preferred
    return _selected_source(inputs)


def _tradeoff_source(inputs: SummaryOutputInputs) -> pd.DataFrame:
    lcc = _read_csv(inputs.output_dir / "module_3_lcc_results.csv")
    lca = _read_csv(inputs.output_dir / "module_4_lca_results.csv")
    if lcc.empty or lca.empty:
        return _selected_source(inputs)

    lcc = lcc.copy()
    lca = lca.copy()
    lcc["_key"] = _build_keys(lcc)
    lca["_key"] = _build_keys(lca)
    merged = lcc.merge(lca, on="_key", suffixes=("", "_lca"))
    return merged


def _plot_lcc_lca_tradeoff(inputs: SummaryOutputInputs) -> dict[str, Any]:
    df = _tradeoff_source(inputs)
    required = {"module", "total_present_worth", "gwp_total_project_kgco2e"}
    if df.empty or not required.issubset(df.columns):
        return {"figure": "lcc_lca_tradeoff", "status": "skipped", "reason": "Merged LCC/LCA result columns were not available."}

    df = df.dropna(subset=["total_present_worth", "gwp_total_project_kgco2e"]).copy()
    if len(df) > inputs.max_tradeoff_points:
        df = df.sort_values("total_present_worth").head(inputs.max_tradeoff_points)

    fig, ax = plt.subplots(figsize=(8.5, 6))
    for module, part in df.groupby(df["module"].astype(str)):
        ax.scatter(part["total_present_worth"], part["gwp_total_project_kgco2e"], label=module, alpha=0.75)
    ax.set_title("LCC vs LCA Tradeoff")
    ax.set_xlabel("Total present worth, $")
    ax.set_ylabel("Total GWP, kg CO2-eq")
    ax.legend(title="System")
    path = _figure_path(inputs, "module_7_02_lcc_lca_tradeoff.png")
    return {"figure": "lcc_lca_tradeoff", "status": "created", "path": _save(fig, path, inputs), "rows_used": int(len(df))}


def _plot_lcc_breakdown(inputs: SummaryOutputInputs) -> dict[str, Any]:
    df = _selected_source(inputs)
    components = [
        "initial_concrete_cost",
        "initial_57_stone_cost",
        "initial_reinforcing_steel_cost",
        "initial_fiber_cost",
        "end_of_life_present_worth",
    ]
    if df.empty or not set(components).issubset(df.columns):
        return {"figure": "lcc_breakdown", "status": "skipped", "reason": "Selected-solution LCC component columns were not available."}

    plot_df = df.copy()
    plot_df["label"] = plot_df.apply(_label, axis=1)
    y = range(len(plot_df))

    fig, ax = plt.subplots(figsize=(10, 5.5))
    left = pd.Series([0.0] * len(plot_df))
    for component in components:
        values = plot_df[component].fillna(0.0)
        ax.barh(plot_df["label"], values, left=left, label=component.replace("_", " "))
        left = left + values
    ax.set_title("Selected Alternative LCC Breakdown")
    ax.set_xlabel("Present worth, $")
    ax.set_ylabel("Selected alternative")
    ax.legend(fontsize=8)
    path = _figure_path(inputs, "module_7_03_lcc_breakdown.png")
    return {"figure": "lcc_breakdown", "status": "created", "path": _save(fig, path, inputs), "rows_used": int(len(plot_df))}


def _plot_lca_breakdown(inputs: SummaryOutputInputs) -> dict[str, Any]:
    df = _selected_source(inputs)
    components = [
        "gwp_concrete_kgco2e",
        "gwp_57_stone_kgco2e",
        "gwp_reinforcing_steel_kgco2e",
        "gwp_tufstrand_sf_kgco2e",
        "gwp_transport_kgco2e",
        "gwp_construction_equipment_kgco2e",
        "gwp_demolition_kgco2e",
        "gwp_crushing_kgco2e",
        "gwp_virgin_aggregate_credit_kgco2e",
    ]
    if df.empty or not set(components).issubset(df.columns):
        return {"figure": "lca_breakdown", "status": "skipped", "reason": "Selected-solution LCA component columns were not available."}

    # Stacked horizontal bar chart, intentionally matching the LCC breakdown format.
    # Positive impacts stack to the right; negative credits stack to the left so aggregate
    # recycling/offsets remain visible instead of being hidden inside the total.
    # Ref: ISO 14040/14044 life-cycle contribution analysis; EPA TRACI 2.1 impact categories.
    component_labels = {
        "gwp_concrete_kgco2e": "Concrete",
        "gwp_57_stone_kgco2e": "No. 57 stone",
        "gwp_reinforcing_steel_kgco2e": "Reinforcing steel",
        "gwp_tufstrand_sf_kgco2e": "Synthetic fiber",
        "gwp_transport_kgco2e": "Transport",
        "gwp_construction_equipment_kgco2e": "Construction equipment",
        "gwp_demolition_kgco2e": "Demolition",
        "gwp_crushing_kgco2e": "Crushing",
        "gwp_virgin_aggregate_credit_kgco2e": "Virgin aggregate credit",
    }

    plot_df = df.copy()
    plot_df["label"] = plot_df.apply(_label, axis=1)

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    positive_left = pd.Series([0.0] * len(plot_df), index=plot_df.index)
    negative_left = pd.Series([0.0] * len(plot_df), index=plot_df.index)

    for component in components:
        values = plot_df[component].fillna(0.0).astype(float)
        positive_values = values.clip(lower=0.0)
        negative_values = values.clip(upper=0.0)

        if positive_values.abs().sum() > 0:
            ax.barh(plot_df["label"], positive_values, left=positive_left, label=component_labels[component])
            positive_left = positive_left + positive_values

        if negative_values.abs().sum() > 0:
            ax.barh(plot_df["label"], negative_values, left=negative_left, label=component_labels[component])
            negative_left = negative_left + negative_values

    ax.axvline(0, linewidth=0.8)
    ax.set_title("Selected Alternative LCA Breakdown")
    ax.set_xlabel("GWP, kg CO2-eq")
    ax.set_ylabel("Selected alternative")
    ax.legend(fontsize=7, loc="center left", bbox_to_anchor=(1.02, 0.5))
    path = _figure_path(inputs, "module_7_04_lca_breakdown.png")
    return {"figure": "lca_breakdown", "status": "created", "path": _save(fig, path, inputs), "rows_used": int(len(plot_df))}


def _plot_traci_comparison(inputs: SummaryOutputInputs) -> dict[str, Any]:
    df = _selected_source(inputs)
    metrics = [
        "gwp_total_project_kgco2e",
        "acidification_total_kgso2e",
        "eutrophication_total_kgn",
        "smog_total_kgo3e",
    ]
    if df.empty or not set(metrics).issubset(df.columns):
        return {"figure": "traci_comparison", "status": "skipped", "reason": "Selected-solution TRACI screening columns were not available."}

    plot_df = df.copy()
    plot_df["label"] = plot_df.apply(_label, axis=1)
    for metric in metrics:
        max_value = plot_df[metric].abs().max()
        plot_df[metric + "_normalized"] = plot_df[metric] / max_value if max_value else 0.0

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = range(len(metrics))
    width = 0.8 / max(len(plot_df), 1)
    labels = ["GWP", "Acidification", "Eutrophication", "Smog"]
    for idx, (_, row) in enumerate(plot_df.iterrows()):
        offsets = [i + (idx - (len(plot_df) - 1) / 2) * width for i in x]
        ax.bar(offsets, [row[m + "_normalized"] for m in metrics], width=width, label=row["label"])
    ax.set_title("Normalized TRACI Screening Comparison")
    ax.set_xlabel("Impact category")
    ax.set_ylabel("Normalized value (max = 1.0)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.legend(fontsize=8)
    path = _figure_path(inputs, "module_7_05_traci_normalized_comparison.png")
    return {"figure": "traci_comparison", "status": "created", "path": _save(fig, path, inputs), "rows_used": int(len(plot_df))}


def _plot_uncertainty_intervals(inputs: SummaryOutputInputs) -> dict[str, Any]:
    summary = _read_csv(inputs.output_dir / "module_5_uncertainty_summary.csv")
    selected = _selected_source(inputs)
    needed = {"module", "pavement_thickness_in", "total_present_worth_p05", "total_present_worth_p50", "total_present_worth_p95", "gwp_total_project_kgco2e_p05", "gwp_total_project_kgco2e_p50", "gwp_total_project_kgco2e_p95"}
    if summary.empty or not needed.issubset(summary.columns):
        return {"figure": "uncertainty_intervals", "status": "skipped", "reason": "Module 5 uncertainty summary percentile columns were not available."}

    plot_df = summary.copy()
    if not selected.empty:
        keys = set(_build_keys(selected))
        plot_df = plot_df.loc[_build_keys(plot_df).isin(keys)].copy()
    if plot_df.empty:
        plot_df = summary.sort_values("total_present_worth_p50").head(6).copy()

    plot_df["label"] = plot_df.apply(_label, axis=1)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    y_positions = range(len(plot_df))
    xerr_low = plot_df["total_present_worth_p50"] - plot_df["total_present_worth_p05"]
    xerr_high = plot_df["total_present_worth_p95"] - plot_df["total_present_worth_p50"]
    ax.errorbar(plot_df["total_present_worth_p50"], list(y_positions), xerr=[xerr_low, xerr_high], fmt="o", capsize=4)
    ax.set_yticks(list(y_positions))
    ax.set_yticklabels(plot_df["label"])
    ax.set_title("LCC Uncertainty Intervals")
    ax.set_xlabel("Total present worth, $ (P05-P95)")
    ax.set_ylabel("Alternative")
    path = _figure_path(inputs, "module_7_06_lcc_uncertainty_intervals.png")
    return {"figure": "uncertainty_intervals", "status": "created", "path": _save(fig, path, inputs), "rows_used": int(len(plot_df))}


def _build_keys(df: pd.DataFrame) -> pd.Series:
    key_cols = ["module", "subbase_thickness_in", "pavement_thickness_in", "bar_size", "bar_spacing_in", "fe3_psi"]
    work = df.copy()
    for col in key_cols:
        if col not in work.columns:
            work[col] = ""
    return work[key_cols].fillna("").astype(str).agg("|".join, axis=1)


def _selected_sensitivity_source(inputs: SummaryOutputInputs) -> pd.DataFrame:
    # Keep sensitivity results aligned with the alternatives selected in Module 6.
    # Ref: Deliverable 6 selection/optimization workflow; Module 5 Spearman sensitivity output.
    sensitivity = _read_csv(inputs.output_dir / "module_5_spearman_sensitivity.csv")
    summary = _read_csv(inputs.output_dir / "module_5_uncertainty_summary.csv")
    selected = _selected_source(inputs)
    required = {"alternative_id", "output", "parameter", "abs_spearman_rho"}
    if sensitivity.empty or not required.issubset(sensitivity.columns):
        return pd.DataFrame()

    filtered = sensitivity.copy()
    if not summary.empty and not selected.empty:
        summary = summary.copy()
        summary["_key"] = _build_keys(summary)
        selected_keys = set(_build_keys(selected))
        selected_ids = summary.loc[summary["_key"].isin(selected_keys), "alternative_id"].dropna().tolist()
        if selected_ids:
            filtered = filtered.loc[filtered["alternative_id"].isin(selected_ids)].copy()
    return filtered


def _plot_sensitivity_by_output(
    inputs: SummaryOutputInputs,
    *,
    output_name: str,
    figure_name: str,
    title: str,
    path_name: str,
    exclude_parameters: set[str] | None = None,
) -> dict[str, Any]:
    sensitivity = _selected_sensitivity_source(inputs)
    if sensitivity.empty:
        return {"figure": figure_name, "status": "skipped", "reason": "Module 5 Spearman sensitivity columns were not available."}

    filtered = sensitivity.loc[sensitivity["output"].astype(str) == output_name].copy()
    if exclude_parameters:
        filtered = filtered.loc[~filtered["parameter"].astype(str).isin(exclude_parameters)].copy()
    if filtered.empty:
        return {"figure": figure_name, "status": "skipped", "reason": f"No Spearman sensitivity rows were found for {output_name}."}

    # Group by parameter so the chart stays readable when multiple alternatives are selected.
    # Absolute rho is used for ranking because both positive and negative monotonic effects are important.
    grouped = (
        filtered.groupby("parameter", dropna=False)["abs_spearman_rho"]
        .max()
        .sort_values(ascending=False)
        .head(inputs.max_sensitivity_parameters)
        .sort_values(ascending=True)
    )

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.barh(grouped.index.astype(str), grouped.values)
    ax.set_title(title)
    ax.set_xlabel("Maximum absolute Spearman rho")
    ax.set_ylabel("Input parameter")
    ax.set_xlim(0, max(1.0, float(grouped.max()) * 1.10 if len(grouped) else 1.0))
    path = _figure_path(inputs, path_name)
    return {"figure": figure_name, "status": "created", "path": _save(fig, path, inputs), "rows_used": int(len(grouped))}


def _plot_lcc_sensitivity(inputs: SummaryOutputInputs) -> dict[str, Any]:
    return _plot_sensitivity_by_output(
        inputs,
        output_name="total_present_worth",
        figure_name="lcc_sensitivity_ranking",
        title="Spearman Sensitivity Ranking – LCC",
        path_name="module_7_07a_spearman_sensitivity_lcc.png",
    )


def _plot_lca_sensitivity(inputs: SummaryOutputInputs) -> dict[str, Any]:
    return _plot_sensitivity_by_output(
        inputs,
        output_name="gwp_total_project_kgco2e",
        figure_name="lca_sensitivity_ranking",
        title="Spearman Sensitivity Ranking – LCA",
        path_name="module_7_07b_spearman_sensitivity_lca.png",
        exclude_parameters={
            # Cost-only variables do not belong on the LCA sensitivity plot.
            # LCA uncertainty should be controlled by environmental inventory/emission factors.
            "concrete_unit_cost",
            "stone_57_unit_cost",
            "rebar_unit_cost",
            "fiber_unit_cost",
            "demolition_cost",
            "crushing_cost",
            "recycled_aggregate_credit",
            "discount_rate",
            "subgrade_k_pci",
        },
    )


def _plot_sensitivity(inputs: SummaryOutputInputs) -> dict[str, Any]:
    # Retain the legacy combined chart for backward compatibility with earlier presentations.
    sensitivity = _selected_sensitivity_source(inputs)
    if sensitivity.empty:
        return {"figure": "sensitivity_ranking", "status": "skipped", "reason": "Module 5 Spearman sensitivity columns were not available."}

    filtered = sensitivity.loc[sensitivity["output"].astype(str).isin(["total_present_worth", "gwp_total_project_kgco2e", "demand_capacity_ratio_k"])]
    if filtered.empty:
        filtered = sensitivity.copy()

    grouped = (
        filtered.groupby("parameter", dropna=False)["abs_spearman_rho"]
        .max()
        .sort_values(ascending=False)
        .head(inputs.max_sensitivity_parameters)
        .sort_values(ascending=True)
    )

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.barh(grouped.index.astype(str), grouped.values)
    ax.set_title("Spearman Sensitivity Ranking – Combined")
    ax.set_xlabel("Maximum absolute Spearman rho")
    ax.set_ylabel("Input parameter")
    path = _figure_path(inputs, "module_7_07_spearman_sensitivity_ranking_combined.png")
    return {"figure": "sensitivity_ranking_combined", "status": "created", "path": _save(fig, path, inputs), "rows_used": int(len(grouped))}


def _plot_selection_summary(inputs: SummaryOutputInputs) -> dict[str, Any]:
    selected = _selected_source(inputs)
    if selected.empty or not {"total_present_worth", "gwp_total_project_kgco2e"}.issubset(selected.columns):
        return {"figure": "selection_summary", "status": "skipped", "reason": "Module 6 selected solution CSV was not available."}

    df = selected.copy()
    df["label"] = df.apply(_label, axis=1)
    metrics = ["total_present_worth", "gwp_total_project_kgco2e"]
    norm = pd.DataFrame({"label": df["label"]})
    for metric in metrics:
        max_value = df[metric].abs().max()
        norm[metric] = df[metric] / max_value if max_value else 0.0

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    x = range(len(df))
    ax.bar([i - 0.2 for i in x], norm["total_present_worth"], width=0.4, label="Normalized LCC")
    ax.bar([i + 0.2 for i in x], norm["gwp_total_project_kgco2e"], width=0.4, label="Normalized GWP")
    ax.set_xticks(list(x))
    ax.set_xticklabels(df["label"], rotation=30, ha="right")
    ax.set_title("Selected Alternative Summary")
    ax.set_ylabel("Normalized value (max = 1.0)")
    ax.legend()
    path = _figure_path(inputs, "module_7_08_selected_alternative_summary.png")
    return {"figure": "selection_summary", "status": "created", "path": _save(fig, path, inputs), "rows_used": int(len(df))}


def run_module_7_summary_output(inputs: SummaryOutputInputs | None = None) -> list[dict[str, Any]]:
    inputs = inputs or SummaryOutputInputs()
    inputs.output_dir.mkdir(parents=True, exist_ok=True)
    (inputs.output_dir / inputs.figure_dir_name).mkdir(parents=True, exist_ok=True)

    manifest = [
        _plot_feasible_by_thickness(inputs),
        _plot_lcc_lca_tradeoff(inputs),
        _plot_lcc_breakdown(inputs),
        _plot_lca_breakdown(inputs),
        _plot_traci_comparison(inputs),
        _plot_uncertainty_intervals(inputs),
        _plot_lcc_sensitivity(inputs),
        _plot_lca_sensitivity(inputs),
        _plot_sensitivity(inputs),
        _plot_selection_summary(inputs),
    ]

    manifest_path = inputs.output_dir / "module_7_figure_manifest.csv"
    pd.DataFrame(manifest).to_csv(manifest_path, index=False)
    return manifest


def write_summary_manifest_csv(results: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(output_path, index=False)
