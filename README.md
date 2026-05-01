# 🧠 Mini-TPU v2: A Tiny Tapeout-Based Systolic Array Accelerator with SPI support for instruction/memory fetch

[![](../../workflows/gds/badge.svg)](../../workflows/gds)
[![](../../workflows/docs/badge.svg)](../../workflows/docs)
[![](../../workflows/test/badge.svg)](../../workflows/test)
[![](../../workflows/fpga/badge.svg)](../../workflows/fpga)

This project implements a **Mini Tensor Processing Unit (Mini-TPU)** on the **Tiny Tapeout** open-source ASIC platform. It features a compact 3×3 systolic array optimized for efficient **matrix multiplication**, making it ideal for resource-constrained AI inference tasks.

> ✨ Built using [Tiny Tapeout](https://tinytapeout.com) and [Skywater 130nm PDK](https://skywater-pdk.readthedocs.io)!

---

## 🔍 Project Overview

The Mini-TPU v2 is designed for **educational** and **exploratory** purposes. Despite the severe area constraints (~160µm × 100µm), it demonstrates:

- A fully functional 3×3 **systolic array** of 8-bit MAC units
- An **output-stationary dataflow**
- Custom instruction set (`LOAD`, `RUN`, `STORE`)
- **Off-chip instructions/memory fetch through SPI** for activations and weights..
- A lightweight **control**

---

## 🎬 Workshop Goal

Optimise this Mini-TPU to fit in the TT Tile of 160x100um^2

---

## 🧱 System Architecture

- `pe.v`: Single Processing Element (4-bit MAC)
- `array.v`: 3x43 systolic array
- `memory.v`: Two 4x4 on-chip memories (A and B)
- `control.v`: Control unit to execute instructions
- `tpu_top.v`: System integration module

---

## 🧪 Verification

We used a combination of:

- `SystemVerilog` + **constraint-random tests**
- `Cocotb` + Python **testbench and reference model**

✅ All modules and system-level simulation passed.
