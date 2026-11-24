#!/usr/bin/env python3
"""
fase1_avaliacao_final.py -- Fase 1A: avaliacao final e estatistica das execucoes do GA e da busca aleatoria.

Para cada celula (<padrao>_m<teto>), usa os best_edges.json das 10 execucoes GA e das 10 RS
(rodar_fase1a.sh), a mesh e o small-world manual:
  1. AVALIACAO: re-simula todas em seeds novas (--eval-seeds, 1000..1009). Delta% por seed contra a
     mesh (pareado), IC95% (t), p (t pareado), Holm dentro da celula; |delta| < 1% = nulo.
  2. GA x RS: unidade = execucao (media das seeds de avaliacao de cada execucao); Mann-Whitney.
  3. CONFIRMACAO (--confirm-seeds, 3000..3029): o melhor GA e a melhor RS escolhidos pela fitness de
     TREINO (nao pela avaliacao, para nao haver vies de selecao), mais small-world e mesh; delta pareado,
     IC95%, Holm, e GA x RS pareado por seed.
Saidas em <runs>/_avaliacao_fase1/: avaliacao_topologias.csv, avaliacao_celulas.csv, confirmacao.csv,
resumo_fase1.md. Tem cache (pode interromper e repetir).

Uso (Linux, na pasta do simulador):
  python3 fase1_avaliacao_final.py --runs runs_fase1 --bin ./main.exe --workers 12 \
     --mesh configs/configs_ciclos/config_mesh_64.json --sw configs/configs_ciclos/config_irregular_smallworld_64.json
"""
import argparse, csv, glob, json, os, re, statistics as st, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy import stats as sps
import ga_common as gc

NP = {"routing_algorithm": "bfs", "dijkstra_dispatch_cycles": 129, "dijkstra_init_cycles_per_node": 1,
      "dijkstra_pq_op_cycles": 39, "dijkstra_edge_check_cycles": 1, "control_clock_ratio": 1.0,
      "reserve_dst_port": True, "reserve_src_port": True, "dijkstra_early_exit": False}
NULL = 1.0


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i]); m = len(ps); adj = [0] * m; run = 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * ps[i])); adj[i] = run
    return adj


def delta_stats(per, mesh):
    d = (np.array(per) / np.array(mesh) - 1) * 100
    if len(d) > 1 and d.std() > 0:
        t = sps.ttest_1samp(d, 0.0); ci = sps.t.interval(0.95, len(d) - 1, loc=d.mean(), scale=sps.sem(d)); p = float(t.pvalue)
    else:
        ci, p = (d.mean(), d.mean()), 1.0
    return float(d.mean()), float(ci[0]), float(ci[1]), p


def verdict(d, p_h):
    if abs(d) < NULL or p_h >= 0.05:
        return "equivalente/n.s."
    return "melhor" if d < 0 else "pior"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default="runs_fase1"); ap.add_argument("--out", default=None)
    ap.add_argument("--bin", default="./main.exe")
    ap.add_argument("--template", default=os.path.join("configs", "configs_ciclos", "config_mesh_64.json"))
    ap.add_argument("--mesh", default=None, help="config da mesh (padrao: --template)")
    ap.add_argument("--sw", default=None, help="config do small-world manual (opcional)")
    ap.add_argument("--cus", type=int, default=16)
    ap.add_argument("--spacing-ns", type=int, default=6700); ap.add_argument("--duration-us", type=float, default=1700)
    ap.add_argument("--eval-seeds", type=int, nargs="+", default=list(range(1000, 1010)))
    ap.add_argument("--confirm-seeds", type=int, nargs="+", default=list(range(3000, 3030)))
    ap.add_argument("--workers", type=int, default=8); ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--cells", nargs="*", default=None)
    a = ap.parse_args()
    out = a.out or os.path.join(a.runs, "_avaliacao_fase1"); os.makedirs(out, exist_ok=True)
    template = gc.load_template(a.template)
    mesh_e = gc.mesh_edges(8)
    sw_e = gc.canon(gc.edges_from_config(a.sw)) if a.sw and os.path.exists(a.sw) else None

    cells = {}
    for d in glob.glob(os.path.join(a.runs, "*_s[0-9]*")):
        m = re.match(r"(.*)_(ga|rs)_s(\d+)$", os.path.basename(d))
        if not m or not os.path.exists(os.path.join(d, "summary.json")):
            continue
        cells.setdefault(m.group(1), {"ga": [], "rs": []})[m.group(2)].append(d)
    if a.cells:
        cells = {k: v for k, v in cells.items() if any(s in k for s in a.cells)}
    if not cells:
        sys.exit("nenhuma celula encontrada em " + a.runs)

    rows_top, rows_cell, rows_conf, md = [], [], [], []
    for cell, v in sorted(cells.items()):
        t0 = time.time()
        pat = re.match(r"(bit_reversal|butterfly|uniform)", cell).group(1)

        def make(seeds, tag):
            return gc.Evaluator(a.bin, template, pat, seeds, cus=a.cus, duration_us=a.duration_us, num_packets=None,
                                injection={"mode": "burst", "burst_max": 4, "spacing_ns": a.spacing_ns},
                                np_overrides=dict(NP), timeout=a.timeout, quiet=True,
                                cache_path=os.path.join(out, f"cache_{cell}_{tag}.jsonl"), objective="total")
        ev_e, ev_c = make(a.eval_seeds, "ev"), make(a.confirm_seeds, "cf")
        items = []  # (label, grupo, dir, edges, treino)
        for g in ("ga", "rs"):
            for d in sorted(v[g]):
                s = json.load(open(os.path.join(d, "summary.json")))
                e = gc.canon(tuple(x) for x in json.load(open(os.path.join(d, "best_edges.json"))))
                items.append((os.path.basename(d), g, d, e, s["best_fitness"], s["best_wire"]))
        if sw_e:
            items.append(("small_world", "sw", None, sw_e, None, gc.wire_total(sw_e, 64)))

        mesh_rec = ev_e.evaluate(mesh_e)
        if mesh_rec["n_fail"] or mesh_rec["fitness"] >= gc.FAIL_PENALTY:
            sys.exit(f"[ERRO] mesh falhou em {cell}")
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            recs = list(ex.map(lambda it: ev_e.evaluate(it[3]), items))
        ms = mesh_rec["per_seed"]
        stats_ = [delta_stats(r["per_seed"], ms) for r in recs]
        ph = holm([s[3] for s in stats_])
        for it, r, s, p_h in zip(items, recs, stats_, ph):
            rows_top.append({"celula": cell, "topologia": it[0], "grupo": it[1], "fio": it[5],
                             "fitness_treino": it[4], "lat_media": round(r["fitness"], 1),
                             "completion": round(r["completion"], 2), "delta_pct": round(s[0], 2),
                             "ic_lo": round(s[1], 2), "ic_hi": round(s[2], 2), "p": s[3], "p_holm": p_h,
                             "veredito": verdict(s[0], p_h)})
        # GA x RS por execucao
        ga_m = [np.mean(r["per_seed"]) for it, r in zip(items, recs) if it[1] == "ga"]
        rs_m = [np.mean(r["per_seed"]) for it, r in zip(items, recs) if it[1] == "rs"]
        mw = sps.mannwhitneyu(ga_m, rs_m, alternative="less").pvalue
        nb = sum(1 for it, s, p_h in zip(items, stats_, ph) if it[1] == "ga" and s[0] < -NULL and p_h < 0.05)
        nbr = sum(1 for it, s, p_h in zip(items, stats_, ph) if it[1] == "rs" and s[0] < -NULL and p_h < 0.05)
        gd = [s[0] for it, s in zip(items, stats_) if it[1] == "ga"]; rd = [s[0] for it, s in zip(items, stats_) if it[1] == "rs"]
        swd = next((s[0] for it, s in zip(items, stats_) if it[1] == "sw"), None)
        # confirmacao
        best = {g: min((it for it in items if it[1] == g), key=lambda it: it[4]) for g in ("ga", "rs")}
        conf_items = [best["ga"], best["rs"]] + ([it for it in items if it[1] == "sw"] if sw_e else [])
        mesh_c = ev_c.evaluate(mesh_e)
        crecs = [ev_c.evaluate(it[3]) for it in conf_items]
        cst = [delta_stats(r["per_seed"], mesh_c["per_seed"]) for r in crecs]
        cph = holm([s[3] for s in cst])
        for it, r, s, p_h in zip(conf_items, crecs, cst, cph):
            rows_conf.append({"celula": cell, "topologia": it[0], "grupo": it[1], "lat_media": round(r["fitness"], 1),
                              "mesh_lat": round(mesh_c["fitness"], 1), "completion": round(r["completion"], 2),
                              "delta_pct": round(s[0], 2), "ic_lo": round(s[1], 2), "ic_hi": round(s[2], 2),
                              "p_holm": p_h, "veredito": verdict(s[0], p_h)})
        # melhor GA x melhor RS, pareado
        dgr = (np.array(crecs[0]["per_seed"]) / np.array(crecs[1]["per_seed"]) - 1) * 100
        tg = sps.ttest_1samp(dgr, 0.0)
        rows_cell.append({"celula": cell, "mesh_lat_eval": round(mesh_rec["fitness"], 1),
                          "ga_delta_mediano_pct": round(st.median(gd), 2), "rs_delta_mediano_pct": round(st.median(rd), 2),
                          "ga_n_melhor_que_mesh": f"{nb}/{len(gd)}", "rs_n_melhor_que_mesh": f"{nbr}/{len(rd)}",
                          "mw_ga_menor_que_rs_p": mw, "sw_delta_pct": round(swd, 2) if swd is not None else "",
                          "conf_ga_delta_pct": round(cst[0][0], 2), "conf_ga_ic": f"[{cst[0][1]:.1f}; {cst[0][2]:.1f}]",
                          "conf_rs_delta_pct": round(cst[1][0], 2), "conf_ga_vs_rs_pct": round(float(dgr.mean()), 2),
                          "conf_ga_vs_rs_p": float(tg.pvalue), "tempo_s": round(time.time() - t0)})
        print(f"[{cell}] GA mediano {st.median(gd):+.1f}% | RS {st.median(rd):+.1f}% | MW p={mw:.4f} | "
              f"GA melhores que a mesh {nb}/{len(gd)} | confirmacao GA {cst[0][0]:+.1f}% (IC {cst[0][1]:.1f}..{cst[0][2]:.1f})", flush=True)

    def wr(name, rows):
        with open(os.path.join(out, name), "w", newline="") as f:
            w = csv.DictWriter(f, list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    wr("avaliacao_topologias.csv", rows_top); wr("avaliacao_celulas.csv", rows_cell); wr("confirmacao.csv", rows_conf)
    cols = list(rows_cell[0].keys())
    with open(os.path.join(out, "resumo_fase1.md"), "w") as f:
        f.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
        for r in rows_cell:
            f.write("| " + " | ".join(f"{r[c]:.4g}" if isinstance(r[c], float) else str(r[c]) for c in cols) + " |\n")
    print("\nresumo em", os.path.join(out, "resumo_fase1.md"))


if __name__ == "__main__":
    main()