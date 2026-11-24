SC_ROOT = /d/Codigos/systemc-3.0.2/systemc-3.0.2
SC_SRC = $(SC_ROOT)/src
SC_OBJ = $(SC_ROOT)/objdir/src
SC_SRC2 = $(SC_ROOT)/srcs
CXX = g++
CXXFLAGS = -I./include -I./srcs -I./tests_plano_rede -I./test_plano_control -I$(SC_SRC) -I$(SC_OBJ) -Wall -O2
LDFLAGS = -L$(SC_OBJ)/.libs -lsystemc
MAIN_SOURCES = main.cpp \
               srcs/Stats.cpp \
               srcs/TrafficInjector.cpp \
               srcs/arbitro.cpp \
               srcs/sdn_controller.cpp \
			   srcs/ControlUnit.cpp

all: con.exe back.exe reset.exe burst.exe integrity.exe testevec.exe main.exe conpl.exe

conpl.exe: test_plano_control/TestControlPlane.cpp
	$(CXX) $(CXXFLAGS) test_plano_control/TestControlPlane.cpp  test_plano_control/Stats.cpp -o test_plano_control/conpl.exe $(LDFLAGS)

# ---- Linux: SystemC 2.3.3 em ~/systemc-2.3.3 (sobrescreva com: make SC_HOME=/outro/caminho main.exe) ----
# Aceita SystemC instalado (include/ e lib-linux64/) ou a arvore de fontes ja compilada (src/ e src/.libs).
SC_HOME   ?= $(HOME)/systemc-2.3.3
SC_INCDIR := $(firstword $(wildcard $(SC_HOME)/include $(SC_HOME)/src))
SC_LIBDIR := $(firstword $(wildcard $(SC_HOME)/lib-linux64 $(SC_HOME)/lib-linux $(SC_HOME)/lib $(SC_HOME)/src/.libs))
# Sem -std de proposito: a biblioteca 2.3.3 checa o padrao C++ no link (sc_api_version_*_cxx...),
# entao o padrao deve ser o mesmo usado para compilar o SystemC (o padrao do g++ da maquina).
LINUX_CXXFLAGS = -I./include -I./srcs -I./tests_plano_rede -I./test_plano_control -I$(SC_INCDIR) -Wall -O2
LINUX_LDFLAGS  = -L$(SC_LIBDIR) -Wl,-rpath,$(SC_LIBDIR) -lsystemc -lpthread

main.exe: main.cpp
	@test -f $(SC_INCDIR)/systemc.h || { echo "ERRO: systemc.h nao encontrado em '$(SC_INCDIR)' (SC_HOME=$(SC_HOME))."; exit 1; }
	@test -n "$(wildcard $(SC_LIBDIR)/libsystemc*)" || { echo "ERRO: libsystemc nao encontrada em '$(SC_LIBDIR)'. O SystemC precisa estar compilado (configure, make, make install)."; exit 1; }
	$(CXX) $(LINUX_CXXFLAGS) $(MAIN_SOURCES) -o main.exe $(LINUX_LDFLAGS)

wmain.exe: main.cpp
	$(CXX) $(CXXFLAGS) $(MAIN_SOURCES) -o main.exe $(LDFLAGS)

testvec.exe: teste_vector.cpp
	$(CXX) $(CXXFLAGS) teste_vector.cpp -o testevec.exe $(LDFLAGS)

con.exe: src_plano_rede/mainCon.cpp
	$(CXX) $(CXXFLAGS) src_plano_rede/mainCon.cpp -o tests_plano_rede/con.exe $(LDFLAGS)

back.exe: src_plano_rede/mainBack.cpp
	$(CXX) $(CXXFLAGS) src_plano_rede/mainBack.cpp -o tests_plano_rede/back.exe $(LDFLAGS)

reset.exe: src_plano_rede/mainRst.cpp
	$(CXX) $(CXXFLAGS) src_plano_rede/mainRst.cpp -o tests_plano_rede/reset.exe $(LDFLAGS)

burst.exe: src_plano_rede/mainBurst.cpp
	$(CXX) $(CXXFLAGS) src_plano_rede/mainBurst.cpp -o tests_plano_rede/burst.exe $(LDFLAGS)

integrity.exe: src_plano_rede/mainIntegrity.cpp
	$(CXX) $(CXXFLAGS) src_plano_rede/mainIntegrity.cpp -o tests_plano_rede/integrity.exe $(LDFLAGS)

cleanmain:
	rm -f main.exe

clean:
	rm -f main.exe tests_plano_rede/con.exe tests_plano_rede/back.exe tests_plano_rede/reset.exe tests_plano_rede/burst.exe tests_plano_rede/integrity.exe test_plano_control/conpl.exe