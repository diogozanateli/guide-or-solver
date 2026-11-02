"""Aplica cada patch gerado na revisão base, adiciona os testes humanos e
classifica a execução como resolvida (F2P todos passam e P2P sem regressão).

Saída: results/evaluation.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.utils import (DATA, RESULTS, WORK, append_jsonl, apply_patch, fresh_checkout,  # noqa: E402
                          read_jsonl, run_tests, setup_venv, split_patch)


def main() -> None:
    out = RESULTS / "evaluation.jsonl"
    done = {(r["instance_id"], r["run"]) for r in read_jsonl(out)}
    for inst in read_jsonl(DATA / "instances.jsonl"):
        for f in sorted((RESULTS / inst["instance_id"]).glob("C*_run*.json")):
            key = (inst["instance_id"], f.stem)
            if key in done:
                continue
            res = json.loads(f.read_text())
            code_patch, _ = split_patch(res.get("patch", ""))  # descarta edições em testes
            wd = fresh_checkout(inst, WORK / f"eval_{inst['instance_id']}")
            rec = {"instance_id": inst["instance_id"], "run": f.stem,
                   "condition": f.stem.split("_")[0], "resolved": False,
                   "applied": False, "empty_patch": not code_patch.strip()}
            if setup_venv(wd) and apply_patch(wd, code_patch) and apply_patch(wd, inst["test_patch"]):
                rec["applied"] = True
                outcome = run_tests(wd, inst["test_files"])
                f2p = all(outcome.get(t) == "passed" for t in inst["FAIL_TO_PASS"])
                p2p = all(outcome.get(t) == "passed" for t in inst["PASS_TO_PASS"])
                rec.update(f2p_ok=f2p, p2p_ok=p2p, resolved=f2p and p2p)
            append_jsonl(out, rec)
            print(rec)


if __name__ == "__main__":
    main()
