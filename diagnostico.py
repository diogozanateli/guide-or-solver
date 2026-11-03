#!/usr/bin/env python3
"""
Diagnóstico mini-swe-agent + LiteLLM + Ollama (Kaggle).

Uso (da raiz do projeto, para `from runner.run_condition import ...` funcionar):

  python diagnostico.py versoes
  python diagnostico.py ollama    --model qwen2.5-coder:7b
  python diagnostico.py ambiente
  python diagnostico.py raw       --model qwen2.5-coder:7b --provider ollama [--debug]
  python diagnostico.py raw       --model qwen2.5-coder:7b --provider ollama_chat
  python diagnostico.py agente    --model qwen2.5-coder:7b --provider ollama --modo minimo
  python diagnostico.py agente    --model qwen2.5-coder:7b --provider ollama --modo default
  python diagnostico.py traj      caminho/trajetoria.json

Cada subcomando responde a uma hipótese (ver comentários). Nenhum altera o pipeline.
"""
import argparse
import collections
import importlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

API_BASE = os.environ.get("OLLAMA_HOST_URL", "http://localhost:11434")
MARKER = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"

BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Execute a bash command",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "The bash command to execute"}},
            "required": ["command"],
        },
    },
}


def hr(t):
    print("\n" + "=" * 8, t, "=" * 8)


# ---------------------------------------------------------------- 1. versões
def cmd_versoes(a):
    """H: versões instaladas e como o provider `ollama/` do LiteLLM trata tools."""
    hr("Versões")
    out = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if any(k in line.lower() for k in ("mini-swe", "minisweagent", "litellm", "ollama")):
            print(line)

    hr("Config carregada por default_agent_config()")
    try:
        from runner.run_condition import default_agent_config
        cfg, extra = default_agent_config()
        print("chaves de topo:", list(cfg.keys()))
        print("chaves de agent:", list(cfg.get("agent", {}).keys()))
        print("model (se houver):", cfg.get("model"))
        st = cfg.get("agent", {}).get("system_template", "")
        print("system_template contém 'mswea_bash_command' (formato TEXTUAL)?", "mswea_bash_command" in st)
        print("system_template contém 'THOUGHT'?", "THOUGHT" in st)
    except Exception as e:
        print("falhou:", type(e).__name__, e)

    hr("Config builtin do pacote")
    try:
        import minisweagent
        base = os.path.join(os.path.dirname(minisweagent.__file__), "config")
        print("dir:", base)
        for root, _, files in os.walk(base):
            for f in files:
                if f.endswith(".yaml"):
                    p = os.path.join(root, f)
                    txt = open(p, encoding="utf-8").read()
                    print(f"{os.path.relpath(p, base):40s} textual={'mswea_bash_command' in txt}  "
                          f"model_class={[l.strip() for l in txt.splitlines() if 'model_class' in l]}")
    except Exception as e:
        print("falhou:", e)

    hr("LiteLLM: como `ollama/` e `ollama_chat/` tratam tools")
    try:
        import litellm
        root = os.path.dirname(litellm.__file__)
        for rel in ("llms/ollama/completion/transformation.py", "llms/ollama/chat/transformation.py"):
            p = os.path.join(root, rel)
            print("\n--", rel, "existe:", os.path.exists(p))
            if os.path.exists(p):
                for i, l in enumerate(open(p, encoding="utf-8").read().splitlines(), 1):
                    s = l.lower()
                    if any(k in s for k in ("tools", "tool_calls", '"format"', "json_schema", "function")):
                        print(f"{i:4d}: {l.rstrip()}")
        print("\n=> Procure por: `format = json` quando há tools, injeção de prompt de função,")
        print("   e qual endpoint (/api/generate vs /api/chat) cada provider usa.")
    except Exception as e:
        print("falhou:", e)


# ---------------------------------------------------------------- 2. Ollama
def _http(path, body=None):
    req = urllib.request.Request(
        API_BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def cmd_ollama(a):
    """H: modelo declara suporte a tools? num_ctx realmente aplicado?"""
    hr(f"/api/show {a.model}")
    info = _http("/api/show", {"model": a.model})
    print("capabilities:", info.get("capabilities"))
    tpl = info.get("template", "")
    print("template contém .Tools?", ".Tools" in tpl)
    print("parameters:", info.get("parameters"))

    hr("num_ctx efetivo (envia num_ctx e consulta /api/ps)")
    _http("/api/chat", {
        "model": a.model, "stream": False,
        "messages": [{"role": "user", "content": "diga ok"}],
        "options": {"num_ctx": 32768, "seed": 42, "temperature": 0},
        "keep_alive": "5m",
    })
    ps = _http("/api/ps")
    for m in ps.get("models", []):
        print(m.get("name"), "context_length:", m.get("context_length"), "size_vram:", m.get("size_vram"))
    print("(se context_length != 32768, o num_ctx NÃO está chegando; se faltar o campo, "
          "veja o log do servidor Ollama por 'truncating input')")


# ---------------------------------------------------------------- 3. ambiente
def cmd_ambiente(a):
    """H: o marcador é interceptado pelo LocalEnvironment da sua instalação?"""
    from minisweagent.environments.local import LocalEnvironment
    try:
        from minisweagent.exceptions import Submitted
    except Exception:
        Submitted = ()
    env = LocalEnvironment(cwd=tempfile.gettempdir(), timeout=20)
    print("assinatura execute:", inspect.signature(env.execute))
    casos = {
        "marcador sozinho": f"echo {MARKER}",
        "marcador && outro": f"echo {MARKER} && echo patch",
        "outro antes": f"echo oi && echo {MARKER}",
        "marcador com exit!=0": f"echo {MARKER}; false",
        "comando normal": "pwd",
        "THOUGHT no command": "THOUGHT: procurar arquivo",
    }
    for nome, cmd in casos.items():
        try:
            out = env.execute({"command": cmd})
            print(f"[{nome:22s}] NÃO levantou Submitted | returncode={out.get('returncode')} "
                  f"| output={str(out.get('output'))[:70]!r}")
        except Exception as e:
            kind = "Submitted" if (Submitted and isinstance(e, Submitted)) else type(e).__name__
            print(f"[{nome:22s}] levantou {kind}")
    print("\nEsperado (main): só os casos com o marcador na PRIMEIRA linha e returncode 0 levantam Submitted.")


# ---------------------------------------------------------------- 4. raw
def cmd_raw(a):
    """H: o que cada provider devolve, passo a passo, sem mini-swe-agent no meio."""
    import litellm
    if a.debug:
        litellm._turn_on_debug()  # imprime o corpo da requisição enviada ao Ollama
    model = f"{a.provider}/{a.model}"
    kw = dict(api_base=API_BASE, temperature=0, seed=42, num_ctx=32768, tools=[BASH_TOOL])
    if a.tool_choice:
        kw["tool_choice"] = a.tool_choice

    msgs = [
        {"role": "system", "content": "You are a helpful assistant. Use the bash tool to run commands. "
         f"When all steps are done, reply in plain text without calling any tool."},
        {"role": "user", "content": "Step 1: run `pwd`. Step 2: run `ls`. Then say DONE in plain text."},
    ]
    for step in range(1, a.steps + 1):
        hr(f"{model} passo {step}")
        t0 = time.time()
        r = litellm.completion(model=model, messages=msgs, **kw)
        m = r.choices[0].message
        print(f"finish_reason={r.choices[0].finish_reason}  n_choices={len(r.choices)}  {time.time()-t0:.1f}s")
        print("content:", repr(m.content)[:300])
        tcs = m.tool_calls or []
        print("tool_calls:", [(t.function.name, t.function.arguments) for t in tcs])
        if not tcs:
            print("-> sem tool_calls: o modelo CONSEGUE responder em texto (encerramento possível).")
            break
        msgs.append(m.model_dump() if hasattr(m, "model_dump") else dict(m))
        for t in tcs:
            try:
                cmd = json.loads(t.function.arguments).get("command", "")
            except Exception:
                cmd = ""
                print("!! arguments inválido:", t.function.arguments)
            if cmd.strip().startswith("THOUGHT"):
                print("!! 'THOUGHT' dentro de command")
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            msgs.append({"role": "tool", "tool_call_id": t.id, "content": (res.stdout + res.stderr)[:2000]})
    else:
        print("\nchegou ao limite de passos sem resposta em texto -> modelo nunca encerra (compare com ollama_chat).")


# ---------------------------------------------------------------- 5. agente
MIN_SYSTEM = "You are a helpful assistant that can interact with a computer. Use the bash tool."
MIN_INSTANCE = (
    "Task: {{task}}\n\nRun commands with the bash tool. When finished, run exactly:\n"
    f"echo {MARKER}\nDo not combine it with other commands."
)


def cmd_agente(a):
    """H: com o ciclo real do mini-swe-agent, qual é o exit_status e onde para?"""
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.environments.local import LocalEnvironment
    from minisweagent.models.litellm_model import LitellmModel

    kwargs = {"step_limit": a.steps}
    if a.modo == "default":
        from runner.run_condition import default_agent_config
        cfg, _ = default_agent_config()
        kwargs = {**cfg.get("agent", {}), "step_limit": a.steps}
    else:
        kwargs.update(system_template=MIN_SYSTEM, instance_template=MIN_INSTANCE)

    model = LitellmModel(
        model_name=f"{a.provider}/{a.model}",
        model_kwargs=dict(api_base=API_BASE, temperature=0, seed=42, num_ctx=32768),
    )
    work = tempfile.mkdtemp()
    open(os.path.join(work, "a.txt"), "w").write("hello\n")
    env = LocalEnvironment(cwd=work, timeout=30)
    agent = DefaultAgent(model, env, **kwargs)

    task = "List the files in the current directory, read a.txt with cat, then finish."
    t0 = time.time()
    try:
        result = agent.run(task)
    except Exception as e:
        result = {"EXCEÇÃO": f"{type(e).__name__}: {e}"}
    print(f"duração {time.time()-t0:.1f}s")

    hr("Retorno de agent.run()")
    print("tipo:", type(result).__name__)
    if isinstance(result, dict):
        print("chaves:", list(result.keys()))
        print("exit_status:", result.get("exit_status"))
        print("submission:", repr(result.get("submission"))[:200])
        print("=> se seu código faz `status, output = agent.run(...)` com dict de 2 chaves, "
              "status vira a STRING 'exit_status'.")
    else:
        print("valor:", repr(result)[:300])

    hr("Mensagens")
    msgs = agent.messages
    print("total:", len(msgs), collections.Counter(m.get("role") for m in msgs))
    n_ass = sum(1 for m in msgs if m.get("role") == "assistant")
    n_tool_calls = sum(len(m.get("tool_calls") or []) for m in msgs if m.get("role") == "assistant")
    print(f"assistant={n_ass}  tool_calls={n_tool_calls}  (diferença = respostas sem tool call/FormatError)")
    for i, m in enumerate(msgs):
        role = m.get("role")
        body = m.get("content")
        if role == "assistant":
            body = f"content={str(m.get('content'))[:80]!r} tool_calls={[t['function'] for t in (m.get('tool_calls') or [])]}"
        print(f"[{i:02d}] {role:9s} {str(body)[:200]!r}")
    for attr in ("n_calls", "cost"):
        if hasattr(model, attr):
            print(f"model.{attr} =", getattr(model, attr))
    out = os.path.join(os.getcwd(), f"diag_traj_{a.provider}_{a.modo}.json")
    json.dump(msgs, open(out, "w"), indent=1, default=str)
    print("trajetória salva em", out)


# ---------------------------------------------------------------- 6. traj
def cmd_traj(a):
    """Analisa uma trajetória já existente (mensagens ou .traj.json)."""
    d = json.load(open(a.path))
    msgs = d["messages"] if isinstance(d, dict) and "messages" in d else d
    if isinstance(d, dict):
        info = d.get("info", {})
        print("exit_status:", info.get("exit_status"), "| model_stats:", info.get("model_stats"))
    roles = collections.Counter(m.get("role") for m in msgs)
    print("roles:", dict(roles))

    cmds, rcs, fmt_err, thought_cmd = [], collections.Counter(), 0, 0
    for m in msgs:
        if m.get("role") == "assistant":
            for t in m.get("tool_calls") or []:
                try:
                    c = json.loads(t["function"]["arguments"]).get("command", "")
                except Exception:
                    c = "<arguments inválido>"
                cmds.append(c)
                thought_cmd += c.strip().startswith("THOUGHT")
        txt = json.dumps(m, default=str)
        if "No tool calls found" in txt or "Format error" in txt or "format error" in txt:
            fmt_err += 1
        ex = (m.get("extra") or {})
        if m.get("role") == "tool" and "returncode" in ex:
            rcs[ex["returncode"]] += 1

    print(f"assistant={roles.get('assistant', 0)}  tool_calls={len(cmds)}  "
          f"respostas sem tool call={roles.get('assistant', 0) - len(cmds)}")
    print("mensagens com erro de formato:", fmt_err)
    print("comandos começando com 'THOUGHT':", thought_cmd)
    print("returncodes:", dict(rcs))
    rep = collections.Counter(cmds).most_common(5)
    print("comandos mais repetidos:")
    for c, n in rep:
        print(f"  {n:3d}x {c[:100]!r}")
    # primeiro passo sem progresso: 3 comandos idênticos consecutivos
    for i in range(2, len(cmds)):
        if cmds[i] == cmds[i - 1] == cmds[i - 2]:
            print(f"primeiro loop (3 repetições seguidas) no tool_call #{i-1}: {cmds[i][:100]!r}")
            break


def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("versoes").set_defaults(f=cmd_versoes)
    sp.add_parser("ambiente").set_defaults(f=cmd_ambiente)
    o = sp.add_parser("ollama"); o.add_argument("--model", required=True); o.set_defaults(f=cmd_ollama)
    r = sp.add_parser("raw")
    r.add_argument("--model", required=True)
    r.add_argument("--provider", default="ollama", choices=["ollama", "ollama_chat"])
    r.add_argument("--steps", type=int, default=5)
    r.add_argument("--tool-choice", dest="tool_choice", default=None)
    r.add_argument("--debug", action="store_true")
    r.set_defaults(f=cmd_raw)
    g = sp.add_parser("agente")
    g.add_argument("--model", required=True)
    g.add_argument("--provider", default="ollama", choices=["ollama", "ollama_chat"])
    g.add_argument("--modo", default="minimo", choices=["minimo", "default"])
    g.add_argument("--steps", type=int, default=8)
    g.set_defaults(f=cmd_agente)
    t = sp.add_parser("traj"); t.add_argument("path"); t.set_defaults(f=cmd_traj)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
