# Python Verilog -> BDD -> NAND/NOR Synthesizer

This is an educational RTL-to-gate-level synthesis prototype.

Flow:

Verilog RTL
-> parser
-> Boolean expression
-> Reduced Ordered BDD (ROBDD)
-> Shannon/MUX decomposition
-> automatic variable-order search (BDD candidate)
-> structural candidate (XOR templates, shared logic across outputs)
-> NAND<->NOR duality candidate
-> exact minimum-gate search for tiny designs (<= 4 inputs)
-> NAND2-only or NOR2-only mapping (constant folding, shared inverters)
-> equivalence check against the original design
-> gate-level Verilog + netlist + SVG circuit

## Run

```powershell
python main.py examples/test.v --style both
```

Options: `--order auto|input` (default `auto`: tries all orders for up to 6 inputs, sifting above that), `--no-check` (skip equivalence check), `--out DIR`.
Every run ends with an equivalence check (exhaustive up to 16 inputs, random sampling above), printed in the report.

Outputs are written to `output/`.

You can open:

- `output/synthesized_nand.v`
- `output/synthesized_nor.v`
- `output/netlist_nand.txt`
- `output/netlist_nor.txt`
- `output/circuit_nand.svg`
- `output/circuit_nor.svg`
- `output/cells.v` (NAND2/NOR2/TIE simulation models)
- reports

## How the netlist is chosen

For every target (NAND2-only, NOR2-only) three mappers run and the smallest result wins:

1. **Structural**: maps the expression DAG directly. XOR uses the shared 4-NAND template (`n1 = NAND(a,b)` is reused for the AND output), and identical sub-gates are shared across outputs.
2. **Duality**: a NOR network for `f` is a NAND network for the dual function `~f(~x)` with every NAND replaced by NOR (and vice versa). If `f` is self-dual (full adder, majority) the NAND netlist is simply swapped.
3. **BDD**: ROBDD + Shannon decomposition with variable-order search.

Then, for designs with at most 4 inputs, an exact search tries to find a netlist with fewer gates (it stops at a node budget and keeps the heuristic result if the budget runs out). The report lists which method won.

Results: half adder = 5 NAND2 / 5 NOR2, full adder = 9 NAND2 / 9 NOR2 (both known minima).

## Supported Verilog subset in this version

- one-bit `input` / `output`
- `assign`
- simple `always_comb` / `always @*` assignments
- `&`, `|`, `^`, `~`, `!`, `&&`, `||`
- parentheses
- 0/1 constants
- ternary `condition ? true_expr : false_expr`
- intermediate one-bit wires via `assign`

This is intentionally NOT a full Verilog compiler. It is a starting synthesis engine. Multi-bit vectors, arithmetic (`+`, `-`, `*`), memories, clocks, flip-flops, and full SystemVerilog are future extensions.

## Important engineering note

NAND/NOR cells are technology-mapped primitives. `TIE0` and `TIE1` are also emitted when a Boolean function needs a constant. In a real standard-cell library, these would be replaced by the library's actual constant/tie cells.

The BDD variable order is searched per target (NAND/NOR) to minimise gate count. For more than 6 inputs this is a greedy sifting heuristic, not a guaranteed optimum. A future step is a cost model with area/delay/power and multi-bit support.
