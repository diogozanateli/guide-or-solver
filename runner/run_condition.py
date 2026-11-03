"""Executa as condições C1, C2 e C3 para cada instância (Kaggle, GPU).

  C1 — resolvedor recebe a issue original (Default do CodeScout)
  C2 — resolvedor recebe a especificação aumentada pelo CodeScout SEM a subseção
       "Implementation Suggestions" (orientação descritiva)
  C3 — resolvedor recebe a especificação aumentada completa do CodeScout

Como no CodeScout, a especificação aumentada SUBSTITUI a issue original e o
resolvedor usa o prompt padrão do mini-swe-agent (mini_textbased.yaml, sem alterações).
C2 e C3 derivam da mesma execução do CodeScout (results/<modelo>/<instancia>/codescout.json).

Grava, por execução: trajetória, patch, tokens, ações, duração, exit_status real,
proveniência (commit, hash da config, versões) e auditoria de vazamento do gabarito.
Retoma automaticamente execuções já concluídas (checkpoint por arquivo).

Uso: python runner/run_condition.py --model qwen2.5-coder:7b [--limit N] [--conditions C1 C2 C3]
                                    [--instances data/instances.jsonl] [--allow-invalid-codescout]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import os
import re
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.utils import (DATA, ROOT, WORK, audit_leak, fresh_checkout, git_diff,  # noqa: E402
                          load_config, model_results_dir, new_files_in, read_jsonl, run,
                          selected_model, setup_venv)
from runner.codescout import run_codescout  # noqa: E402

# API do mini-swe-agent 2.4.6 — confira a versão instalada caso os nomes mudem.
from minisweagent.agents.default import DefaultAgent  # noqa: E402
from minisweagent.environments.local import LocalEnvironment  # noqa: E402
from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel  # noqa: E402

os.environ.setdefault("MSWEA_COST_TRACKING", "ignore_errors")  # modelos locais têm custo 0

MODEL = selected_model()
RESULTS = model_results_dir()


def default_agent_config() -> tuple[dict, str]:
    from minisweagent.config import get_config_path

    path = Path(get_config_path("mini_textbased"))
    return yaml.safe_load(path.read_text()), str(path)


def config_sha(agent_cfg: dict) -> str:
    return hashlib.sha256(json.dumps(agent_cfg, sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------- contagem de uso
class UsageCounter:
    """Conta chamadas e tokens interceptando litellm.completion.

    O mini-swe-agent faz o parse da resposta DEPOIS da chamada; quando o parse falha
    (FormatError) a resposta não vira mensagem do assistente, então contar pela trajetória
    subestima chamadas e tokens justamente nas execuções com erro de formato.
    """

    def __init__(self):
        self._installed = False
        self.reset()

    def reset(self):
        self.calls = self.inp = self.out = self.errors = 0

    def install(self):
        if self._installed:
            return
        import litellm

        original = litellm.completion

        def counted(*a, **k):
            try:
                resp = original(*a, **k)
            except Exception:
                self.errors += 1
                raise
            self.calls += 1
            u = getattr(resp, "usage", None)
            if u is None and isinstance(resp, dict):
                u = resp.get("usage")
            get = (lambda key: (u.get(key) if isinstance(u, dict) else getattr(u, key, 0)) or 0) if u else (lambda key: 0)
            self.inp += get("prompt_tokens")
            self.out += get("completion_tokens")
            return resp

        litellm.completion = counted
        self._installed = True


USAGE = UsageCounter()


def trajectory_usage(messages: list[dict]) -> tuple[int, int, int]:
    """Plano B (subconta chamadas com erro de formato): usa extra.response de cada mensagem."""
    inp = out = calls = 0
    for m in messages:
        resp = (m.get("extra") or {}).get("response")
        usage = resp.get("usage") if isinstance(resp, dict) else getattr(resp, "usage", None)
        if not usage:
            continue
        g = (lambda k: (usage.get(k) if isinstance(usage, dict) else getattr(usage, k, 0)) or 0)
        calls += 1
        inp += g("prompt_tokens")
        out += g("completion_tokens")
    return calls, inp, out


# ---------------------------------------------------------------- agente
def make_model(cfg: dict, agent_cfg: dict | None = None) -> LitellmTextbasedModel:
    """Modelo textual (ollama_chat/): não depende de tool calling do Ollama, então vale
    igualmente para Qwen (com tools) e DeepSeek-Coder-V2 (sem tools)."""
    g = cfg["generation"]
    agent_cfg = agent_cfg or default_agent_config()[0]

    model_name = MODEL["name"]
    if model_name.startswith("ollama/"):
        model_name = model_name.replace("ollama/", "ollama_chat/", 1)
    elif not model_name.startswith("ollama_chat/"):
        model_name = f"ollama_chat/{model_name}"

    # Seção `model` do mini_textbased.yaml (observation_template, format_error_template,
    # action_regex...) — a mesma usada na validação com o diagnóstico.
    model_cfg = {k: v for k, v in agent_cfg.get("model", {}).items()
                 if k not in ("model_class", "model_name", "model_kwargs", "cost_tracking")}

    return LitellmTextbasedModel(
        model_name=model_name,
        model_kwargs={
            "api_base": g["api_base"],
            "temperature": g["temperature"],
            "seed": g["seed"],
            "num_ctx": g["num_ctx"],
        },
        cost_tracking="ignore_errors",
        **model_cfg,
    )


def run_agent(cfg: dict, workdir: Path, task: str) -> dict:
    agent_cfg, cfg_path = default_agent_config()
    agent_kwargs = {
        **agent_cfg.get("agent", {}),
        "step_limit": cfg["agent"]["step_limit"],
    }

    USAGE.install()
    USAGE.reset()
    model = make_model(cfg, agent_cfg)
    env = LocalEnvironment(
        cwd=str(workdir),
        timeout=cfg["agent"]["command_timeout_s"],
        env={"PATH": f"{workdir}/.venv/bin:/usr/local/bin:/usr/bin:/bin"},
    )
    agent = DefaultAgent(model, env, **agent_kwargs)

    t0 = time.time()
    try:
        result = agent.run(task)  # dict: {"exit_status", "submission"}
        status = result.get("exit_status", "unknown")
        output = result.get("submission", "")
    except Exception as e:
        status, output = type(e).__name__, str(e)
    duration = round(time.time() - t0, 1)

    msgs = agent.messages
    if USAGE.calls > 0:
        llm_calls, in_tok, out_tok, usage_source = USAGE.calls, USAGE.inp, USAGE.out, "litellm.completion"
    else:  # interceptação não pegou (classe chama completion por outro caminho)
        llm_calls, in_tok, out_tok = trajectory_usage(msgs)
        usage_source = "trajectory (subconta chamadas com erro de formato)"

    body = [m for m in msgs[2:] if m.get("role") in ("user", "tool")]
    obs = [m for m in body if "<returncode>" in str(m.get("content"))]
    exit_msg = next((m for m in reversed(msgs) if m.get("role") == "exit"), {})

    return {
        "status": status,
        "output": output,
        "exit_status": status,
        "submission": output,
        "exit_message": str(exit_msg.get("content", ""))[:500],
        "duration_s": duration,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "llm_calls": llm_calls,
        "llm_errors": USAGE.errors,
        "usage_source": usage_source,
        "n_assistant_msgs": sum(1 for m in msgs if m.get("role") == "assistant"),
        "actions": len(obs),  # comandos efetivamente executados (observações com returncode)
        # mensagens de usuário/ferramenta que NÃO são observação (heurística de erro de formato)
        "n_non_observation_msgs": len(body) - len(obs),
        "trajectory": msgs,
        "provenance": {
            "git_commit": run("git rev-parse HEAD", cwd=ROOT).stdout.strip(),
            "agent_config": cfg_path,
            "agent_config_sha256": config_sha(agent_cfg),
            "versions": {p: md.version(p) for p in ("mini-swe-agent", "litellm")},
            "model": MODEL["name"],
        },
    }


# ---------------------------------------------------------------- CodeScout
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
          f"C2 removeu implementação: {res['c2_removed_implementation']}, "
          f"truncado: {res.get('any_truncated')}")
    return res


def codescout_problems(cs: dict) -> list[str]:
    """Portão de validade: C2 e C3 só são comparáveis se C2 realmente não tem as sugestões."""
    p = []
    if not cs.get("c2_removed_implementation"):
        p.append("C2 não removeu 'Implementation Suggestions' (C2 seria igual a C3)")
    if cs.get("c2_contains_code"):
        p.append("C2 contém blocos de código fora de Reproduction Steps")
    if cs.get("any_truncated"):
        p.append("contexto truncado em alguma chamada do CodeScout")
    return p


def save_agent_config() -> None:
    cfg, src = default_agent_config()
    (RESULTS / "agent_config.json").write_text(json.dumps(
        {"source": src, "sha256": config_sha(cfg), "config": cfg}, indent=1, default=str))


def skip(out_dir: Path, cond: str, k: int, reason, inst_id: str) -> None:
    (out_dir / f"{cond}_run{k}.skipped.json").write_text(
        json.dumps({"instance_id": inst_id, "condition": cond, "reason": reason}, indent=1, ensure_ascii=False))
    print(f"[{cond}] {inst_id} run{k}: PULADA — {reason}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="modelo de config/experiment.yaml (padrão: o primeiro)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--conditions", nargs="+")
    ap.add_argument("--instances", default=str(DATA / "instances.jsonl"),
                    help="Arquivo JSONL com as instâncias do experimento")
    ap.add_argument("--allow-invalid-codescout", action="store_true",
                    help="roda C2/C3 mesmo se o portão de validade do CodeScout falhar")
    args = ap.parse_args()
    cfg = load_config()
    print(f"Modelo: {MODEL['name']} → {RESULTS} | WORK={WORK}")
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
                    problems = codescout_problems(cs)
                    if problems and not args.allow_invalid_codescout:
                        skip(out_dir, cond, k, problems, inst["instance_id"])
                        continue
                    task = cs["ps_aug_c2"] if cond == "C2" else cs["ps_aug_c3"]
                wd = fresh_checkout(inst, WORK / inst["instance_id"])
                venv_ok = setup_venv(wd)
                if not venv_ok:
                    skip(out_dir, cond, k, "setup_venv falhou (ambiente inválido)", inst["instance_id"])
                    continue
                res = run_agent(cfg, wd, task)
                res["task"] = task
                res["venv_ok"] = venv_ok
                res["patch"] = git_diff(wd)
                res["patch_nonempty"] = bool(res["patch"].strip())
                res["new_files"] = new_files_in(res["patch"])
                res["leak_audit"] = audit_leak(res["trajectory"])
                if res["leak_audit"]:
                    print(f"!! [{cond}] {inst['instance_id']}: INDÍCIO DE ACESSO AO GABARITO/PROJETO "
                          f"({res['leak_audit'][0]['match']}) — execução deve ser invalidada")
                if cs:  # custo do contextualizador (compartilhado entre C2 e C3: NÃO somar os dois)
                    res["contextualizer"] = {"input_tokens": cs["input_tokens"],
                                             "output_tokens": cs["output_tokens"],
                                             "llm_calls": cs["llm_calls"], "actions": 0,
                                             "duration_s": cs["duration_s"]}
                target.write_text(json.dumps(res, indent=1, default=str))
                print(f"[{cond}] {inst['instance_id']} run{k}: {res['status']} "
                      f"{res['actions']} ações, {res['llm_calls']} chamadas, "
                      f"{res['input_tokens']}+{res['output_tokens']} tokens, patch={'sim' if res['patch_nonempty'] else 'vazio'}")


if __name__ == "__main__":
    main()
