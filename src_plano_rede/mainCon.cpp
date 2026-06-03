#include <systemc.h>
#include "ConnectivityTest.h"

int sc_main(int argc, char* argv[]) {
    ConnectivityTest test("Connectivity_Bateria_1");
    sc_start();
    return 0;
}

// O que faz: Envia um único flit de teste através de uma rota pré-configurada e verifica se ele chega exatamente igual à saída.

//Por que é importante: É o teste de sanidade ("Smoke Test"). 
//Se este falhar, a estrutura básica do barramento, os multiplexadores ou o roteamento lógico interno estão quebrados.

// O que esperar: O log deve confirmar que o ID enviado na entrada (in_data) 
// aparece identicamente na saída (out_data) no ciclo de processamento esperado, sem erros de valor.