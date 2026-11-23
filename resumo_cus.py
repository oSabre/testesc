#!/usr/bin/env python3
"""Resume as varreduras: python3 resumo_cus.py [prefixo, ex.: final_eval_bfs_r1_rho0.5]
Le <prefixo>_cu<C>.csv (colunas: candidate,pattern,mean,std,completion,p_vs_ref,delta_vs_ref_pct).
Por CU e padrao: latencia da mesh, conclusao minima, nº de candidatas (treinadas) melhores/piores
que a mesh com p<0.05, faixa de delta% e o small-world. Celulas com conclusao < 100% sao marcadas SAT."""
import csv, glob, re, sys

prefix = sys.argv[1] if len(sys.argv) > 1 else "final_eval_bfs_r1_rho0.5"
files = [f for f in glob.glob(prefix + "_cu*.csv") if re.search(r"_cu\d+\.csv$", f)]
files.sort(key=lambda f: int(re.search(r"_cu(\d+)\.csv$", f).group(1)))
if not files:
    sys.exit("nenhum arquivo %s_cu*.csv" % prefix)
print("%-4s %-12s %9s %7s %-4s %6s %6s | %5s %5s %-17s | %s" % ("CUs", "padrao", "mesh", "conc%", "", "ni%", "pr%", "melh", "pior", "delta% (treinadas)", "small-world"))
print("  ni% = fluxos NAO INICIADOS (janela curta), pr% = presos em roteamento (fila do controle), em % dos fluxos; so ni%=0 e pr%~0 indicam janela adequada")
for f in files:
    c = int(re.search(r"_cu(\d+)\.csv$", f).group(1))
    rows = list(csv.DictReader(open(f)))
    alarm = {}
    af = f[:-4] + '_completion_alarm.csv'
    import os
    # ignora alarme velho: a rodada nova nao reescreve o arquivo quando nao ha alarme
    if os.path.exists(af) and os.path.getmtime(af) >= os.path.getmtime(f) - 120:
        for a_ in csv.DictReader(open(af)):
            pat_ = a_['context'].split()[0]
            d_ = alarm.setdefault(pat_, [0.0, 0.0]); d_[0] += float(a_['nao_iniciados']); d_[1] += float(a_['presos_roteamento'])
    for pat in sorted({r["pattern"] for r in rows}):
        rp = [r for r in rows if r["pattern"] == pat]
        mesh = next(r for r in rp if r["candidate"] == "mesh")
        sw = next((r for r in rp if r["candidate"] == "smallworld"), None)
        tr = [r for r in rp if r["candidate"] not in ("mesh", "smallworld")]
        minc = min(float(r["completion"]) for r in rp)
        d = [float(r["delta_vs_ref_pct"]) for r in tr]
        better = sum(1 for r in tr if float(r["delta_vs_ref_pct"]) < 0 and float(r["p_vs_ref"]) < 0.05)
        worse = sum(1 for r in tr if float(r["delta_vs_ref_pct"]) > 0 and float(r["p_vs_ref"]) < 0.05)
        swtxt = "%+.1f%% (p=%.3f)" % (float(sw["delta_vs_ref_pct"]), float(sw["p_vs_ref"])) if sw else "-"
        nsim = len({x["candidate"] for x in rp}) * 10 * 100.0   # candidatas x 10 seeds x 100 fluxos
        ni, pr = (alarm.get(pat, [0, 0])[0] / nsim * 100, alarm.get(pat, [0, 0])[1] / nsim * 100)
        print("%-4d %-12s %9.0f %7.1f %-4s %6.2f %6.2f | %2d/%-2d %2d/%-2d %+6.1f a %+6.1f      | %s" % (
            c, pat, float(mesh["mean"]), minc, "SAT" if minc < 99.95 else "", ni, pr, better, len(tr), worse, len(tr),
            min(d), max(d), swtxt))