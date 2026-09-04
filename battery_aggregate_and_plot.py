#!/usr/bin/env python3
"""
battery_aggregate_and_plot.py

Le battery_manifest.txt + os results_seed*.csv de cada combinacao
(topologia x tamanho x padrao de trafego), agrega em media/desvio padrao
entre replicas, escreve um CSV resumo (battery_summary.csv) e gera
graficos de barra comparando as topologias, agrupados por padrao de
trafego -- um par de graficos (latencia, taxa de conclusao) por tamanho
de rede (16 e 64 nos).

Uso: python3 battery_aggregate_and_plot.py [battery_out_dir]
(default do diretorio: battery_out)
"""

import csv
import glob
import sys
import statistics as st
from collections import defaultdict

try:
    import matplotlib
    matplotlib.use("Agg")  # sem display, so salva arquivo -- funciona
                            # em qualquer ambiente, inclusive sem GUI
    import matplotlib.pyplot as plt
except ImportError:
    print("ERRO: matplotlib nao encontrado. Instale com:")
    print("  pip install matplotlib --break-system-packages")
    print("(ou, no MSYS2/MinGW64: pacman -S mingw-w64-x86_64-python-matplotlib)")
    sys.exit(1)


TOPO_ORDER = ["mesh", "fewlinks", "smallworld", "morelinks"]
TRAFFIC_ORDER = ["uniform", "bit_reversal", "butterfly"]
TRAFFIC_LABELS = {
    "uniform": "Uniforme",
    "bit_reversal": "Bit-reversal",
    "butterfly": "Butterfly (shuffle)",
}


def read_manifest(path):
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)
    return rows


def parse_results_dir(result_dir):
    """Le todos os results_seed*.csv de um diretorio, retorna listas de
    latencia (ciclos) e taxa de conclusao (%) entre as replicas."""
    latencies, completions = [], []
    for path in sorted(glob.glob(f"{result_dir}/results_seed*.csv")):
        with open(path, newline="") as f:
            for row in csv.reader(f):
                if not row:
                    continue
                if row[0].startswith("Latencia media regime permanente"):
                    try:
                        latencies.append(float(row[1]))
                    except ValueError:
                        pass
                if row[0].startswith("Taxa de conclusao"):
                    try:
                        completions.append(float(row[1]))
                    except ValueError:
                        pass
    return latencies, completions


def mean_std(values):
    if not values:
        return None, None
    mean = st.mean(values)
    std = st.stdev(values) if len(values) > 1 else 0.0
    return mean, std


def make_grouped_bar_chart(data, size, metric_name, ylabel, filename):
    """data[topology][traffic] = (mean, std). Barras agrupadas por
    topologia, uma cor por padrao de trafego."""
    topologies = [t for t in TOPO_ORDER if t in data]
    traffics = [t for t in TRAFFIC_ORDER if any(t in data[topo] for topo in topologies)]

    n_groups = len(topologies)
    n_bars = len(traffics)
    bar_width = 0.8 / max(n_bars, 1)

    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(n_groups)

    for i, traffic in enumerate(traffics):
        means = []
        stds = []
        for topo in topologies:
            mean, std = data[topo].get(traffic, (None, None))
            means.append(mean if mean is not None else 0)
            stds.append(std if std is not None else 0)
        offsets = [xi + i * bar_width - (bar_width * (n_bars - 1) / 2) for xi in x]
        ax.bar(offsets, means, width=bar_width, yerr=stds, capsize=4,
               label=TRAFFIC_LABELS.get(traffic, traffic))

    ax.set_xticks(list(x))
    ax.set_xticklabels(topologies)
    ax.set_xlabel("Topologia")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{metric_name} -- rede de {size} nos")
    ax.legend(title="Padrao de trafego")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    fig.tight_layout()
    fig.savefig(filename, dpi=150)
    plt.close(fig)
    print(f"  -> grafico salvo: {filename}")


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "battery_out"
    manifest = read_manifest("battery_manifest.txt")

    # latency_data[size][topology][traffic] = (mean, std)
    latency_data = defaultdict(lambda: defaultdict(dict))
    completion_data = defaultdict(lambda: defaultdict(dict))

    summary_rows = []

    for row in manifest:
        topo = row["topology"]
        size = row["size"]
        traffic = row["traffic"]
        result_dir = f"{out_dir}/{topo}_{size}_{traffic}"

        latencies, completions = parse_results_dir(result_dir)
        lat_mean, lat_std = mean_std(latencies)
        comp_mean, comp_std = mean_std(completions)

        summary_rows.append({
            "topology": topo, "size": size, "traffic": traffic,
            "n": len(latencies),
            "latency_mean_cycles": lat_mean, "latency_std_cycles": lat_std,
            "completion_mean_pct": comp_mean, "completion_std_pct": comp_std,
        })

        if lat_mean is not None:
            latency_data[size][topo][traffic] = (lat_mean, lat_std)
        if comp_mean is not None:
            completion_data[size][topo][traffic] = (comp_mean, comp_std)

    # --- CSV resumo ---
    with open("battery_summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)
    print("Resumo escrito: battery_summary.csv\n")

    # --- Tabela no terminal ---
    print(f"{'Topologia':<12} {'Tam.':>4} {'Trafego':<14} {'N':>3} "
          f"{'Latencia (ciclos)':>20} {'Conclusao (%)':>16}")
    print("-" * 78)
    for r in summary_rows:
        lat_str = (f"{r['latency_mean_cycles']:.2f} +/- {r['latency_std_cycles']:.2f}"
                   if r["latency_mean_cycles"] is not None else "N/A")
        comp_str = (f"{r['completion_mean_pct']:.2f} +/- {r['completion_std_pct']:.2f}"
                    if r["completion_mean_pct"] is not None else "N/A")
        print(f"{r['topology']:<12} {r['size']:>4} {r['traffic']:<14} {r['n']:>3} "
              f"{lat_str:>20} {comp_str:>16}")

    # --- Graficos de barra: um par (latencia, conclusao) por tamanho ---
    print("\nGerando graficos...")
    for size in sorted(latency_data.keys()):
        make_grouped_bar_chart(
            latency_data[size], size,
            "Latencia media (regime permanente)", "Ciclos de clock (media +/- desvio padrao)",
            f"battery_latency_{size}.png")
    for size in sorted(completion_data.keys()):
        make_grouped_bar_chart(
            completion_data[size], size,
            "Taxa de conclusao", "Taxa de conclusao (%) (media +/- desvio padrao)",
            f"battery_completion_{size}.png")


if __name__ == "__main__":
    main()