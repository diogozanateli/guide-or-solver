"""Executa as condições C1, C2 e C3 para cada instância (Kaggle, GPU).

  C1 — resolvedor recebe a issue original (Default do CodeScout)
  C2 — resolvedor recebe a especificação aumentada pelo CodeScout SEM a subseção
       "Implementation Suggestions" (orientação descritiva)
  C3 — resolvedor recebe a especificação aumentada completa do CodeScout

Como no CodeScout, a especificação aumentada SUBSTITUI a issue original e o
resolvedor usa o prompt padrão do mini-swe-agent. C2 e C3 derivam da mesma
execução do CodeScout (results/<modelo>/<instancia>/codescout.json).

Grava, por execução: trajetória, patch, tokens, ações e duração. Retoma
automaticamente execuções já concluídas (checkpoint por arquivo).

Uso: python runner/run_condition.py --model qwen2.5-coder:7b [--limit N] [--conditions C1 C2 C3]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.utils import (DATA, WORK, fresh_checkout, git_diff, load_config,  # noqa: E402
                          model_results_dir, read_jsonl, selected_model, setup_venv)
from runner.codescout import run_codescout  # noqa: E402

MODEL = selected_model()
RESULTS = model_results_dir()

# API do mini-swe-agent — confira a versão instalada caso os nomes mudem.
from minisweagent.agents.default import DefaultAgent  # noqa: E402
from minisweagent.environments.local import LocalEnvironment  # noqa: E402
from minisweagent.models.litellm_model import LitellmModel  # noqa: E402


def default_agent_config() -> tuple[dict, str]:
    from minisweagent.config import get_config_path

    path = Path(get_config_path("mini_textbased"))
    return yaml.safe_load(path.read_text()), str(path)

class Counter:
    """Acumula tokens reportados pelo Ollama (via LiteLLM) e chamadas ao modelo."""

    def __init__(self, model: LitellmModel):
        self.inp, self.out, self.calls = 0, 0, 0
        original = model.query

        def query(messages, **kw):
            resp = original(messages, **kw)
            extra = resp.get("extra", {}) if isinstance(resp, dict) else {}
            raw = extra.get("response", {}) or {}
            usage = raw.get("usage", {}) if isinstance(raw, dict) else getattr(raw, "usage", {}) or {}
            if not isinstance(usage, dict):
                usage = getattr(usage, "model_dump", lambda: {})()
            self.inp += usage.get("prompt_tokens", 0) or 0
            self.out += usage.get("completion_tokens", 0) or 0
            self.calls += 1
            return resp

        model.query = query


def make_model(cfg: dict) -> LitellmTextbasedModel:
    g = cfg["generation"]

    model_name = MODEL["name"]

    # Converte o provedor Ollama para o modo textual do LiteLLM.
    if model_name.startswith("ollama/"):
        model_name = model_name.replace("ollama/", "ollama_chat/", 1)
    elif not model_name.startswith("ollama_chat/"):
        model_name = f"ollama_chat/{model_name}"

    return LitellmTextbasedModel(
        model_name=model_name,
        model_kwargs={
            "api_base": g["api_base"],
            "temperature": g["temperature"],
            "seed": g["seed"],
            "num_ctx": g["num_ctx"],
            "drop_params": True,
        },
        cost_tracking="ignore_errors",
    )


def run_agent(cfg: dict, workdir: Path, task: str) -> dict:
    agent_cfg, _ = default_agent_config()

    agent_kwargs = {
        **agent_cfg.get("agent", {}),
        "step_limit": cfg["agent"]["step_limit"],
    }

    model = make_model(cfg)

    env = LocalEnvironment(
        cwd=str(workdir),
        timeout=cfg["agent"]["command_timeout_s"],
        env={
            "PATH": f"{workdir}/.venv/bin:/usr/local/bin:/usr/bin:/bin"
        },
    )

    agent = DefaultAgent(model, env, **agent_kwargs)

    t0 = time.time()

    try:
        result = agent.run(task)

        status = result.get("exit_status", "unknown")
        output = result.get("submission", "")

    except Exception as e:
        status = type(e).__name__
        output = str(e)
        result = {}

    duration = round(time.time() - t0, 1)

    # Coleta métricas diretamente da trajetória.
    input_tokens = 0
    output_tokens = 0
    llm_calls = 0
    actions = 0

    for message in agent.messages:
        extra = message.get("extra", {})

        # Contabiliza ações produzidas pelo modelo.
        actions += len(extra.get("actions", []))

        # Recupera uso de tokens da resposta do LiteLLM.
        response = extra.get("response", {})
        usage = response.get("usage", {})

        if usage:
            llm_calls += 1
            input_tokens += usage.get("prompt_tokens", 0) or 0
            output_tokens += usage.get("completion_tokens", 0) or 0

    return {
        "status": status,
        "output": output,
        "exit_status": status,
        "submission": output,
        "duration_s": duration,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "llm_calls": llm_calls,
        "actions": actions,
        "trajectory": agent.messages,
    }


def issue_text(inst: dict) -> str:
    return f"{inst['issue_title']}\n\n{inst['issue_body']}"


def codescout(cfg: dict, inst: dict, out_dir: Path) -> dict:
    path = out_dir / "codescout.json"
    if path.exists():
        return json.loads(path.read_text())
    wd = fresh_checkout(inst, WORK / f"{inst['instance_id']}_cs")
    res = run_codescout(wd, issue_text(inst), MODEL["name"], cfg["generation"], cfg["codescout"])
    path.write_text(json.dumps(res, indent=1))
    print(f"[CodeScout] {inst['instance_id']}: {res['n_targets']} alvos, {res['n_analyzed']} analisados, "
          f"{res['n_kept']} >= tau, {res['llm_calls']} chamadas, "
          f"C2 removeu implementação: {res['c2_removed_implementation']}")
    return res


def save_agent_config() -> None:
    path = RESULTS / "agent_config.json"
    if not path.exists():
        cfg, src = default_agent_config()
        path.write_text(json.dumps({"source": src, "config": cfg}, indent=1, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="modelo de config/experiment.yaml (padrão: o primeiro)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--conditions", nargs="+")
    ap.add_argument("--instances", default=str(DATA / "instances.jsonl"), help="Arquivo JSONL com as instâncias do experimento")
    args = ap.parse_args()
    cfg = load_config()
    print(f"Modelo: {MODEL['name']} → {RESULTS}")
    save_agent_config()
    instances = read_jsonl(Path(args.instances))

    if args.limit:
        instances = instances[:args.limit]

    print(f"Instâncias carregadas: {len(instances)}")

    for inst in instances:
        out_dir = RESULTS / inst["instance_id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        for cond in args.conditions or cfg["conditions"]:
            for k in range(cfg["runs_per_condition"]):
                target = out_dir / f"{cond}_run{k}.json"
                if target.exists():
                    continue
                cs = None
                if cond == "C1":
                    task = issue_text(inst)
                else:
                    cs = codescout(cfg, inst, out_dir)
                    task = cs["ps_aug_c2"] if cond == "C2" else cs["ps_aug_c3"]
                wd = fresh_checkout(inst, WORK / inst["instance_id"])
                setup_venv(wd)
                res = run_agent(cfg, wd, task)
                res["task"] = task
                res["patch"] = git_diff(wd)
                if cs:  # custo do contextualizador (compartilhado entre C2 e C3)
                    res["contextualizer"] = {"input_tokens": cs["input_tokens"],
                                             "output_tokens": cs["output_tokens"],
                                             "llm_calls": cs["llm_calls"], "actions": 0,
                                             "duration_s": cs["duration_s"]}
                target.write_text(json.dumps(res, indent=1, default=str))
                print(f"[{cond}] {inst['instance_id']} run{k}: {res['status']} "
                      f"{res['actions']} ações, {res['input_tokens']}+{res['output_tokens']} tokens")


if __name__ == "__main__":
    main()
