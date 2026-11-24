#!/usr/bin/env python3
"""
analyze_pareto.py -- Fase 3: analise das frentes de Pareto do NSGA-II (rodar_fase3a.py).

Por celula (= mesmo nome sem o sufixo _nsga_sN: padrao x cfg x core x CUs):
  1. Frente combinada: une os pontos de Pareto das N sementes e refiltra (nao dominados em treino).
  2. Avaliacao final PAREADA: cada ponto e a mesh sao re-simulados em seeds novas (--eval-seeds,
     padrao 1000..1009). Delta de latencia por seed vs mesh; IC95% (t) e p (t pareado), Holm
     dentro da celula. |delta| < 1% = equivalente (limiar nulo). Area e deterministica.
  3. Frente validada: nao dominados pela latencia media de avaliacao. Hipervolume normalizado
     pela mesh (ref 1.25, 1.5).
  4. Confirmacao: ate --max-confirm pontos da frente validada (espalhados em area) + mesh sao
     re-simulados em outras seeds (--confirm-seeds, padrao 3000..3029) com a mesma estatistica.
  5. Pontos de interesse: iso-area (menor latencia com area <= mesh), iso-latencia (menor area com
     latencia equivalente ou melhor) e joelho (mais perto do ideal normalizado).
Tambem agrega o HV de treino por semente (media, desvio, IC) como medida de reprodutibilidade.

Saidas em <out>/ (padrao <runs>/_analise): <celula>_validada.csv, <celula>_confirmacao.csv,
resumo_fase3.csv, resumo_fase3.md, e <celula>_pareto.png (se matplotlib existir).
Usa cache (analise_cache_*.jsonl) -> pode interromper e repetir.

Uso (Windows):
  py analyze_pareto.py --runs runs_fase3 --bin main.exe --spacing-ns 6700 --duration-us 1700 --workers 8
"""
import argparse, csv, glob, json, os, re, statistics as st, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy import stats as sps
from pymoo.indicators.hv import HV

import ga_common as gc
import area_model as am
from nsga2_optimize import PRESETS, COMMON_NP

LAT_NULL = 1.0   # |delta lat| < 1% = equivalente
AREA_NULL = 1.0


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    m, adj, run = len(ps), [None] * len(ps), 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * ps[i]))
        adj[i] = run
    return adj


def nondom(items, kl="lat", ka="area"):
    out = []
    for r in items:
        if not any(q[kl] <= r[kl] and q[ka] <= r[ka] and (q[kl] < r[kl] or q[ka] < r[ka]) for q in items):
            out.append(r)
    out.sort(key=lambda r: (r[ka], r[kl]))
    res, seen = [], set()
    for r in out:
        k = (round(r[kl], 6), round(r[ka], 9))
        if k not in seen:
            seen.add(k)
            res.append(r)
    return res


def state(delta, null):
    return "equiv" if abs(delta) < null else ("melhor" if delta < 0 else "pior")


class Ev:
    """avaliador com cache por (cus, core, seeds)"""
    def __init__(self, a, cell, out_dir):
        self.a, self.cell, self.out = a, cell, out_dir
        self.template = gc.load_template(a.template)
        self.evs = {}

    def get(self, cus, core, seeds, tag):
        k = (cus, core, tuple(seeds))
        if k not in self.evs:
            c = self.cell
            np_over = dict(COMMON_NP)
            np_over.update(PRESETS[c["ctrl"]][core])
            np_over.update(gc.parse_kv(self.a.np))
            self.evs[k] = gc.Evaluator(
                self.a.bin, self.template, c["traffic"], list(seeds), cus=cus,
                duration_us=self.a.duration_us, num_packets=self.a.num_packets,
                injection={"mode": self.a.injection_mode, "burst_max": self.a.burst_max,
                           "spacing_ns": self.a.spacing_ns},
                np_overrides=np_over, timeout=self.a.timeout,
                cache_path=os.path.join(self.out, f"analise_cache_{c['name']}_{tag}_{core}_cu{cus}.jsonl"),
                objective=self.a.objective, quiet=True)
        return self.evs[k]


def paired(ev_pts, ev_mesh_rec, workers):
    """retorna, por ponto, lista de deltas % por seed vs mesh"""
    mesh_seed = ev_mesh_rec["per_seed"]
    return mesh_seed


def evaluate_points(ev, pts, seeds, tag, mesh_edges, workers):
    cus0, core0 = pts[0]["cus"], pts[0]["core"]
    mesh_rec = ev.get(cus0, core0, seeds, tag).evaluate(mesh_edges)
    if mesh_rec["fitness"] >= gc.FAIL_PENALTY or mesh_rec["n_fail"]:
        sys.exit(f"[ERRO] mesh falhou na avaliacao ({tag}); confira main.exe e parametros.")

    def one(p):
        rec = ev.get(p["cus"], p["core"], seeds, tag).evaluate(p["edges"])
        return rec
    with ThreadPoolExecutor(max_workers=workers) as ex:
        recs = list(ex.map(one, pts))
    ms = np.array(mesh_rec["per_seed"])
    rows, ps = [], []
    for p, r in zip(pts, recs):
        row = dict(p)
        if r["n_fail"] or r["completion"] < 99.95:
            row.update(lat_eval=float("nan"), ok=False, completion_eval=r["completion"], d=None)
            rows.append(row); ps.append(1.0); continue
        per = np.array(r["per_seed"])
        d = (per / ms - 1) * 100
        t = sps.ttest_1samp(d, 0.0) if len(d) > 1 and d.std() > 0 else None
        ci = sps.t.interval(0.95, len(d) - 1, loc=d.mean(), scale=sps.sem(d)) if t is not None else (d.mean(), d.mean())
        row.update(lat_eval=float(per.mean()), ok=True, completion_eval=r["completion"], d=d,
                   dlat=float(d.mean()), ci_lo=float(ci[0]), ci_hi=float(ci[1]),
                   p=float(t.pvalue) if t is not None else 1.0)
        rows.append(row); ps.append(row["p"])
    adj = holm(ps)
    for row, pa in zip(rows, adj):
        row["p_holm"] = pa
        if row["ok"]:
            row["darea"] = (row["area"] / row["mesh_area"] - 1) * 100
            sl = state(row["dlat"], LAT_NULL) if row["p_holm"] < 0.05 or abs(row["dlat"]) < LAT_NULL else "equiv"
            sa = state(row["darea"], AREA_NULL)
            row["lat_state"], row["area_state"] = sl, sa
            row["verdict"] = ("domina" if "pior" not in (sl, sa) and "melhor" in (sl, sa)
                              else "equivalente" if (sl, sa) == ("equiv", "equiv")
                              else "pior" if "melhor" not in (sl, sa) else "troca")
    return rows, float(ms.mean())


def load_cells(runs):
    cells = {}
    for sj in glob.glob(os.path.join(runs, "*_nsga_s*", "summary.json")):
        d = os.path.dirname(sj)
        m = re.match(r"(.*)_nsga_s(\d+)$", os.path.basename(d))
        if not m:
            continue
        s = json.load(open(sj))
        c = cells.setdefault(m.group(1), {"name": m.group(1), "dirs": [], "sums": []})
        c["dirs"].append(d); c["sums"].append(s)
    for c in cells.values():
        s0 = c["sums"][0]
        c.update(traffic=s0["traffic"], ctrl=s0["ctrl"], flit=s0["flit"])
    return cells


def load_front(c):
    pts, seen = [], set()
    for d in c["dirs"]:
        for pj in glob.glob(os.path.join(d, "pareto", "pt*", "point.json")):
            p = json.load(open(pj))
            e = gc.canon(tuple(x) for x in json.load(open(os.path.join(os.path.dirname(pj), "best_edges.json"))))
            k = (gc.edges_hash(e), p["cus"], p["core"])
            if k in seen:
                continue
            seen.add(k)
            p["edges"] = e
            p["lat"] = float(p["lat"]); p["area"] = float(p["area"])
            p["run"] = os.path.basename(d)
            pts.append(p)
    return nondom(pts)


def hv_norm(rows, mesh_lat, mesh_area, ref):
    P = [(r["lat_eval"] / mesh_lat, r["area"] / mesh_area) for r in rows if r["ok"]]
    return float(HV(ref_point=np.array(ref))(np.array(P))) if P else float("nan")


def spread(rows, k):
    if len(rows) <= k:
        return rows
    idx = sorted({round(i * (len(rows) - 1) / (k - 1)) for i in range(k)})
    return [rows[i] for i in idx]


def write_csv(path, rows, cols):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([("" if r.get(c) is None else (round(r[c], 4) if isinstance(r.get(c), float) else r.get(c))) for c in cols])


COLS = ["lat_eval", "dlat", "ci_lo", "ci_hi", "p_holm", "lat_state", "area", "darea", "area_state",
        "verdict", "L", "wire", "cus", "core", "completion_eval", "hash", "run"]


def plot(path, c, val, conf, mesh_lat, mesh_area, train_front):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    fig, ax = plt.subplots(figsize=(6.4, 4.6), dpi=130)
    ax.scatter([r["lat"] / mesh_lat for r in train_front], [r["area"] / mesh_area for r in train_front],
               s=14, c="#b0b0b0", label="frente combinada (treino)")
    v = [r for r in val if r["ok"]]
    ax.plot([r["lat_eval"] / mesh_lat for r in v], [r["area"] / mesh_area for r in v], "-o", ms=4, lw=1.2,
            c="#2a6fb0", label="frente validada (seeds de avaliacao)")
    cf = [r for r in conf if r["ok"]]
    ax.scatter([r["lat_eval"] / r["mesh_lat_c"] for r in cf], [r["area"] / mesh_area for r in cf], s=36,
               facecolors="none", edgecolors="#d95f02", label="confirmacao")
    ax.scatter([1], [1], marker="*", s=140, c="#111", label="mesh", zorder=5)
    ax.axvline(1, c="#ccc", lw=.8); ax.axhline(1, c="#ccc", lw=.8)
    ax.set_xlabel("latencia / mesh"); ax.set_ylabel("area total / mesh"); ax.set_title(c["name"], fontsize=9)
    ax.legend(fontsize=7); fig.tight_layout(); fig.savefig(path); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    gc.common_args(ap)
    ap.add_argument("--runs", default="runs_fase3")
    ap.add_argument("--out", default=None)
    ap.add_argument("--eval-seeds", type=int, nargs="+", default=list(range(1000, 1010)))
    ap.add_argument("--confirm-seeds", type=int, nargs="+", default=list(range(3000, 3030)))
    ap.add_argument("--max-confirm", type=int, default=15)
    ap.add_argument("--max-eval", type=int, default=60, help="maximo de pontos da frente combinada avaliados")
    ap.add_argument("--hv-ref", type=float, nargs=2, default=[1.25, 1.5])
    ap.add_argument("--cells", nargs="*", default=None, help="filtrar celulas por substring")
    a = ap.parse_args()
    a.bin = a.bin
    out = a.out or os.path.join(a.runs, "_analise")
    os.makedirs(out, exist_ok=True)
    cells = load_cells(a.runs)
    if a.cells:
        cells = {k: v for k, v in cells.items() if any(s in k for s in a.cells)}
    if not cells:
        sys.exit("nenhuma celula com summary.json em " + a.runs)
    summ = []
    for name, c in sorted(cells.items()):
        t0 = time.time()
        s0 = c["sums"][0]
        cus, core = s0["mesh_ref"]["cus"], s0["mesh_ref"]["core"]
        mesh_e = gc.mesh_edges(8)
        mesh_area = s0["mesh_ref"]["area"]
        front = load_front(c)
        for p in front:
            p["mesh_area"] = mesh_area
        # 1 treino -> limita pontos avaliados (espalha em area)
        sel = spread(front, a.max_eval)
        print(f"[{name}] {len(c['dirs'])} execucoes; frente combinada {len(front)} pts (avaliando {len(sel)})", flush=True)
        ev = Ev(a, c, out)
        val_all, mesh_lat = evaluate_points(ev, sel, a.eval_seeds, "ev", mesh_e, a.workers)
        val = nondom([r for r in val_all if r["ok"]], "lat_eval", "area")
        for r in val:
            r["mesh_lat"] = mesh_lat
        hv_val = hv_norm(val, mesh_lat, mesh_area, a.hv_ref)
        write_csv(os.path.join(out, f"{name}_validada.csv"), val, COLS)
        # confirmacao
        cs = spread(val, a.max_confirm)
        conf, mesh_lat_c = evaluate_points(ev, cs, a.confirm_seeds, "cf", mesh_e, a.workers) if cs else ([], float("nan"))
        for r in conf:
            r["mesh_lat_c"] = mesh_lat_c
        write_csv(os.path.join(out, f"{name}_confirmacao.csv"), conf, COLS)
        plot(os.path.join(out, f"{name}_pareto.png"), c, val, conf, mesh_lat, mesh_area, front)
        # treino por semente
        hvs = [s["hv_pareto_final"] for s in c["sums"] if s.get("hv_pareto_final") is not None]
        hv_mu = st.mean(hvs); hv_sd = st.stdev(hvs) if len(hvs) > 1 else 0.0
        hv_ci = (sps.t.ppf(0.975, len(hvs) - 1) * hv_sd / len(hvs) ** 0.5) if len(hvs) > 1 else float("nan")
        okc = [r for r in conf if r["ok"]]
        iso_a = min([r for r in okc if r["area"] <= mesh_area * 1.0001], key=lambda r: r["lat_eval"], default=None)
        iso_l = min([r for r in okc if r["dlat"] < LAT_NULL], key=lambda r: r["area"], default=None)
        knee = min(okc, key=lambda r: ((r["lat_eval"] / mesh_lat_c) - 0) ** 2 + (r["area"] / mesh_area) ** 2, default=None)
        n_dom = sum(1 for r in okc if r["verdict"] == "domina")
        row = {"celula": name, "n_exec": len(c["dirs"]), "n_front_comb": len(front), "n_val": len(val),
               "n_conf": len(okc), "n_conf_domina_mesh": n_dom,
               "hv_treino_media": round(hv_mu, 4), "hv_treino_dp": round(hv_sd, 4),
               "hv_treino_ic95": round(hv_ci, 4) if hv_ci == hv_ci else "",
               "hv_validada": round(hv_val, 4),
               "isoarea_dlat_pct": round(iso_a["dlat"], 2) if iso_a else "",
               "isoarea_darea_pct": round(iso_a["darea"], 2) if iso_a else "",
               "isolat_darea_pct": round(iso_l["darea"], 2) if iso_l else "",
               "isolat_dlat_pct": round(iso_l["dlat"], 2) if iso_l else "",
               "joelho_dlat_pct": round(knee["dlat"], 2) if knee else "",
               "joelho_darea_pct": round(knee["darea"], 2) if knee else "",
               "joelho_L": knee["L"] if knee else "", "joelho_verdict": knee["verdict"] if knee else "",
               "tempo_s": round(time.time() - t0)}
        summ.append(row)
        print(f"   HV treino {hv_mu:.3f}±{hv_sd:.3f}; HV validada {hv_val:.3f}; confirmados {len(okc)}, "
              f"dominam a mesh: {n_dom}", flush=True)
    cols = list(summ[0].keys())
    with open(os.path.join(out, "resumo_fase3.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, cols); w.writeheader(); w.writerows(summ)
    with open(os.path.join(out, "resumo_fase3.md"), "w") as f:
        f.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
        for r in summ:
            f.write("| " + " | ".join(str(r[c]) for c in cols) + " |\n")
    print(f"\nresumo em {os.path.join(out, 'resumo_fase3.md')}")


if __name__ == "__main__":
    main()