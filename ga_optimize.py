#!/usr/bin/env python3
"""
ga_optimize.py -- GA mono-objetivo (pymoo) para minimizar a latencia media
penalizada (ciclos) de uma topologia 8x8 com orcamento fixo de links.

Modos:
  --algo ga             algoritmo genetico (padrao)
  --algo random_search  baseline: sorteia topologias validas, mesmo orcamento
                        de avaliacoes do GA (pop*(gens+1))
Populacao inicial (so no GA):
  --init seeded   top-k aleatorias (--seeds-file) + mesh + small-world
                  (--refs) + resto aleatorio
  --init random   somente topologias aleatorias (controle: mostra se semear ajudou)

Fitness = media da latencia penalizada nas seeds de TREINO (--train-seeds,
fixas durante todo o GA, entao o fitness e deterministico e comparavel entre
geracoes). A reavaliacao com seeds novas e feita em ga_final_eval.py.

Saidas em runs/<name>/: history.csv, best_config.json (pronto para o
main.exe), best_edges.json, all_evals.csv, summary.json, cache.jsonl.
Reexecutar o mesmo comando reaproveita o cache (retoma barato).
"""

import argparse
import csv
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from pymoo.algorithms.soo.nonconvex.ga import GA
from pymoo.core.callback import Callback
from pymoo.core.crossover import Crossover
from pymoo.core.duplicate import ElementwiseDuplicateElimination
from pymoo.core.mutation import Mutation
from pymoo.core.problem import Problem
from pymoo.core.sampling import Sampling
from pymoo.optimize import minimize

import ga_common as gc


class TopoProblem(Problem):
    def __init__(self, ev, pool):
        super().__init__(n_var=1, n_obj=1, n_ieq_constr=0, xl=None, xu=None)
        self.ev = ev
        self.pool = pool

    def _evaluate(self, X, out, *args, **kwargs):
        edges = [X[i, 0] for i in range(len(X))]
        with ThreadPoolExecutor(max_workers=self.pool) as ex:
            recs = list(ex.map(self.ev.evaluate, edges))
        out["F"] = np.array([[r["fitness"]] for r in recs])


class TopoSampling(Sampling):
    def __init__(self, seeds, n, m, rng):
        super().__init__()
        self.seeds, self.n, self.m, self.rng = seeds, n, m, rng

    def _do(self, problem, n_samples, **kwargs):
        pop = list(self.seeds)[:n_samples]
        seen = set(pop)
        while len(pop) < n_samples:
            t = gc.random_topology(self.n, self.m, self.rng)
            if t not in seen:
                seen.add(t)
                pop.append(t)
        X = np.empty((n_samples, 1), dtype=object)
        for i, t in enumerate(pop):
            X[i, 0] = t
        return X


class TopoCrossover(Crossover):
    def __init__(self, n, m, rng, **kw):
        super().__init__(2, 2, **kw)
        self.n, self.m, self.rng = n, m, rng

    def _do(self, problem, X, **kwargs):
        _, n_matings, _ = X.shape
        Y = np.empty((2, n_matings, 1), dtype=object)
        for k in range(n_matings):
            a, b = X[0, k, 0], X[1, k, 0]
            Y[0, k, 0] = gc.crossover(a, b, self.n, self.m, self.rng)
            Y[1, k, 0] = gc.crossover(b, a, self.n, self.m, self.rng)
        return Y


class TopoMutation(Mutation):
    def __init__(self, n, m, rng, max_ops=3, **kw):
        super().__init__(**kw)
        self.n, self.m, self.rng, self.max_ops = n, m, rng, max_ops

    def _do(self, problem, X, **kwargs):
        Y = X.copy()
        for i in range(len(X)):
            Y[i, 0] = gc.mutate(X[i, 0], self.n, self.m, self.rng, self.max_ops)
        return Y


class TopoDup(ElementwiseDuplicateElimination):
    def is_equal(self, a, b):
        return a.X[0] == b.X[0]


class HistoryCB(Callback):
    def __init__(self, ev, out_dir, t0):
        super().__init__()
        self.ev, self.out_dir, self.t0 = ev, out_dir, t0
        self.path = os.path.join(out_dir, "history.csv")
        with open(self.path, "w", newline="") as f:
            csv.writer(f).writerow(["gen", "n_eval", "best", "mean", "worst", "elapsed_s"])

    def notify(self, algorithm):
        F = algorithm.pop.get("F").flatten()
        row = [algorithm.n_gen, algorithm.evaluator.n_eval, float(F.min()),
               float(F.mean()), float(F.max()), round(time.time() - self.t0, 1)]
        with open(self.path, "a", newline="") as f:
            csv.writer(f).writerow(row)
        print(f"[gen {row[0]:>3}] evals={row[1]:>5} melhor={row[2]:.3f} "
              f"media={row[3]:.3f} ({row[5]}s)", flush=True)


def load_seed_topologies(path, m, n_keep):
    """--seeds-file: JSON gerado por ga_select_topk.py (lista ordenada)."""
    out = []
    if not path:
        return out
    with open(path) as f:
        data = json.load(f)
    for item in data["candidates"][:n_keep]:
        e = gc.edges_from_config(item["path"])
        if len(e) == m:
            out.append(e)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    gc.common_args(ap)
    ap.add_argument("--algo", default="ga", choices=["ga", "random_search"])
    ap.add_argument("--init", default="seeded", choices=["seeded", "random"])
    ap.add_argument("--seeds-file", default=None, help="topk_<padrao>.json (ga_select_topk.py)")
    ap.add_argument("--seed-dirs", nargs="*", default=[],
                    help="pastas de execucoes (glob) cujo best_edges.json entra na populacao inicial")
    ap.add_argument("--n-seeds", type=int, default=10, help="quantas top-k entram na populacao inicial")
    ap.add_argument("--refs", nargs="*", default=[],
                    help="configs de referencia (mesh, small-world); entram na populacao "
                         "inicial se --init seeded e tem fitness registrado")
    ap.add_argument("--nodes", type=int, default=64)
    ap.add_argument("--links", type=int, default=112)
    ap.add_argument("--pop", type=int, default=30)
    ap.add_argument("--gens", type=int, default=40)
    ap.add_argument("--train-seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--p-cross", type=float, default=0.9)
    ap.add_argument("--ga-seed", type=int, default=1, help="seed do GA (operadores/sorteios)")
    ap.add_argument("--name", required=True, help="nome da execucao -> runs/<name>/")
    ap.add_argument("--out-root", default="runs")
    a = ap.parse_args()

    out_dir = os.path.join(a.out_root, a.name)
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(a.ga_seed)
    n, m = a.nodes, a.links
    if a.traffic == "mix":
        import copy
        evs = {}
        for p in a.mix_patterns:
            la = copy.copy(a)
            la.traffic = p
            evs[p] = gc.evaluator_from_args(la, a.train_seeds,
                                            cache_path=os.path.join(out_dir, f"cache_{p}.jsonl"))
        ev = gc.MixEvaluator(evs, gc.mesh_edges(int(round(n ** 0.5))))
        print("[mix] fitness = media das razoes vs mesh nos padroes", a.mix_patterns,
              "(1.0 = igual a mesh; <1 melhor)")
    else:
        ev = gc.evaluator_from_args(a, a.train_seeds, cache_path=os.path.join(out_dir, "cache.jsonl"))
    t0 = time.time()

    # --- referencias (fitness nas mesmas seeds de treino) ---
    refs = {}
    for p in a.refs:
        e = gc.edges_from_config(p)
        refs[os.path.basename(p)] = (e, ev.evaluate(e)["fitness"])
        print(f"[ref] {os.path.basename(p)}: fitness={refs[os.path.basename(p)][1]:.3f}")

    # --- populacao inicial ---
    init = []
    if a.algo == "ga" and a.init == "seeded":
        init += load_seed_topologies(a.seeds_file, m, a.n_seeds)
        import glob as _glob
        for pat in a.seed_dirs:
            for d in sorted(_glob.glob(pat)):
                pth = os.path.join(d, "best_edges.json")
                if os.path.exists(pth):
                    e = gc.canon(tuple(x) for x in json.load(open(pth)))
                    if len(e) == m:
                        init.append(e)
        init += [e for e, _ in refs.values() if len(e) == m]
        init = list(dict.fromkeys(init))
    print(f"[init] {len(init)} topologias semeadas + {a.pop - min(len(init), a.pop)} aleatorias")

    problem = TopoProblem(ev, a.workers)
    budget = a.pop * (a.gens + 1)

    if a.algo == "ga":
        algo = GA(pop_size=a.pop,
                  sampling=TopoSampling(init, n, m, rng),
                  crossover=TopoCrossover(n, m, rng, prob=a.p_cross),
                  mutation=TopoMutation(n, m, rng, prob=1.0),
                  eliminate_duplicates=TopoDup())
        res = minimize(problem, algo, ("n_gen", a.gens + 1), seed=a.ga_seed,
                       callback=HistoryCB(ev, out_dir, t0), verbose=False)
        bx = res.X
        while isinstance(bx, np.ndarray):
            bx = bx.flatten()[0]
        best_edges = gc.canon(bx)
    else:  # random search com o mesmo orcamento
        hist = os.path.join(out_dir, "history.csv")
        with open(hist, "w", newline="") as f:
            csv.writer(f).writerow(["gen", "n_eval", "best", "mean", "worst", "elapsed_s"])
        best_edges, best_f, seen, n_eval = None, float("inf"), set(), 0
        for g in range(1, a.gens + 2):
            batch = []
            while len(batch) < a.pop:
                t = gc.random_topology(n, m, rng)
                if t not in seen:
                    seen.add(t)
                    batch.append(t)
            with ThreadPoolExecutor(max_workers=a.workers) as ex:
                recs = list(ex.map(ev.evaluate, batch))
            n_eval += len(batch)
            fs = [r["fitness"] for r in recs]
            i = int(np.argmin(fs))
            if fs[i] < best_f:
                best_f, best_edges = fs[i], batch[i]
            with open(hist, "a", newline="") as f:
                csv.writer(f).writerow([g, n_eval, best_f, sum(fs) / len(fs), max(fs),
                                        round(time.time() - t0, 1)])
            print(f"[lote {g:>3}] evals={n_eval:>5} melhor-ate-agora={best_f:.3f}", flush=True)

    best_rec = ev.evaluate(best_edges)
    cfg = gc.build_config(ev.template, best_edges, a.mix_patterns[0] if a.traffic == "mix" else a.traffic,
                          a.train_seeds[0], a.cus,
                          a.duration_us, a.num_packets, ev.injection, ev.np_overrides)
    cfg["topology_description"] = (f"{a.name}: melhor topologia ({a.algo}, init={a.init}), "
                                   f"fitness treino={best_rec['fitness']:.3f} ciclos")
    with open(os.path.join(out_dir, "best_config.json"), "w") as f:
        json.dump(cfg, f, indent=2)
    with open(os.path.join(out_dir, "best_edges.json"), "w") as f:
        json.dump([list(e) for e in best_edges], f)
    with open(os.path.join(out_dir, "all_evals.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hash", "fitness", "std", "completion"])
        for r in sorted(ev.cache.values(), key=lambda r: r["fitness"]):
            w.writerow([r["hash"], r["fitness"], r["std"], r["completion"]])
    avg, dia = gc.avg_path_and_diameter(best_edges, n)
    summary = {"name": a.name, "algo": a.algo, "init": a.init, "traffic": a.traffic,
               "cus": a.cus, "pop": a.pop, "gens": a.gens, "budget_evals": budget,
               "unique_topologies_evaluated": len(ev.cache),
               "train_seeds": a.train_seeds, "best_fitness": best_rec["fitness"],
               "best_completion": best_rec["completion"],
               "best_avg_path": avg, "best_diameter": dia,
               "refs": {k: v[1] for k, v in refs.items()},
               "best_per_pattern_ratio_vs_mesh": best_rec.get("per_pattern"),
               "elapsed_s": round(time.time() - t0, 1)}
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    _ca_code = gc._ca.summary(os.path.join(out_dir, "completion"), "(treino)")
    if _ca_code:
        sys.exit(_ca_code)


if __name__ == "__main__":
    main()