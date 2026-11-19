#!/usr/bin/env python3
"""
apply_defaults_and_alarm.py

1) main.cpp: reserve_dst_port e reserve_src_port passam a ser TRUE por padrao
   (para reproduzir o simulador antigo: --np reserve_dst_port=false reserve_src_port=false).
2) Alarme de conclusao (<100%) nos scripts Python:
   - cria completion_alarm.py ao lado do ga_common.py;
   - ga_common.py: le presos/timeouts do resultado e registra o alarme em cada simulacao;
     o cache de avaliacoes passa a depender do HASH DO BINARIO (rebuild invalida o cache);
   - ga_optimize.py, ga_final_eval.py, ga_retries.py, ga_diag.py: resumo do alarme no fim;
   - ga_pilot.py: alarme DESLIGADO (o piloto explora de proposito regimes saturados).

Severidades:
   VIOLACAO = ha fluxo PRESO_TRANSMISSAO (rota alocada, entrega nunca confirmada).
              Com as reservas ligadas isso nao deveria acontecer: indica bug do simulador.
   AVISO    = conclusao < 100% sem presos (timeouts de roteamento, nao iniciados):
              pode ser congestao real da topologia, mas confira.
   COMPLETION_STRICT=1 no ambiente => os scripts terminam com codigo 3 se houver VIOLACAO.

Uso:  py apply_defaults_and_alarm.py --src . [--check]
Cria .bak; se qualquer ancora falhar (nao encontrada exatamente 1x), NADA e escrito.
"""
import argparse, os, sys

ALARM_MODULE = '''"""
completion_alarm.py -- alarme de conclusao (<100%) para os scripts de experimento.

Uso interno (ga_common.Evaluator registra cada simulacao). Severidades:
  VIOLACAO : algum fluxo PRESO_TRANSMISSAO (rota alocada, entrega nunca confirmada).
             Com reserve_dst_port e reserve_src_port ligados nao deveria ocorrer.
  AVISO    : conclusao < 100% sem presos (timeouts / nao iniciados): pode ser congestao
             real da topologia, mas deve ser conferido.
COMPLETION_STRICT=1 => summary() devolve 3 quando ha VIOLACAO (os scripts saem com 3).
"""
import csv
import os
import sys
import threading

_lock = threading.Lock()
_events = []
_checked = 0
_enabled = True
MAX_PRINT = 8


def disable():
    global _enabled
    _enabled = False


def _i(x):
    try:
        return int(round(float(x)))
    except (TypeError, ValueError):
        return 0


def record(context, seed, res):
    """res = dict de ga_common.parse_results."""
    global _checked
    if not _enabled:
        return
    comp = res.get("completion")
    with _lock:
        _checked += 1
    if comp is None or comp >= 100.0:
        return
    ev = {"context": context, "seed": seed, "completion": comp,
          "presos_transmissao": _i(res.get("stuck_tx")),
          "presos_roteamento": _i(res.get("stuck_route")),
          "timeouts": _i(res.get("timeouts")),
          "nao_iniciados": _i(res.get("not_started"))}
    ev["severity"] = "VIOLACAO" if ev["presos_transmissao"] > 0 else "AVISO"
    with _lock:
        _events.append(ev)
        n = len(_events)
    if n <= MAX_PRINT:
        print(f"[ALARME CONCLUSAO][{ev['severity']}] {context} seed={seed} conclusao={comp:.1f}% "
              f"presos_transmissao={ev['presos_transmissao']} timeouts={ev['timeouts']} "
              f"presos_roteamento={ev['presos_roteamento']} nao_iniciados={ev['nao_iniciados']}",
              file=sys.stderr, flush=True)
    elif n == MAX_PRINT + 1:
        print("[ALARME CONCLUSAO] (demais ocorrencias so no resumo final)", file=sys.stderr, flush=True)


def check_table(rows, label="conclusao"):
    """rows: dicts com candidate, pattern, completion (ex.: tabela da avaliacao final)."""
    if not _enabled:
        return
    bad = [r for r in rows if r.get("completion") is not None and r["completion"] < 100.0]
    if bad:
        print(f"\\n[ALARME CONCLUSAO] {len(bad)} combinacao(oes) candidata x padrao com {label} < 100%:")
        for r in bad:
            print(f"   {r['candidate']:<34} {r['pattern']:<14} {r['completion']:.1f}%")
    else:
        print("\\n[ALARME CONCLUSAO] OK: todas as candidatas x padroes com 100% de conclusao (media das seeds).")


def summary(prefix=None, title=""):
    """Imprime o resumo e grava <prefix>_completion_alarm.csv. Devolve 0 ou 3 (modo estrito)."""
    if not _enabled:
        return 0
    with _lock:
        evs = list(_events)
        n_checked = _checked
    head = f"== ALARME DE CONCLUSAO {title} =="
    if not evs:
        if n_checked == 0:
            print(f"\\n{head}\\nNenhuma simulacao nova (tudo veio do cache): confira a tabela de conclusao acima.")
        else:
            print(f"\\n{head}\\nOK: {n_checked} simulacao(oes) novas, todas com 100% de conclusao.")
        return 0
    viol = [e for e in evs if e["severity"] == "VIOLACAO"]
    print(f"\\n{head}\\n{len(evs)} de {n_checked} simulacao(oes) com conclusao < 100% "
          f"({len(viol)} VIOLACAO, {len(evs) - len(viol)} AVISO).")
    if viol:
        print("VIOLACAO = fluxo preso em transmissao: o simulador violou um invariante "
              "(reserve_dst_port/reserve_src_port ligados? binario recompilado?). "
              "Nao use estes resultados antes de investigar (ga_diag.py + trace_flow_ids).")
    show = sorted(evs, key=lambda e: (e["severity"] != "VIOLACAO", e["completion"]))[:15]
    for e in show:
        print(f"  [{e['severity']}] {e['context']} seed={e['seed']} conclusao={e['completion']:.1f}% "
              f"presos_tx={e['presos_transmissao']} timeouts={e['timeouts']}")
    if len(evs) > len(show):
        print(f"  ... (+{len(evs) - len(show)}; lista completa no CSV)")
    if prefix:
        path = prefix + "_completion_alarm.csv"
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(evs[0]))
            w.writeheader()
            w.writerows(evs)
        print(f"Lista completa: {path}")
    if viol and os.environ.get("COMPLETION_STRICT") == "1":
        return 3
    return 0
'''

# (arquivo, ancora, texto_antes, texto_depois)   -- insercao; ou modo "replace"
INS = [
    # ---- ga_common.py
    ("ga_common.py", "import threading", "", "\nimport completion_alarm as _ca  # alarme de conclusao (<100%)"),
    ("ga_common.py", '"penalty": num("Penalidade por fluxo (ciclos)"),', "",
     '\n        "stuck_tx": num("Presos em transmissao (rota alocada mas sem confirmacao)"),'
     '\n        "stuck_route": num("Presos em roteamento (aguardando alocacao de rota)"),'
     '\n        "timeouts": num("Descartados por timeout de roteamento"),'
     '\n        "not_started": num("Nao iniciados (fora da janela de simulacao)"),'),
    ("ga_common.py", "class Evaluator:",
     'def _file_md5(path):\n'
     '    """Hash do binario: entra na chave do cache (rebuild => cache antigo ignorado)."""\n'
     '    try:\n'
     '        h = hashlib.md5()\n'
     '        with open(path, "rb") as f:\n'
     '            for chunk in iter(lambda: f.read(1 << 20), b""):\n'
     '                h.update(chunk)\n'
     '        return h.hexdigest()[:12]\n'
     '    except OSError:\n'
     '        return ""\n\n\n', ""),
    ("ga_common.py", "        self.cmd = parts", "",
     '\n        self.bin_id = "".join(_file_md5(x) for x in parts if os.path.isfile(x))'),
    ("ga_common.py", 'template.get("network_params", {}), objective],', "", ""),  # tratado abaixo (replace)
    ("ga_common.py", "    def run_one(self, edges, seed):",
     '    def _alarm_ctx(self, edges):\n'
     '        return f"{self.traffic} cus={self.cus} topo={edges_hash(canon(edges))[:8]}"\n\n', ""),
    ("ga_common.py", 'if res["pen"] is None:', "_ca.record(self._alarm_ctx(edges), seed, res)\n                ", ""),
    # ---- ga_optimize.py
    ("ga_optimize.py", "    print(json.dumps(summary, indent=2))", "",
     '\n    _ca_code = gc._ca.summary(os.path.join(out_dir, "completion"), "(treino)")\n'
     '    if _ca_code:\n        sys.exit(_ca_code)'),
    # ---- ga_final_eval.py
    ("ga_final_eval.py", 'print("\\nObs.: confira a conclusao% -- se diferir entre candidatas, compare a media penalizada,"', "",
     ""),  # placeholder (substituido abaixo por ancora mais simples)
]
INS = [e for e in INS if not (e[0] == "ga_final_eval.py")]
INS += [
    ("ga_final_eval.py", '    print(f"\\n== Media dos padroes (delta% vs \'{a.ref}\'; negativo = melhor que a referencia) ==")',
     '    gc._ca.check_table(rows)\n', ""),
    ("ga_final_eval.py", '        print("(sem grafico:", exc, ")")', "",
     '\n    _ca_code = gc._ca.summary(a.out, "(avaliacao final)")\n    if _ca_code:\n        raise SystemExit(_ca_code)'),
    # ---- ga_retries.py
    ("ga_retries.py", 'allf[k] += flows; comp[k].append(res["completion"] or 0); pen[k].append(res["pen"] or 0)',
     'gc._ca.record(f"{a.traffic} cus={a.cus} topo={k}", s, res)\n        ', ""),
    ("ga_retries.py", '    print(f"\\nSalvo em {out_csv}")', "",
     '\n    _ca_code = gc._ca.summary(out_csv[:-4], "(retries)")\n    if _ca_code:\n        raise SystemExit(_ca_code)'),
    # ---- ga_diag.py
    ("ga_diag.py", "            show(dst_file, label, a, alg, seed)", "",
     '\n            gc._ca.record(f"{label} {a.traffic}", seed, gc.parse_results(dst_file))'),
    ("ga_diag.py", "    main()", "", "\n    _ca_code = gc._ca.summary(None, \"(diag)\")\n    if _ca_code:\n        raise SystemExit(_ca_code)"),
    # ---- ga_pilot.py (explora regimes saturados de proposito)
    ("ga_pilot.py", "import ga_common as gc", "", "\ngc._ca.disable()  # o piloto explora de proposito regimes com conclusao < 100%"),
]

REPL = [
    ("ga_common.py", 'template.get("network_params", {}), objective],',
     'template.get("network_params", {}), objective, self.bin_id],'),
    ("main.cpp", 'value("reserve_dst_port", false)', 'value("reserve_dst_port", true)'),
    ("main.cpp", 'value("reserve_src_port", false)', 'value("reserve_src_port", true)'),
]
# a insercao vazia de ga_common (placeholder) e o replace compartilham a ancora: remove o placeholder
INS = [e for e in INS if not (e[0] == "ga_common.py" and e[1] == 'template.get("network_params", {}), objective],')]


def find_file(src, name):
    hits = []
    for root, _, files in os.walk(src):
        if any(p in root for p in ("/.git", "/runs", "/__pycache__")):
            continue
        if name in files:
            hits.append(os.path.join(root, name))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=".")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    names = sorted({e[0] for e in INS} | {e[0] for e in REPL})
    paths, texts, crlf = {}, {}, {}
    for n in names:
        hits = find_file(a.src, n)
        if len(hits) != 1:
            sys.exit(f"ERRO: esperava 1 arquivo '{n}' sob {a.src}, achei {len(hits)}: {hits}")
        raw = open(hits[0], "rb").read().decode("utf-8")
        paths[n], crlf[n] = hits[0], "\r\n" in raw
        texts[n] = raw.replace("\r\n", "\n")
        if "_ca." in texts[n] or "completion_alarm" in texts[n]:
            sys.exit(f"{n} ja contem o patch do alarme. Nada feito.")
    errors = []
    for n, anchor, before, after in INS:
        c = texts[n].count(anchor)
        if c != 1:
            errors.append(f"  {n}: ancora aparece {c}x (esperado 1): {anchor!r}")
            continue
        texts[n] = texts[n].replace(anchor, before + anchor + after, 1)
    for n, anchor, new in REPL:
        c = texts[n].count(anchor)
        if c != 1:
            errors.append(f"  {n}: ancora aparece {c}x (esperado 1): {anchor!r}")
            continue
        texts[n] = texts[n].replace(anchor, new, 1)
    if errors:
        sys.exit("ERRO: ancoras nao encontradas (nada foi escrito):\n" + "\n".join(errors) +
                 "\nMande os arquivos citados para eu ajustar o patch.")
    if a.check:
        print("OK: todas as ancoras foram encontradas 1x. Nada escrito (--check).")
        return
    for n in names:
        p = paths[n]
        if not os.path.exists(p + ".bak"):
            open(p + ".bak", "wb").write(open(p, "rb").read())
        out = texts[n].replace("\n", "\r\n") if crlf[n] else texts[n]
        open(p, "wb").write(out.encode("utf-8"))
        print("patch aplicado:", p)
    alarm_path = os.path.join(os.path.dirname(paths["ga_common.py"]), "completion_alarm.py")
    open(alarm_path, "w", newline="\n").write(ALARM_MODULE)
    print("criado:", alarm_path)
    print("\nFeito. Recompile o simulador (make clean && make main.exe) para os novos padroes das reservas.")


if __name__ == "__main__":
    main()