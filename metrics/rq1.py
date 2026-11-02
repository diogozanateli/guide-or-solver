"""RQ1: taxa de resolução, ações e tokens por condição."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.utils import RESULTS, read_jsonl  # noqa: E402


def main() -> None:
    rows = []
    for ev in read_jsonl(RESULTS / "evaluation.jsonl"):
        res = json.loads((RESULTS / ev["instance_id"] / f"{ev['run']}.json").read_text())
        ctx = res.get("contextualizer") or {}
        rows.append({
            **{k: ev[k] for k in ("instance_id", "condition", "run", "resolved")},
            "solver_actions": res["actions"],
            "solver_tokens": res["input_tokens"] + res["output_tokens"],
            "ctx_actions": ctx.get("actions", 0),
            "ctx_tokens": ctx.get("input_tokens", 0) + ctx.get("output_tokens", 0),
            "duration_s": res["duration_s"] + ctx.get("duration_s", 0),
        })
    df = pd.DataFrame(rows)
    df["total_actions"] = df.solver_actions + df.ctx_actions
    df["total_tokens"] = df.solver_tokens + df.ctx_tokens
    df.to_csv(RESULTS / "rq1_per_instance.csv", index=False)
    summary = df.groupby("condition").agg(
        resolution_rate=("resolved", "mean"), n=("resolved", "size"),
        solver_tokens=("solver_tokens", "mean"), ctx_tokens=("ctx_tokens", "mean"),
        total_tokens=("total_tokens", "mean"), total_actions=("total_actions", "mean"),
        duration_s=("duration_s", "mean"))
    summary.to_csv(RESULTS / "rq1_summary.csv")
    print(summary)


if __name__ == "__main__":
    main()
