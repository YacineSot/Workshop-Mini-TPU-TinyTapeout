# =========================================================
# Mini TPU regression tests — assertion-based.
#
# Tile-fit version: 3x3 array, DATA_WIDTH = ACC_WIDTH = 4.
# All math is mod 16.
# =========================================================
import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

DATA_MASK = 0x0F
N         = 3   # array size

OP_RUN, OP_LOAD, OP_STORE = 0b01, 0b10, 0b11

def make_instr(op, mem_sel=0, row=0, col=0, imm=0):
    return ((op & 3) << 14) | ((mem_sel & 1) << 13) | \
           ((row & 3) << 10) | ((col & 3) << 8) | (imm & 0xff)

async def send_instr(dut, instr):
    dut.ui_in.value  = instr & 0xff
    dut.uio_in.value = instr >> 8
    await RisingEdge(dut.clk)

async def hw_reset(dut, n=3):
    dut.rst_n.value = 0
    for _ in range(n):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

def matmul_ref(a, b):
    c = [[0]*N for _ in range(N)]
    for i in range(N):
        for j in range(N):
            c[i][j] = sum(a[i][k] * b[k][j] for k in range(N)) & DATA_MASK
    return c

async def load_matrices(dut, a, b):
    # A normal layout, B transposed (matches the dataflow).
    for r in range(N):
        for c in range(N):
            await send_instr(dut, make_instr(OP_LOAD, 0, r, c, a[r][c] & DATA_MASK))
    for r in range(N):
        for c in range(N):
            await send_instr(dut, make_instr(OP_LOAD, 1, r, c, b[c][r] & DATA_MASK))

async def read_matrix(dut):
    out = [[0]*N for _ in range(N)]
    for r in range(N):
        for c in range(N):
            await send_instr(dut, make_instr(OP_STORE, 0, r, c))
            await Timer(1, unit="ns")
            out[r][c] = int(dut.uo_out.value) & DATA_MASK
    return out

async def run_once(dut, a, b, run_cycles=2*N + 3):
    # 2N + 3 RUN cycles is enough drain time for an NxN OS systolic array.
    await hw_reset(dut)
    await load_matrices(dut, a, b)
    for _ in range(run_cycles):
        await send_instr(dut, make_instr(OP_RUN))
    return await read_matrix(dut)

def assert_eq(dut, name, hw, sw):
    mismatches = []
    for i in range(N):
        for j in range(N):
            if hw[i][j] != sw[i][j]:
                mismatches.append((i, j, hw[i][j], sw[i][j]))
    if mismatches:
        dut._log.error(f"FAIL {name}")
        dut._log.error(f"  HW: {hw}")
        dut._log.error(f"  SW: {sw}")
        for i, j, h, s in mismatches:
            dut._log.error(f"  C[{i}][{j}] hw={h} sw={s}")
    assert not mismatches, f"{name}: {len(mismatches)} mismatches"


def rand_mat(rng, hi=DATA_MASK):
    return [[rng.randint(0, hi) for _ in range(N)] for _ in range(N)]


# =========================================================
@cocotb.test()
async def test_identity(dut):
    """A * I = A and I * A = A"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.ena.value, dut.ui_in.value, dut.uio_in.value = 1, 0, 0

    I = [[1 if i == j else 0 for j in range(N)] for i in range(N)]
    A = [[1, 2, 3], [5, 6, 7], [9, 10, 11]]

    hw = await run_once(dut, A, I)
    assert_eq(dut, "A*I", hw, matmul_ref(A, I))

    hw = await run_once(dut, I, A)
    assert_eq(dut, "I*A", hw, matmul_ref(I, A))


@cocotb.test()
async def test_zero(dut):
    """0 * X = 0 and X * 0 = 0"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.ena.value, dut.ui_in.value, dut.uio_in.value = 1, 0, 0

    Z = [[0]*N for _ in range(N)]
    X = [[7, 13, 9], [3, 5, 14], [2, 8, 6]]

    hw = await run_once(dut, Z, X)
    assert_eq(dut, "Z*X", hw, matmul_ref(Z, X))

    hw = await run_once(dut, X, Z)
    assert_eq(dut, "X*Z", hw, matmul_ref(X, Z))


@cocotb.test()
async def test_diagonal(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.ena.value, dut.ui_in.value, dut.uio_in.value = 1, 0, 0

    A = [[1, 2, 3], [5, 6, 7], [9, 10, 11]]
    D = [[2, 0, 0], [0, 3, 0], [0, 0, 4]]

    hw = await run_once(dut, A, D)
    assert_eq(dut, "A*D", hw, matmul_ref(A, D))

    hw = await run_once(dut, D, A)
    assert_eq(dut, "D*A", hw, matmul_ref(D, A))


@cocotb.test()
async def test_overflow_truncation(dut):
    """4-bit accumulator wraparound matches the spec (mod 16)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.ena.value, dut.ui_in.value, dut.uio_in.value = 1, 0, 0

    A = [[15]*N for _ in range(N)]
    B = [[15]*N for _ in range(N)]

    hw = await run_once(dut, A, B)
    assert_eq(dut, "overflow", hw, matmul_ref(A, B))


@cocotb.test()
async def test_random(dut):
    """50 random 4-bit matrices."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.ena.value, dut.ui_in.value, dut.uio_in.value = 1, 0, 0

    rng = random.Random(0xC0DE)
    for trial in range(50):
        A = rand_mat(rng)
        B = rand_mat(rng)
        hw = await run_once(dut, A, B)
        assert_eq(dut, f"rand-{trial}", hw, matmul_ref(A, B))


@cocotb.test()
async def test_back_to_back(dut):
    """Two consecutive matmuls; both must match."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.ena.value, dut.ui_in.value, dut.uio_in.value = 1, 0, 0

    rng = random.Random(0xDEAD)
    A1, B1 = rand_mat(rng), rand_mat(rng)
    A2, B2 = rand_mat(rng), rand_mat(rng)

    hw1 = await run_once(dut, A1, B1)
    assert_eq(dut, "b2b-1", hw1, matmul_ref(A1, B1))

    hw2 = await run_once(dut, A2, B2)
    assert_eq(dut, "b2b-2", hw2, matmul_ref(A2, B2))
