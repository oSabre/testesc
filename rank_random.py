#!/usr/bin/env python3
"""Ranking das topologias aleatorias por latencia.
Uso: py rank_random.py [random_out_dir] [top_n]
Mostra: rotulo, latencia (regime permanente), latencia penalizada,
taxa de conclusao e o config_random_XXXX.json correspondente."""
import csv, glob, os, sys, statistics as st

d = sys.argv[1] if len(sys.argv) > 1 else "random_out_112"
top = int(sys.argv[2]) if len(sys.argv) > 2 else 10

def vals(path):
    out = {}
    with open(path, newline="") as f:
        for r in csv.reader(f):
            if len(r) >= 2:
                out[r[0]] = r[1]
    return out

rows = []
for sub in sorted(glob.glob(f"{d}/random_*")):
    lat, pen, comp = [], [], []
    for p in glob.glob(f"{sub}/results_seed*.csv"):
        if p.endswith("_linkusage.csv"):
            continue
        v = vals(p)
        try:
            lat.append(float(v.get("Latencia media exata sem arredondar ciclos",
                                   v.get("Latencia media regime permanente exclui warmup ciclos"))))
        except (TypeError, ValueError):
            pass
        try: pen.append(float(v["Latencia media penalizada ciclos"]))
        except (KeyError, ValueError): pass
        try: comp.append(float(v["Taxa de conclusao (%)"]))
        except (KeyError, ValueError): pass
    if lat:
        label = os.path.basename(sub)
        rows.append((label, st.mean(lat), st.mean(pen) if pen else float("nan"),
                     st.mean(comp) if comp else float("nan"), len(lat)))

rows.sort(key=lambda r: r[1])
print(f"{'topologia':<14}{'lat(ciclos)':>12}{'lat penaliz.':>14}{'conclusao%':>12}{'N':>4}  config")
for label, l, p, c, n in rows[:top]:
    print(f"{label:<14}{l:>12.2f}{p:>14.2f}{c:>12.1f}{n:>4}  configs/configs_ciclos/config_{label}.json")
print("\n(ordenado pela latencia; confira a conclusao% -- latencia baixa com conclusao baixa e viés)")