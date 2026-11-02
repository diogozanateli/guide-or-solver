"""Executa as condições C1, C2 e C3 para cada instância (Kaggle, GPU).

Grava, por execução: trajetória, patch, orientação, tokens, ações e duração.
Retoma automaticamente execuções já concluídas (checkpoint por arquivo).

Uso: python runner/run_condition.py [--limit N] [--conditions C1 C2 C3]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.utils import (DATA, RESULTS, ROOT, WORK, fresh_checkout, git_diff,  # noqa: E402
                          load_config, read_jsonl, setup_venv)

# API do mini-swe-agent — confira a versão instalada caso os nomes mudem.
from minisweagent.agents.default import DefaultAgent  # noqa: E402
from minisweagent.environments.local import LocalEnvironment  # noqa: E402
from minisweagent.models.litellm_model import LitellmModel  # noqa: E402

CODE_RE = re.compile(r"```|^\s*(def |class |import |from \S+ import )|^[+-]{1}\s", re.M)


class Counter:
    """Acumula tokens reportados pelo Ollama (via LiteLLM) e ações executadas."""

    def __init__(self, model: LitellmModel):
        self.model, self.inp, self.out, self.calls = model, 0, 0, 0
        original = model.query

        def query(messages, **kw):
            resp = original(messages, **kw)
            usage = (resp.get("extra", {}).get("response", {}) or {}).get("usage", {}) \
                if isinstance(resp, dict) else {}
            self.inp += usage.get("prompt_tokens", 0)
            self.out += usage.get("completion_tokens", 0)
            self.calls += 1
            return resp

        model.query = query


def make_model(cfg: dict) -> LitellmModel:
    m = cfg["model"]
    return LitellmModel(
        model_name=m["name"],
        model_kwargs={"api_base": m["api_base"], "temperature": m["temperature"],
                      "seed": m["seed"], "num_ctx": m["num_ctx"]},
        cost_tracking="ignore_errors",
    )


def run_agent(cfg: dict, workdir: Path, task: str, step_limit: int) -> dict:
    model = make_model(cfg)
    counter = Counter(model)
    env = LocalEnvironment(cwd=str(workdir), timeout=cfg["agent"]["command_timeout_s"],
                           env={"PATH": f"{workdir}/.venv/bin:/usr/local/bin:/usr/bin:/bin"})
    agent = DefaultAgent(model, env, step_limit=step_limit)
    t0 = time.time()
    try:
        status, output = agent.run(task)
    except Exception as e:  # registrar falhas de execução em vez de abortar
        status, output = type(e).__name__, str(e)
    return {
        "status": status, "output": output, "duration_s": round(time.time() - t0, 1),
        "input_tokens": counter.inp, "output_tokens": counter.out,
        "llm_calls": counter.calls,
        "actions": sum(1 for m in agent.messages if m.get("role") == "assistant"),
        "trajectory": agent.messages,
    }


def issue_text(inst: dict) -> str:
    return f"# {inst['issue_title']}\n\n{inst['issue_body']}"


def parse_guidance(output: str) -> dict:
    m = re.search(r"\{.*\}", output or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {"raw": output}


def contextualize(cfg: dict, inst: dict, kind: str, out_dir: Path) -> dict:
    path = out_dir / f"guidance_{kind}.json"
    if path.exists():
        return json.loads(path.read_text())
    prompt = (ROOT / "prompts" / f"contextualizer_{kind}.md").read_text()
    wd = fresh_checkout(inst, WORK / f"{inst['instance_id']}_ctx")
    setup_venv(wd)
    res = run_agent(cfg, wd, prompt.replace("{issue}", issue_text(inst)),
                    cfg["agent"]["contextualizer_step_limit"])
    guidance = parse_guidance(res["output"])
    if kind == "desc":
        text = json.dumps({k: v for k, v in guidance.items()})
        guidance["_contains_code"] = bool(CODE_RE.search(text))
    res["guidance"] = guidance
    path.write_text(json.dumps(res, indent=1))
    return res


def format_guidance(g: dict) -> str:
    g = {k: v for k, v in g.items() if not k.startswith("_")}
    return "## Guidance from a previous analysis\n\n```json\n" + json.dumps(g, indent=1) + "\n```"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--conditions", nargs="+")
    args = ap.parse_args()
    cfg = load_config()
    solver_prompt = (ROOT / "prompts" / "solver.md").read_text()
    instances = read_jsonl(DATA / "instances.jsonl")[: args.limit]

    for inst in instances:
        out_dir = RESULTS / inst["instance_id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        for cond in args.conditions or cfg["conditions"]:
            for k in range(cfg["runs_per_condition"]):
                target = out_dir / f"{cond}_run{k}.json"
                if target.exists():
                    continue
                guidance, ctx = "", None
                if cond in ("C2", "C3"):
                    ctx = contextualize(cfg, inst, "desc" if cond == "C2" else "impl", out_dir)
                    guidance = format_guidance(ctx["guidance"])
                task = solver_prompt.replace("{issue}", issue_text(inst)).replace("{guidance}", guidance)
                wd = fresh_checkout(inst, WORK / inst["instance_id"])
                setup_venv(wd)
                res = run_agent(cfg, wd, task, cfg["agent"]["step_limit"])
                res["patch"] = git_diff(wd)
                if ctx:
                    res["contextualizer"] = {k2: ctx[k2] for k2 in
                                             ("input_tokens", "output_tokens", "actions", "duration_s")}
                target.write_text(json.dumps(res, indent=1))
                print(f"[{cond}] {inst['instance_id']} run{k}: {res['status']} "
                      f"{res['actions']} ações, {res['input_tokens']}+{res['output_tokens']} tokens")


if __name__ == "__main__":
    main()
