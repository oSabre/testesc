#!/usr/bin/env python3
"""
nsga2_optimize.py -- Fase 3: NSGA-II (pymoo) latencia x area para topologias 8x8 (64 nos).

Objetivos (minimizar):  F1 = latencia media penalizada (ciclos, seeds de treino)
                        F2 = A_total = n_CU * A_core + A_NoC  (mm2 a 28 nm, area_model.py)
Restricao:              conclusao = 100% (alarme) -> individuos que saturam sao inviaveis.
Topologia: grau <= 4, conexa, L enlaces com L em [--links-min, --links-max] (L variavel =
"orcamentos diferentes"; --links-min = --links-max = 112 e "orcamento igual"),
fio total <= --wire-mult * L (ou --wire-cap absoluto).

VERSAO A (padrao): CUs e core fixos (--cus, --core). So a topologia e variavel.
VERSAO B (co-projeto): --cus-set 1 2 4 8 16 e/ou --core-set minor o3 tornam o numero de
  CUs e o tipo de core variaveis de decisao. Use CARGA FIXA (--spacing-ns e --duration-us
  iguais para todos), pois o espacamento nao pode depender do individuo.

Algoritmo de controle: --ctrl bfs (padrao) | dij. Os coeficientes por core estao em PRESETS
(calibracao da Fase 0.7/0.8): minor, timing (coeficientes proprios), o3 (= minor com
control_clock_ratio 2,54 BFS / 2,37 Dijkstra).

Saidas em <out-root>/<name>/: history.csv (gen, n_eval, n_viaveis, hipervolume),
pareto.csv, pareto/pt01../{best_edges.json,best_config.json}, all_evals.csv,
summary.json (inclui o ponto da mesh de referencia), cache_<core>_cu<k>.jsonl.
Reexecutar o mesmo comando reaproveita o cache.
"""
import argparse, csv, json, os, random, sys, time, glob as _glob
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.callback import Callback
from pymoo.core.crossover import Crossover
from pymoo.core.duplicate import ElementwiseDuplicateElimination
from pymoo.core.mutation import Mutation
from pymoo.core.problem import Problem
from pymoo.core.sampling import Sampling
from pymoo.indicators.hv import HV
from pymoo.optimize import minimize

import ga_common as gc
import area_model as am

COMMON_NP = {"reserve_dst_port": True, "reserve_src_port": True, "dijkstra_early_exit": False}
PRESETS = {
    "bfs": {
        "minor":  {"routing_algorithm": "bfs", "dijkstra_dispatch_cycles": 129, "dijkstra_init_cycles_per_node": 1,
                   "dijkstra_pq_op_cycles": 39, "dijkstra_edge_check_cycles": 1, "control_clock_ratio": 1.0},
        "timing": {"routing_algorithm": "bfs", "dijkstra_dispatch_cycles": 109, "dijkstra_init_cycles_per_node": 1,
                   "dijkstra_pq_op_cycles": 39, "dijkstra_edge_check_cycles": 9, "control_clock_ratio": 1.0},
        "o3":     {"routing_algorithm": "bfs", "dijkstra_dispatch_cycles": 129, "dijkstra_init_cycles_per_node": 1,
                   "dijkstra_pq_op_cycles": 39, "dijkstra_edge_check_cycles": 1, "control_clock_ratio": 2.54},
    },
    "dij": {
        "minor":  {"routing_algorithm": "dijkstra", "dijkstra_dispatch_cycles": 227, "dijkstra_init_cycles_per_node": 5,
                   "dijkstra_pq_base_cycles": 45, "dijkstra_pq_op_cycles": 11, "dijkstra_edge_check_cycles": 1,
                   "control_clock_ratio": 1.0},
        "timing": {"routing_algorithm": "dijkstra", "dijkstra_dispatch_cycles": 465, "dijkstra_init_cycles_per_node": 3,
                   "dijkstra_pq_base_cycles": 34, "dijkstra_pq_op_cycles": 17, "dijkstra_edge_check_cycles": 12,
                   "control_clock_ratio": 1.0},
        "o3":     {"routing_algorithm": "dijkstra", "dijkstra_dispatch_cycles": 227, "dijkstra_init_cycles_per_node": 5,
                   "dijkstra_pq_base_cycles": 45, "dijkstra_pq_op_cycles": 11, "dijkstra_edge_check_cycles": 1,
                   "control_clock_ratio": 2.37},
    },
}


CTX = None


class Ctx:
    """Estado compartilhado (parametros, avaliadores, arquivo de avaliacoes)."""
    pass


def set_cap(ctx, L):
    if ctx.wire_cap is not None:
        gc.set_wire_cap(ctx.wire_cap)
    elif ctx.wire_mult is not None:
        gc.set_wire_cap(int(round(ctx.wire_mult * L)))
    else:
        gc.set_wire_cap(None)


def key_of(ind):
    return (gc.edges_hash(ind[0]), ind[1], ind[2])


def get_evaluator(ctx, cus, core):
    k = (cus, core)
    if k not in ctx.evs:
        np_over = dict(COMMON_NP)
        np_over.update(PRESETS[ctx.ctrl][core])
        np_over.update(gc.parse_kv(ctx.a.np))
        ctx.evs[k] = gc.Evaluator(
            ctx.a.bin, ctx.template, ctx.a.traffic, ctx.a.train_seeds, cus=cus,
            duration_us=ctx.a.duration_us, num_packets=ctx.a.num_packets,
            injection={"mode": ctx.a.injection_mode, "burst_max": ctx.a.burst_max,
                       "spacing_ns": ctx.a.spacing_ns},
            np_overrides=np_over, timeout=ctx.a.timeout,
            cache_path=os.path.join(ctx.out_dir, f"cache_{core}_cu{cus}.jsonl"),
            objective=ctx.a.objective)
    return ctx.evs[k]


def evaluate_ind(ctx, ind):
    edges, cus, core = ind
    rec = get_evaluator(ctx, cus, core).evaluate(edges)
    a_noc, _, _ = am.noc_area(edges, ctx.n, ctx.a.flit)
    a_tot = cus * am.CORE_MM2[core] + a_noc
    out = {"lat": rec["fitness"], "area": a_tot, "area_noc": a_noc,
           "completion": rec["completion"], "L": len(edges),
           "wire": gc.wire_total(edges, ctx.n), "cus": cus, "core": core,
           "hash": gc.edges_hash(edges), "edges": edges}
    ctx.archive[key_of(ind)] = out
    return out


class MOProblem(Problem):
    def __init__(self, ctx):
        super().__init__(n_var=1, n_obj=2, n_ieq_constr=1)

    def _evaluate(self, X, out, *args, **kwargs):
        inds = [X[i, 0] for i in range(len(X))]
        with ThreadPoolExecutor(max_workers=CTX.a.workers) as ex:
            recs = list(ex.map(lambda i: evaluate_ind(CTX, i), inds))
        out["F"] = np.array([[r["lat"], r["area"]] for r in recs])
        out["G"] = np.array([[99.95 - r["completion"]] for r in recs])


def rand_L(ctx):
    return ctx.rng.randint(ctx.a.links_min, ctx.a.links_max)


def rand_cc(ctx):
    return ctx.rng.choice(ctx.cus_set), ctx.rng.choice(ctx.core_set)


class MOSampling(Sampling):
    def __init__(self, ctx, seeds):
        super().__init__()
        self.seeds = seeds

    def _do(self, problem, n_samples, **kwargs):
        ctx = CTX
        pop = list(self.seeds)[:n_samples]
        seen = {key_of(i) for i in pop}
        guard = 0
        while len(pop) < n_samples and guard < 50 * n_samples:
            guard += 1
            L = rand_L(ctx)
            set_cap(ctx, L)
            try:
                t = gc.random_topology(ctx.n, L, ctx.rng)
            except RuntimeError:
                continue
            c, k = rand_cc(ctx)
            ind = (t, c, k)
            if key_of(ind) not in seen:
                seen.add(key_of(ind))
                pop.append(ind)
        X = np.empty((len(pop), 1), dtype=object)
        for i, ind in enumerate(pop):
            X[i, 0] = ind
        return X


class MOCrossover(Crossover):
    def __init__(self, ctx, **kw):
        super().__init__(2, 2, **kw)

    def _child(self, p, q):
        ctx = CTX
        (ea, ca, ka), (eb, cb, kb) = p, q
        lo, hi = sorted((len(ea), len(eb)))
        L = ctx.rng.randint(lo, hi)
        set_cap(ctx, L)
        t = gc.crossover(ea, eb, ctx.n, L, ctx.rng)
        if len(t) != L:                    # fallback: herda o pai
            t = ea
        c, k = (ca, ka) if ctx.rng.random() < 0.5 else (cb, kb)
        return (t, c, k)

    def _do(self, problem, X, **kwargs):
        _, n_matings, _ = X.shape
        Y = np.empty((2, n_matings, 1), dtype=object)
        for j in range(n_matings):
            a, b = X[0, j, 0], X[1, j, 0]
            Y[0, j, 0] = self._child(a, b)
            Y[1, j, 0] = self._child(b, a)
        return Y


class MOMutation(Mutation):
    def __init__(self, ctx, p_len=0.3, p_cc=0.2, **kw):
        super().__init__(**kw)
        self.p_len, self.p_cc = p_len, p_cc

    def _one(self, ind):
        ctx = CTX
        e, c, k = ind
        L = len(e)
        if ctx.a.links_max > ctx.a.links_min and ctx.rng.random() < self.p_len:
            L2 = min(ctx.a.links_max, max(ctx.a.links_min, L + ctx.rng.choice([-6, -3, -2, -1, 1, 2, 3, 6])))
            if L2 != L:
                set_cap(ctx, L2)
                r = gc.repair(e, ctx.n, L2, ctx.rng)
                if r is not None and len(r) == L2:
                    e, L = r, L2
        set_cap(ctx, L)
        e = gc.mutate(e, ctx.n, L, ctx.rng, 3)
        if (len(ctx.cus_set) > 1 or len(ctx.core_set) > 1) and ctx.rng.random() < self.p_cc:
            c, k = rand_cc(ctx)
        return (e, c, k)

    def _do(self, problem, X, **kwargs):
        Y = X.copy()
        for i in range(len(X)):
            Y[i, 0] = self._one(X[i, 0])
        return Y


class MODup(ElementwiseDuplicateElimination):
    def is_equal(self, a, b):
        return key_of(a.X[0]) == key_of(b.X[0])


class HistCB(Callback):
    def __init__(self, ctx, t0):
        super().__init__()
        self.t0 = t0
        self.path = os.path.join(ctx.out_dir, "history.csv")
        with open(self.path, "w", newline="") as f:
            csv.writer(f).writerow(["gen", "n_eval", "n_viaveis", "hipervolume", "min_lat", "min_area", "elapsed_s"])

    def notify(self, algorithm):
        ctx = CTX
        F = algorithm.pop.get("F")
        cv = algorithm.pop.get("CV").flatten()
        ok = cv <= 0
        hv, mlat, marea = float("nan"), float("nan"), float("nan")
        if ok.any():
            Fn = F[ok] / np.array([ctx.mesh["lat"], ctx.mesh["area"]])
            hv = float(HV(ref_point=np.array(ctx.a.hv_ref))(Fn))
            mlat, marea = float(F[ok][:, 0].min()), float(F[ok][:, 1].min())
        row = [algorithm.n_gen, algorithm.evaluator.n_eval, int(ok.sum()), hv, mlat, marea,
               round(time.time() - self.t0, 1)]
        with open(self.path, "a", newline="") as f:
            csv.writer(f).writerow(row)
        print(f"[gen {row[0]:>3}] evals={row[1]:>5} viaveis={row[2]:>3} HV={hv:.4f} "
              f"(min lat={mlat:.1f}, min area={marea:.3f}) ({row[6]}s)", flush=True)


def nondominated(rows):
    out = []
    for r in rows:
        if r["completion"] < 99.95:
            continue
        if not any((q["lat"] <= r["lat"] and q["area"] <= r["area"]) and
                   (q["lat"] < r["lat"] or q["area"] < r["area"]) for q in rows if q["completion"] >= 99.95):
            out.append(r)
    out.sort(key=lambda r: (r["area"], r["lat"]))
    seen, uniq = set(), []
    for r in out:
        k = (round(r["lat"], 6), round(r["area"], 9))
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    gc.common_args(ap)
    ap.add_argument("--nodes", type=int, default=64)
    ap.add_argument("--links-min", type=int, default=84)
    ap.add_argument("--links-max", type=int, default=124)
    ap.add_argument("--core", default="minor", choices=["minor", "timing", "o3"])
    ap.add_argument("--core-set", nargs="*", default=None, help="versao B: tipos de core variaveis")
    ap.add_argument("--cus-set", type=int, nargs="*", default=None, help="versao B: nº de CUs variavel")
    ap.add_argument("--ctrl", default="bfs", choices=["bfs", "dij"])
    ap.add_argument("--flit", type=int, default=64, choices=[32, 64, 128])
    ap.add_argument("--pop", type=int, default=40)
    ap.add_argument("--gens", type=int, default=40)
    ap.add_argument("--train-seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--p-cross", type=float, default=0.9)
    ap.add_argument("--ga-seed", type=int, default=1)
    ap.add_argument("--hv-ref", type=float, nargs=2, default=[1.25, 1.5],
                    help="ponto de referencia do hipervolume, em unidades da mesh (lat, area)")
    ap.add_argument("--seed-dirs", nargs="*", default=[],
                    help="pastas (glob) com best_edges.json (ex.: melhores do GA da Fase 1) para a populacao inicial")
    ap.add_argument("--name", required=True)
    ap.add_argument("--out-root", default="runs_fase3")
    a = ap.parse_args()
    if a.cus is None and not a.cus_set:
        sys.exit("informe --cus (versao A) ou --cus-set (versao B)")

    global CTX
    ctx = CTX = Ctx()
    ctx.a, ctx.n = a, a.nodes
    ctx.template = gc.load_template(a.template)
    ctx.ctrl, ctx.wire_mult, ctx.wire_cap = a.ctrl, a.wire_mult, a.wire_cap
    ctx.rng = random.Random(a.ga_seed)
    ctx.cus_set = a.cus_set or [a.cus]
    ctx.core_set = a.core_set or [a.core]
    ctx.evs, ctx.archive = {}, {}
    ctx.out_dir = os.path.join(a.out_root, a.name)
    os.makedirs(ctx.out_dir, exist_ok=True)
    t0 = time.time()

    base_cc = (ctx.cus_set[-1] if a.cus is None else a.cus, ctx.core_set[0] if a.core_set else a.core)
    mesh_e = gc.mesh_edges(int(round(ctx.n ** 0.5)))
    set_cap(ctx, len(mesh_e))
    ctx.mesh = evaluate_ind(ctx, (mesh_e, base_cc[0], base_cc[1]))
    print(f"[mesh] cus={base_cc[0]} core={base_cc[1]}: lat={ctx.mesh['lat']:.1f} ciclos, "
          f"area={ctx.mesh['area']:.3f} mm2 (NoC {ctx.mesh['area_noc']:.3f}), conclusao={ctx.mesh['completion']:.1f}%")
    if ctx.mesh["lat"] >= gc.FAIL_PENALTY:
        sys.exit("[ERRO] a simulacao da mesh falhou; corrija antes de rodar.")

    # populacao inicial: mesh + sementes (best_edges de execucoes anteriores) + aleatorias
    seeds = [(mesh_e, base_cc[0], base_cc[1])]
    for pat in a.seed_dirs:
        for d in sorted(_glob.glob(pat)):
            p = os.path.join(d, "best_edges.json")
            if os.path.exists(p):
                e = gc.canon(tuple(x) for x in json.load(open(p)))
                set_cap(ctx, len(e))
                if a.links_min <= len(e) <= a.links_max and gc.is_valid(e, ctx.n, len(e)):
                    for c in ctx.cus_set:
                        seeds.append((e, c, ctx.core_set[0]))
    uniq = {}
    for s in seeds:
        uniq[key_of(s)] = s
    seeds = list(uniq.values())
    if not (a.links_min <= len(mesh_e) <= a.links_max):
        seeds = [x for x in seeds if key_of(x) != key_of((mesh_e, base_cc[0], base_cc[1]))]
    print(f"[init] {len(seeds)} semente(s) + {max(0, a.pop - len(seeds))} aleatoria(s); "
          f"L em [{a.links_min},{a.links_max}], CUs {ctx.cus_set}, core {ctx.core_set}")

    problem = MOProblem(ctx)
    algo = NSGA2(pop_size=a.pop, sampling=MOSampling(ctx, seeds[:a.pop]),
                 crossover=MOCrossover(ctx, prob=a.p_cross), mutation=MOMutation(ctx, prob=1.0),
                 eliminate_duplicates=MODup())
    res = minimize(problem, algo, ("n_gen", a.gens + 1), seed=a.ga_seed,
                   callback=HistCB(ctx, t0), verbose=False)

    rows = [r for r in ctx.archive.values()]
    front = nondominated(rows)
    cols = ["lat", "area", "area_noc", "L", "wire", "cus", "core", "completion", "hash"]
    with open(os.path.join(ctx.out_dir, "pareto.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ponto"] + cols + ["lat_vs_mesh_pct", "area_vs_mesh_pct"])
        for i, r in enumerate(front, 1):
            w.writerow([i] + [r[c] for c in cols] +
                       [round((r["lat"] / ctx.mesh["lat"] - 1) * 100, 2),
                        round((r["area"] / ctx.mesh["area"] - 1) * 100, 2)])
    for i, r in enumerate(front, 1):
        d = os.path.join(ctx.out_dir, "pareto", f"pt{i:02d}")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "best_edges.json"), "w") as f:
            json.dump([list(e) for e in r["edges"]], f)
        np_over = dict(COMMON_NP)
        np_over.update(PRESETS[ctx.ctrl][r["core"]])
        np_over.update(gc.parse_kv(a.np))
        cfg = gc.build_config(ctx.template, r["edges"], a.traffic, a.train_seeds[0], r["cus"],
                              a.duration_us, a.num_packets,
                              {"mode": a.injection_mode, "burst_max": a.burst_max, "spacing_ns": a.spacing_ns},
                              np_over)
        cfg["topology_description"] = (f"{a.name} pt{i:02d}: L={r['L']} cus={r['cus']} core={r['core']} "
                                       f"lat={r['lat']:.1f} area={r['area']:.3f}")
        with open(os.path.join(d, "best_config.json"), "w") as f:
            json.dump(cfg, f, indent=2)
        with open(os.path.join(d, "point.json"), "w") as f:
            json.dump({k: r[k] for k in cols}, f)
    with open(os.path.join(ctx.out_dir, "all_evals.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in sorted(rows, key=lambda r: r["lat"]):
            w.writerow([r[c] for c in cols])
    hist_hv = None
    try:
        Fn = np.array([[r["lat"], r["area"]] for r in front]) / np.array([ctx.mesh["lat"], ctx.mesh["area"]])
        hist_hv = float(HV(ref_point=np.array(a.hv_ref))(Fn)) if len(Fn) else None
    except Exception:
        pass
    summary = {"name": a.name, "version": "B" if (a.cus_set or a.core_set) else "A",
               "traffic": a.traffic, "ctrl": a.ctrl, "flit": a.flit,
               "links": [a.links_min, a.links_max], "wire_mult": a.wire_mult, "wire_cap": a.wire_cap,
               "cus_set": ctx.cus_set, "core_set": ctx.core_set, "pop": a.pop, "gens": a.gens,
               "train_seeds": a.train_seeds, "n_avaliacoes_unicas": len(rows),
               "mesh_ref": {k: ctx.mesh[k] for k in ("lat", "area", "area_noc", "completion", "cus", "core")},
               "n_pareto": len(front), "hv_pareto_final": hist_hv, "hv_ref": a.hv_ref,
               "elapsed_s": round(time.time() - t0, 1)}
    with open(os.path.join(ctx.out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    print("\nPareto (lat, area, L, cus, core):")
    for i, r in enumerate(front, 1):
        print(f"  pt{i:02d}: lat={r['lat']:.1f} ({(r['lat']/ctx.mesh['lat']-1)*100:+.1f}% vs mesh) "
              f"area={r['area']:.3f} ({(r['area']/ctx.mesh['area']-1)*100:+.1f}%) L={r['L']} "
              f"wire={r['wire']} cus={r['cus']} {r['core']}")


if __name__ == "__main__":
    main()