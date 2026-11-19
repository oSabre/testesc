#!/usr/bin/env python3
"""Desenha a topologia de um config.json como grade (no = linha*N + coluna).
Links de mesh (vizinhos na grade) em cinza; links de longo alcance em cor.
Uso: py draw_topology.py config.json [saida.png]"""
import json, math, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from collections import Counter

path = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else path.rsplit(".", 1)[0] + ".png"
links = json.load(open(path))["topology"]
n = max(max(l["u"], l["v"]) for l in links) + 1
side = int(round(math.sqrt(n)))
pos = lambda i: (i % side, side - 1 - i // side)
deg = Counter()
fig, ax = plt.subplots(figsize=(8, 8))
longs = 0
for l in links:
    u, v = l["u"], l["v"]
    deg[u] += 1; deg[v] += 1
    (x1, y1), (x2, y2) = pos(u), pos(v)
    near = abs(x1 - x2) + abs(y1 - y2) == 1
    if near:
        ax.plot([x1, x2], [y1, y2], color="#999999", lw=1.5, zorder=1)
    else:
        longs += 1
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-",
                     connectionstyle="arc3,rad=0.18", color="#d6336c", lw=1.4,
                     alpha=0.8, zorder=2))
for i in range(n):
    x, y = pos(i)
    ax.scatter([x], [y], s=330, c="white", edgecolors="black", zorder=3)
    ax.text(x, y, str(i), ha="center", va="center", fontsize=7, zorder=4)
ax.set_title(f"{path.split('/')[-1]}: {n} nos, {len(links)} links "
             f"({longs} de longo alcance, grau {min(deg.values())}-{max(deg.values())})")
ax.set_aspect("equal"); ax.axis("off")
fig.savefig(out, dpi=150, bbox_inches="tight")
print("Salvo:", out)