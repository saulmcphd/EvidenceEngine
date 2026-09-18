"""
reliability.py - EvidenceEngine Phase 4: recall-first reliability of AI screening/extraction
=============================================================================================
Measures the AI second screener/extractor against INDEPENDENT, BLIND human decisions (the human
decided before seeing any AI output - never a reconciled consensus that already contains the AI or
the screener being measured; that would inflate agreement). Recall-first throughout (RAISE 2 §1,
p.5: recall must not be sacrificed for precision; Appendix 1, p.34: F1 is usually wrong for
screening - prefer F-beta).

This module was hardened against a 34-finding adversarial methodology review (2026-06-29). Key
choices a Research Synthesis Methods referee should know are documented in the output `_caveats`
of each function (sidedness of the acceptance bound, WSS applicability, kappa CI method, the
fatigue estimand, the blind-first reference, etc.) so every report is self-documenting.

CLI
---
  python reliability.py screening  --human human_decisions.csv --ai Abstract_Audit_*.csv [--stage abstract] [--recall 0.95] [--stratify study_design] [--beta 3] [--beta-rationale "..."]
  python reliability.py fatigue     --human human_decisions.csv   # leave-one-screener-out human-only reference
  python reliability.py extraction  --audit Audit_Ready_Research_Data_*.csv
  python reliability.py selftest
"""

from __future__ import annotations

import argparse
import json
import math
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

POSITIVE = "include"
LANDIS_KOCH = [(-1.0, "Poor"), (0.0, "Slight"), (0.20, "Fair"), (0.40, "Moderate"),
               (0.60, "Substantial"), (0.80, "Almost perfect")]
# Default labels that count as a fabrication/hallucination in the extraction audit Error_Category.
HALLUCINATION_LABELS = {"confabulation", "fabrication", "hallucination", "not in source", "not_in_source"}


def landis_koch(kappa: float) -> str:
    if kappa is None or (isinstance(kappa, float) and math.isnan(kappa)):
        return "n/a"
    band = "Poor"
    for lo, name in LANDIS_KOCH:
        if kappa >= lo:
            band = name
    return band


def to_binary(label, uncertain_as_include: bool = True) -> int:
    """Map a screening decision to 1 (include / positive) or 0 (exclude). Recall-first default:
    an 'uncertain' abstract decision counts as INCLUDE (it stays in)."""
    s = str(label).strip().lower()
    if s in ("1", "include", "included", "yes", "y", "true", "maybe"):
        return 1
    if s in ("uncertain", "unclear", "unsure"):
        return 1 if uncertain_as_include else 0
    return 0


# --------------------------------------------------------------------------------------------------
# Confidence intervals
# --------------------------------------------------------------------------------------------------
def wilson_ci(successes: int, n: int, conf: float = 0.95, one_sided: bool = False) -> tuple[float, float]:
    """Wilson score interval for a proportion (correct near 0/1 and for small n). With one_sided=True
    returns a one-sided (1-alpha) LOWER bound paired with 1.0 - used for the recall acceptance gate,
    where the decision question ('is true recall >= T?') is inherently one-sided."""
    if n == 0:
        return (float("nan"), float("nan"))
    from scipy.stats import norm
    z = norm.ppf(conf) if one_sided else norm.ppf(1 - (1 - conf) / 2)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    if one_sided:
        return (max(0.0, centre - half), 1.0)
    return (max(0.0, centre - half), min(1.0, centre + half))


def bootstrap_ci(values_a, values_b, stat_fn, n_boot: int = 5000, conf: float = 0.95,
                 seed: int = 12345) -> tuple[float, float, float]:
    """Percentile bootstrap CI for a paired statistic (resample record indices with replacement).
    Returns (lo, hi, dropped_fraction). NaN-returning resamples (e.g. degenerate kappa) are dropped
    and their fraction reported as a stability diagnostic. NB: a record-level i.i.d. bootstrap
    assumes records are exchangeable - if labels cluster by screener/stratum it is anti-conservative;
    use a cluster bootstrap and document the inferential unit in the methods."""
    a = np.asarray(values_a)
    b = np.asarray(values_b)
    rng = np.random.default_rng(seed)
    n = len(a)
    stats, dropped = [], 0
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        try:
            v = stat_fn(a[idx], b[idx])
        except Exception:
            v = float("nan")
        if v is None or (isinstance(v, float) and math.isnan(v)):
            dropped += 1
        else:
            stats.append(v)
    if not stats:
        return (float("nan"), float("nan"), 1.0)
    lo = float(np.percentile(stats, 100 * (1 - conf) / 2))
    hi = float(np.percentile(stats, 100 * (1 - (1 - conf) / 2)))
    return (lo, hi, dropped / n_boot)


# --------------------------------------------------------------------------------------------------
# Screening metrics (recall-first)
# --------------------------------------------------------------------------------------------------
def _confusion(human_bin, ai_bin):
    h = np.asarray(human_bin); a = np.asarray(ai_bin)
    return (int(np.sum((h == 1) & (a == 1))), int(np.sum((h == 0) & (a == 1))),
            int(np.sum((h == 0) & (a == 0))), int(np.sum((h == 1) & (a == 0))))


def kappa_with_ci(human_bin, ai_bin, conf: float = 0.95, seed: int = 12345, n_boot: int = 5000) -> dict:
    """Cohen's kappa (SECONDARY) with a percentile-bootstrap 95% CI, Landis-Koch band on BOTH the
    point and the interval, prevalence index + a clearly-flagged PABAK diagnostic."""
    from sklearn.metrics import cohen_kappa_score

    def _kappa(x, y):
        # a resample where EITHER rater is single-class makes kappa undefined (0/0) -> NaN (dropped),
        # not 0 (which would bias the CI lower bound toward 0 at low prevalence).
        if len(np.unique(x)) < 2 or len(np.unique(y)) < 2:
            return np.nan
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return cohen_kappa_score(x, y)

    h = np.asarray(human_bin); a = np.asarray(ai_bin)
    k = float(_kappa(h, a))
    lo, hi, dropped = bootstrap_ci(h, a, _kappa, conf=conf, seed=seed, n_boot=n_boot)
    prev_index = abs(float(np.mean(h == 1)) - float(np.mean(h == 0)))
    po = float(np.mean(h == a))
    band = landis_koch(k)
    band_lo, band_hi = landis_koch(lo), landis_koch(hi)
    return {"kappa": k, "ci": [lo, hi], "ci_method": f"percentile bootstrap, n_boot={n_boot}, seed={seed}",
            "bootstrap_dropped_fraction": dropped,
            "interpretation_landis_koch": band if band_lo == band_hi else f"{band_lo}–{band_hi} (band of the 95% CI)",
            "prevalence_index": prev_index,
            "pabak_DIAGNOSTIC": 2 * po - 1,
            "pabak_caveat": ("PABAK = 2*observed_agreement - 1, computed under an ASSUMED balanced 50/50 "
                             "margin; it is NOT prevalence-corrected for this dataset and must not be read as "
                             "'the prevalence-adjusted kappa'. Diagnostic only."),
            "note": ("kappa is prevalence-sensitive and unstable at small n; screening is highly imbalanced, "
                     "so this is SECONDARY, reported with its 95% CI, never the headline. The percentile "
                     "bootstrap is the weakest CI for kappa - cross-check with an analytic/BCa SE before the "
                     "paper. CI assumes records are exchangeable (no screener/stratum clustering). "
                     "(Landis & Koch 1977; RAISE 2 Appendix 1.)")}


def wss_at_recall(human_bin, scores, target_recall: float = 0.95) -> dict:
    """Work Saved over Sampling at a target recall. Needs a per-record AI RANKING score. Tie-safe:
    the cutoff is the highest SCORE value whose at-or-above set reaches the target recall, and ties
    are broken PESSIMISTICALLY (a whole tied block counts as screened), so WSS does not depend on
    input row order. WSS@r = (TN+FN)/N - (1-r) at that cutoff."""
    h = np.asarray(human_bin)
    n = len(h); pos = int(h.sum())
    caveat = ("WSS assumes a PRIORITISED-screening workflow (screen the top-ranked, stop at the recall "
              "target). EvidenceEngine's default is a binary second screener that reconciles EVERY record, "
              "so WSS here is a RANKING-QUALITY diagnostic of the confidence signal, not a literal workload "
              "saving. The scores are uncalibrated LLM self-reported confidence. (Cohen et al. 2006.)")
    if scores is None or pos == 0:
        return {"wss": None, "note": "WSS needs AI ranking scores and >=1 positive; not computed.", "_caveat": caveat}
    s = np.asarray(scores, dtype=float)
    keep = ~np.isnan(s)
    excluded_unscored = int((~keep).sum())
    h, s = h[keep], s[keep]
    n = len(h); pos = int(h.sum())
    if pos == 0 or len(np.unique(s)) < 2:
        return {"wss": None, "excluded_unscored": excluded_unscored,
                "note": "after dropping unscored records, too few positives or no score variation for WSS.",
                "_caveat": caveat}
    need = math.ceil(target_recall * pos)
    # distinct scores, descending; smallest cutoff (largest 'screened' set) is pessimistic on ties
    for t in sorted(np.unique(s), reverse=True):
        at_or_above = s >= t
        tp_above = int(h[at_or_above].sum())
        if tp_above >= need:
            reached = int(at_or_above.sum())
            break
    else:
        reached = n
    saved = n - reached
    realised_recall = int(h[s >= t].sum()) / pos
    tp_at = int(np.sum((h == 1) & (s >= t)))
    precision_at = tp_at / max(1, reached)
    return {"wss": float(saved / n - (1 - target_recall)), "target_recall": target_recall,
            "realised_recall_at_cutoff": float(realised_recall),
            "screened_to_reach_recall": reached, "records_saved": int(saved),
            "number_needed_to_read": float(1 / precision_at) if precision_at else None,
            "excluded_unscored": excluded_unscored, "n_distinct_scores": int(len(np.unique(s))),
            "_caveat": caveat}


def screening_metrics(human, ai, scores=None, recall_threshold: float | None = None,
                      beta: float = 3.0, beta_rationale: str | None = None,
                      uncertain_as_include: bool = True, min_positives: int = 30,
                      threshold_independent: bool = False) -> dict:
    """Recall-first screening metrics, AI vs BLIND human. Positive class = 'include'."""
    human_bin = np.array([to_binary(x, uncertain_as_include) for x in human])
    ai_bin = np.array([to_binary(x, uncertain_as_include) for x in ai])
    if len(human_bin) != len(ai_bin) or len(human_bin) == 0:
        raise ValueError("human and ai decision arrays must be non-empty and the same length")
    tp, fp, tn, fn = _confusion(human_bin, ai_bin)
    n = tp + fp + tn + fn; pos = tp + fn

    recall = tp / pos if pos else float("nan")
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    specificity = tn / (tn + fp) if (tn + fp) else float("nan")
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) and not math.isnan(precision) and not math.isnan(recall) else float("nan"))
    b2 = beta * beta
    fbeta = ((1 + b2) * precision * recall / (b2 * precision + recall)
             if (b2 * precision + recall) and not math.isnan(precision) and not math.isnan(recall) else float("nan"))
    ci2 = wilson_ci(tp, pos) if pos else (float("nan"), float("nan"))
    lower_1s = wilson_ci(tp, pos, one_sided=True)[0] if pos else float("nan")

    auc = avg_prec = None
    if scores is not None:
        s = np.asarray(scores, dtype=float)
        m = ~np.isnan(s)
        if m.sum() and len(set(human_bin[m])) == 2:
            from sklearn.metrics import roc_auc_score, average_precision_score
            try:
                auc = float(roc_auc_score(human_bin[m], s[m]))
                avg_prec = float(average_precision_score(human_bin[m], s[m]))
            except Exception:
                auc = None

    out = {
        "n": n, "positives_in_human": pos, "confusion": {"TP": tp, "FP": fp, "TN": tn, "FN": fn},
        "recall_HEADLINE": recall, "recall_95ci_twosided": list(ci2),
        "recall_95_onesided_lower": lower_1s,
        "fbeta": fbeta, "beta": beta,
        "beta_rationale": beta_rationale or f"beta={beta:g}: a missed relevant study judged ~{beta**2:g}x "
                          "costlier than an extra full-text screen (recall-first; RAISE 2 Appendix 1 p.34, "
                          "Wang et al.). State and pre-register the chosen beta in the methods.",
        "precision": precision, "specificity_secondary": specificity,
        "f1_secondary": f1, "auc_secondary": auc, "average_precision_secondary": avg_prec,
        "kappa_secondary": kappa_with_ci(human_bin, ai_bin),
        "wss_diagnostic": wss_at_recall(human_bin, scores, target_recall=recall_threshold or 0.95)
                          if scores is not None else {"wss": None, "note": "no AI scores supplied"},
        "missed_relevant_FN": fn,
        "_caveats": [
            "Recall (sensitivity) + its CI is the HEADLINE; F-beta weights recall ~beta^2 x precision; F1, "
            "kappa, AUC, specificity are SECONDARY (RAISE 2 p.5, p.34).",
            "AUC/AP and WSS are computed against SINGLE BLIND-HUMAN labels (not a multiply-adjudicated gold "
            "standard) and from UNCALIBRATED LLM confidence; treat as ranking-quality diagnostics.",
            "FN = relevant studies the AI would have missed - the cost recall-first minimises.",
        ],
    }
    if recall_threshold is not None:
        if pos == 0 or math.isnan(recall):
            acc = {"status": "not_estimable", "reason": "no positive (include) records in the human reference",
                   "recall_threshold": recall_threshold}
        else:
            acc = {"status": "estimable", "recall_threshold": recall_threshold,
                   "decision_bound": "one-sided 95% Wilson lower bound on recall (the headline gate)",
                   "passes_headline": lower_1s >= recall_threshold,
                   "passes_point_estimate_only": recall >= recall_threshold,
                   "sufficient_positives": pos >= min_positives,
                   "positives": pos, "min_positives_recommended": min_positives}
            if fn == 0:
                acc["rule_of_three_note"] = (
                    f"recall=1.0 observed on {pos} positives is the rule-of-three regime: the one-sided 95% "
                    f"bound on the miss rate is ~3/{pos}={3/pos:.2f}, so true recall could be as low as "
                    f"{lower_1s:.2f}. Zero observed misses on {pos} positives is weak evidence "
                    "(Hanley & Lippman-Hand 1983).")
            if pos < min_positives:
                acc["precision_warning"] = (
                    f"only {pos} validation positives; the lower-bound gate is dominated by N, not by true "
                    "performance. Pre-register the required number of positives via a precision/assurance "
                    "calculation (RAISE 2 Box 2, p.9; Cochrane RCT-classifier 99%-recall precedent set a priori "
                    "and independently of the developer).")
        acc["threshold_independent"] = bool(threshold_independent)
        if threshold_independent:
            acc["note"] = ("Threshold recorded as set a priori and independently of the developer (see provenance). "
                           "The HEADLINE pass/fail keys off the one-sided 95% lower bound, not the point estimate.")
        else:
            acc["note"] = ("This bar is the tool's DEFAULT recall target — independence is NOT established: no one is "
                           "recorded as having set it a priori, independently of the developer (RAISE Part 2 §1 "
                           "Box 2, p.9). Record who set it, and when, on the Reliability screen before treating this as an "
                           "a-priori gate. The HEADLINE pass/fail keys off the one-sided 95% lower bound, not the "
                           "point estimate.")
        out["acceptance"] = acc
    return out


def stratified_metrics(human, ai, strata, scores=None, **kw) -> dict:
    human = list(human); ai = list(ai); strata = list(strata)
    scores = list(scores) if scores is not None else None
    out = {}
    for value in sorted(set(strata), key=str):
        idx = [i for i, s in enumerate(strata) if s == value]
        sc = [scores[i] for i in idx] if scores is not None else None
        try:
            out[str(value)] = screening_metrics([human[i] for i in idx], [ai[i] for i in idx], scores=sc, **kw)
        except ValueError as e:
            out[str(value)] = {"error": str(e), "n": len(idx)}
    return out


# --------------------------------------------------------------------------------------------------
# Stability (test-retest across repeated identical AI runs)
# --------------------------------------------------------------------------------------------------
def stability(runs: list) -> dict:
    """runs = list of decision arrays for the SAME records across repeated AI runs (RAISE 2 p.11,20,39).
    Computed on the RAW categories (include/exclude/uncertain) so include<->uncertain churn is visible."""
    from sklearn.metrics import cohen_kappa_score
    raw = [[str(x).strip().lower() for x in r] for r in runs]
    if len(raw) < 2 or len({len(r) for r in raw}) != 1:
        raise ValueError("stability needs >=2 runs of equal length over the same records")
    n = len(raw[0])
    pair_agree, pair_kappa = [], []
    for i in range(len(raw)):
        for j in range(i + 1, len(raw)):
            pair_agree.append(float(np.mean([raw[i][k] == raw[j][k] for k in range(n)])))
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    pair_kappa.append(float(cohen_kappa_score(raw[i], raw[j])))
            except Exception:
                pass
    flips = sum(1 for k in range(n) if len({raw[r][k] for r in range(len(raw))}) > 1)
    lo, hi = wilson_ci(n - flips, n)
    return {"runs": len(raw), "records": n,
            "mean_pairwise_agreement": float(np.mean(pair_agree)),
            "min_pairwise_agreement": float(np.min(pair_agree)),
            "mean_pairwise_kappa": float(np.mean(pair_kappa)) if pair_kappa else None,
            "records_that_flipped": flips, "flip_rate": flips / n, "flip_rate_95ci": [1 - hi, 1 - lo],
            "note": ("Production LLMs are NON-deterministic even at temperature=0 (batching/hardware); flips "
                     "quantify run-to-run instability over identical inputs. Run on the same held-out records, "
                     "watching for the RAISE 2 caching false-negative (a cached identical record returning a "
                     "stale decision).")}


# --------------------------------------------------------------------------------------------------
# Fatigue mixed-effects model
# --------------------------------------------------------------------------------------------------
def fatigue_model(df: pd.DataFrame) -> dict:
    """Mixed-effects logistic: error ~ cumulative_time + order_index + (1|screener)[+ (1|record_id)].

    df columns: error (0/1), cumulative_time, order_index, screener (id); record_id + agent optional.
    `error` should be scored against an INDEPENDENT reference (see _fatigue_frame: a leave-one-screener-
    out human-only majority), NOT against a consensus that contains the screener or the AI.
    Reports the cumulative_time effect, the time/position collinearity (corr + VIF), the estimand, and
    the interval type. >=5 screeners are needed to estimate a screener variance component; below that
    screener is fit as a FIXED effect (the variance component is not identifiable)."""
    need = {"error", "cumulative_time", "order_index", "screener"}
    if not need.issubset(df.columns):
        raise ValueError(f"fatigue_model needs columns {sorted(need)}; got {list(df.columns)}")
    d = df.dropna(subset=list(need)).copy()
    d["error"] = d["error"].astype(int)
    n_screeners = d["screener"].nunique()
    has_record = "record_id" in d.columns and d["record_id"].nunique() > 1

    r = float(np.corrcoef(d["cumulative_time"], d["order_index"])[0, 1]) if len(d) > 2 else float("nan")
    vif = (1 / (1 - r * r)) if (not math.isnan(r) and abs(r) < 1) else float("inf")
    result = {"n_decisions": len(d), "n_screeners": n_screeners, "error_rate": float(d["error"].mean()),
              "time_position_corr": r, "time_position_vif": vif,
              "_caveats": [
                  "cumulative_time and order_index are intrinsically collinear (later position => more elapsed "
                  "time); high VIF means the two coefficients are unstable and 'fatigue vs learning' is only "
                  "weakly identified. Randomised order ACROSS screeners (different order->record maps) is what "
                  "breaks the position<->case-difficulty confound - confirm it holds.",
                  "The 'AI stays flat' benefit claim requires fitting the AI's error the same way (an "
                  "agent x time interaction); pass an `agent` column (human/ai) to test it.",
              ]}
    if abs(r) > 0.95 or vif > 10:
        result["collinearity_warning"] = (f"|corr|={abs(r):.2f}, VIF={vif:.1f}: severe collinearity; report a "
                                          "single time term or a within-position time contrast instead of both.")
    if n_screeners < 3:
        result["warning"] = ("Fewer than 3 screeners: fatigue cannot be separated from individual differences "
                             "or learning. Descriptive only.")
    if has_record:
        # randomisation sanity check: do screeners use DIFFERENT orderings of the same records?
        orders = d.groupby("screener").apply(
            lambda g: tuple(g.sort_values("order_index")["record_id"]), include_groups=False)
        result["distinct_orders_across_screeners"] = int(len(set(orders)))

    for col in ("cumulative_time", "order_index"):
        sd = d[col].std()
        d[col + "_z"] = (d[col] - d[col].mean()) / (sd if sd else 1.0)
    formula = "error ~ cumulative_time_z + order_index_z"

    # >=5 screeners: random-intercept GLMM (VB) -> GEE fallback. <5: screener as a FIXED effect.
    if n_screeners >= 5:
        try:
            from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
            vc = {"screener": "0 + C(screener)"}
            if has_record and d["record_id"].nunique() <= 400:
                vc["record"] = "0 + C(record_id)"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = BinomialBayesMixedGLM.from_formula(formula, vc, d).fit_vb()
            names = list(res.model.exog_names); i = names.index("cumulative_time_z")
            mean, sd = float(res.fe_mean[i]), float(res.fe_sd[i])
            result.update({
                "method": "BinomialBayesMixedGLM (random intercept per screener" +
                          (" + per record" if "record" in vc else "") + ")",
                "estimand": "subject_specific (conditional on the random effects)",
                "interval_type": "VB posterior credible interval (mean-field VARIATIONAL Bayes UNDER-covers; "
                                 "treat as approximate, not a calibrated frequentist 95% CI)",
                "cumulative_time_coef": mean, "cumulative_time_credible_interval": [mean - 1.96 * sd, mean + 1.96 * sd],
                "order_index_coef": float(res.fe_mean[names.index("order_index_z")]),
                "fatigue_detected": (mean - 1.96 * sd) > 0,
                "interpretation": ("positive cumulative_time coef with interval excluding 0 ⇒ odds of a human "
                                   "error rise with time-on-task (fatigue), holding position + screener fixed."),
            })
            _agent_contrast(d, formula, result)
            return result
        except Exception as e:
            result["glmm_error"] = f"{type(e).__name__}: {e}"
        try:
            import statsmodels.api as sm
            import statsmodels.formula.api as smf
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = smf.gee(formula, groups="screener", data=d, family=sm.families.Binomial(),
                              cov_struct=sm.cov_struct.Exchangeable()).fit()
            ci = res.conf_int().loc["cumulative_time_z"].tolist()
            result.update({
                "method": "GEE logit (cluster-robust on screener) - FALLBACK",
                "estimand": "population_averaged (NOT the subject-specific GLMM estimand; under a logit link "
                            "the marginal slope is attenuated toward 0 vs the conditional slope - not interchangeable)",
                "estimand_warning": "GLMM failed; this is a population-averaged GEE, a different estimand.",
                "interval_type": "frequentist cluster-robust 95% CI",
                "cumulative_time_coef": float(res.params["cumulative_time_z"]), "cumulative_time_95ci": ci,
                "order_index_coef": float(res.params["order_index_z"]), "fatigue_detected": ci[0] > 0,
            })
            _agent_contrast(d, formula, result)
            return result
        except Exception as e:
            result["gee_error"] = f"{type(e).__name__}: {e}"
            result["method"] = "FAILED"
            return result
    else:
        try:  # screener as a FIXED effect (variance component not estimable on <5 groups)
            import statsmodels.formula.api as smf
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = smf.logit(formula + " + C(screener)", data=d).fit(disp=0)
            ci = res.conf_int().loc["cumulative_time_z"].tolist()
            result.update({
                "method": f"fixed-effects logit (screener as a fixed effect; only {n_screeners} screeners, a "
                          "random intercept is not identifiable - >=5 needed)",
                "estimand": "conditional (screener fixed effects)", "interval_type": "frequentist Wald 95% CI",
                "cumulative_time_coef": float(res.params["cumulative_time_z"]), "cumulative_time_95ci": ci,
                "order_index_coef": float(res.params["order_index_z"]), "fatigue_detected": ci[0] > 0,
            })
            _agent_contrast(d, formula, result)
            return result
        except Exception as e:
            result["fit_error"] = f"{type(e).__name__}: {e}"; result["method"] = "FAILED"
            return result


def _agent_contrast(d, formula, result):
    """If an `agent` column (human/ai) is present, fit error ~ time*agent to test the 'AI stays flat' claim."""
    if "agent" not in d.columns or d["agent"].nunique() < 2:
        return
    try:
        import statsmodels.formula.api as smf
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = smf.logit("error ~ cumulative_time_z * C(agent)", data=d).fit(disp=0)
        inter = [p for p in res.params.index if "cumulative_time_z:" in p]
        result["agent_x_time_interaction"] = {p: float(res.params[p]) for p in inter}
        result["agent_contrast_note"] = ("a near-zero AI time-slope vs a positive human time-slope supports "
                                          "'humans tire, the AI stays flat'.")
    except Exception as e:
        result["agent_contrast_error"] = f"{type(e).__name__}: {e}"


# --------------------------------------------------------------------------------------------------
# Extraction agreement + hallucination rate
# --------------------------------------------------------------------------------------------------
def _norm_val(v) -> str:
    return "".join(ch for ch in str(v).strip().lower() if ch.isalnum())


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


_CONT_TOKENS = {"mean", "median", "sd", "se", "ci", "effect", "score", "value", "rate", "ratio",
                "percent", "pct", "age", "duration", "dose", "weight", "bmi", "change", "difference",
                "md", "smd", "or", "rr", "hr", "auc", "r2"}
_EXACT_TOKENS = {"id", "doi", "pmid", "year", "n", "count", "size", "design", "country", "type",
                 "setting", "tool", "category", "group", "sex", "gender", "arm", "yes", "no", "status"}


def _is_continuous(var_name: str) -> bool:
    """TOKEN-based (not substring) heuristic so 'mean_age' is not mis-flagged by a substring like 'n_':
    a continuous token (mean/sd/age/rate/effect…) ⇒ tolerance match; otherwise EXACT (counts/IDs/
    categoricals). Field-role matching should be PRE-REGISTERED per field in the methods, not inferred."""
    tokens = {t for t in re.split(r"[^a-z0-9]+", str(var_name).lower()) if t}
    if tokens & _CONT_TOKENS:
        return True
    return False   # default to exact match


def extraction_agreement(audit_df: pd.DataFrame, rel_tol: float = 0.05, abs_tol: float = 0.0,
                         hallucination_labels: set | None = None) -> dict:
    """Field-by-field AI-vs-BLIND-human agreement + hallucination rate from the extraction audit CSV
    (FileName | Variable_Name | AI_Extracted_Value | Manual_Value/Consensus_Value | Error_Category).

    BLIND-FIRST: the reference is the BLIND Manual_Value where available; Consensus_Value is used only
    as a fallback (with a warning, since an AI-influenced consensus inflates agreement). Match rule:
    EXACT (normalised) for counts/IDs/categoricals; max(abs_tol, rel_tol*|truth|) for continuous fields.
    Hallucination = a non-empty AI value whose reference is blank/'not reported' OR an Error_Category in
    `hallucination_labels` - computed over the FULL audit, not only reconciled rows."""
    labels = hallucination_labels or HALLUCINATION_LABELS
    cols = {c.lower().strip(): c for c in audit_df.columns}
    ai_c = cols.get("ai_extracted_value") or cols.get("ai_value")
    manual_c = cols.get("manual_value"); consensus_c = cols.get("consensus_value")
    truth_c = manual_c or consensus_c
    var_c = cols.get("variable_name") or cols.get("variable")
    err_c = cols.get("error_category")
    if not (ai_c and truth_c and var_c):
        raise ValueError("extraction audit needs Variable_Name, AI_Extracted_Value and "
                         "Manual_Value/Consensus_Value columns")
    warn = None
    if not manual_c and consensus_c:
        warn = ("reference is Consensus_Value (no blind Manual_Value column): if the AI contributed to that "
                "consensus, agreement is inflated and hallucination deflated. Prefer the blind Manual_Value.")

    full = audit_df.copy()
    full["_truth_blank"] = full[truth_c].astype(str).str.strip().isin(["", "not reported", "nr", "na", "n/a"])
    full["_ai_present"] = full[ai_c].astype(str).str.strip() != ""

    # --- hallucination over the FULL audit ---
    label_hit = (full[err_c].astype(str).str.strip().str.lower().isin(labels)) if err_c else False
    fabricated = full["_ai_present"] & full["_truth_blank"]      # AI invented a value with no support
    hall_mask = fabricated | label_hit
    h_n = int(hall_mask.sum()); h_lo, h_hi = wilson_ci(h_n, len(full))

    # --- agreement over RECONCILED rows only ---
    rows = full[~full["_truth_blank"]].copy()
    if rows.empty:
        return {"note": "no reference values to compare", "hallucination_count": h_n,
                "hallucination_rate": h_n / max(1, len(full)), "hallucination_95ci": [h_lo, h_hi],
                "reference_warning": warn}

    def matched(r):
        ai, tr, var = r[ai_c], r[truth_c], r[var_c]
        an, tn = _num(ai), _num(tr)
        if an is not None and tn is not None and _is_continuous(var):
            return abs(an - tn) <= max(abs_tol, rel_tol * abs(tn))
        if an is not None and tn is not None:                  # numeric but exact-match field (counts/IDs)
            return an == tn
        return _norm_val(ai) == _norm_val(tr)

    rows["_match"] = rows.apply(matched, axis=1)
    per_field = {}
    for var, g in rows.groupby(var_c):
        mn = int(g["_match"].sum()); lo, hi = wilson_ci(mn, len(g))
        per_field[str(var)] = {"n": int(len(g)), "agreement": float(g["_match"].mean()),
                               "agreement_95ci": [lo, hi]}
    worst = min(per_field.items(), key=lambda kv: kv[1]["agreement"]) if per_field else None
    o_n = int(rows["_match"].sum()); o_lo, o_hi = wilson_ci(o_n, len(rows))
    return {"fields_compared": int(len(rows)),
            "overall_agreement": float(rows["_match"].mean()), "overall_agreement_95ci": [o_lo, o_hi],
            "worst_field": {"variable": worst[0], **worst[1]} if worst else None,
            "hallucination_count": h_n, "hallucination_rate": h_n / len(full),
            "hallucination_95ci": [h_lo, h_hi], "hallucination_over_n": int(len(full)),
            "per_field": per_field, "reference_used": "Manual_Value (blind)" if manual_c else "Consensus_Value",
            "reference_warning": warn,
            "_caveats": ["Overall agreement is row-pooled - read the per-field table and worst_field, not just "
                         "the single number (a critical low-frequency field can be masked).",
                         "Hallucination here is a passive audit tally; for the paper add an active faithfulness "
                         "probe (inject fields known absent; measure invention vs abstention) - RAISE 2 p.20.",
                         "Extraction is accuracy-first, NOT recall-first."]}


# --------------------------------------------------------------------------------------------------
# Loaders + orchestration
# --------------------------------------------------------------------------------------------------
def _col(df, *names):
    low = {c.lower().strip(): c for c in df.columns}
    for n in names:
        if n in low:
            return low[n]
    return None


def abstract_length_bucket(text) -> str:
    """Bin an abstract's word count into the third stratification dimension playbook-reliability.md and
    PLAN.md both call for (alongside study design and source database) — a strong AVERAGE recall can hide
    the AI doing worse on short/terse abstracts specifically. '' (not '(not recorded)') for missing text, so
    the caller can render it as its own visible '(not recorded)' stratum, same as the other two dimensions."""
    n = len(str(text or "").split())
    if n == 0:
        return ""
    if n < 100:
        return "short (<100 words)"
    if n <= 250:
        return "medium (100-250 words)"
    return "long (>250 words)"


def load_screening_join(human_csv, ai_csv, stage=None, master_csv=None):
    """Join BLIND human decisions to AI decisions on record_id. Returns (human, ai, scores, merged).
    Missing AI confidence is kept as NaN (NOT imputed) so AUC/WSS drop it rather than rank on a constant.
    `master_csv` (optional) is master_records.csv — when given, an 'abstract_length' column is added to
    `merged` (bucketed via abstract_length_bucket) even if it isn't already a column on the human file."""
    H = pd.read_csv(human_csv).fillna("")
    A = pd.read_csv(ai_csv).fillna("")
    h_id, a_id = _col(H, "record_id"), _col(A, "record_id")
    h_dec = _col(H, "human_decision", "consensus_decision")
    a_dec = _col(A, "ai_decision", "decision")
    if not (h_id and a_id and h_dec and a_dec):
        raise ValueError("need record_id + a human decision column + an AI decision column")
    a_score = _col(A, "ai_confidence", "confidence")
    extra = [c for c in (_col(H, "study_design"), _col(H, "source_db"), _col(H, "abstract_length")) if c]
    if master_csv is not None and not _col(H, "abstract_length"):
        try:
            M = pd.read_csv(master_csv).fillna("")
            m_id, m_ab = _col(M, "record_id"), _col(M, "abstract")
            if m_id and m_ab:
                lengths = M[[m_id, m_ab]].copy()
                lengths["abstract_length"] = lengths[m_ab].map(abstract_length_bucket)
                H = H.merge(lengths[[m_id, "abstract_length"]], left_on=h_id, right_on=m_id, how="left")
                if "abstract_length" not in extra:
                    extra.append("abstract_length")
        except Exception:
            pass   # stratification is a diagnostic extra — never let it block the headline metrics
    merged = H[[h_id, h_dec] + extra].merge(
        A[[a_id, a_dec] + ([a_score] if a_score else [])], left_on=h_id, right_on=a_id, how="inner")
    if merged.empty:
        raise ValueError("no records joined on record_id between the human and AI files")
    scores = pd.to_numeric(merged[a_score], errors="coerce").tolist() if a_score else None
    return (merged[h_dec].tolist(), merged[a_dec].tolist(), scores, merged)


def format_report(title: str, payload: dict) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, indent=2, default=str)}\n```\n"


def _write_reliability_okf_node(ai_csv, stage, metrics, metrics_path) -> None:
    """Write the reliability report into the OKF bundle (RAISE 1.8/1.9a provenance) - non-fatal, mirroring
    every other stage's producer: a bundle-writing problem must never break a reliability run. Provenance
    names the AI screener BEING MEASURED (read from the audit CSV's own model/prompt_file/prompt_version
    columns, already written there by screener_abstract.py/screener_fulltext.py), not the reliability
    computation itself (which is deterministic maths, not an AI judgement)."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        import okf_writer

        model_val = prompt_file_val = prompt_version_val = ""
        try:
            ai_df = pd.read_csv(ai_csv, nrows=1).fillna("")
            mc, pfc, pvc = _col(ai_df, "model"), _col(ai_df, "prompt_file"), _col(ai_df, "prompt_version")
            if mc:
                model_val = str(ai_df[mc].iloc[0]).strip()
            if pfc:
                prompt_file_val = str(ai_df[pfc].iloc[0]).strip()
            if pvc:
                prompt_version_val = str(ai_df[pvc].iloc[0]).strip()
        except Exception:
            pass
        if not model_val:
            print("OKF: skipped reliability node (AI audit file carries no 'model' column to attribute it to)")
            return

        prov = okf_writer.build_provenance(
            model_val, prompt_file_val or "reliability.py",
            prompt_version=prompt_version_val or None)
        bundle = okf_writer.okf_tools.find_bundle(None)
        okf_writer.write_reliability_node(bundle, stage=stage or "screening", metrics=metrics,
                                          provenance=prov, metrics_path=str(metrics_path))
        okf_writer.write_index(bundle)
        r = metrics.get("recall_HEADLINE")
        acc = metrics.get("acceptance") or {}
        verdict = ("pass" if acc.get("passes_headline") else "not met") if "passes_headline" in acc else ""
        recall_part = f"recall={r:.3f}" if isinstance(r, (int, float)) else "recall not estimable"
        verdict_part = f", verdict={verdict}" if verdict else ""
        okf_writer.append_log(bundle,
            f"**Reliability run ({stage or 'screening'})**: AI (`{model_val}`) vs. blind human — "
            f"{recall_part}{verdict_part}.")
        print(f"OKF: wrote reliability report node (stage={stage or 'screening'}, human_verified:false) in {bundle}")
    except Exception as e:  # noqa: BLE001 - OKF writing is best-effort, never fatal
        print(f"OKF: skipped reliability node writing ({e})")


def run_screening(human_csv, ai_csv, outdir="Outputs/reliability", stage=None,
                  recall_threshold=None, stratify=None, beta=3.0, beta_rationale=None,
                  threshold_independent=False, master_csv=None) -> dict:
    human, ai, scores, merged = load_screening_join(human_csv, ai_csv, stage, master_csv=master_csv)
    metrics = screening_metrics(human, ai, scores=scores, recall_threshold=recall_threshold,
                                beta=beta, beta_rationale=beta_rationale,
                                threshold_independent=threshold_independent)
    if stratify:
        col = _col(merged, stratify)
        # Same beta/threshold_independent as the headline, or a per-stratum table can silently DISAGREE with
        # it (e.g. report F-beta(2) overall but F-beta(3) in every subgroup) purely because these overrides
        # weren't threaded through — not because the subgroups actually differ.
        metrics["stratified_by_" + stratify] = (
            stratified_metrics(human, ai, merged[col].tolist(), scores=scores, recall_threshold=recall_threshold,
                               beta=beta, beta_rationale=beta_rationale, threshold_independent=threshold_independent)
            if col else f"column '{stratify}' not found")
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    (out / f"screening-metrics{('-' + stage) if stage else ''}.md").write_text(
        format_report(f"AI screening reliability{(' - ' + stage) if stage else ''}", metrics), encoding="utf-8")
    metrics_path = out / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    _write_reliability_okf_node(ai_csv, stage, metrics, metrics_path)
    r, ci = metrics["recall_HEADLINE"], metrics["recall_95ci_twosided"]
    print(f"Recall (headline): {r:.3f}  95% CI [{ci[0]:.3f}, {ci[1]:.3f}]  on {metrics['positives_in_human']} "
          f"positives | F-beta({beta:g})={metrics['fbeta']:.3f} | missed (FN)={metrics['missed_relevant_FN']}")
    print(f"Reports written to {out}/")
    return metrics


def _fatigue_frame(human_csv) -> pd.DataFrame:
    """Build the fatigue frame from the instrumented human file (record_id, human_decision, screener,
    order_index[, decided_at]). `error` is scored LEAVE-ONE-SCREENER-OUT: each decision is compared to
    the MAJORITY decision of the OTHER human screeners on that record (independent + AI-free, satisfying
    blind-first). Needs >=2 humans per record for the reference to exist."""
    H = pd.read_csv(human_csv).fillna("")
    rid, dec = _col(H, "record_id"), _col(H, "human_decision", "decision")
    scr, oi = _col(H, "screener"), _col(H, "order_index")
    ts = _col(H, "decided_at", "timestamp")
    if not (rid and dec and scr and oi):
        raise ValueError("fatigue needs record_id, human_decision, screener, order_index (+ decided_at)")
    H = H.rename(columns={scr: "screener", oi: "order_index", rid: "record_id"})
    H["order_index"] = pd.to_numeric(H["order_index"], errors="coerce")
    H["_bin"] = H[dec].map(lambda x: to_binary(x))
    if ts:
        H["cumulative_time"] = H.groupby("screener")[ts].transform(
            lambda s: (pd.to_datetime(s, errors="coerce") - pd.to_datetime(s, errors="coerce").min()).dt.total_seconds())
        H["cumulative_time"] = H["cumulative_time"].fillna(H["order_index"])
    else:
        H["cumulative_time"] = H["order_index"]
    # leave-one-screener-out human-only reference (majority of OTHER screeners on the same record)
    by_rec = H.groupby("record_id")["_bin"].agg(["sum", "count"])
    errs = []
    for _, row in H.iterrows():
        s, c = by_rec.loc[row["record_id"], "sum"], by_rec.loc[row["record_id"], "count"]
        if c < 2:
            errs.append(np.nan); continue                      # no independent reference for this record
        others_mean = (s - row["_bin"]) / (c - 1)              # leave-one-out
        ref = 1 if others_mean >= 0.5 else 0
        errs.append(int(row["_bin"] != ref))
    H["error"] = errs
    keep = ["screener", "order_index", "cumulative_time", "error", "record_id"]
    return H[keep].dropna(subset=["error", "cumulative_time", "order_index"])


# --------------------------------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------------------------------
def _selftest() -> int:
    fails = []

    # 1) confusion + recall-first metrics (19 caught / 1 missed of 20; 10 FP of 80)
    human = [1] * 20 + [0] * 80
    ai = ([1] * 19 + [0]) + ([1] * 10 + [0] * 70)
    m = screening_metrics(human, ai, recall_threshold=0.95, min_positives=30)
    c = m["confusion"]
    if (c["TP"], c["FP"], c["TN"], c["FN"]) != (19, 10, 70, 1):
        fails.append(f"confusion: {c}")
    if abs(m["recall_HEADLINE"] - 0.95) > 1e-9 or abs(m["specificity_secondary"] - 0.875) > 1e-9:
        fails.append("recall/specificity wrong")
    if not (m["fbeta"] > m["f1_secondary"]):
        fails.append("F-beta(3) should exceed F1 when recall>precision")
    if not (m["recall_95_onesided_lower"] > m["recall_95ci_twosided"][0]):
        fails.append("one-sided lower bound should exceed the two-sided lower bound")
    a = m["acceptance"]
    if a["status"] != "estimable" or a["passes_headline"] or not a["passes_point_estimate_only"]:
        fails.append(f"acceptance gate logic: {a}")
    if a["sufficient_positives"]:
        fails.append("20 positives should be flagged insufficient vs min_positives=30")

    # 2) recall=1.0 -> rule_of_three note; pos=0 stratum -> not_estimable
    m1 = screening_metrics([1] * 12, [1] * 12, recall_threshold=0.95)
    if "rule_of_three_note" not in m1["acceptance"]:
        fails.append("recall=1.0 should attach a rule_of_three_note")
    m0 = screening_metrics([0] * 10, [0] * 10, recall_threshold=0.95)
    if m0["acceptance"]["status"] != "not_estimable":
        fails.append("pos=0 should be not_estimable, not a failure")

    # 3) WSS tie-safe + AUC drops missing scores (no constant imputation)
    scores = ([0.9] * 19 + [0.1]) + ([0.2] * 10 + [0.05] * 70)
    w = wss_at_recall(np.array(human), np.array(scores), 0.95)
    if w["wss"] is None or not (-0.05 <= w["wss"] <= 0.95) or "realised_recall_at_cutoff" not in w:
        fails.append(f"WSS implausible: {w}")
    tied = wss_at_recall(np.array([1, 1, 0, 0]), np.array([0.5, 0.5, 0.5, 0.5]), 0.95)  # all tied
    if tied["wss"] is not None:
        fails.append("all-tied scores should not yield a WSS (no score variation)")
    m2 = screening_metrics(human, ai, scores=scores)
    if m2["auc_secondary"] is None or m2["auc_secondary"] < 0.8:
        fails.append(f"AUC should be high: {m2['auc_secondary']}")
    mNaN = screening_metrics(human, ai, scores=[float("nan")] * 100)  # all-missing -> AUC None, no crash
    if mNaN["auc_secondary"] is not None:
        fails.append("all-missing scores should give AUC None, not a constant-imputed value")

    # 4) kappa OR-guard: single-class-in-one-rater resample -> NaN (not 0)
    kp = kappa_with_ci([1, 1, 0, 0, 1, 0], [1, 1, 0, 0, 1, 0])
    if abs(kp["kappa"] - 1.0) > 1e-9 or "pabak_caveat" not in kp:
        fails.append(f"kappa(perfect)/caveat: {kp}")

    # 5) stability on RAW categories (uncertain flip visible)
    runs = [["include", "uncertain", "exclude"], ["include", "include", "exclude"], ["include", "exclude", "exclude"]]
    st = stability(runs)
    if st["records_that_flipped"] != 1 or "flip_rate_95ci" not in st:
        fails.append(f"stability raw-category flip: {st}")

    # 6) fatigue: 6 screeners share records, error vs leave-one-out rises with time -> positive coef
    import csv, tempfile, os
    rng = np.random.default_rng(11)
    rows = [("record_id", "human_decision", "screener", "order_index", "decided_at")]
    recids = [f"R{i:03d}" for i in range(60)]
    for s in range(6):
        order = list(rng.permutation(recids))               # DIFFERENT random order per screener
        for pos, rec in enumerate(order):
            truth = "include" if (int(rec[1:]) % 4 == 0) else "exclude"
            p = 1 / (1 + math.exp(-(-2.6 + 1.0 * (pos - 30) / 15)))   # error prob rises with position/time
            dec = ("exclude" if truth == "include" else "include") if rng.random() < p else truth
            rows.append((rec, dec, f"S{s}", pos, f"2026-06-29T09:{pos:02d}:00"))
    with tempfile.TemporaryDirectory() as t:
        fp = os.path.join(t, "h.csv")
        with open(fp, "w", newline="") as f:
            csv.writer(f).writerows(rows)
        fm = fatigue_model(_fatigue_frame(fp))
    if "cumulative_time_coef" not in fm:
        fails.append(f"fatigue did not fit: {fm.get('glmm_error') or fm.get('gee_error') or fm.get('fit_error')}")
    elif fm["cumulative_time_coef"] <= 0:
        fails.append(f"fatigue: expected positive time coef; got {fm.get('cumulative_time_coef')}")
    if "estimand" not in fm or "time_position_vif" not in fm:
        fails.append("fatigue must report estimand + collinearity (VIF)")

    # 7) extraction: blind-first ref, field-role tolerance, fabrication-on-blank, CIs
    audit = pd.DataFrame({
        "FileName": ["a.pdf"] * 5,
        "Variable_Name": ["Sample_Size", "Design", "Mean_age", "Country", "Outcome"],
        "AI_Extracted_Value": ["204", "RCT", "10.4", "Spain", "invented"],
        "Manual_Value": ["204", "RCT", "10.0", "Germany", ""],          # Mean within tol; Country wrong; Outcome blank->fabrication
        "Error_Category": ["", "", "", "", ""],
    })
    ex = extraction_agreement(audit, rel_tol=0.05)
    if ex["fields_compared"] != 4:                              # 4 reconciled (Outcome blank excluded from agreement)
        fails.append(f"extraction reconciled count: {ex['fields_compared']}")
    if ex["hallucination_count"] != 1 or "hallucination_95ci" not in ex:
        fails.append(f"extraction hallucination (blank-truth fabrication): {ex.get('hallucination_count')}")
    if abs(ex["overall_agreement"] - 0.75) > 1e-9:             # N, Design, Mean match; Country differs
        fails.append(f"extraction agreement should be 0.75: {ex['overall_agreement']}")
    if ex["reference_used"] != "Manual_Value (blind)":
        fails.append("extraction should prefer the blind Manual_Value reference")

    if fails:
        print("SELFTEST FAILED:")
        for f in fails:
            print("  - " + f)
        return 1
    print("SELFTEST PASSED: recall+CI(one-sided gate), tie-safe WSS, AUC(no-impute), kappa, stability(raw), "
          "fatigue(LOO ref + estimand + VIF), extraction(blind-first + fabrication + CIs) all OK.")
    print(f"  (fatigue method: {fm.get('method')})")
    return 0


# --------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="EvidenceEngine reliability metrics (recall-first)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("screening"); s.add_argument("--human", required=True); s.add_argument("--ai", required=True)
    s.add_argument("--stage", default=None); s.add_argument("--outdir", default="Outputs/reliability")
    s.add_argument("--recall", type=float, default=None); s.add_argument("--stratify", default=None)
    s.add_argument("--beta", type=float, default=3.0); s.add_argument("--beta-rationale", dest="beta_rationale", default=None)
    s.add_argument("--master", default=None,
                    help="master_records.csv — pass this to make 'abstract_length' available as a --stratify value")
    f = sub.add_parser("fatigue"); f.add_argument("--human", required=True); f.add_argument("--outdir", default="Outputs/reliability")
    e = sub.add_parser("extraction"); e.add_argument("--audit", required=True); e.add_argument("--outdir", default="Outputs/reliability")
    sub.add_parser("selftest")
    args = ap.parse_args()

    if args.cmd == "selftest":
        return _selftest()
    if args.cmd == "screening":
        run_screening(args.human, args.ai, outdir=args.outdir, stage=args.stage, recall_threshold=args.recall,
                      stratify=args.stratify, beta=args.beta, beta_rationale=args.beta_rationale,
                      master_csv=args.master); return 0
    if args.cmd == "fatigue":
        res = fatigue_model(_fatigue_frame(args.human))
        out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
        (out / "fatigue-analysis.md").write_text(format_report("Fatigue model", res), encoding="utf-8")
        print(json.dumps(res, indent=2, default=str)[:1400]); print(f"\nWritten to {out}/fatigue-analysis.md"); return 0
    if args.cmd == "extraction":
        res = extraction_agreement(pd.read_csv(args.audit).fillna(""))
        out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
        (out / "extraction-agreement.md").write_text(format_report("Extraction agreement", res), encoding="utf-8")
        print(json.dumps(res, indent=2, default=str)); print(f"\nWritten to {out}/extraction-agreement.md"); return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
