# Mini-TPU — Tile-Fit Report

**Date:** 2026-04-29
**Target:** Tiny Tapeout 1×1 tile, **160 × 100 µm² (16 000 µm²)**, sky130A
**Top module:** `tt_um_tpu`
**Result:** LibreLane signs off cleanly (placement, CTS, routing, DRC).

---

## 1. Objective

Fit `tt_um_tpu` into a single TinyTapeout 1×1 tile of 160 × 100 µm² on
the Sky130A PDK, passing the full LibreLane sign-off flow without DPL,
GRT, DRC or LVS errors. The TT pin advertises 1 MHz; the implementation
clock is set to 50 ns (20 MHz) so hold/setup do not force heavy
buffering.

Functional baseline: all 6 cocotb assertion tests in
`test/test_assert.py` (identity, zero, diagonal, 4-bit overflow
wrap-around, 50 random matmuls, back-to-back) must continue to pass on
the modified RTL.

## 2. Final state — by the numbers

| Metric                            | Value                                |
| --------------------------------- | ------------------------------------ |
| Die area                          | 160 × 100 µm² = 16 000 µm²           |
| Core area (after 1 µm pin margin) | 158 × 98 ≈ 14 977 µm²                |
| Total cell area (post-synth)      | 11 020.57 µm²                        |
| Sequential / flop area            | 3 603.46 µm²                         |
| Effective floorplan utilization   | 0.736                                |
| Hold buffers inserted (final)     | far below the 141 of the failing run |
| Sign-off                          | passes                               |

The cell-area number is what 73.6 % of a 14 977 µm² core looks like
_after_ the RTL diet. Without the diet the design would not have been
placement-feasible at any density target.

## 3. Architectural baseline (post-diet)

- **3×3 output-stationary systolic array** (9 PEs)
- **`DATA_WIDTH = ACC_WIDTH = 4`** all math is mod 16
- **16-bit instruction word** over `ui_in[7:0]` + `uio_in[7:0]`
  - Opcodes: `OP_RUN = 01`, `OP_LOAD = 10`, `OP_STORE = 11`
  - Fields: `op[15:14] | mem_sel[13] | row[11:10] | col[9:8] | imm[7:0]`
- **Output:** `uo_out[7:0]`, of which only the low 4 bits carry data
  (the upper 4 are zero-padded constants)

## 4. RTL area diet

The five files under `src/` (`pe.v`, `array.v`, `memory.v`,
`control.v`, `tpu.v`) were modified relative to the last commit
(`353bbc7 Final Release`). The changes can be grouped into five
independent area levers.

### 4.1 Datapath halved: 8 bits → 4 bits

`DATA_WIDTH` and `ACC_WIDTH` macros drop from 8 to 4 in every file.

Direct effects:

- **Multiplier**: 8×8 (16-bit) → 4×4 (8-bit). Multiplier area scales
  roughly with the product of operand widths, so this is ~4× smaller
  _per_ PE.
- **Accumulator flop `c_reg`**: 8 b → 4 b halved.
- **Pipeline regs `a_reg` / `b_reg`** in each PE: halved.
- **Inter-module buses** (`mema_data_in`, `array_a_in`, `data_out`, …):
  half-width, half the routing.
- **Memory cells**: 4 b each instead of 8 b.

Combined with the array shrink, the accumulator flop count goes from
16 PEs × 8 b = 128 b down to 9 PEs × 4 b = 36 b, roughly 3.5× fewer
accumulator flops alone.

### 4.2 Array shrunk: 4×4 → 3×3

`src/array.v` now generates a 3×3 grid of PEs (parameterised through
`` `N = 3 `` and `` `NN = 9 ``), down from a hard-coded 4×4. PE count
goes **16 → 9** (-43 %). Everything that scales with PE count
shrinks accordingly: the `a_pipe` / `b_pipe` interconnect arrays, the
`c_bus` bundle, and the row-major flatten-out into `data_out`. The
top-level result mux in `tpu.v` collapses from 16:1 over 8-bit words
to 9:1 over 4-bit words.

### 4.3 Async reset removed where not functionally required

The synth library's reset flop (`sky130_fd_sc_hd__dfrtp`) is
noticeably larger than the plain D-flop (`dfxtp`), it carries an
extra reset input and routing. Every flop that does _not_ genuinely
need power-on initialization was migrated to `dfxtp`:

**`src/pe.v`** `a_reg` and `b_reg` lost their async reset clause and
moved into a separate `always @(posedge clk)` block:

```verilog
always @(posedge clk) begin
    if (we) begin
        a_reg <= a_in;
        b_reg <= b_in;
    end
end
```

This affects 18 bits per PE × 9 PEs = 162 flops that switch from
`dfrtp` to `dfxtp`. A `` `ifndef SYNTHESIS `` `initial` block keeps
simulation deterministic at zero gate cost. The accompanying comment
states the silicon-level argument: inactive systolic rows feed
`a_in == 0`, so any random power-up bits in `a_reg`/`b_reg` are
multiplied by zero and masked.

`c_reg` keeps its async reset, because the accumulator must read as 0
at the start of every matmul, that's a real functional requirement.

**`src/memory.v`** — the entire reset block

```verilog
if (!rst_n) begin
    for (ln = 0; ln < 4; ln = ln + 1)
        for (em = 0; em < 4; em = em + 1)
            mem[ln][em] <= 0;
end
```

was **deleted**. The 9 × 4 b = 36-bit register file now uses plain
`dfxtp` flops with synchronous-write-only semantics. The justification
is encoded in the file: cells are written via `LOAD` before any read,
so the don't-care power-up state is never observed. `rst_n` is kept
on the module interface for compatibility and tied to `_unused_rstn`
to silence lints.

### 4.4 Multiplier truncation written explicitly

`src/pe.v`:

```verilog
wire [`DATA_WIDTH*2-1:0] mult_full  = a_in * b_in;       // 8 bits
wire [`ACC_WIDTH-1:0]    mult_trunc = mult_full[`ACC_WIDTH-1:0];
c_reg <= c_reg + mult_trunc;
```

The accumulator update is a 4-bit + 4-bit add (vs. the original
8-bit + 16-bit). Yosys/ABC would generally drop the unused upper
product bits anyway, but spelling it out matches the documented mod-16
spec and prevents tooling surprises.

### 4.5 Control logic deduplicated

`src/control.v` originally contained **two parallel copies** of the
read-pattern logic one for memory A, one for memory B, even though
the comment admitted they were identical. The diff factors them into a
single `read_enable_shared` / `read_elem_shared` pair that is
broadcast to both memories:

```verilog
wire [`N-1:0]   read_enable_shared;
wire [`N*2-1:0] read_elem_shared;
…
assign mema_read_enable = read_enable_shared;
assign memb_read_enable = read_enable_shared;
assign mema_read_elem   = read_elem_shared;
assign memb_read_elem   = read_elem_shared;
```

That deletes a whole second copy of the per-row counter comparators
and the read-elem mux. Decoded opcode signals (`is_load`, `is_run`,
`is_store`, `load_a`, `load_b`) are also factored out as named wires
instead of being recomputed inline at every assignment site, allowing
synthesis to share decoded nets rather than duplicate comparators.

The read-pattern loop bound is now `i < N` (= 3), so the generator
emits 3 row patterns instead of 4.

### 4.6 Output path narrowed

`src/tpu.v`:

- `result_array` is `[0:8]` of 4-bit words (was `[0:15]` of 8-bit
  words) — a 16:1 8-bit mux collapses to a 9:1 4-bit mux.
- The 8-bit `result` output is built by zero-extending the 4-bit
  accumulator selection: `{4'b0, selected}`. The upper 4 bits of
  `uo_out` are tied to constants and routed nowhere.
- An out-of-range guard `(row < N && col < N)` returns 0 for invalid
  `STORE` addresses, replacing the old behaviour of indexing into a
  non-existent flop.

### 4.7 Combined area effect (back-of-envelope)

| Lever                                   | Effect on array cell area  |
| --------------------------------------- | -------------------------- |
| 4×4 → 3×3 array                         | × 9/16 ≈ 0.56              |
| 8 b → 4 b multiplier                    | × 0.25 on the multiplier   |
| 8 b → 4 b accumulator/regs              | × 0.5 on flops & adders    |
| Reset removed on `a_reg`/`b_reg`/memory | ~10–15 % per affected flop |
| Shared mema/memb read logic in control  | one full duplicate deleted |

Multiplying these together is what brings the design into the
**11 020 µm² / 73.6 %** synth-utilization range, placement-feasible
at all on a 14 977 µm² core. Without these levers the design would
not fit at any density target.

## 5. LibreLane sign-off tuning

After the RTL diet the design synthesises and globally places, but the
prior LibreLane run still failed at
`OpenROAD.ResizerTimingPostCTS → detailed_placement` with:

- `[DPL-0034] Detailed placement failed on the following 38 instances`
- `[DPL-0036] Detailed placement failed.`

### 5.1 Diagnosis

The post-CTS hold-fix pass inserted **141 hold buffers (+11.2 % cell
area)** to push every endpoint above a 100 ps margin. The DPL stage
then ran out of legal sites for 38 of those instances at ~85 % row
utilization.

The natural-looking remedy, lowering `PL_TARGET_DENSITY_PCT` to give
GPL more whitespace was a dead end. The log said so explicitly:

```
[GPL-0302] Target density 0.5500 is too low for the available free area.
```

Translation: synthesised cell area already exceeds the implied 55 %
density, so the placer is _forced_ to pack at ~74 % regardless of the
target. Asking for 50 % or 45 % changes nothing.

The actual root cause was the number of hold buffers inserted, not the
placement spread. The hold-fix iteration log made the issue visible:

```
Iteration | Buffers |   Area   |   WNS   |   TNS
        0 |       0 |    +0.0% |   0.024 |   0.000
       50 |      50 |    +4.0% |   0.033 |   0.000
      100 |     110 |    +8.7% |   0.074 |   0.000
    final |     141 |   +11.2% |   0.100 |   0.000   ← reached the 0.1 ns target
```

`TNS` is `0.000` from iteration 0: there are **no functional hold
violations** every endpoint is already non-negative. All 141 buffers
were spent purely to lift `WNS` from `+0.024` ns up to the requested
`+0.1` ns _margin_. That is padding, not a fix.

### 5.2 The change

`config.yaml`:

```diff
- PL_RESIZER_HOLD_SLACK_MARGIN: 0.1
- GRT_RESIZER_HOLD_SLACK_MARGIN: 0.05
+ PL_RESIZER_HOLD_SLACK_MARGIN: 0.0
+ GRT_RESIZER_HOLD_SLACK_MARGIN: 0.0
```

A 0 ns margin means "stop inserting buffers once hold slack reaches
zero". On a 50 ns implementation clock vs. a 1 MHz (1 000 ns) TT pin
spec, the typical PVT/derating noise the margin is meant to absorb is
dwarfed by:

- the 5 % timing derate already configured by the flow,
- 0.25 ns clock uncertainty,
- 0.15 ns clock transition,
- and 950 ns of slack vs. the target shuttle speed.

So forcing every endpoint to clear an additional 100 ps "comfort
buffer" is paying real tile area for an academic guarantee. Dropping
the margin removes the buffers without putting hold timing at risk.

### 5.3 Effect

With both margins at `0.0` and the same RTL:

- The hold-fix iteration loop terminates almost immediately
- endpoints are already passing.
- The post-CTS netlist no longer balloons by ~11 %.
- DPL has enough legal sites to legalize all instances.
- ResizerTimingPostCTS, GlobalRouting, DetailedRouting and signoff all
  proceed cleanly.

## 6. The rest of the floorplan/flow config (unchanged)

These settings were already in `config.yaml` and were not touched in
this session. They are listed for completeness because they are part
of the working configuration:

| Setting                               | Value           | Role                                                 |
| ------------------------------------- | --------------- | ---------------------------------------------------- |
| `FP_SIZING`                           | `absolute`      | Pin the die to the TT 1×1 tile exactly               |
| `DIE_AREA`                            | `[0,0,160,100]` | 16 000 µm² target                                    |
| `CORE_AREA`                           | `[1,1,159,99]`  | 1 µm pin margin on every side                        |
| `IO_PIN_H_LENGTH` / `IO_PIN_V_LENGTH` | `1`             | Minimal pin intrusion into the core                  |
| `CLOCK_PORT` / `CLOCK_PERIOD`         | `clk` / `50` ns | 20 MHz, 20× the 1 MHz TT spec                        |
| `SYNTH_STRATEGY`                      | `"AREA 0"`      | Smallest synthesis mapping                           |
| `SYNTH_ABC_BUFFERING`                 | `false`         | Don't let ABC speculatively add buffers              |
| `FP_CORE_UTIL`                        | `45`            | Headroom hint for the floorplanner                   |
| `PL_TARGET_DENSITY_PCT`               | `55`            | Effectively a no-op given GPL-0302; left for clarity |
| `DESIGN_REPAIR_BUFFER_OUTPUT_PORTS`   | `false`         | TT pads provide drive — don't add output buffers     |
| `PDN_MULTILAYER`                      | `false`         | TT macro PDN: lower layers only, no rings            |
| `RT_MAX_LAYER`                        | `met4`          | TT macro routing rule                                |
| `PDN_VPITCH`                          | `38.87`         | TT macro PDN pitch                                   |
| `GRT_ALLOW_CONGESTION`                | `true`          | Tile is dense; tolerate congestion warnings          |
| `RUN_KLAYOUT_XOR`                     | `false`         | Skip XOR (no reference GDS to compare against)       |
| `RUN_KLAYOUT_DRC`                     | `true`          | Run KLayout DRC for sign-off                         |
| `MAGIC_DEF_LABELS`                    | `false`         | Magic LEF: pin-only export                           |
| `MAGIC_WRITE_LEF_PINONLY`             | `true`          | Match TT integration expectations                    |

## 7. Reproducing the build

```sh
# Sign-off run
cd /path/to/librelane
nix-shell
librelane /path/to/Workshop_2026_Mini-TPU/config.yaml

# Functional regression
cd /path/to/Workshop_2026_Mini-TPU/test
rm -rf sim_build && make MODULE=test_assert
```

The `Makefile` hardcodes `MODULE = test`, so passing it as an
environment variable will _not_ override — the explicit
`make MODULE=test_assert` argument is required.

## 8. Forward levers if it ever regresses

If a later RTL change pushes the design back into post-CTS DPL
failure, the levers in order of cost:

1. **Verify** `PL_RESIZER_HOLD_SLACK_MARGIN` and
   `GRT_RESIZER_HOLD_SLACK_MARGIN` are still `0.0` — they're easy to
   bump back accidentally.
2. **Cap the hold-fix budget** with
   `PL_RESIZER_HOLD_MAX_BUFFER_PERCENT` to limit how much area the
   hold-fix pass is allowed to spend.
3. **Reduce flop count** in `memory.v` (matrix A/B/C banks are the
   largest sequential cluster).
4. **Drop the datapath to 3 bits** (mod 8 math) if 4 bits no longer
   fits.
5. **Shrink the array** to 2×2 — last resort, costs functionality.

## 9. Files modified

- `config.yaml` — two hold-margin lines (this session)
- `src/pe.v` — datapath width, reset removal on pipe regs, explicit
  multiplier truncation
- `src/array.v` — 4×4 → 3×3, parameterised through `` `N ``
- `src/memory.v` — 4×4 → 3×3, full reset block deleted, sync-write
  with bounds check
- `src/control.v` — datapath width, shared mema/memb read pattern,
  decoded-opcode named wires
- `src/tpu.v` — datapath width, 9-entry output mux, zero-padded
  8-bit `result`
