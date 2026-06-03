#include <systemc.h>
#include "TestIntegrity.h"

int sc_main(int argc, char* argv[]) {
    TestIntegrity test("Integrity_Bateria_1");
    sc_start();
    return 0;
}

//O que faz: Envia padrões binários críticos 
// (0x0000, 0xFFFF, 0xAAAA, 0x5555) para checar se algum bit é invertido ou "preso" durante o chaveamento.

// Por que é importante: Garante a fidelidade dos dados. 
// Verifica se os caminhos de dados (MUX) estão fisicamente íntegros e se não há interferência entre os bits do barramento (crosstalk), 
//assegurando que o que entra é exatamente o que sai.

//O que esperar: A saída deve ser bit a bit idêntica à entrada para cada um dos padrões de teste. 
//Se qualquer bit for diferente, o teste deve disparar um erro de integridade imediato.