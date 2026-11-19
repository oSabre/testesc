# Estudo GA (pymoo) — latência mono-objetivo, 8x8, 112 links

## Instalação (uma vez)
    py -m pip install pymoo matplotlib      # (ou python3 -m pip ...)

## Arquivos
| Arquivo | Função |
|---|---|
| ga_common.py | Topologia canônica (arestas ordenadas), validade (grau≤4, conexa, 112 links), reparo, crossover/mutação, **Evaluator** (roda o main.exe em pasta temporária; fitness = média da latência **penalizada**; cache em disco) |
| ga_select_topk.py | Avalia as `config_random_*` (112 links) nas seeds de treino, pega as `--pre` melhores e **reavalia em seeds novas** (corrige o viés de seleção); salva `topk_<padrão>_cu<k>.json` |
| ga_optimize.py | GA (pymoo) ou busca aleatória (mesmo orçamento). `--init seeded` (top-k + mesh + small-world + aleatórias) ou `--init random` (controle) |
| ga_final_eval.py | Reavalia as melhores (e mesh/small-world) em **seeds novas** nos 3 padrões: matriz de generalização, Welch vs mesh, gráfico |
| run_ga_battery.sh | Orquestra tudo, para cada padrão e nº de CUs |
| mock_sim.py | Simulador FALSO só para testar o pipeline (não usar para conclusões) |

## Teste rápido do pipeline (sem SystemC, ~1 min)
    BIN="python3 mock_sim.py" CUS="2" POP=8 GENS=2 PRE=5 KEEP=3 REPLICAS=3 ./run_ga_battery.sh

## Execução real (pasta com main.exe, configs/configs_ciclos/ e estes scripts)
    # 1) teste pequeno com o simulador de verdade:
    CUS="2" POP=6 GENS=2 PRE=4 KEEP=3 REPLICAS=3 PATTERNS="uniform" ./run_ga_battery.sh
    # 2) bateria completa (padrão: CUS="1 2", POP=30, GENS=40):
    ./run_ga_battery.sh
Variáveis úteis: `CUS`, `POP`, `GENS`, `WORKERS` (simulações em paralelo), `TRAIN_SEEDS`,
`REPLICAS` (avaliação final), `PATTERNS`, `DURATION_US`, `NUM_PACKETS`, `BIN`, `CFG_DIR`.

Custo: simulações por execução do GA ≈ POP×(GENS+1)×nº de seeds de treino (30×41×3 ≈ 3.700).
Há 3 execuções (GA semeado, GA aleatório, busca aleatória) por padrão e por nº de CUs.
Reexecutar o mesmo comando reaproveita o cache (`runs/<nome>/cache.jsonl`).

## Saídas
- `runs/<padrão>_cu<k>_<ga_seeded|ga_random|random_search>/`: `history.csv` (convergência),
  `best_config.json` (pronto para o main.exe), `best_edges.json`, `all_evals.csv`, `summary.json`
- `topk_<padrão>_cu<k>.json`: top-k aleatórias reavaliadas
- `final_eval_cu<k>.csv/.png`: avaliação final (seeds 1000..1009), 3 padrões × candidatas

## Decisões metodológicas (para citar)
- Fitness = latência média **penalizada** (fluxo não concluído conta com a duração total da simulação).
- Seeds de treino **fixas** durante o GA (fitness determinística); avaliação final em seeds **novas**.
- Cada réplica usa `traffic.seed = injection.seed = simulation.seed` (tráfego e rajadas diferentes por réplica).
- Arestas sempre em ordem canônica (portas/desempate do Dijkstra dependem da ordem dos links).
- Operadores com reparo: sempre 112 links, grau≤4, grafo conexo.
- CUs e demais hiperparâmetros são **fatores do experimento** (`--cus`, `--np chave=valor`, `--duration-us`), não genes.
- Controles: GA só aleatório (semear ajudou?) e busca aleatória com o mesmo nº de avaliações (GA > sorteio?).
- Limitação: com o plano de controle dominando a latência, o ótimo reflete esse regime; repetir depois de tratá-lo.
