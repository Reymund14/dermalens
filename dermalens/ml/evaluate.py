"""Level 2 evaluation: classification metrics for the DermaLens model.

Input: a CSV with one row per test session and columns
    person_id, fitzpatrick (1-6),
    y_<label>, p_<label>, g_<label>, gpred_<label>   for label in LABELS
    y_refer_out, p_refer_out
where y_* are adjudicated 0/1 labels, p_* calibrated probabilities, g_* the
adjudicated grade (0 none .. 3 marked) and gpred_* the predicted grade.

    python ml/evaluate.py predictions.csv --thresholds thresholds.json --out report.json

Reports per-label precision / recall / F1 / AUROC / AUPRC / ECE, macro- and
micro-F1, Hamming loss, exact-match accuracy, quadratic-weighted kappa for
grades, refer-out recall, the Fitzpatrick fairness gap, and 95% bootstrap CIs
(resampled by person) for macro-F1 and refer-out recall. Targets come from the
roadmap's evaluation section.
"""
from __future__ import annotations

import argparse
import csv
import json

import numpy as np

LABELS = ("acne", "hyperpigmentation", "erythema", "texture")
TARGETS = {"label_f1": 0.75, "macro_f1": 0.75, "auroc": 0.85, "hamming_loss": 0.12, "qwk": 0.60, "ece": 0.05,
           "refer_out_recall": 0.95, "fairness_gap": 0.10}
GROUPS = {"I-II": (1, 2), "III-IV": (3, 4), "V-VI": (5, 6)}


def prf(y, yhat):
    tp = int(((y == 1) & (yhat == 1)).sum())
    fp = int(((y == 0) & (yhat == 1)).sum())
    fn = int(((y == 1) & (yhat == 0)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f, tp, fp, fn


def auroc(y, s):
    pos, neg = s[y == 1], s[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    # Mann-Whitney U with ties counted half.
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def auprc(y, s):
    order = np.argsort(-s, kind="mergesort")
    y = y[order]
    tp = np.cumsum(y)
    precision = tp / np.arange(1, len(y) + 1)
    return float((precision * y).sum() / max(1, y.sum()))


def ece(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi) if hi < 1 else (p >= lo) & (p <= hi)
        if m.any():
            total += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(total)


def qwk(a, b, k=4):
    a, b = a.astype(int), b.astype(int)
    o = np.zeros((k, k))
    for i, j in zip(a, b):
        o[i, j] += 1
    w = np.array([[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)])
    e = np.outer(o.sum(1), o.sum(0)) / max(1, o.sum())
    den = (w * e).sum()
    return float(1 - (w * o).sum() / den) if den else float("nan")


def load(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    cols = {k: np.array([float(r[k]) for r in rows]) for k in rows[0] if k != "person_id"}
    cols["person_id"] = np.array([r["person_id"] for r in rows])
    return cols


def evaluate(d, thr):
    out = {"n": int(len(d["person_id"])), "labels": {}}
    Y = np.stack([d[f"y_{c}"] for c in LABELS], 1)
    Yhat = np.stack([(d[f"p_{c}"] >= thr[c]).astype(int) for c in LABELS], 1)
    tps = fps = fns = 0
    for i, c in enumerate(LABELS):
        p, r, f, tp, fp, fn = prf(Y[:, i], Yhat[:, i])
        tps, fps, fns = tps + tp, fps + fp, fns + fn
        out["labels"][c] = {
            "precision": p, "recall": r, "f1": f, "auroc": auroc(Y[:, i], d[f"p_{c}"]),
            "auprc": auprc(Y[:, i], d[f"p_{c}"]), "ece": ece(Y[:, i], d[f"p_{c}"]),
            "qwk": qwk(d[f"g_{c}"], d[f"gpred_{c}"]),
            "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": int(len(Y) - tp - fp - fn)},
        }
    out["macro_f1"] = float(np.mean([v["f1"] for v in out["labels"].values()]))
    mp = tps / (tps + fps) if tps + fps else 0.0
    mr = tps / (tps + fns) if tps + fns else 0.0
    out["micro_f1"] = 2 * mp * mr / (mp + mr) if mp + mr else 0.0
    out["hamming_loss"] = float((Y != Yhat).mean())
    out["exact_match"] = float((Y == Yhat).all(1).mean())
    ro = (d["p_refer_out"] >= thr["refer_out"]).astype(int)
    out["refer_out_recall"] = prf(d["y_refer_out"], ro)[1]

    groups = {}
    for name, (lo, hi) in GROUPS.items():
        m = (d["fitzpatrick"] >= lo) & (d["fitzpatrick"] <= hi)
        if m.sum():
            groups[name] = {"n": int(m.sum()), "macro_f1": float(np.mean(
                [prf(Y[m, i], Yhat[m, i])[2] for i in range(len(LABELS))]))}
    out["by_fitzpatrick"] = groups
    vals = [g["macro_f1"] for g in groups.values()]
    out["fairness_gap"] = float(max(vals) - min(vals)) if len(vals) > 1 else 0.0
    return out


def bootstrap(d, thr, n=1000, seed=0):
    rng = np.random.default_rng(seed)
    people = np.unique(d["person_id"])
    idx_by = {p: np.where(d["person_id"] == p)[0] for p in people}
    mf, rr = [], []
    for _ in range(n):
        pick = rng.choice(people, size=len(people), replace=True)
        idx = np.concatenate([idx_by[p] for p in pick])
        sub = {k: v[idx] for k, v in d.items()}
        r = evaluate(sub, thr)
        mf.append(r["macro_f1"])
        rr.append(r["refer_out_recall"])
    ci = lambda a: [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]  # noqa: E731
    return {"macro_f1_ci95": ci(mf), "refer_out_recall_ci95": ci(rr)}


def check_targets(r):
    t = TARGETS
    return {
        "each_label_f1>=0.75": all(v["f1"] >= t["label_f1"] for v in r["labels"].values()),
        "macro_f1>=0.75": r["macro_f1"] >= t["macro_f1"],
        "each_label_auroc>=0.85": all(v["auroc"] >= t["auroc"] for v in r["labels"].values()),
        "hamming_loss<=0.12": r["hamming_loss"] <= t["hamming_loss"],
        "each_label_qwk>=0.60": all(v["qwk"] >= t["qwk"] for v in r["labels"].values()),
        "each_label_ece<=0.05": all(v["ece"] <= t["ece"] for v in r["labels"].values()),
        "refer_out_recall>=0.95": r["refer_out_recall"] >= t["refer_out_recall"],
        "fairness_gap<=0.10": r["fairness_gap"] <= t["fairness_gap"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--thresholds", help="JSON with per-label and refer_out thresholds (default 0.5 / 0.3)")
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--out")
    a = ap.parse_args()
    thr = {c: 0.5 for c in LABELS} | {"refer_out": 0.3}
    if a.thresholds:
        thr.update(json.load(open(a.thresholds)))
    d = load(a.csv)
    r = evaluate(d, thr)
    if a.bootstrap:
        r.update(bootstrap(d, thr, a.bootstrap))
    r["targets_met"] = check_targets(r)
    text = json.dumps(r, indent=2)
    if a.out:
        open(a.out, "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
