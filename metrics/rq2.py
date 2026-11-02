"""RQ2: precisão, revocação, F1 e acerto exato da localização (arquivo e função)
indicada nas orientações (C2 e C3) em relação ao patch humano. Média macro.
Uso: python metrics/rq2.py --model <modelo>"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.utils import DATA, WORK, fresh_checkout, model_results_dir, patch_files, read_jsonl  # noqa: E402
from metrics.functions import changed_functions  # noqa: E402

RESULTS = model_results_dir()


def prf(pred: set, ref: set) -> dict:
    tp = len(pred & ref)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(ref) if ref else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f, "exact": pred == ref}


def norm_func(name: str) -> str:
    return name.strip().replace("::", ".").replace("/", ".").removesuffix("()")


def main() -> None:
    rows = []
    for inst in read_jsonl(DATA / "instances.jsonl"):
        ref_files = set(patch_files(inst["code_patch"]))
        wd = fresh_checkout(inst, WORK / f"rq2_{inst['instance_id']}")
        sources = {f: (wd / f).read_text() for f in ref_files if (wd / f).exists()}
        ref_funcs = changed_functions(inst["code_patch"], sources)
        for kind, cond in (("desc", "C2"), ("impl", "C3")):
            path = RESULTS / inst["instance_id"] / f"guidance_{kind}.json"
            if not path.exists():
                continue
            g = json.loads(path.read_text()).get("guidance", {})
            pred_files = {f.strip().lstrip("./") for f in g.get("files", [])}
            pred_funcs = {norm_func(f) for f in g.get("functions", [])}
            # aceita nomes não totalmente qualificados por sufixo
            matched = {r for r in ref_funcs for p in pred_funcs if r == p or r.endswith("." + p)}
            pred_funcs_aligned = matched | {p for p in pred_funcs
                                            if not any(r == p or r.endswith("." + p) for r in ref_funcs)}
            for level, pred, ref in (("file", pred_files, ref_files),
                                     ("function", pred_funcs_aligned, ref_funcs)):
                rows.append({"instance_id": inst["instance_id"], "condition": cond,
                             "level": level, **prf(pred, ref)})
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "rq2_per_instance.csv", index=False)
    summary = df.groupby(["condition", "level"])[["precision", "recall", "f1", "exact"]].mean()
    summary.to_csv(RESULTS / "rq2_summary.csv")
    print(summary)


if __name__ == "__main__":
    main()
