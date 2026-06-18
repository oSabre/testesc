import json
import numpy as np
import subprocess
from pymoo.core.problem import ElementwiseProblem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.termination import get_termination

class SystemCProblem(ElementwiseProblem):
    def __init__(self, n_vars, xl, xu, caminho_executavel, caminho_trafego, arquivo_modelo):
        super().__init__(n_var=n_vars, n_obj=2, n_ieq_constr=n_vars, xl=xl, xu=xu)
        self.caminho_executavel = caminho_executavel
        self.caminho_trafego = caminho_trafego
        self.arquivo_modelo = arquivo_modelo

    def _evaluate(self, x, out, *args, **kwargs):
        valores_v = [int(np.round(val)) for val in x]
        
        # 1. Aplicar restrições: Evitar que um nó aponte para si mesmo (u == v)
        # No Pymoo, valores > 0 indicam violação da restrição. Valores <= 0 estão OK.
        restricoes = []
        for i in range(len(valores_v)):
            if valores_v[i] == i:
                restricoes.append(1.0) 
            else:
                restricoes.append(-1.0)
        out["G"] = restricoes

        # Se a topologia quebrar a restrição de loop, penalizamos direto sem rodar o simulador
        if any(g > 0 for g in restricoes):
            out["F"] = [1e9, 1e9]
            return

        # 2. Carregar o template original (config.json)
        with open(self.arquivo_modelo, "r") as f:
            config = json.load(f)
        
        # Reconstruir a lista de topologia dinamicamente mudando apenas o destino 'v'
        nova_topologia = []
        for i in range(len(valores_v)):
            nova_topologia.append({
                "id": i, 
                "u": i, 
                "v": valores_v[i]
            })
        
        config["topology"] = nova_topologia
        
        # 3. Salvar o arquivo temporário que o seu simulador vai ler
        arquivo_temp = "config_atual.json"
        with open(arquivo_temp, "w") as f:
            json.dump(config, f, indent=2)
        
        # 4. Executar o simulador SystemC
        try:
            subprocess.run(
                [self.caminho_executavel, arquivo_temp, self.caminho_trafego],
                check=True,
                capture_output=True,
                text=True
            )
            
            # 5. Ler o resultado gerado pelo simulador
            with open("resultados.json", "r") as f:
                res = json.load(f)
            
            out["F"] = [res["latencia"], res["area"]]
            
        except Exception as e:
            print(f"Erro na simulação para a topologia {valores_v}: {e}")
            out["F"] = [1e9, 1e9] # Penalidade em caso de falha física do simulador

# --- Configuração do Otimizador ---
if __name__ == "__main__":
    # Como temos 4 nós (0, 1, 2, 3), precisamos de 4 variáveis de decisão
    n_vars = 4  
    xl = 0      # ID mínimo do vértice de destino
    xu = 3      # ID máximo do vértice de destino
    
    # Instanciando o problema com todos os parâmetros corretos
    problem = SystemCProblem(
        n_vars=n_vars, 
        xl=xl, 
        xu=xu,
        caminho_executavel="./main.exe",
        caminho_trafego="traces/trace_01.csv", # Caminho ajustado para sua pasta de traces
        arquivo_modelo="config.json"           # Seu arquivo base contendo os "network_params"
    )
    
    # Configuração do Algoritmo NSGA-II
    # pop_size=20 significa que ele testará 20 combinações de topologia por rodada
    algorithm = NSGA2(pop_size=20)
    
    # Critério de parada: 10 gerações (iterações do algoritmo)
    termination = get_termination("n_gen", 10)
    
    print("Iniciando a otimização da topologia com NSGA-II...")
    
    # Executa o processo completo de otimização
    res = minimize(
        problem,
        algorithm,
        termination,
        seed=1,
        save_history=True,
        verbose=True
    )
    
    print("\n--- Otimização Concluída ---")
    print("Melhores configurações de destino 'v' encontradas para os nós [0, 1, 2, 3]:")
    
    # Arredonda e converte o resultado final para exibição limpa em inteiros
    melhores_topologias = np.round(res.X).astype(int)
    print(melhores_topologias)
    
    print("\nRespectivos valores de objetivo encontrados [Latência, Área]:")
    print(res.F)