"""RQ3: CodeBLEU entre métodos alterados pelo agente e pelo humano, e
volatilidade (linhas adicionadas + removidas) de cada patch.
Uso: python metrics/rq3.py --model <modelo>"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pandas as pd
from codebleu import calc_codebleu

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.utils import (DATA, WORK, apply_patch, fresh_checkout,  # noqa: E402
                          model_results_dir, patch_files, read_jsonl, split_patch)
from metrics.functions import changed_functions, function_spans, module_name  # noqa: E402

RESULTS = model_results_dir()


def volatility(diff: str) -> int:
    return sum(1 for l in diff.splitlines()
               if l[:1] in "+-" and not l.startswith(("+++", "---")))


def function_sources(repo: Path, files: list[str], names: set[str]) -> dict[str, str]:
    out = {}
    for f in files:
        p = repo / f
        if not p.exists() or not f.endswith(".py"):
            continue
        src = p.read_text()
        lines = src.splitlines()
        for name, s, e in function_spans(src, module_name(f)):
            if name in names:
                out[name] = "\n".join(lines[s - 1:e])
    return out


def patched_tree(inst: dict, diff: str, tag: str) -> Path:
    wd = fresh_checkout(inst, WORK / f"rq3_{tag}_{inst['instance_id']}")
    apply_patch(wd, diff)
    return wd


def main() -> None:
    rows = []
    for inst in read_jsonl(DATA / "instances.jsonl"):
        human = inst["code_patch"]
        h_tree = patched_tree(inst, human, "human")
        base = fresh_checkout(inst, WORK / f"rq3_base_{inst['instance_id']}")
        for f in sorted((RESULTS / inst["instance_id"]).glob("C*_run*.json")):
            agent_patch, _ = split_patch(json.loads(f.read_text()).get("patch", ""))
            row = {"instance_id": inst["instance_id"], "run": f.stem,
                   "condition": f.stem.split("_")[0],
                   "volatility_agent": volatility(agent_patch),
                   "volatility_human": volatility(human), "codebleu": None}
            if agent_patch.strip():
                files = sorted(set(patch_files(agent_patch)) | set(patch_files(human)))
                srcs = {p: (base / p).read_text() for p in files if (base / p).exists()}
                names = changed_functions(agent_patch, srcs) | changed_functions(human, srcs)
                a_tree = patched_tree(inst, agent_patch, "agent")
                a_src = function_sources(a_tree, files, names)
                h_src = function_sources(h_tree, files, names)
                common = sorted(set(a_src) & set(h_src))
                if common:
                    preds = ["\n\n".join(a_src[n] for n in common)]
                    refs = ["\n\n".join(h_src[n] for n in common)]
                    row.update({k: v for k, v in calc_codebleu(refs, preds, lang="python").items()})
            rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "rq3_per_instance.csv", index=False)
    summary = df.groupby("condition")[["codebleu", "volatility_agent", "volatility_human"]].mean()
    summary.to_csv(RESULTS / "rq3_summary.csv")
    print(summary)


if __name__ == "__main__":
    main()
