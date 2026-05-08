# =========================================================
# Mini TPU Test
# =========================================================
import random
import cocotb
from cocotb.clock     import Clock
from cocotb.triggers  import RisingEdge, Timer
#from cocotb.handle import NonHierarchyIndexableObject



## Port assignment:
# ui_in[0]: mosi
# ui_in[1]: cs
# ui_in[2]: sck
# uio_out[0]: miso
# ui_out : result

# Instruction Encoding
OP_RUN, OP_LOAD, OP_STORE = 0b01, 0b10, 0b11

def make_instr(op, mem_sel=0, row=0, col=0, imm=0):
    return ((op & 3) << 10) | ((mem_sel & 1) << 9) | \
           ((row & 3) << 6) | ((col & 3) << 2) | (imm & 0xf)


async def await_for_data_received(dut):
    # print ("Waiting for data to be received...")
    spi = dut.user_project.uut_tpu_interface.uut_spi
    data = 0
    while 1:
        is_sending = spi.is_sending.value
        if not is_sending:
            break
        data = (data << 1) | int(spi.miso.value)
        dut.ui_in.value = int(dut.ui_in.value) | 4  # sclk=1
        await RisingEdge(dut.clk)  #  sck=1
        await RisingEdge(dut.clk)  #  sck=1
        dut.ui_in.value = int(dut.ui_in.value) & 0xfb  # sclk=0
        await RisingEdge(dut.clk)  #  sclk=0 
        await RisingEdge(dut.clk)  #  sclk=0 
    # print (f"Receiving... MISO={spi.miso.value}, current_data={data:035b}")

# async def send_instr(dut, instr):
#     dut.ui_in.value  = instr & 0xff
#     dut.uio_in.value = instr >> 8
#     await RisingEdge(dut.clk)
async def send_instr(dut, instr):
    dut.ui_in.value = int(dut.ui_in.value) & 0xf9 # Ensure CS=1
    await RisingEdge(dut.clk)  # CS=1 
    spi = dut.user_project.uut_tpu_interface.uut_spi
    # tpu = dut.user_project.uut_tpu_interface.uut_tpu
    #print (f"CS state: {dut.user_project.uut_tpu_interface.uut_spi.cs.value}")
    for i in range(12):
        bit = ((instr >> i) & 1) | 4
        dut.ui_in.value = (int(dut.ui_in.value) & 0xfa) | bit  # mosi
        await RisingEdge(dut.clk)  #  sck = 1
        await RisingEdge(dut.clk)  #  sck  = 1
        if spi.is_sending.value:
            await await_for_data_received(dut)
        # print(f"Sent bit {i}: {bit&1}, CS={spi.cs.value}, SCK={spi.sclk.value}, bit_counter={int(spi.bit_counter.value)}")
        dut.ui_in.value = int(dut.ui_in.value) & 0xfb  # sclk=0
        # if spi.data_ready.value:
        #     print (f"Sent instruction: {spi.data_buffer_output.value} as {instr:12b}")
        #     print(f"Tpu instruction: {tpu.instruction.value}")
        await RisingEdge(dut.clk)  #  sclk=0 
        await RisingEdge(dut.clk)  #  sclk=0
    
    # await RisingEdge(dut.clk)  # Ensure last bit is processed
    
    
    
       #print (f"Sending bit {i}: {bit}, CS={spi.cs.value}, SCK={spi.sclk.value}")
    
    #dut.ui_in.value = int(dut.ui_in.value) | 2  # CS=0
    #await RisingEdge(dut.clk)

# Reset
async def hw_reset(dut, n=3):
    dut.rst_n.value = 0
    for _ in range(n):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

# 4×4 Matrix Multiplication
def matmul_ref(a, b):
    n = len(a)
    c = [[0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            c[i][j] = sum(a[i][k] * b[k][j] for k in range(n)) & 0xf
    return c

# LOAD A、B
async def load_matrices(dut, a, b):
    for r in range(3):
        for c in range(3):
            await send_instr(dut, make_instr(OP_LOAD, 0, r, c, a[r][c]))
    for r in range(3):
        for c in range(3):
            await send_instr(dut, make_instr(OP_LOAD, 1, r, c, b[c][r]))

# STORE
async def read_matrix(dut):
    out = [[0]*3 for _ in range(3)]
    for r in range(3):
        for c in range(3):
            await send_instr(dut, make_instr(OP_STORE, 0, r, c))
            await Timer(1, units="ns")        # 
            out[r][c] = int(dut.uo_out.value)
    return out

# Matrix Multiplication
async def run_once(dut, a, b):
    await hw_reset(dut)
    await load_matrices(dut, a, b)

    # 11 Cycle, RUN=1
    await send_instr(dut, make_instr(OP_RUN))
    for _ in range(9):
        await RisingEdge(dut.clk)

    hw_out = await read_matrix(dut)
    sw_out = matmul_ref(a, b)
    return hw_out, sw_out

# Print Matrix
def log_matrix(dut, title, mat):
    dut._log.info(f"--- {title} ---")
    for i, row in enumerate(mat):
        dut._log.info(f"Row {i}: {row}")

# =========================================================
async def generate_clock(dut, bit_index, period_ns):
    period_sec = period_ns / 1e9
    while True:
        # Read current value, set the bit, write back
        current = int(dut.ui_in.value)
        # Set the bit
        current |= (1 << bit_index)
        dut.ui_in.value = current
        await Timer(period_sec/2, units='sec')
        
        # Clear the bit
        current = int(dut.ui_in.value)
        current &= ~(1 << bit_index)
        dut.ui_in.value = current
        await Timer(period_sec/2, units='sec')


@cocotb.test()
async def Test_TPU(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    #ui_in_view = NonHierarchyIndexableObject(dut.ui_in)
    #cocotb.start_soon(Clock(dut.sck, 20, units="ns").start())  # sck
    #cocotb.start_soon(generate_clock(dut, bit_index=2, period_ns=20))
    dut.ena.value, dut.ui_in.value, dut.uio_in.value = 1, 0, 0
    dut.ui_in.value = int(dut.ui_in.value) | 2 # Ensure CS=0 at start

    cocotb.log.info("\nStart Testing TPU\n")

    async def test_and_log(A: list, B: list):
        hw_res, sw_res = await run_once(dut, A, B)

        log_matrix(dut, "Matrix A", A)
        log_matrix(dut, "Matrix B", B)
        log_matrix(dut, "SW  Result (A×B)", sw_res)
        log_matrix(dut, "HW  Result", hw_res)
        print("\n")

    I = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

    zero = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]

    await test_and_log(I, zero)

    A = [[1,2,3],[5,6,7],[9,10,11]]
    B = [[2,0,0],[0,3,0],[0,0,4]]

    await test_and_log(A, I)
    await test_and_log(B, I)
    await test_and_log(A, B)

    A = [[(i + j) % 2 for j in range(3)] for i in range(3)]
    B = [[(i * j) % 2 for j in range(3)] for i in range(3)]
    await test_and_log(A, B)

    A = [[5, 5, 5] for _ in range(3)]  # all rows identical
    B = [[1, 2, 3]] * 3       # all columns identical
    await test_and_log(A, B)

    for _ in range(3):
        A = [[random.randint(0, 15) for _ in range(3)] for _ in range(3)]
        B = [[random.randint(0, 15) for _ in range(3)] for _ in range(3)]

        await test_and_log(A, B)
