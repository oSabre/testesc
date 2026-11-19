#!/usr/bin/env python3
"""
ga_select_topk.py -- escolhe as melhores topologias ALEATORIAS para semear o GA,
corrigindo o vies de selecao (winner's curse):

  1) avalia todas as config_random_*.json com o numero certo de links nas
     seeds de TREINO (as mesmas do GA) e pega as --pre melhores;
  2) REAVALIA essas --pre com seeds NOVAS (--fresh-seeds, padrao 1000..1009);
  3) fica com as --keep melhores pelo resultado nas seeds novas.

Saida: topk_<padrao>.json, lista ordenada (melhor primeiro), usada pelo
ga_optimize.py via --seeds-file.
"""

import argparse
import glob
import json
import os
from concurrent.futures import ThreadPoolExecutor

import ga_common as gc


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    gc.common_args(ap)
    ap.add_argument("--config-dir", default="configs/configs_ciclos")
    ap.add_argument("--pattern", default="config_random_*.json")
    ap.add_argument("--links", type=int, default=112)
    ap.add_argument("--train-seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--fresh-seeds", type=int, nargs="+", default=list(range(1000, 1010)))
    ap.add_argument("--pre", type=int, default=15)
    ap.add_argument("--keep", type=int, default=10)
    ap.add_argument("--out", default=None, help="padrao: topk_<traffic>[_cu<k>].json")
    ap.add_argument("--cache-dir", default="runs/_select_cache")
    a = ap.parse_args()

    os.makedirs(a.cache_dir, exist_ok=True)
    tag = f"{a.traffic}" + (f"_cu{a.cus}" if a.cus else "")
    out = a.out or f"topk_{tag}.json"

    cands = []
    for p in sorted(glob.glob(os.path.join(a.config_dir, a.pattern))):
        e = gc.edges_from_config(p)
        if len(e) == a.links:
            cands.append((p, e))
    print(f"[select] {len(cands)} candidatas com {a.links} links")
    if not cands:
        raise SystemExit("nenhuma candidata encontrada (confira --config-dir/--pattern)")

    ev_train = gc.evaluator_from_args(a, a.train_seeds,
                                      cache_path=os.path.join(a.cache_dir, f"train_{tag}.jsonl"))
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        recs = list(ex.map(lambda c: ev_train.evaluate(c[1]), cands))
    bad = sum(1 for r in recs if r["fitness"] >= gc.FAIL_PENALTY)
    if bad > 0.2 * len(recs):
        raise SystemExit(f"[ERRO] {bad}/{len(recs)} candidatas falharam no treino (simulacao com erro/timeout). "
                         "Corrija o simulador/--timeout e apague runs/_select_cache antes de repetir.")
    # distribuicao completa das aleatorias (baseline para percentis/histograma)
    import csv as _csv
    with open(f"select_all_{tag}.csv", "w", newline="") as _f:
        _w = _csv.writer(_f)
        _w.writerow(["label", "fitness", "std", "completion", "control", "data"])
        for (p, e), r in zip(cands, recs):
            _w.writerow([os.path.basename(p).replace("config_", "").replace(".json", ""),
                         r["fitness"], r["std"], r["completion"], r.get("control"), r.get("data")])
    print(f"[select] distribuicao completa: select_all_{tag}.csv")
    ranked = sorted(zip(cands, recs), key=lambda x: x[1]["fitness"])[:a.pre]
    print(f"[select] top-{a.pre} no treino; reavaliando em seeds novas {a.fresh_seeds[0]}..{a.fresh_seeds[-1]}")

    ev_fresh = gc.evaluator_from_args(a, a.fresh_seeds,
                                      cache_path=os.path.join(a.cache_dir, f"fresh_{tag}.jsonl"))
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        fresh = list(ex.map(lambda x: ev_fresh.evaluate(x[0][1]), ranked))

    rows = []
    for ((p, e), rt), rf in zip(ranked, fresh):
        rows.append({"label": os.path.basename(p).replace("config_", "").replace(".json", ""),
                     "path": p, "train_fitness": rt["fitness"],
                     "fresh_fitness": rf["fitness"], "fresh_std": rf["std"],
                     "fresh_completion": rf["completion"]})
    rows.sort(key=lambda r: r["fresh_fitness"])
    rows = rows[:a.keep]
    print(f"{'topologia':<16}{'treino':>10}{'seeds novas':>14}{'conclusao%':>12}")
    for r in rows:
        print(f"{r['label']:<16}{r['train_fitness']:>10.2f}{r['fresh_fitness']:>14.2f}"
              f"{r['fresh_completion']:>12.1f}")
    with open(out, "w") as f:
        json.dump({"traffic": a.traffic, "cus": a.cus, "train_seeds": a.train_seeds,
                   "fresh_seeds": a.fresh_seeds, "candidates": rows}, f, indent=2)
    print(f"[select] salvo: {out}")


if __name__ == "__main__":
    main()