"""Valida candidatos: identifica FAIL_TO_PASS e PASS_TO_PASS e descarta casos
não reprodutíveis ou instáveis.

Entrada: data/candidates.jsonl  Saída: data/instances.jsonl, data/exclusions.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.utils import (DATA, WORK, append_jsonl, apply_patch, fresh_checkout,  # noqa: E402
                          load_config, patch_files, read_jsonl, run, run_tests, setup_venv)


def exclude(iid: str, reason: str) -> None:
    path = DATA / "exclusions.csv"
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["instance_id", "reason"])
        w.writerow([iid, reason])
    print(f"[-] {iid}: {reason}")


def resolve_base(inst: dict) -> str | None:
    """Revisão base = primeiro pai do merge commit."""
    tmp = WORK / "_base"
    run(f"rm -rf {tmp} && git init -q {tmp}")
    run(f"git fetch -q --depth 2 https://github.com/{inst['repo']}.git {inst['merge_commit']}", cwd=tmp)
    r = run("git rev-parse FETCH_HEAD^1", cwd=tmp)
    return r.stdout.strip() if r.returncode == 0 else None


def validate(inst: dict, cfg: dict) -> dict | None:
    iid = inst["instance_id"]
    inst["base_commit"] = inst.get("base_commit") or resolve_base(inst)
    if not inst["base_commit"]:
        return exclude(iid, "historico_irrecuperavel")
    d = WORK / iid
    try:
        fresh_checkout(inst, d)
    except RuntimeError:
        return exclude(iid, "checkout_falhou")
    if not setup_venv(d, cfg["install_timeout_s"]):
        return exclude(iid, "ambiente_nao_executavel")
    if not apply_patch(d, inst["test_patch"]):
        return exclude(iid, "test_patch_nao_aplica")
    tests = patch_files(inst["test_patch"])

    before = [run_tests(d, tests, cfg["test_timeout_s"]) for _ in range(cfg["repeats"])]
    if not apply_patch(d, inst["code_patch"]):
        return exclude(iid, "code_patch_nao_aplica")
    after = [run_tests(d, tests, cfg["test_timeout_s"]) for _ in range(cfg["repeats"])]

    if not before[0] or not after[0]:
        return exclude(iid, "testes_nao_executam")
    if any(b != before[0] for b in before) or any(a != after[0] for a in after):
        return exclude(iid, "testes_instaveis")

    f2p = [t for t, o in after[0].items() if o == "passed" and before[0].get(t) != "passed"]
    p2p = [t for t, o in after[0].items() if o == "passed" and before[0].get(t) == "passed"]
    if not f2p:
        return exclude(iid, "sem_fail_to_pass")
    inst.update(FAIL_TO_PASS=f2p, PASS_TO_PASS=p2p, test_files=tests)
    return inst


def main() -> None:
    cfg = load_config()["validation"]
    out = DATA / "instances.jsonl"
    done = {i["instance_id"] for i in read_jsonl(out)}
    excluded = set()
    if (DATA / "exclusions.csv").exists():
        excluded = {r["instance_id"] for r in csv.DictReader((DATA / "exclusions.csv").open())}
    for inst in read_jsonl(DATA / "candidates.jsonl"):
        if inst["instance_id"] in done | excluded:
            continue
        ok = validate(inst, cfg)
        if ok:
            append_jsonl(out, ok)
            print(f"[+] {inst['instance_id']}: {len(ok['FAIL_TO_PASS'])} F2P")
        run(f"rm -rf {WORK / inst['instance_id']}")


if __name__ == "__main__":
    main()
