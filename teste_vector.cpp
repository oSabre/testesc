
#include <iostream>
#include <vector>
#include <systemc.h>

int sc_main(int argc, char* argv[]) {
    std::vector<std::vector<int>> adj;
    adj.resize(5);
    
    adj[0].push_back(1);
    
    std::cout << "Se voce esta lendo isso, o vector esta funcionando!" << std::endl;
    
    return 0;
}