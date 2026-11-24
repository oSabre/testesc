#!/usr/bin/env python3
"""
baselines_d9.py -- linhas de base D9 da Fase 1B (e da Fase 3A): MESH COM ENLACES REMOVIDOS (L < 112) e MESH COM
ATALHOS ALEATORIOS (L > 112), contra a mesh, para cada padrao e nivel L.

Para cada (padrao, tipo, L): sorteia --n topologias (conectadas, grau <= 4). Todas sao avaliadas nas seeds de avaliacao
(1000..1009, pareado contra a mesh de 112 enlaces): mediana/p10/melhor dos delta% e fio/area. A "melhor por treino"
(seeds 1,2,3) e reavaliada em 30 seeds (3000..3029) com IC95% -- mesmo protocolo do GA/RS, sem viés de selecao.
Para comparar com o GA/RS no mesmo L (runs_fase1b) use a confirmacao do fase1_avaliacao_final.py.
Atalhos: sorteio entre nos com grau < 4 (so as bordas tem folga: no maximo 128 enlaces), com teto de fio --wire-mult*L.

Saidas em <out>/: baselines_topologias.csv, baselines_resumo.csv/.md, baselines_confirmacao.csv, e best_edges.json
em <out>/<padrao>_<tipo>_L<L>/ (para entrar na avaliacao da Fase 3).
Uso: python3 baselines_d9.py --bin ./main.exe --levels 84 98 124 --n 100 --workers 12 --out runs_baselines
"""
import argparse, csv, json, os, random, statistics as st, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy import stats as sps
import ga_common as gc
try:
    import area_model as am
except Exception:
    am = None

NP = {"routing_algorithm": "bfs", "dijkstra_dispatch_cycles": 129, "dijkstra_init_cycles_per_node": 1,
      "dijkstra_pq_op_cycles": 39, "dijkstra_edge_check_cycles": 1, "control_clock_ratio": 1.0,
      "reserve_dst_port": True, "reserve_src_port": True, "dijkstra_early_exit": False}
N = 64


def mesh_removal(L, rng):
    gc.set_wire_cap(None)
    E = set(gc.mesh_edges(8))
    while len(E) > L:
        cand = list(E); rng.shuffle(cand)
        for e in cand:
            T = E - {e}
            if gc.is_valid(gc.canon(T), N, len(T)):
                E = T; break
        else:
            raise RuntimeError("nao ha mais enlace removivel")
    return gc.canon(E)


def mesh_shortcuts(L, rng, cap):
    E = set(gc.mesh_edges(8))
    deg = {i: 0 for i in range(N)}
    for u, v in E:
        deg[u] += 1; deg[v] += 1
    W = gc.grid_w(N)
    wire = gc.wire_total(gc.canon(E), N)
    guard = 0
    while len(E) < L:
        guard += 1
        if guard > 3000:
            raise RuntimeError("sem atalhos viaveis")
        free = [i for i in range(N) if deg[i] < 4]
        if len(free) < 2:
            raise RuntimeError("sem nos livres")
        u, v = sorted(rng.sample(free, 2))
        if (u, v) in E:
            continue
        ln = abs(u % W - v % W) + abs(u // W - v // W)
        if cap is not None and wire + ln > cap:
            continue
        E.add((u, v)); deg[u] += 1; deg[v] += 1; wire += ln
    return gc.canon(E)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bin", default="./main.exe")
    ap.add_argument("--template", default=os.path.join("configs", "configs_ciclos", "config_mesh_64.json"))
    ap.add_argument("--levels", type=int, nargs="+", default=[84, 98, 124])
    ap.add_argument("--patterns", nargs="+", default=["bit_reversal", "butterfly", "uniform"])
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--cus", type=int, default=16)
    ap.add_argument("--spacing-ns", type=int, default=6700); ap.add_argument("--duration-us", type=float, default=1700)
    ap.add_argument("--wire-mult", type=float, default=1.5, help="teto de fio dos atalhos (x L)")
    ap.add_argument("--train-seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--eval-seeds", type=int, nargs="+", default=list(range(1000, 1010)))
    ap.add_argument("--confirm-seeds", type=int, nargs="+", default=list(range(3000, 3030)))
    ap.add_argument("--flit", type=int, default=64)
    ap.add_argument("--workers", type=int, default=8); ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--rng", type=int, default=1)
    ap.add_argument("--out", default="runs_baselines")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    template = gc.load_template(a.template)
    mesh_e = gc.mesh_edges(8)
    rows_t, rows_s, rows_c = [], [], []
    for pat in a.patterns:
        def mk(seeds, tag):
            return gc.Evaluator(a.bin, template, pat, seeds, cus=a.cus, duration_us=a.duration_us, num_packets=None,
                                injection={"mode": "burst", "burst_max": 4, "spacing_ns": a.spacing_ns},
                                np_overrides=dict(NP), timeout=a.timeout, quiet=True,
                                cache_path=os.path.join(a.out, f"cache_{pat}_{tag}.jsonl"), objective="total")
        evT, evE, evC = mk(a.train_seeds, "tr"), mk(a.eval_seeds, "ev"), mk(a.confirm_seeds, "cf")
        mE, mC = evE.evaluate(mesh_e), evC.evaluate(mesh_e)
        if mE["n_fail"] or mC["n_fail"]:
            sys.exit(f"[ERRO] mesh falhou ({pat})")
        for L in a.levels:
            kind = "remocao" if L < 112 else "atalhos"
            rng = random.Random(a.rng * 1000 + L)
            tops = []
            guard = 0
            while len(tops) < a.n and guard < a.n * 20:
                guard += 1
                try:
                    e = mesh_removal(L, rng) if L < 112 else mesh_shortcuts(L, rng, int(round(a.wire_mult * L)))
                except RuntimeError:
                    continue
                if e not in tops:
                    tops.append(e)
            if len(tops) < a.n:
                print(f"[aviso] {pat} {kind} L={L}: so {len(tops)} topologias distintas viaveis de {a.n} pedidas")
            if not tops:
                continue
            t0 = time.time()
            with ThreadPoolExecutor(max_workers=a.workers) as ex:
                trn = list(ex.map(lambda e: evT.evaluate(e)["fitness"], tops))
                ev = list(ex.map(lambda e: evE.evaluate(e), tops))
            dl = []
            for e, r in zip(tops, ev):
                d = (np.array(r["per_seed"]) / np.array(mE["per_seed"]) - 1) * 100
                dl.append(float(d.mean()))
                ar = (am.total_area(e, N, a.cus, "minor", a.flit) / am.total_area(gc.mesh_edges(8), N, a.cus, "minor", a.flit) - 1) * 100 if am else ""
                rows_t.append({"padrao": pat, "tipo": kind, "L": L, "fio": gc.wire_total(e, N), "delta_pct": round(float(d.mean()), 2),
                               "completion": round(r["completion"], 2), "darea_pct": round(ar, 2) if ar != "" else ""})
            # melhor por treino -> confirmacao
            ib = int(np.argmin(trn)); eb = tops[ib]
            rc = evC.evaluate(eb); d = (np.array(rc["per_seed"]) / np.array(mC["per_seed"]) - 1) * 100
            ci = sps.t.interval(0.95, len(d) - 1, loc=d.mean(), scale=sps.sem(d)); p = float(sps.ttest_1samp(d, 0.0).pvalue)
            od = os.path.join(a.out, f"{pat}_{kind}_L{L}"); os.makedirs(od, exist_ok=True)
            json.dump([list(x) for x in eb], open(os.path.join(od, "best_edges.json"), "w"))
            rows_c.append({"padrao": pat, "tipo": kind, "L": L, "fio": gc.wire_total(eb, N), "lat": round(rc["fitness"], 1),
                           "delta_pct": round(float(d.mean()), 2), "ic_lo": round(float(ci[0]), 2), "ic_hi": round(float(ci[1]), 2), "p": p,
                           "completion": round(rc["completion"], 2)})
            ok = sum(1 for r in ev if r["completion"] >= 99.95)
            rows_s.append({"padrao": pat, "tipo": kind, "L": L, "n": len(tops), "n_conclui_100": ok,
                           "delta_mediano": round(st.median(dl), 2), "delta_p10": round(float(np.percentile(dl, 10)), 2),
                           "delta_melhor": round(min(dl), 2), "fio_medio": round(st.mean(gc.wire_total(e, N) for e in tops), 1),
                           "darea_pct": round((am.total_area(tops[0], N, a.cus, "minor", a.flit) / am.total_area(gc.mesh_edges(8), N, a.cus, "minor", a.flit) - 1) * 100, 2) if am else "",
                           "conf_melhor_treino_pct": round(float(d.mean()), 2), "tempo_s": round(time.time() - t0)})
            r = rows_s[-1]
            print(f"[{pat} {kind} L={L}] n={r['n']} mediana {r['delta_mediano']:+.1f}% p10 {r['delta_p10']:+.1f}% melhor {r['delta_melhor']:+.1f}% | melhor-por-treino em 30 seeds {r['conf_melhor_treino_pct']:+.1f}%", flush=True)
    def wr(name, rows):
        with open(os.path.join(a.out, name), "w", newline="") as f:
            w = csv.DictWriter(f, list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    wr("baselines_topologias.csv", rows_t); wr("baselines_resumo.csv", rows_s); wr("baselines_confirmacao.csv", rows_c)
    cols = list(rows_s[0].keys())
    with open(os.path.join(a.out, "baselines_resumo.md"), "w") as f:
        f.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
        for r in rows_s:
            f.write("| " + " | ".join(str(r[c]) for c in cols) + " |\n")
    print("resumo em", os.path.join(a.out, "baselines_resumo.md"))


if __name__ == "__main__":
    main()