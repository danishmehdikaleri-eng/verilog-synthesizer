import argparse
import itertools
import time
from pathlib import Path

from synth.verilog_parser import parse_verilog, Design, Expr
from synth.bdd import BDDManager, BDDLimit
from synth.mapper import NANDMapper, NORMapper
from synth.svg import write_svg
from synth.bdd_svg import save_bdd_svg
from synth.verify import check_equivalence, is_self_dual
from synth.exact import exact_improve


CELLS_V = """// Behavioural models of the cells used by the synthesized netlists.
module NAND2(input A, input B, output Y); assign Y = ~(A & B); endmodule
module NOR2 (input A, input B, output Y); assign Y = ~(A | B); endmodule
module TIE0 (output Y); assign Y = 1'b0; endmodule
module TIE1 (output Y); assign Y = 1'b1; endmodule
"""


def main():
    ap = argparse.ArgumentParser(
        description="Small educational Verilog -> BDD -> NAND/NOR synthesizer"
    )

    ap.add_argument(
        "verilog",
        help="Input Verilog file"
    )

    ap.add_argument(
        "--style",
        choices=["nand", "nor", "both"],
        default="both"
    )

    ap.add_argument(
        "--out",
        default="output",
        help="Output directory"
    )

    ap.add_argument(
        "--order",
        choices=["auto", "input"],
        default="auto",
        help="BDD variable order: 'auto' searches for the smallest "
             "netlist, 'input' keeps the port order"
    )

    ap.add_argument(
        "--no-check",
        action="store_true",
        help="skip the equivalence check"
    )

    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # Read and parse input Verilog
    # ---------------------------------------------------------

    text = Path(args.verilog).read_text(encoding="utf-8")
    design = parse_verilog(text)

    print("\n=== INPUT DESIGN ===")
    print("Module :", design.module)
    print("Inputs :", ", ".join(design.inputs))
    print("Outputs:", ", ".join(design.outputs))

    for name, expr in design.assignments.items():
        print(f"  {name} = {expr}")

    # ---------------------------------------------------------
    # Cell simulation models
    # ---------------------------------------------------------

    (out / "cells.v").write_text(
        CELLS_V,
        encoding="utf-8"
    )

    all_reports = []

    # ---------------------------------------------------------
    # NAND / NOR synthesis
    # ---------------------------------------------------------

    styles = (
        ["nand", "nor"]
        if args.style == "both"
        else [args.style]
    )

    for style in styles:

        print(f"\n=== {style.upper()} SYNTHESIS ===")

        result = synthesize(
            design,
            style,
            auto_order=(args.order == "auto")
        )

        # -----------------------------------------------------
        # Equivalence checking
        # -----------------------------------------------------

        if not args.no_check:

            ok, mode, total, bad = check_equivalence(
                design,
                result["gates"]
            )

            verdict = (
                f"EQUIVALENT ({mode}, {total} vectors)"
                if ok
                else f"MISMATCH at {bad}"
            )

            result["report"] += (
                f"\n\nBDD variable order: "
                f"{', '.join(result['order'])}"
                f"\nEquivalence check : {verdict}"
            )

            if not ok:
                print(
                    "!!! SYNTHESIS BUG:",
                    verdict
                )

        else:

            result["report"] += (
                f"\n\nBDD variable order: "
                f"{', '.join(result['order'])}"
            )

        # -----------------------------------------------------
        # Output file names
        # -----------------------------------------------------

        vfile = out / f"synthesized_{style}.v"
        nfile = out / f"netlist_{style}.txt"
        sfile = out / f"circuit_{style}.svg"
        rfile = out / f"report_{style}.txt"

        # -----------------------------------------------------
        # BDD information
        # -----------------------------------------------------

        bdd = result.get("bdd")
        output_nodes = result.get("output_nodes", {})

        # -----------------------------------------------------
        # Generate BDD SVG diagrams
        # -----------------------------------------------------

        if bdd is not None:

            for output_name, root in output_nodes.items():

                bdd_file = out / f"bdd_{output_name}.svg"

                save_bdd_svg(
                    bdd,
                    root,
                    bdd_file,
                    title=f"ROBDD - {output_name}"
                )

        # -----------------------------------------------------
        # Generate gate-level Verilog
        # -----------------------------------------------------

        vfile.write_text(
            result["verilog"],
            encoding="utf-8"
        )

        # -----------------------------------------------------
        # Generate netlist
        # -----------------------------------------------------

        nfile.write_text(
            result["netlist"],
            encoding="utf-8"
        )

        # -----------------------------------------------------
        # Generate synthesized circuit SVG
        # -----------------------------------------------------

        sfile.write_text(
            write_svg(
                result["gates"],
                design.inputs,
                design.outputs
            ),
            encoding="utf-8"
        )

        # -----------------------------------------------------
        # Generate report
        # -----------------------------------------------------

        rfile.write_text(
            result["report"],
            encoding="utf-8"
        )

        # -----------------------------------------------------
        # Print results
        # -----------------------------------------------------

        print(result["report"])

        print(
            f"Gate-level Verilog: {vfile}"
        )

        print(
            f"Netlist          : {nfile}"
        )

        print(
            f"Circuit SVG      : {sfile}"
        )

        if bdd is not None:

            for output_name in output_nodes:

                print(
                    f"BDD SVG          : "
                    f"{out / f'bdd_{output_name}.svg'}"
                )

        all_reports.append(
            result["report"]
        )

    print("\nDone.")


# =============================================================
# BDD synthesis
# =============================================================

def synthesize_with_order(
    design,
    style,
    order,
    max_nodes=None
):

    bdd = BDDManager(
        order,
        max_nodes
    )

    cache = {}

    def build_signal(name):

        if name in cache:
            return cache[name]

        if name in design.assignments:

            node = bdd.build(
                design.assignments[name],
                build_signal
            )

        else:

            node = bdd.var(name)

        cache[name] = node

        return node

    output_nodes = {
        o: build_signal(o)
        for o in design.outputs
    }

    Mapper = (
        NANDMapper
        if style == "nand"
        else NORMapper
    )

    mapper = Mapper(
        bdd,
        design.inputs,
        design.outputs
    )

    for out, node in output_nodes.items():

        mapper.map_output(
            out,
            node
        )

    mapper.finalize()

    return (
        bdd,
        mapper,
        output_nodes
    )


# =============================================================
# BDD optimization settings
# =============================================================

BDD_NODE_CAP = 30000
ORDER_SEARCH_SECONDS = 4.0

INF = (
    10 ** 9,
    10 ** 9
)


# =============================================================
# Calculate variable usage
# =============================================================

def _var_counts(design):

    counts = {
        v: 0
        for v in design.inputs
    }

    def walk(e):

        if e.kind == "var":

            if e.a in counts:
                counts[e.a] += 1

            return

        for x in (
            e.a,
            e.b,
            e.c
        ):

            if isinstance(x, Expr):
                walk(x)

    for e in design.assignments.values():
        walk(e)

    return counts


# =============================================================
# BDD variable ordering
# =============================================================

EXHAUSTIVE_MAX_VARS = 6


def _cost(
    design,
    style,
    order
):

    try:

        _, mapper, _ = synthesize_with_order(
            design,
            style,
            order,
            BDD_NODE_CAP
        )

    except BDDLimit:

        return INF

    return (
        len(mapper.gates),
        mapper.bdd.next_id
    )


def find_order(
    design,
    style
):

    """
    Pick a BDD variable order that minimises
    the mapped gate count.

    <= 6 inputs:
        try every permutation.

    More than 6 inputs:
        start from sensible orders and perform
        a simple sifting heuristic.
    """

    inputs = list(
        design.inputs
    )

    if len(inputs) <= 1:

        return inputs

    # ---------------------------------------------------------
    # Exhaustive ordering for small circuits
    # ---------------------------------------------------------

    if len(inputs) <= EXHAUSTIVE_MAX_VARS:

        return list(
            min(
                itertools.permutations(inputs),
                key=lambda o:
                    _cost(
                        design,
                        style,
                        list(o)
                    )
            )
        )

    # ---------------------------------------------------------
    # Heuristic ordering for larger circuits
    # ---------------------------------------------------------

    counts = _var_counts(
        design
    )

    starts = [
        inputs,

        sorted(
            inputs,
            key=lambda v: -counts[v]
        ),

        inputs[::-1]
    ]

    best = min(
        starts,
        key=lambda o:
            _cost(
                design,
                style,
                o
            )
    )

    best_cost = _cost(
        design,
        style,
        best
    )

    deadline = (
        time.time()
        + ORDER_SEARCH_SECONDS
    )

    improved = (
        best_cost < INF
    )

    while (
        improved
        and time.time() < deadline
    ):

        improved = False

        for v in inputs:

            rest = [
                x
                for x in best
                if x != v
            ]

            for pos in range(
                len(inputs)
            ):

                if time.time() > deadline:
                    break

                cand = (
                    rest[:pos]
                    + [v]
                    + rest[pos:]
                )

                c = _cost(
                    design,
                    style,
                    cand
                )

                if c < best_cost:

                    best = cand
                    best_cost = c
                    improved = True

    return best


# =============================================================
# Structural synthesis
# =============================================================

def synthesize_structural(
    design,
    style
):

    """
    Map the expression DAG directly.

    Uses:
      - XOR templates
      - common subexpression sharing
      - output sharing
    """

    Mapper = (
        NANDMapper
        if style == "nand"
        else NORMapper
    )

    mapper = Mapper(
        None,
        design.inputs,
        design.outputs
    )

    cache = {}

    def sig(name):

        if name in cache:
            return cache[name]

        if name in design.assignments:

            r = mapper.map_expr(
                design.assignments[name],
                sig
            )

        elif name in design.inputs:

            r = name

        else:

            raise ValueError(
                f"Signal {name!r} is not defined"
            )

        cache[name] = r

        return r

    for o in design.outputs:

        mapper.bind_output(
            o,
            sig(o)
        )

    mapper.finalize()

    return mapper


# =============================================================
# Dual expression
# =============================================================

def _dual_expr(e):

    """
    Dual function:

        D(e)(x) = ~e(~x)

    Operators:

        AND -> OR
        OR  -> AND
        XOR -> XNOR
    """

    k = e.kind

    if k == "const":

        return Expr(
            "const",
            1 - int(bool(e.a))
        )

    if k == "var":

        return e

    if k == "not":

        return Expr(
            "not",
            _dual_expr(e.a)
        )

    if k == "AND":

        return Expr(
            "OR",
            _dual_expr(e.a),
            _dual_expr(e.b)
        )

    if k == "OR":

        return Expr(
            "AND",
            _dual_expr(e.a),
            _dual_expr(e.b)
        )

    if k == "XOR":

        return Expr(
            "not",
            Expr(
                "XOR",
                _dual_expr(e.a),
                _dual_expr(e.b)
            )
        )

    if k == "mux":

        return Expr(
            "mux",
            _dual_expr(e.a),
            _dual_expr(e.c),
            _dual_expr(e.b)
        )

    raise ValueError(k)


# =============================================================
# Dual synthesis
# =============================================================

def synthesize_dual(
    design,
    style
):

    """
    Generate NAND/NOR implementation through
    Boolean duality.
    """

    other = (
        "nor"
        if style == "nand"
        else "nand"
    )

    dual = Design(
        design.module,
        design.inputs,
        design.outputs,
        {
            n: _dual_expr(e)
            for n, e in design.assignments.items()
        }
    )

    if is_self_dual(design):

        m_other = synthesize_structural(
            design,
            other
        )

    else:

        m_other = synthesize_structural(
            dual,
            other
        )

    swap = {
        "NAND2": "NOR2",
        "NOR2": "NAND2",
        "TIE0": "TIE1",
        "TIE1": "TIE0"
    }

    for g in m_other.gates:

        g.cell = swap[g.cell]

    Mapper = (
        NANDMapper
        if style == "nand"
        else NORMapper
    )

    m = Mapper(
        None,
        design.inputs,
        design.outputs
    )

    m.gates = m_other.gates

    return m


# =============================================================
# Main synthesis function
# =============================================================

def synthesize(
    design,
    style,
    auto_order=True,
    exact=True
):

    # ---------------------------------------------------------
    # Find BDD variable order
    # ---------------------------------------------------------

    order = (
        find_order(design, style)
        if auto_order
        else list(design.inputs)
    )

    # ---------------------------------------------------------
    # BDD synthesis
    # ---------------------------------------------------------

    try:

        (
            bdd,
            m_bdd,
            output_nodes
        ) = synthesize_with_order(
            design,
            style,
            order,
            BDD_NODE_CAP
        )

    except BDDLimit:

        bdd = None
        m_bdd = None
        output_nodes = {}

    # ---------------------------------------------------------
    # Structural synthesis
    # ---------------------------------------------------------

    m_str = synthesize_structural(
        design,
        style
    )

    # ---------------------------------------------------------
    # Dual synthesis
    # ---------------------------------------------------------

    m_dual = synthesize_dual(
        design,
        style
    )

    # ---------------------------------------------------------
    # Candidate selection
    # ---------------------------------------------------------

    cands = [
        (
            m_str,
            "structural (expression DAG)"
        ),
        (
            m_dual,
            f"structural via "
            f"{'NOR' if style == 'nand' else 'NAND'} duality"
        ),
        (
            m_bdd,
            "BDD (Shannon decomposition)"
        )
    ]

    cands = [
        c
        for c in cands
        if c[0] is not None
    ]

    # Select smallest gate count

    best, method = min(
        cands,
        key=lambda c:
            len(c[0].gates)
    )

    best.bdd = bdd

    notes = [
        "candidates: "
        + ", ".join(
            f"{name.split(' (')[0]}="
            f"{len(m.gates)}"
            for m, name in cands
        )
    ]

    if m_bdd is None:

        notes.append(
            f"BDD candidate skipped "
            f"(more than {BDD_NODE_CAP} nodes)"
        )

    # ---------------------------------------------------------
    # Exact improvement
    # ---------------------------------------------------------

    if exact:

        gates, note = exact_improve(
            design,
            style,
            len(best.gates)
        )

        notes.append(
            f"exact search: {note}"
        )

        if gates:

            best.gates = gates

            method = (
                "exact search "
                "(minimum gates)"
            )

    # ---------------------------------------------------------
    # Generate Verilog and netlist
    # ---------------------------------------------------------

    verilog = best.emit_verilog(
        design.module,
        design.inputs,
        design.outputs
    )

    netlist = best.emit_netlist()

    # ---------------------------------------------------------
    # Generate report
    # ---------------------------------------------------------

    report = best.report(
        module=design.module,
        inputs=design.inputs,
        outputs=design.outputs,
        output_nodes=output_nodes
    )

    report += (
        "\n\nMapping method    : "
        + method
    )

    report += (
        "\n"
        + "\n".join(
            "  " + n
            for n in notes
        )
    )

    # ---------------------------------------------------------
    # Return everything
    # ---------------------------------------------------------

    return {
        "verilog": verilog,
        "netlist": netlist,
        "report": report,
        "gates": best.gates,
        "order": order,

        # BDD information for SVG generation
        "bdd": bdd,
        "output_nodes": output_nodes,
    }


if __name__ == "__main__":
    main()