#!/usr/bin/env python3
"""
fase1_reavaliacao.py -- reavalia as topologias JA TREINADAS (best_edges.json de runs_fase1*) em outro cenario,
sem retreinar: outro numero de CUs, outro algoritmo de controle (bfs|dij), outra utilizacao rho, alcance do fio.
Serve a varredura de CUs {1,2,4,8,16} e as sensibilidades (Dijkstra, alcance) da Fase 1.

Regime (protocolo D15): spacing = S/(c*rho); janela = 200*spacing + 6*S, com S = custo medido da mesh 8x8 no
Minor (BFS 53,3 us; Dijkstra 109,6 us; r = 1). Coeficientes do Minor (calibracao 0.7).
Por celula: mesh, small-world (se --sw) e as execucoes GA/RS (todas as 10+10 ou so a melhor por treino com
--best-only). Delta% pareado por seed (1000..1009) contra a mesh, IC95%, Holm dentro da celula; |delta|<1% = nulo.
IMPORTANTE: com carga fixada por rho, as latencias absolutas NAO sao comparaveis entre numeros de CUs;
compare so o delta contra a mesh de cada cenario.

Saidas em <out>/ : reaval_<tag>.csv (por topologia), reaval_<tag>_celulas.csv, reaval_<tag>.md.
Uso:
  python3 fase1_reavaliacao.py --runs runs_fase1 --bin ./main.exe --cus 4 --ctrl bfs --workers 12 --sw <small-world.json>
  python3 fase1_reavaliacao.py --runs runs_fase1 --cus 16 --ctrl dij ...
  python3 fase1_reavaliacao.py --runs runs_fase1 --cus 16 --ctrl bfs --np link_reach_tiles_per_cycle=2 --tag reach2 ...
"""
import argparse, csv, glob, json, os, re, statistics as st, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy import stats as sps
import ga_common as gc

COMMON = {"reserve_dst_port": True, "reserve_src_port": True, "dijkstra_early_exit": False}
COEF = {
    "bfs": {"routing_algorithm": "bfs", "dijkstra_dispatch_cycles": 129, "dijkstra_init_cycles_per_node": 1,
            "dijkstra_pq_op_cycles": 39, "dijkstra_edge_check_cycles": 1, "control_clock_ratio": 1.0},
    "dij": {"routing_algorithm": "dijkstra", "dijkstra_dispatch_cycles": 227, "dijkstra_init_cycles_per_node": 5,
            "dijkstra_pq_base_cycles": 45, "dijkstra_pq_op_cycles": 11, "dijkstra_edge_check_cycles": 1,
            "control_clock_ratio": 1.0}}
S_NS = {"bfs": 53300.0, "dij": 109600.0}


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i]); m = len(ps); adj = [0] * m; run = 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * ps[i])); adj[i] = run
    return adj


def dstat(per, mesh):
    d = (np.array(per) / np.array(mesh) - 1) * 100
    if len(d) > 1 and d.std() > 0:
        t = sps.ttest_1samp(d, 0.0); ci = sps.t.interval(0.95, len(d) - 1, loc=d.mean(), scale=sps.sem(d)); return float(d.mean()), float(ci[0]), float(ci[1]), float(t.pvalue)
    return float(d.mean()), float(d.mean()), float(d.mean()), 1.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default="runs_fase1"); ap.add_argument("--out", default=None)
    ap.add_argument("--bin", default="./main.exe")
    ap.add_argument("--template", default=os.path.join("configs", "configs_ciclos", "config_mesh_64.json"))
    ap.add_argument("--sw", default=None)
    ap.add_argument("--cus", type=int, required=True)
    ap.add_argument("--ctrl", default="bfs", choices=["bfs", "dij"])
    ap.add_argument("--rho", type=float, default=0.5)
    ap.add_argument("--np", action="append", default=[], help="chave=valor extra (ex.: link_reach_tiles_per_cycle=2)")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--seeds", type=int, nargs="+", default=list(range(1000, 1010)))
    ap.add_argument("--best-only", action="store_true", help="so o melhor GA e a melhor RS (por treino) de cada celula")
    ap.add_argument("--workers", type=int, default=8); ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--cells", nargs="*", default=None)
    a = ap.parse_args()
    tag = a.tag or f"cu{a.cus}_{a.ctrl}_rho{a.rho}"
    out = a.out or os.path.join(a.runs, "_reavaliacao"); os.makedirs(out, exist_ok=True)
    S = S_NS[a.ctrl]; spacing = int(round(S / (a.cus * a.rho))); dur_us = (200 * spacing + 6 * S) / 1000.0
    print(f"[cenario {tag}] spacing {spacing} ns, janela {dur_us:.0f} us", flush=True)
    template = gc.load_template(a.template)
    np_over = dict(COMMON); np_over.update(COEF[a.ctrl]); np_over.update(gc.parse_kv(a.np))
    mesh_e = gc.mesh_edges(8)
    sw_e = gc.canon(gc.edges_from_config(a.sw)) if a.sw and os.path.exists(a.sw) else None
    cells = {}
    for d in glob.glob(os.path.join(a.runs, "*_s[0-9]*")):
        m = re.match(r"(.*)_(ga|rs)_s(\d+)$", os.path.basename(d))
        if m and os.path.exists(os.path.join(d, "best_edges.json")):
            cells.setdefault(m.group(1), []).append((m.group(2), d))
    if a.cells:
        cells = {k: v for k, v in cells.items() if any(s in k for s in a.cells)}
    rows_t, rows_c = [], []
    for cell, runs in sorted(cells.items()):
        t0 = time.time(); pat = re.match(r"(bit_reversal|butterfly|uniform)", cell).group(1)
        ev = gc.Evaluator(a.bin, template, pat, a.seeds, cus=a.cus, duration_us=dur_us, num_packets=None,
                          injection={"mode": "burst", "burst_max": 4, "spacing_ns": spacing},
                          np_overrides=np_over, timeout=a.timeout, quiet=True,
                          cache_path=os.path.join(out, f"cache_{tag}_{pat}.jsonl"), objective="total")
        items = []
        for g, d in sorted(runs):
            s = json.load(open(os.path.join(d, "summary.json")))
            items.append((os.path.basename(d), g, gc.canon(tuple(x) for x in json.load(open(os.path.join(d, "best_edges.json")))), s["best_fitness"]))
        if a.best_only:
            items = [min((i for i in items if i[1] == g), key=lambda i: i[3]) for g in ("ga", "rs")]
        if sw_e:
            items.append(("small_world", "sw", sw_e, None))
        mrec = ev.evaluate(mesh_e)
        if mrec["n_fail"] or mrec["completion"] < 99.95:
            print(f"[ALERTA] mesh em {cell}: conclusao {mrec['completion']:.1f}% / falhas {mrec['n_fail']} -- cenario saturado? celula ignorada", flush=True)
            continue
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            recs = list(ex.map(lambda it: ev.evaluate(it[2]), items))
        stt = [dstat(r["per_seed"], mrec["per_seed"]) for r in recs]; ph = holm([s[3] for s in stt])
        for it, r, s, p in zip(items, recs, stt, ph):
            ok = r["completion"] >= 99.95
            ver = "satura" if not ok else ("equiv/n.s." if (abs(s[0]) < 1 or p >= .05) else ("melhor" if s[0] < 0 else "pior"))
            rows_t.append({"cenario": tag, "celula": cell, "topologia": it[0], "grupo": it[1], "lat": round(r["fitness"], 1),
                           "completion": round(r["completion"], 2), "delta_pct": round(s[0], 2), "ic_lo": round(s[1], 2),
                           "ic_hi": round(s[2], 2), "p_holm": p, "veredito": ver})
        g = {k: [(s[0], v) for it, s, v in zip(items, stt, [r["completion"] >= 99.95 for r in recs]) if it[1] == k] for k in ("ga", "rs", "sw")}
        def med(k): return round(st.median(x[0] for x in g[k]), 2) if g[k] else ""
        def nb(k): return f"{sum(1 for it, s, p in zip(items, stt, ph) if it[1] == k and s[0] < -1 and p < .05)}/{len(g[k])}" if g[k] else ""
        rows_c.append({"cenario": tag, "celula": cell, "mesh_lat": round(mrec["fitness"], 1), "ga_delta_mediano": med("ga"), "ga_melhores": nb("ga"),
                       "rs_delta_mediano": med("rs"), "rs_melhores": nb("rs"), "sw_delta": med("sw"),
                       "ga_pior_que_mesh": f"{sum(1 for it, s, p in zip(items, stt, ph) if it[1]=='ga' and s[0] > 1 and p < .05)}/{len(g['ga'])}" if g["ga"] else "",
                       "tempo_s": round(time.time() - t0)})
        r = rows_c[-1]
        print(f"[{cell}] GA {r['ga_delta_mediano']}% ({r['ga_melhores']} melhores, {r['ga_pior_que_mesh']} piores) | RS {r['rs_delta_mediano']}% | sw {r['sw_delta']}%", flush=True)
    if not rows_c:
        sys.exit("nenhuma celula avaliada")
    def wr(name, rows):
        with open(os.path.join(out, name), "w", newline="") as f:
            w = csv.DictWriter(f, list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    wr(f"reaval_{tag}.csv", rows_t); wr(f"reaval_{tag}_celulas.csv", rows_c)
    cols = list(rows_c[0].keys())
    with open(os.path.join(out, f"reaval_{tag}.md"), "w") as f:
        f.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
        for r in rows_c:
            f.write("| " + " | ".join(str(r[c]) for c in cols) + " |\n")
    print("resumo em", os.path.join(out, f"reaval_{tag}.md"))


if __name__ == "__main__":
    main()