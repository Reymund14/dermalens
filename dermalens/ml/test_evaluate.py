import numpy as np

from evaluate import LABELS, auroc, ece, evaluate, prf, qwk


def test_prf_and_auroc():
    y = np.array([1, 1, 0, 0])
    assert prf(y, np.array([1, 0, 1, 0]))[:3] == (0.5, 0.5, 0.5)
    assert auroc(y, np.array([0.9, 0.8, 0.2, 0.1])) == 1.0
    assert auroc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 0.0


def test_qwk_perfect_and_ece_calibrated():
    g = np.array([0, 1, 2, 3, 2, 1])
    assert qwk(g, g) == 1.0
    p = np.full(1000, 0.3)
    y = (np.arange(1000) < 300).astype(float)
    assert ece(y, p) < 1e-9


def test_perfect_predictions_meet_everything():
    rng = np.random.default_rng(0)
    n = 120
    d = {"person_id": np.array([f"p{i // 2}" for i in range(n)]), "fitzpatrick": rng.integers(1, 7, n).astype(float)}
    for c in LABELS:
        y = rng.integers(0, 2, n).astype(float)
        d[f"y_{c}"], d[f"p_{c}"] = y, np.where(y == 1, 0.9, 0.1)
        d[f"g_{c}"] = d[f"gpred_{c}"] = y * rng.integers(1, 4, n)
    d["y_refer_out"] = rng.integers(0, 2, n).astype(float)
    d["p_refer_out"] = d["y_refer_out"] * 0.8
    r = evaluate(d, {c: 0.5 for c in LABELS} | {"refer_out": 0.3})
    assert r["macro_f1"] == 1.0 and r["hamming_loss"] == 0.0 and r["refer_out_recall"] == 1.0
    assert r["fairness_gap"] == 0.0
