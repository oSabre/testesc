#include "SDN_Controller.h"

SDN_Controller::SDN_Controller(sc_module_name name, int num_cus):
    sc_module(name),
    internal_fifo_to_arb("internal_fifo", 100),
    num_cus(num_cus),
    cu_buses("cu_buses", num_cus){
        arb = new Arbitro("arb", num_cus);
        arb->clk(clk);
        arb->requisitions_in(internal_fifo_to_arb);

        cus.init(num_cus);
        for(int i = 0; i < num_cus; i++){
            std::string cu_name = "CU_" + std::to_string(i);
            cus[i] = ControlUnit(cu_name.c_str());

            arb->cu_request_ports[i](cu_buses[i]);
            cus[i]->request_in(cu_buses[i]);
        }

        SC_METHOD(bridge_port_to_fifo);
        sensitive << clk.pos();
    }

void SDN_Controller::bridge_port_to_fifo(){
    if(requisitions_in.event() && internal_fifo_to_arb.num_free() > 0){
        internal_fifo_to_arb.write(requisitions_in.read());
    }
}