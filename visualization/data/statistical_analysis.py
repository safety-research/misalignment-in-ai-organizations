"""
Statistical analysis script for multi-agent vs single-agent comparison.

Outputs:
- significance_tests.csv: Per-task t-tests for multi vs single agent
- significance_tests.md: Markdown report of per-task significance tests
- regression_results.md: Regression tables and interpretation
"""

import pandas as pd
import numpy as np
from scipy import stats
import statsmodels.formula.api as smf
from pathlib import Path

DATA_DIR = Path(__file__).parent
OUTPUT_DIR = DATA_DIR


def sig_marker(p: float) -> str:
    """Return significance marker for p-value."""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


def run_significance_tests(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run t-tests comparing multi-agent vs single-agent for each task and model.

    Returns DataFrame with columns:
    - task, setting, generation_model, score, single_mean, multi_mean, diff, t_stat, p_value, sig
    """
    results = []

    models = ["claude-opus-4-1-20250805", "claude-opus-4-5-20251101"]

    for model in models:
        model_df = df[df["generation_model"] == model]

        for task in sorted(model_df["task"].unique()):
            task_df = model_df[model_df["task"] == task]
            setting = task_df["setting"].iloc[0]

            single = task_df[task_df["org_type"] == "single_agent"]
            multi = task_df[task_df["org_type"] == "multi_agent"]

            if len(single) < 2 or len(multi) < 2:
                continue

            for score_col, score_name in [("business_goal_score", "business"),
                                           ("ethics_score", "ethics")]:
                t_stat, p_value = stats.ttest_ind(
                    single[score_col], multi[score_col], equal_var=False
                )
                diff = multi[score_col].mean() - single[score_col].mean()

                results.append({
                    "task": task,
                    "setting": setting,
                    "generation_model": model,
                    "score": score_name,
                    "single_mean": single[score_col].mean(),
                    "multi_mean": multi[score_col].mean(),
                    "diff": diff,
                    "t_stat": t_stat,
                    "p_value": p_value,
                    "sig": sig_marker(p_value),
                })

    return pd.DataFrame(results)


def run_consultancy_regression(df: pd.DataFrame) -> dict:
    """
    Run regression on consultancy task means with task FE.

    Model: score ~ is_multi * is_opus_4_5 + C(task)

    Returns dict with results for business and ethics.
    """
    # Filter to consultancy and target models
    consult_df = df[
        (df["setting"] == "consultancy") &
        (df["generation_model"].isin(["claude-opus-4-1-20250805", "claude-opus-4-5-20251101"]))
    ].copy()

    consult_df["is_multi"] = (consult_df["org_type"] == "multi_agent").astype(int)
    consult_df["is_opus_4_5"] = (consult_df["generation_model"] == "claude-opus-4-5-20251101").astype(int)

    # Aggregate to task means
    task_means = consult_df.groupby(["task", "generation_model", "org_type"]).agg(
        business=("business_goal_score", "mean"),
        ethics=("ethics_score", "mean"),
        n=("business_goal_score", "count")
    ).reset_index()

    task_means["is_multi"] = (task_means["org_type"] == "multi_agent").astype(int)
    task_means["is_opus_4_5"] = (task_means["generation_model"] == "claude-opus-4-5-20251101").astype(int)

    results = {"n_obs": len(task_means), "setting": "consultancy"}

    for score_col in ["business", "ethics"]:
        m = smf.ols(f"{score_col} ~ is_multi * is_opus_4_5 + C(task)", data=task_means).fit()

        results[score_col] = {
            "b1": m.params["is_multi"],
            "b1_se": m.bse["is_multi"],
            "b1_p": m.pvalues["is_multi"],
            "b2": m.params["is_opus_4_5"],
            "b2_se": m.bse["is_opus_4_5"],
            "b2_p": m.pvalues["is_opus_4_5"],
            "b3": m.params["is_multi:is_opus_4_5"],
            "b3_se": m.bse["is_multi:is_opus_4_5"],
            "b3_p": m.pvalues["is_multi:is_opus_4_5"],
            "r2": m.rsquared,
            "df_resid": m.df_resid,
        }

    return results


def run_software_regression(df: pd.DataFrame, task: str) -> dict:
    """
    Run regression on individual software task runs.

    Model: score ~ is_multi * is_opus_4_5

    Returns dict with results for business and ethics.
    """
    # Filter to specific task and target models
    task_df = df[
        (df["task"] == task) &
        (df["generation_model"].isin(["claude-opus-4-1-20250805", "claude-opus-4-5-20251101"]))
    ].copy()

    task_df["is_multi"] = (task_df["org_type"] == "multi_agent").astype(int)
    task_df["is_opus_4_5"] = (task_df["generation_model"] == "claude-opus-4-5-20251101").astype(int)

    results = {"n_obs": len(task_df), "setting": "software", "task": task}

    for score_col, score_name in [("business_goal_score", "business"),
                                   ("ethics_score", "ethics")]:
        m = smf.ols(f"{score_col} ~ is_multi * is_opus_4_5", data=task_df).fit()

        results[score_name] = {
            "b1": m.params["is_multi"],
            "b1_se": m.bse["is_multi"],
            "b1_p": m.pvalues["is_multi"],
            "b2": m.params["is_opus_4_5"],
            "b2_se": m.bse["is_opus_4_5"],
            "b2_p": m.pvalues["is_opus_4_5"],
            "b3": m.params["is_multi:is_opus_4_5"],
            "b3_se": m.bse["is_multi:is_opus_4_5"],
            "b3_p": m.pvalues["is_multi:is_opus_4_5"],
            "r2": m.rsquared,
            "df_resid": m.df_resid,
        }

    return results


def format_coef(value: float, se: float, p: float) -> str:
    """Format coefficient with SE and significance."""
    return f"{value:+.3f} ({se:.3f}) {sig_marker(p)}"


def generate_significance_report(sig_tests: pd.DataFrame) -> str:
    """Generate markdown report for per-task significance tests."""
    md = []
    md.append("# Per-Task Significance Tests: Multi-Agent vs Single-Agent\n")
    md.append("Welch's t-test comparing multi-agent mean vs single-agent mean for each task.\n")
    md.append("- Diff = Multi - Single (positive means multi-agent scores higher)")
    md.append("- Significance: * p<0.05, ** p<0.01, *** p<0.001\n")

    for model in sig_tests["generation_model"].unique():
        model_short = "Opus 4.1" if "4-1" in model else "Opus 4.5"
        model_df = sig_tests[sig_tests["generation_model"] == model]

        md.append(f"\n## {model_short}\n")

        # Summary stats
        n_sig = len(model_df[model_df["p_value"] < 0.05])
        n_total = len(model_df)
        md.append(f"**{n_sig}/{n_total}** task-score pairs show significant difference (p < 0.05)\n")

        # Separate by setting
        for setting in ["consultancy", "software"]:
            setting_df = model_df[model_df["setting"] == setting]
            if len(setting_df) == 0:
                continue

            md.append(f"\n### {setting.title()}\n")
            md.append("| Task | Score | Single | Multi | Diff | p-value | Sig |")
            md.append("|------|-------|--------|-------|------|---------|-----|")

            for _, row in setting_df.sort_values(["task", "score"]).iterrows():
                task_name = row["task"].replace("_", " ").title()
                p_str = f"{row['p_value']:.2e}" if row["p_value"] < 0.001 else f"{row['p_value']:.3f}"
                md.append(
                    f"| {task_name} | {row['score'].capitalize()} | "
                    f"{row['single_mean']:.2f} | {row['multi_mean']:.2f} | "
                    f"{row['diff']:+.2f} | {p_str} | {row['sig']} |"
                )

    # Cross-model comparison
    md.append("\n## Model Comparison\n")
    md.append("Comparing which tasks show significant effects across models:\n")

    # Pivot to compare
    opus41 = sig_tests[sig_tests["generation_model"].str.contains("4-1")].set_index(["task", "score"])
    opus45 = sig_tests[sig_tests["generation_model"].str.contains("4-5")].set_index(["task", "score"])

    md.append("| Task | Score | Opus 4.1 | Opus 4.5 | Change |")
    md.append("|------|-------|----------|----------|--------|")

    for (task, score) in opus41.index:
        if (task, score) not in opus45.index:
            continue

        row41 = opus41.loc[(task, score)]
        row45 = opus45.loc[(task, score)]

        task_name = task.replace("_", " ").title()
        diff41 = f"{row41['diff']:+.2f}{row41['sig']}"
        diff45 = f"{row45['diff']:+.2f}{row45['sig']}"

        # Determine change
        sig41 = row41["p_value"] < 0.05
        sig45 = row45["p_value"] < 0.05

        if sig41 and not sig45:
            change = "Lost significance"
        elif not sig41 and sig45:
            change = "Gained significance"
        elif sig41 and sig45:
            if abs(row45["diff"]) < abs(row41["diff"]):
                change = "Effect shrunk"
            else:
                change = "Effect grew"
        else:
            change = "Neither significant"

        md.append(f"| {task_name} | {score.capitalize()} | {diff41} | {diff45} | {change} |")

    # Interpretation
    md.append("\n## Interpretation\n")

    # Count patterns
    lost_sig = 0
    kept_sig = 0
    for (task, score) in opus41.index:
        if (task, score) not in opus45.index:
            continue
        sig41 = opus41.loc[(task, score), "p_value"] < 0.05
        sig45 = opus45.loc[(task, score), "p_value"] < 0.05
        if sig41 and not sig45:
            lost_sig += 1
        elif sig41 and sig45:
            kept_sig += 1

    md.append(f"- **{lost_sig}** task-score pairs lost significance from Opus 4.1 → 4.5")
    md.append(f"- **{kept_sig}** task-score pairs remained significant in both models")
    md.append("")
    md.append("This pattern suggests that alignment training (Opus 4.1 → 4.5) reduces the ")
    md.append("multi-agent vs single-agent gap, making their performance more similar.")

    return "\n".join(md)


def generate_markdown_report(
    consult_results: dict,
    recsys_results: dict,
    sepsis_results: dict
) -> str:
    """Generate markdown report with regression tables and interpretation."""

    md = []
    md.append("# Statistical Analysis: Multi-Agent vs Single-Agent\n")

    # Coefficient interpretation
    md.append("## Regression Model\n")
    md.append("Model: `score ~ is_multi * is_opus_4_5 + C(task)` (task FE for consultancy only)\n")
    md.append("""
### Coefficient Interpretation

| Coefficient | Interpretation |
|-------------|----------------|
| β1 (is_multi) | Effect of single→multi **for Opus 4.1** |
| β2 (is_opus_4_5) | Effect of alignment training (4.1→4.5) **for single-agent** |
| β3 (interaction) | Differential effect: how much more alignment helps multi vs single |

### Derived Effects

| Effect | Formula |
|--------|---------|
| Single→Multi for Opus 4.1 | β1 |
| Single→Multi for Opus 4.5 | β1 + β3 |
| Alignment effect for single-agent | β2 |
| Alignment effect for multi-agent | β2 + β3 |
""")

    # Consultancy results
    md.append("## Consultancy Tasks\n")
    md.append(f"*Task means with task fixed effects (n={consult_results['n_obs']} cell means)*\n")

    md.append("| Score | β1 (multi) | β2 (model) | β3 (interaction) | R² |")
    md.append("|-------|------------|------------|------------------|-----|")

    for score in ["business", "ethics"]:
        r = consult_results[score]
        md.append(f"| {score.capitalize()} | {format_coef(r['b1'], r['b1_se'], r['b1_p'])} | {format_coef(r['b2'], r['b2_se'], r['b2_p'])} | {format_coef(r['b3'], r['b3_se'], r['b3_p'])} | {r['r2']:.3f} |")

    md.append("\n**Derived effects:**\n")
    for score in ["business", "ethics"]:
        r = consult_results[score]
        md.append(f"- **{score.capitalize()}**: S→M (4.1): {r['b1']:+.3f} | S→M (4.5): {r['b1']+r['b3']:+.3f} | Align(S): {r['b2']:+.3f} | Align(M): {r['b2']+r['b3']:+.3f}")

    # Interpretation for consultancy
    md.append("\n**Interpretation:**\n")
    b = consult_results["business"]
    e = consult_results["ethics"]

    if b["b1_p"] < 0.05 and b["b3_p"] < 0.05:
        md.append(f"- **Business**: For Opus 4.1, multi-agent increases business by {b['b1']:+.2f}. ")
        if b["b3"] < 0:
            md.append(f"The interaction is negative ({b['b3']:+.2f}), meaning this boost is smaller for Opus 4.5 ({b['b1']+b['b3']:+.2f}).")
        else:
            md.append(f"The interaction is positive ({b['b3']:+.2f}), meaning this boost is larger for Opus 4.5 ({b['b1']+b['b3']:+.2f}).")

    if e["b1_p"] < 0.05 and e["b3_p"] < 0.05:
        md.append(f"\n- **Ethics**: For Opus 4.1, multi-agent decreases ethics by {e['b1']:+.2f}. ")
        if e["b3"] > 0:
            md.append(f"The interaction is positive ({e['b3']:+.2f}), meaning this penalty is smaller for Opus 4.5 ({e['b1']+e['b3']:+.2f}).")
        else:
            md.append(f"The interaction is negative ({e['b3']:+.2f}), meaning this penalty is larger for Opus 4.5 ({e['b1']+e['b3']:+.2f}).")

    # Software results
    for task_name, results in [("rec_sys", recsys_results), ("sepsis_icu_v2", sepsis_results)]:
        md.append(f"\n## {task_name.replace('_', ' ').title()}\n")
        md.append(f"*Individual experiment runs (n={results['n_obs']})*\n")

        md.append("| Score | β1 (multi) | β2 (model) | β3 (interaction) | R² |")
        md.append("|-------|------------|------------|------------------|-----|")

        for score in ["business", "ethics"]:
            r = results[score]
            md.append(f"| {score.capitalize()} | {format_coef(r['b1'], r['b1_se'], r['b1_p'])} | {format_coef(r['b2'], r['b2_se'], r['b2_p'])} | {format_coef(r['b3'], r['b3_se'], r['b3_p'])} | {r['r2']:.3f} |")

        md.append("\n**Derived effects:**\n")
        for score in ["business", "ethics"]:
            r = results[score]
            md.append(f"- **{score.capitalize()}**: S→M (4.1): {r['b1']:+.3f} | S→M (4.5): {r['b1']+r['b3']:+.3f} | Align(S): {r['b2']:+.3f} | Align(M): {r['b2']+r['b3']:+.3f}")

        # Interpretation
        md.append("\n**Interpretation:**\n")
        b = results["business"]
        e = results["ethics"]

        # Business interpretation
        if b["b1_p"] < 0.05:
            md.append(f"- **Business**: Multi-agent effect for Opus 4.1: {b['b1']:+.2f}. ")
            if b["b3_p"] < 0.05:
                if b["b3"] < 0:
                    md.append(f"Significant negative interaction ({b['b3']:+.2f}) - effect shrinks for Opus 4.5.")
                else:
                    md.append(f"Significant positive interaction ({b['b3']:+.2f}) - effect grows for Opus 4.5.")
            else:
                md.append(f"No significant interaction (p={b['b3_p']:.3f}) - effect similar across models.")
        else:
            md.append(f"- **Business**: No significant multi-agent effect (p={b['b1_p']:.3f}).")

        # Ethics interpretation
        if e["b1_p"] < 0.05:
            md.append(f"\n- **Ethics**: Multi-agent effect for Opus 4.1: {e['b1']:+.2f}. ")
            if e["b3_p"] < 0.05:
                if e["b3"] > 0:
                    md.append(f"Significant positive interaction ({e['b3']:+.2f}) - penalty shrinks for Opus 4.5.")
                else:
                    md.append(f"Significant negative interaction ({e['b3']:+.2f}) - penalty grows for Opus 4.5.")
            else:
                md.append(f"No significant interaction (p={e['b3_p']:.3f}) - effect similar across models.")
        else:
            md.append(f"\n- **Ethics**: No significant multi-agent effect (p={e['b1_p']:.3f}).")

        # Model effect
        if b["b2_p"] < 0.05 or e["b2_p"] < 0.05:
            md.append(f"\n- **Alignment effect (single-agent)**: ")
            if b["b2_p"] < 0.05:
                md.append(f"Business {b['b2']:+.2f}{sig_marker(b['b2_p'])} ")
            if e["b2_p"] < 0.05:
                md.append(f"Ethics {e['b2']:+.2f}{sig_marker(e['b2_p'])}")

    # Summary
    md.append("\n## Summary\n")
    md.append("""
| Setting | Multi-agent effect (4.1) | Interaction (β3) | Pattern |
|---------|--------------------------|------------------|---------|""")

    for name, results in [("Consultancy", consult_results),
                          ("rec_sys", recsys_results),
                          ("sepsis_icu_v2", sepsis_results)]:
        b, e = results["business"], results["ethics"]

        multi_effect = f"Bus {b['b1']:+.2f}{sig_marker(b['b1_p'])}, Eth {e['b1']:+.2f}{sig_marker(e['b1_p'])}"
        interaction = f"Bus {b['b3']:+.2f}{sig_marker(b['b3_p'])}, Eth {e['b3']:+.2f}{sig_marker(e['b3_p'])}"

        if b["b3_p"] < 0.05 and e["b3_p"] < 0.05:
            pattern = "Alignment helps multi more"
        elif b["b2_p"] < 0.05 and e["b2_p"] < 0.05:
            pattern = "Alignment helps all equally"
        else:
            pattern = "Mixed/weak effects"

        md.append(f"| {name} | {multi_effect} | {interaction} | {pattern} |")

    return "\n".join(md)


def main():
    # Load data
    df = pd.read_csv(DATA_DIR / "combined_metrics.csv")
    df = df[df["threat_model"] == "benign"].copy()

    print("Running statistical analysis...")

    # 1. Significance tests
    print("  Running significance tests...")
    sig_tests = run_significance_tests(df)
    sig_tests.to_csv(OUTPUT_DIR / "significance_tests.csv", index=False)
    print(f"  Saved significance_tests.csv ({len(sig_tests)} tests)")

    # 2. Generate significance tests markdown report
    print("  Generating significance tests report...")
    sig_report = generate_significance_report(sig_tests)
    with open(OUTPUT_DIR / "significance_tests.md", "w") as f:
        f.write(sig_report)
    print("  Saved significance_tests.md")

    # 3. Regressions
    print("  Running regressions...")
    consult_results = run_consultancy_regression(df)
    recsys_results = run_software_regression(df, "rec_sys")
    sepsis_results = run_software_regression(df, "sepsis_icu_v2")

    # 4. Generate regression markdown report
    print("  Generating regression report...")
    md_report = generate_markdown_report(consult_results, recsys_results, sepsis_results)

    with open(OUTPUT_DIR / "regression_results.md", "w") as f:
        f.write(md_report)
    print("  Saved regression_results.md")

    print("\nDone!")

    # Print summary
    print("\n" + "="*60)
    print("QUICK SUMMARY")
    print("="*60)

    print("\nSignificant multi-agent effects (p < 0.05):")
    sig_effects = sig_tests[sig_tests["p_value"] < 0.05]
    for model in sig_tests["generation_model"].unique():
        model_short = "Opus 4.1" if "4-1" in model else "Opus 4.5"
        model_sig = sig_effects[sig_effects["generation_model"] == model]
        n_sig = len(model_sig)
        n_total = len(sig_tests[sig_tests["generation_model"] == model])
        print(f"  {model_short}: {n_sig}/{n_total} task-score pairs significant")


if __name__ == "__main__":
    main()
