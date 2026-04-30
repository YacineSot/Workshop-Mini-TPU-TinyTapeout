# Specify the simulator
SIM ?= verilator  # Default to Icarus Verilog

# Verilog source file
VERILOG_SOURCES = tpu_interface_tb.v tpu_interface.v spi.v tpu.v control.v array.v memory.v pe.v

# Top-level module in Verilog
TOPLEVEL = tpu_interface_tb

# Python test module
MODULE = tpu_interface_tb

EXTRA_ARGS += --trace --trace-structs

# Include Cocotb makefile rules
include $(shell cocotb-config --makefiles)/Makefile.sim
