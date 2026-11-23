#!/usr/bin/env python3
"""Teste PAREADO por seed contra a referencia, lendo direto o cache do ga_final_eval.py (nao roda o simulador).

As seeds sao pareadas: o mesmo trafego (mesmas chegadas e pares) vale para todas as candidatas numa seed,
entao d_i = latencia(candidata, seed i) - latencia(mesh, seed i) remove a variacao comum do trafego.
Por celula (CUs, padrao): delta% medio, p do t pareado (scipy) e do Wilcoxon, p de Holm entre as candidatas
da celula, e quantas seeds a candidata ganha.

Uso (na pasta do simulador, onde esta ga_common.py):
  python3 compare_paired.py --cache-glob "cache_bfs_r1_rho0.5_cu*" \
      --run-dirs "runs/bfs_*_cu16_*" \
      --extra mesh:configs/configs_ciclos/config_mesh_64.json \
      --extra smallworld:configs/configs_ciclos/config_irregular_smallworld_64.json \
      --out paired_bfs_r1_rho0.5
Cada pasta de cache deve terminar em _cu<N> (como cria o run_cu_sweep.sh); a rodada deve ter conclusao 100%.
"""
import argparse, csv, glob, json, os, re, statistics as st
import ga_common as gc

def holm(ps):
    idx = sorted(range(len(ps)), key=lambda i: ps[i]); out = [None] * len(ps); run = 0.0
    for rank, i in enumerate(idx):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i])); out[i] = run
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-glob", required=True)
    ap.add_argument("--run-dirs", nargs="*", default=[])
    ap.add_argument("--extra", action="append", default=[])
    ap.add_argument("--ref", default="mesh")
    ap.add_argument("--out", default="paired")
    a = ap.parse_args()
    try:
        from scipy import stats
    except Exception:
        raise SystemExit("precisa de scipy: pip install scipy")

    label_by_hash = {}
    for rd in a.run_dirs:
        for d in sorted(glob.glob(rd)):
            p = os.path.join(d, "best_edges.json")
            if os.path.exists(p):
                e = gc.canon(tuple(x) for x in json.load(open(p)))
                label_by_hash[gc.edges_hash(e)] = os.path.basename(d.rstrip("/"))
    for it in a.extra:
        lab, path = it.split(":", 1)
        label_by_hash[gc.edges_hash(gc.edges_from_config(path))] = lab

    rows = []
    dirs = [d for d in glob.glob(a.cache_glob) if re.search(r"_cu(\d+)$", d.rstrip("/"))]
    dirs.sort(key=lambda d: int(re.search(r"_cu(\d+)$", d.rstrip("/")).group(1)))
    for d in dirs:
        cu = int(re.search(r"_cu(\d+)$", d.rstrip("/")).group(1))
        for f in sorted(glob.glob(os.path.join(d, "final_*.jsonl"))):
            pat = re.match(r"final_(.+?)(?:_cu\d+)?\.jsonl$", os.path.basename(f)).group(1)
            recs = {}
            for line in open(f):
                line = line.strip()
                if line:
                    r = json.loads(line); recs[r["hash"]] = r          # ultimo vence
            by = {label_by_hash[h]: r for h, r in recs.items() if h in label_by_hash}
            if a.ref not in by:
                print("sem referencia em", f); continue
            ref = by[a.ref]["per_seed"]; refm = st.mean(ref)
            cell = []
            for lab, r in by.items():
                if lab == a.ref: continue
                x = r["per_seed"]
                if len(x) != len(ref): continue
                diff = [u - v for u, v in zip(x, ref)]
                pt = float(stats.ttest_rel(x, ref).pvalue)
                try: pw = float(stats.wilcoxon(diff).pvalue)
                except Exception: pw = float("nan")
                cell.append(dict(cus=cu, pattern=pat, candidate=lab, delta_pct=100 * st.mean(diff) / refm,
                                 mean_diff=st.mean(diff), p_paired_t=pt, p_wilcoxon=pw,
                                 wins=sum(1 for v in diff if v < 0), n=len(diff),
                                 completion=r.get("completion")))
            ph = holm([c["p_paired_t"] for c in cell])
            for c, p in zip(cell, ph): c["p_holm"] = p
            rows += cell

    if not rows:
        raise SystemExit("nada encontrado (confira --cache-glob e se as pastas terminam em _cu<N>)")
    with open(a.out + ".csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    print("Teste pareado por seed contra '%s' (celula = CUs x padrao; candidatas treinadas = todas menos smallworld)" % a.ref)
    print("%-4s %-12s | %-27s | %-17s | %-14s | %s" % ("CUs", "padrao", "delta% treinadas (min a max)", "melh p<.05 / Holm", "seeds ganhas", "small-world (delta%, p pareado)"))
    for cu in sorted({r["cus"] for r in rows}):
        for pat in sorted({r["pattern"] for r in rows if r["cus"] == cu}):
            cl = [r for r in rows if r["cus"] == cu and r["pattern"] == pat]
            tr = [r for r in cl if r["candidate"] != "smallworld"]
            sw = next((r for r in cl if r["candidate"] == "smallworld"), None)
            if not tr: continue
            d = [r["delta_pct"] for r in tr]
            b1 = sum(1 for r in tr if r["delta_pct"] < 0 and r["p_paired_t"] < 0.05)
            b2 = sum(1 for r in tr if r["delta_pct"] < 0 and r["p_holm"] < 0.05)
            wi = st.mean(r["wins"] for r in tr)
            swt = "%+.1f%% p=%.3f" % (sw["delta_pct"], sw["p_paired_t"]) if sw else "-"
            print("%-4d %-12s | %+8.1f a %+8.1f %-8s | %2d/%-2d  /  %2d/%-2d     | %4.1f de %-2d      | %s" % (
                cu, pat, min(d), max(d), "", b1, len(tr), b2, len(tr), wi, tr[0]["n"], swt))
    print("\nCSV: %s.csv   (p_holm: Holm entre as candidatas de cada celula; exploratorio)" % a.out)

if __name__ == "__main__":
    main()