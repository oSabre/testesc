#!/usr/bin/env python3
"""
ga_linkusage.py -- mede a CONCENTRACAO de trafego nos links de varias topologias
(testa a hipotese 'o small-world concentra o trafego em poucos atalhos').

Roda o simulador (main.exe) para cada topologia x seed, soma o uso por link
(usage_count = circuitos alocados no link) e mostra, por topologia:
  Gini do uso, fracao do uso nos top-5 links, max/media, links nunca usados,
  fracao do uso em links de LONGO ALCANCE (fora da grade) e os links mais usados.
Tambem mostra conclusao% e latencia (controle/dados) para contexto.

Uso:
  py ga_linkusage.py --bin ./main.exe --traffic butterfly --cus 16 --duration-us 150 \
     --spacing-ns 800 --np dijkstra_early_exit=false --replicas 5 \
     mesh:configs/configs_ciclos/config_mesh_64.json \
     smallworld:configs/configs_ciclos/config_irregular_smallworld_64.json \
     gaBF:runs/butterfly_cu16_ga_random/best_config.json
Saida: linkusage_<padrao>.csv (uso por link e topologia) + tabela.
"""
import argparse, csv, json, os, shutil, statistics as st, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor
import ga_common as gc


def gini(v):
    v = sorted(v); n = len(v); tot = sum(v)
    if n == 0 or tot == 0:
        return 0.0
    return (2 * sum((i + 1) * x for i, x in enumerate(v))) / (n * tot) - (n + 1) / n


def run(a, edges, seed):
    cfg = gc.build_config(gc.load_template(a.template), edges, a.traffic, seed, a.cus,
                          a.duration_us, a.num_packets,
                          {"mode": a.injection_mode, "burst_max": a.burst_max, "spacing_ns": a.spacing_ns},
                          gc.parse_kv(a.np))
    tmp = tempfile.mkdtemp(prefix="lu_")
    try:
        os.makedirs(os.path.join(tmp, "log"), exist_ok=True)
        json.dump(cfg, open(os.path.join(tmp, "config.json"), "w"))
        cmd = a.bin.split()
        if os.path.exists(cmd[0]):
            cmd[0] = os.path.abspath(cmd[0])
        subprocess.run(cmd, cwd=tmp, timeout=a.timeout, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        res = gc.parse_results(os.path.join(tmp, "results.csv"))
        usage = {}
        with open(os.path.join(tmp, "results_linkusage.csv"), newline="") as f:
            for r in csv.DictReader(f):
                u, v = int(r["u"]), int(r["v"])
                usage[(min(u, v), max(u, v))] = int(r["usage_count"])
        return res, usage
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    gc.common_args(ap)
    ap.add_argument("--replicas", type=int, default=5)
    ap.add_argument("--seed-start", type=int, default=2000)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--side", type=int, default=8)
    ap.add_argument("topos", nargs="+", help="rotulo:config.json")
    a = ap.parse_args()
    seeds = list(range(a.seed_start, a.seed_start + a.replicas))
    topos = {}
    for it in a.topos:
        k, p = it.split(":", 1)
        topos[k] = gc.edges_from_config(p)
    jobs = [(k, s) for k in topos for s in seeds]
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        out = list(ex.map(lambda j: run(a, topos[j[0]], j[1]), jobs))
    agg = {k: {} for k in topos}; meta = {k: [] for k in topos}
    for (k, s), (res, usage) in zip(jobs, out):
        meta[k].append(res)
        for e, c in usage.items():
            agg[k][e] = agg[k].get(e, 0) + c
    man = lambda e: abs(e[0] // a.side - e[1] // a.side) + abs(e[0] % a.side - e[1] % a.side)
    rows = []
    print(f"\nPadrao {a.traffic} | {a.replicas} replicas | uso = circuitos alocados por link (soma)\n")
    print(f"{'topologia':<16}{'gini':>6}{('top'+str(a.top)+'%'):>8}{'max/med':>8}{'nunca':>7}{'long%':>7}"
          f"{'concl%':>8}{'ctrl':>8}{'dados':>7}")
    for k, e in topos.items():
        use = [agg[k].get(x, 0) for x in e]
        tot = sum(use) or 1
        top = sorted(((agg[k].get(x, 0), x) for x in e), reverse=True)
        topshare = 100 * sum(u for u, _ in top[:a.top]) / tot
        longshare = 100 * sum(agg[k].get(x, 0) for x in e if man(x) > 1) / tot
        never = sum(1 for u in use if u == 0)
        mm = max(use) / (sum(use) / len(use)) if sum(use) else 0
        comp = st.mean(m["completion"] for m in meta[k])
        ctrl = st.mean(m["control"] for m in meta[k] if m["control"] is not None)
        dat = st.mean(m["data"] for m in meta[k] if m["data"] is not None)
        print(f"{k:<16}{gini(use):>6.2f}{topshare:>8.1f}{mm:>8.2f}{never:>7}{longshare:>7.1f}"
              f"{comp:>8.1f}{ctrl:>8.1f}{dat:>7.1f}")
        for x, u in zip(e, use):
            rows.append([k, x[0], x[1], man(x), u, round(100 * u / tot, 3)])
    print(f"\nLinks mais usados (u-v, comprimento na grade, % do uso total):")
    for k, e in topos.items():
        tot = sum(agg[k].get(x, 0) for x in e) or 1
        top = sorted(((agg[k].get(x, 0), x) for x in e), reverse=True)[:a.top]
        print(f"  {k:<14}" + "  ".join(f"{x[0]}-{x[1]}(len{man(x)}, {100*u/tot:.1f}%)" for u, x in top))
    with open(f"linkusage_{a.traffic}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["topologia", "u", "v", "comprimento", "uso", "pct_uso"]); w.writerows(rows)
    print(f"\nSalvo: linkusage_{a.traffic}.csv")
    print("Leitura: gini alto / top-k% alto / max/med alto = trafego concentrado em poucos links (gargalo).")

if __name__ == "__main__":
    main()