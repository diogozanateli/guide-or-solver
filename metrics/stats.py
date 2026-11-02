"""Comparações pareadas entre condições: McNemar (resolução) com correção de Holm
e IC 95% por bootstrap das instâncias para as diferenças das demais métricas.
Uso: python metrics/stats.py --model <modelo>"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.multitest import multipletests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.utils import model_results_dir  # noqa: E402

RESULTS = model_results_dir()

PAIRS = list(itertools.combinations(["C1", "C2", "C3"], 2))


def bootstrap_ci(diff: np.ndarray, n: int = 10000, seed: int = 42) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    means = rng.choice(diff, (n, len(diff)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    rq1 = pd.read_csv(RESULTS / "rq1_per_instance.csv")
    rq1 = rq1[rq1.run.str.endswith("run0")]  # uma execução por condição
    wide = rq1.pivot(index="instance_id", columns="condition")

    rows = []
    for a, b in PAIRS:
        ra, rb = wide["resolved"][a].astype(bool), wide["resolved"][b].astype(bool)
        table = [[(ra & rb).sum(), (ra & ~rb).sum()], [(~ra & rb).sum(), (~ra & ~rb).sum()]]
        p = mcnemar(table, exact=True).pvalue
        row = {"pair": f"{a} vs {b}", "metric": "resolved", "p": p,
               "diff": float(rb.mean() - ra.mean())}
        rows.append(row)
        for metric in ("total_tokens", "total_actions"):
            d = (wide[metric][b] - wide[metric][a]).dropna().to_numpy()
            lo, hi = bootstrap_ci(d)
            rows.append({"pair": f"{a} vs {b}", "metric": metric,
                         "diff": float(d.mean()), "ci_low": lo, "ci_high": hi})
    df = pd.DataFrame(rows)
    mask = df.metric == "resolved"
    df.loc[mask, "p_holm"] = multipletests(df.loc[mask, "p"], method="holm")[1]
    df.to_csv(RESULTS / "stats.csv", index=False)
    print(df)


if __name__ == "__main__":
    main()
