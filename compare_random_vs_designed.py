#!/usr/bin/env python3
"""
compare_random_vs_designed.py

Compara as topologias desenhadas a mao (mesh, small-world, fewlinks,
morelinks -- 64 nos) contra a DISTRIBUICAO de desempenho das 50
topologias aleatorias (mesmo orcamento de links da mesh/small-world: 112).

Calcula o percentil de cada topologia desenhada dentro da distribuicao
aleatoria e gera um histograma marcando onde cada uma cai.

IMPORTANTE: fewlinks (93 links) e morelinks (128 links) tem orcamento
DIFERENTE do lote aleatorio (112 links) -- a comparacao de desempenho
absoluto contra eles e ilustrativa, mas nao é "mesmo orcamento". Só mesh
e small-world sao diretamente comparaveis em pe de igualdade com este
lote aleatorio especifico.

Uso: python3 compare_random_vs_designed.py [random_out_dir] [designed_out_dir]
Defaults: random_out, battery_out
"""

import csv
import glob
import json
import sys
import statistics as st

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    print("ERRO: matplotlib nao encontrado. Instale com:")
    print("  py -m pip install matplotlib   (Windows)")
    print("  pip install matplotlib --break-system-packages   (Linux/Mac)")
    sys.exit(1)


def parse_results_dir(result_dir):
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


def mean_or_none(values):
    return st.mean(values) if values else None


def percentile_rank(value, distribution):
    """% da distribuicao que e PIOR (maior latencia) que `value` --
    quanto maior o percentil, melhor a topologia se saiu comparada ao
    lote aleatorio."""
    if value is None or not distribution:
        return None
    better_or_equal = sum(1 for d in distribution if d >= value)
    return 100.0 * better_or_equal / len(distribution)


def main():
    random_dir = sys.argv[1] if len(sys.argv) > 1 else "random_out_112"

    # Cada comparacao extra: "rotulo:caminho_do_resultado:links"
    # Se nenhuma for passada, usa o default historico (as 4 topologias
    # desenhadas, lote de 112 links, contra battery_out/).
    extra_args = sys.argv[2:]
    if extra_args:
        designed = {}
        for arg in extra_args:
            label, path, links = arg.split(":")
            designed[label] = (path, int(links))
    else:
        designed = {
            "mesh":       ("battery_out/mesh_64_uniform", 112),
            "smallworld": ("battery_out/smallworld_64_uniform", 112),
            "fewlinks":   ("battery_out/fewlinks_64_uniform", 93),
            "morelinks":  ("battery_out/morelinks_64_uniform", 128),
        }

    # --- Coleta a distribuicao das topologias aleatorias deste lote ---
    random_latencies = []
    random_dirs = sorted(glob.glob(f"{random_dir}/random_*"))
    if not random_dirs:
        print(f"ERRO: nenhum resultado encontrado em '{random_dir}/random_*'. "
              "Rode run_random_battery.sh primeiro.")
        sys.exit(1)

    for d in random_dirs:
        lat, _ = parse_results_dir(d)
        m = mean_or_none(lat)
        if m is not None:
            random_latencies.append(m)

    # Descobre o orcamento de links REAL deste lote (lendo o config de uma
    # das topologias), em vez de assumir 112 -- os lotes de 93/128 tambem
    # usam este mesmo script.
    random_budget = None
    if random_dirs:
        sample_label = random_dirs[0].split("/")[-1]  # "random_1234"
        sample_config = f"config_{sample_label}.json"
        try:
            with open(sample_config) as f:
                random_budget = len(json.load(f)["topology"])
        except (FileNotFoundError, KeyError):
            pass

    print(f"Distribuicao aleatoria: {len(random_latencies)}/{len(random_dirs)} "
          "topologias com dado valido.")
    if len(random_latencies) >= 2:
        print(f"  media={st.mean(random_latencies):.2f}  "
              f"desvio={st.stdev(random_latencies):.2f}  "
              f"min={min(random_latencies):.2f}  max={max(random_latencies):.2f}\n")
    elif len(random_latencies) == 1:
        print(f"  unico valor={random_latencies[0]:.2f} (n=1, sem desvio padrao)\n")

    print(f"{'Topologia':<12} {'Links':>6} {'Latencia media':>16} {'Percentil vs random':>22}")
    print("-" * 60)

    designed_results = {}
    for label, (path, links) in designed.items():
        lat, _ = parse_results_dir(path)
        m = mean_or_none(lat)
        designed_results[label] = (m, links)
        if m is None:
            print(f"{label:<12} {links:>6} {'N/A':>16} {'N/A':>22}")
            continue
        pct = percentile_rank(m, random_latencies)
        same_budget_note = "" if links == random_budget else "  (orcamento DIFERENTE!)"
        pct_str = f"{pct:.1f}%{same_budget_note}" if pct is not None else "N/A"
        print(f"{label:<12} {links:>6} {m:>16.2f} {pct_str:>22}")

    budget_str = str(random_budget) if random_budget is not None else "desconhecido"
    print(f"\nOrcamento do lote aleatorio detectado: {budget_str} links.")
    print("Leitura do percentil: '85%' significa que a topologia desenhada foi")
    print(f"mais rapida (menor latencia) que 85% das {len(random_latencies)} topologias")
    print("aleatorias -- valido em pe de igualdade so quando 'Links' bate com o")
    print("orcamento do lote acima; comparacoes marcadas 'orcamento DIFERENTE' sao")
    print("apenas ilustrativas.\n")

    # --- Grafico: histograma da distribuicao aleatoria + marcadores ---
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(random_latencies, bins=15, color="lightgray", edgecolor="black",
            label="Topologias aleatorias (n=%d)" % len(random_latencies))

    colors = {"mesh": "tab:red", "smallworld": "tab:blue",
              "fewlinks": "tab:orange", "morelinks": "tab:green"}
    for label, (m, links) in designed_results.items():
        if m is None:
            continue
        style = "-" if links == random_budget else "--"
        ax.axvline(m, color=colors[label], linestyle=style, linewidth=2,
                   label=f"{label} ({links} links)")

    ax.set_xlabel("Latencia media (ciclos de clock)")
    ax.set_ylabel("Numero de topologias aleatorias")
    ax.set_title("Topologias desenhadas vs. distribuicao de topologias aleatorias\n"
                 f"(64 nos, trafego uniforme -- linha solida = mesmo orcamento de {budget_str} links)")
    ax.legend(fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    fig.tight_layout()
    fig.savefig("random_vs_designed_histogram.png", dpi=150)
    plt.close(fig)
    print("Grafico salvo: random_vs_designed_histogram.png")

    # --- CSV com a distribuicao completa, para analise posterior ---
    with open("random_topologies_latency.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["random_topology_idx", "latency_mean_cycles"])
        for i, lat in enumerate(random_latencies):
            writer.writerow([i, lat])
    print("Distribuicao completa salva: random_topologies_latency.csv")


if __name__ == "__main__":
    main()