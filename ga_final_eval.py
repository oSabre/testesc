#!/usr/bin/env python3
"""
ga_final_eval.py -- avaliacao FINAL, fora da amostra: reavalia candidatas
(melhores do GA, do random search, top-k aleatorias, mesh, small-world) com
seeds NOVAS (padrao 1000..1009) em cada padrao de trafego, gerando a matriz
candidata x padrao (generalizacao) e testes de Welch contra uma referencia.

Candidatas: --run-dirs runs/*   (usa best_config.json de cada execucao)
            --extra rotulo:caminho_do_config.json (repetivel)
Referencia dos testes: --ref <rotulo> (padrao: mesh)

Saidas: final_eval.csv (media, desvio, conclusao, p-valor Welch vs ref),
final_eval.png (barras por padrao) e tabela no terminal.
"""

import argparse
import csv
import glob
import json
import os
import statistics as st
from concurrent.futures import ThreadPoolExecutor

import ga_common as gc

PATTERNS = ["uniform", "bit_reversal", "butterfly"]


def welch_p(a, b):
    try:
        from scipy import stats
        return float(stats.ttest_ind(a, b, equal_var=False).pvalue)
    except Exception:
        return float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    gc.common_args(ap)
    ap.add_argument("--run-dirs", nargs="*", default=[])
    ap.add_argument("--extra", action="append", default=[])
    ap.add_argument("--ref", default="mesh")
    ap.add_argument("--patterns", nargs="+", default=PATTERNS)
    ap.add_argument("--seed-start", type=int, default=1000)
    ap.add_argument("--replicas", type=int, default=10)
    ap.add_argument("--out", default="final_eval")
    ap.add_argument("--cache-dir", default="runs/_final_cache")
    a = ap.parse_args()

    cands = {}
    for rd in a.run_dirs:
        for d in sorted(glob.glob(rd)):
            p = os.path.join(d, "best_edges.json")
            if os.path.exists(p):
                with open(p) as f:
                    cands[os.path.basename(d.rstrip("/\\"))] = gc.canon(tuple(e) for e in json.load(f))
    for it in a.extra:
        label, path = it.split(":", 1)
        cands[label] = gc.edges_from_config(path)
    if a.ref not in cands:
        raise SystemExit(f"referencia '{a.ref}' nao esta entre as candidatas: {sorted(cands)}")
    seeds = list(range(a.seed_start, a.seed_start + a.replicas))
    os.makedirs(a.cache_dir, exist_ok=True)
    print(f"[final] {len(cands)} candidatas x {len(a.patterns)} padroes x {len(seeds)} seeds")

    results = {}  # (label, pattern) -> rec
    for pat in a.patterns:
        a.traffic = pat
        tag = f"{pat}" + (f"_cu{a.cus}" if a.cus else "")
        ev = gc.evaluator_from_args(a, seeds, cache_path=os.path.join(a.cache_dir, f"final_{tag}.jsonl"))
        labels = list(cands)
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            recs = list(ex.map(lambda l: ev.evaluate(cands[l]), labels))
        for l, r in zip(labels, recs):
            results[(l, pat)] = r

    rows = []
    for pat in a.patterns:
        ref = results[(a.ref, pat)]
        for l in cands:
            r = results[(l, pat)]
            p = 1.0 if l == a.ref else welch_p(r["per_seed"], ref["per_seed"])
            rows.append({"candidate": l, "pattern": pat, "mean": r["fitness"], "std": r["std"],
                         "completion": r["completion"], "p_vs_ref": p,
                         "delta_vs_ref_pct": 100 * (r["fitness"] / ref["fitness"] - 1)})
    with open(a.out + ".csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"\nLatencia media penalizada (ciclos), seeds {seeds[0]}..{seeds[-1]}; "
          f"delta% e p-valor (Welch) vs '{a.ref}'")
    for pat in a.patterns:
        print(f"\n== {pat} ==")
        print(f"{'candidata':<26}{'media':>9}{'dp':>8}{'concl%':>8}{'delta%':>9}{'p':>9}")
        for r in sorted([x for x in rows if x['pattern'] == pat], key=lambda x: x["mean"]):
            print(f"{r['candidate']:<26}{r['mean']:>9.2f}{r['std']:>8.2f}{r['completion']:>8.1f}"
                  f"{r['delta_vs_ref_pct']:>9.1f}{r['p_vs_ref']:>9.3f}")
    gc._ca.check_table(rows)
    print(f"\n== Media dos padroes (delta% vs '{a.ref}'; negativo = melhor que a referencia) ==")
    print(f"{'candidata':<34}{'media delta%':>13}{'melhor':>9}{'pior':>9}")
    summ = []
    for l in cands:
        ds = [r["delta_vs_ref_pct"] for r in rows if r["candidate"] == l]
        summ.append((sum(ds) / len(ds), min(ds), max(ds), l))
    for mdl, lo, hi, l in sorted(summ):
        print(f"{l:<34}{mdl:>13.1f}{lo:>9.1f}{hi:>9.1f}")
    with open(a.out + "_summary.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["candidate", "mean_delta_pct", "best_delta_pct", "worst_delta_pct"])
        for mdl, lo, hi, l in sorted(summ):
            w.writerow([l, mdl, lo, hi])
    print("\nObs.: confira a conclusao% -- se diferir entre candidatas, compare a media penalizada,"
          " nao a latencia dos concluidos.")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axs = plt.subplots(1, len(a.patterns), figsize=(5 * len(a.patterns), 5), sharey=False)
        axs = [axs] if len(a.patterns) == 1 else axs
        for ax, pat in zip(axs, a.patterns):
            rs = sorted([x for x in rows if x["pattern"] == pat], key=lambda x: x["mean"])
            ax.barh([r["candidate"] for r in rs], [r["mean"] for r in rs],
                    xerr=[r["std"] for r in rs], color="#4c78a8")
            ax.set_title(pat)
            ax.set_xlabel("latencia media penalizada (ciclos)")
            ax.invert_yaxis()
        fig.tight_layout()
        fig.savefig(a.out + ".png", dpi=150)
        print(f"Grafico: {a.out}.png | tabela: {a.out}.csv")
    except Exception as exc:
        print("(sem grafico:", exc, ")")
    _ca_code = gc._ca.summary(a.out, "(avaliacao final)")
    if _ca_code:
        raise SystemExit(_ca_code)


if __name__ == "__main__":
    main()