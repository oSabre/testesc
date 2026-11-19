"""
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
        print(f"\n[ALARME CONCLUSAO] {len(bad)} combinacao(oes) candidata x padrao com {label} < 100%:")
        for r in bad:
            print(f"   {r['candidate']:<34} {r['pattern']:<14} {r['completion']:.1f}%")
    else:
        print("\n[ALARME CONCLUSAO] OK: todas as candidatas x padroes com 100% de conclusao (media das seeds).")


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
            print(f"\n{head}\nNenhuma simulacao nova (tudo veio do cache): confira a tabela de conclusao acima.")
        else:
            print(f"\n{head}\nOK: {n_checked} simulacao(oes) novas, todas com 100% de conclusao.")
        return 0
    viol = [e for e in evs if e["severity"] == "VIOLACAO"]
    print(f"\n{head}\n{len(evs)} de {n_checked} simulacao(oes) com conclusao < 100% "
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
