#!/usr/bin/env python3
"""
rodar_fase3a.py -- bateria da Fase 3, VERSAO A (NSGA-II latencia x area, CUs e core fixos).
Retomavel: pula toda execucao cujo <OUT>/<nome>/summary.json ja existe. Pode parar (Ctrl+C)
e rodar de novo o mesmo comando. Funciona no Windows (py) e no Linux (python3).

Exemplos (Windows, na pasta do simulador):
  py rodar_fase3a.py --bin main.exe --dry-run            # so lista o que rodaria
  py rodar_fase3a.py --bin main.exe --workers 8          # bateria completa
  py rodar_fase3a.py --bin main.exe --patterns uniform --runs 2 --pop 12 --gens 5 --out runs_teste3   # teste curto

Celulas: padrao x configuracao de orcamento x semente do NSGA-II.
  cfg "var"  : L variavel em [84,124], teto de fio = 2.0*L          (orcamentos diferentes)
  cfg "L112" : L = 112 fixo, teto de fio = 1.5*L                     (orcamento igual a mesh)
"""
import argparse, itertools, os, subprocess, sys, time

p = argparse.ArgumentParser()
p.add_argument("--bin", default="main.exe")
p.add_argument("--template", default=os.path.join("configs", "configs_ciclos", "config_mesh_64.json"))
p.add_argument("--out", default="runs_fase3")
p.add_argument("--workers", type=int, default=8)
p.add_argument("--patterns", nargs="+", default=["bit_reversal", "butterfly", "uniform"])
p.add_argument("--cfgs", nargs="+", default=["var", "L112"], choices=["var", "L112"])
p.add_argument("--runs", type=int, default=10)
p.add_argument("--pop", type=int, default=40)
p.add_argument("--gens", type=int, default=40)
p.add_argument("--cus", type=int, default=16)
p.add_argument("--core", default="minor", choices=["minor", "timing", "o3"])
p.add_argument("--ctrl", default="bfs", choices=["bfs", "dij"])
p.add_argument("--flit", type=int, default=64)
p.add_argument("--spacing-ns", type=int, default=6700)
p.add_argument("--duration-us", type=float, default=1700)
p.add_argument("--seed-dirs", nargs="*", default=[],
               help="globs de pastas com best_edges.json (ex.: runs_fase1/*_ga_s*) p/ semear a populacao")
p.add_argument("--dry-run", action="store_true")
a = p.parse_args()

CFG = {"var":  ["--links-min", "84", "--links-max", "124", "--wire-mult", "2.0"],
       "L112": ["--links-min", "112", "--links-max", "112", "--wire-mult", "1.5"]}
here = os.path.dirname(os.path.abspath(__file__))
script = os.path.join(here, "nsga2_optimize.py")
cells = [(c, pat, i) for c in a.cfgs for pat in a.patterns for i in range(1, a.runs + 1)]
todo = 0
t0 = time.time()
for k, (c, pat, i) in enumerate(cells, 1):
    name = f"{pat}_{c}_{a.core}_cu{a.cus}_nsga_s{i}"
    if os.path.exists(os.path.join(a.out, name, "summary.json")):
        continue
    todo += 1
    cmd = [sys.executable, script, "--bin", a.bin, "--template", a.template,
           "--traffic", pat, "--cus", str(a.cus), "--core", a.core, "--ctrl", a.ctrl,
           "--flit", str(a.flit), "--spacing-ns", str(a.spacing_ns), "--duration-us", str(a.duration_us),
           "--pop", str(a.pop), "--gens", str(a.gens), "--train-seeds", "1", "2", "3",
           "--workers", str(a.workers), "--ga-seed", str(i), "--name", name, "--out-root", a.out] + CFG[c]
    if a.seed_dirs:
        cmd += ["--seed-dirs"] + a.seed_dirs
    print(f"[{k}/{len(cells)}] {name}", flush=True)
    if a.dry_run:
        print("   ", " ".join(cmd))
        continue
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"[ERRO] {name} falhou (codigo {r.returncode}); sigo para a proxima. "
              f"Rode de novo depois para retomar.", flush=True)
print(f"fim: {todo} execucao(oes) pendente(s) processada(s) em {time.time()-t0:.0f}s")