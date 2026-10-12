"""Exact (minimum-gate) search for very small designs.

Used as a final refinement step: if the heuristic mappers produced N gates,
look for a NAND2-only / NOR2-only netlist with fewer than N gates using
iterative-deepening search over truth tables.  Only for <= 4 inputs and a
node budget, so it never blocks for long; if the budget runs out the
heuristic result is kept.
"""
from .mapper import Gate
from .verify import _eval_expr


class _Budget(Exception):
    pass


def truth_tables(design):
    n = len(design.inputs)
    rows = 1 << n
    mask = (1 << rows) - 1
    in_tt = [sum(((v >> i) & 1) << v for v in range(rows)) for i in range(n)]
    out_tt = {}
    for o in design.outputs:
        tt = 0
        for v in range(rows):
            env = {nm: (v >> i) & 1 for i, nm in enumerate(design.inputs)}
            if o in design.assignments:
                val = _eval_expr(design.assignments[o], env, design, {})
            else:
                val = env[o]
            tt |= val << v
        out_tt[o] = tt
    return in_tt, out_tt, mask


def exact_improve(design, style, current_count, budget=300000):
    """Returns (gates or None, note)."""
    n = len(design.inputs)
    if n < 1 or n > 4:
        return None, "skipped (more than 4 inputs)"
    in_tt, out_tt, mask = truth_tables(design)
    targets = list(out_tt.values())
    if (len(set(targets)) != len(targets)
            or any(t in (0, mask) or t in in_tt for t in targets)):
        return None, "skipped (constant/duplicate/pass-through output)"
    if current_count <= len(targets):
        return None, "already minimal"

    if style == "nand":
        f = lambda x, y: ~(x & y) & mask
        cell = "NAND2"
    else:
        f = lambda x, y: ~(x | y) & mask
        cell = "NOR2"
    target_set = set(targets)
    nodes = [0]

    def dfs(sigs, pairs, limit):
        nodes[0] += 1
        if nodes[0] > budget:
            raise _Budget
        miss = sum(1 for t in targets if t not in sigs)
        if miss == 0:
            return pairs
        r = limit - len(pairs)
        if r < miss:
            return None
        m = len(sigs)
        last = m - 1 if pairs else -1
        prev = pairs[-1] if pairs else None
        for i in range(m):
            for j in range(i, m):
                # independent neighbouring gates are kept in canonical order
                if prev is not None and last not in (i, j) and (i, j) <= prev:
                    continue
                v = f(sigs[i], sigs[j])
                if v in sigs:
                    continue
                if r == miss and v not in target_set:
                    continue
                res = dfs(sigs + [v], pairs + [(i, j)], limit)
                if res:
                    return res
        return None

    try:
        found = None
        for lim in range(len(targets), current_count):
            found = dfs(list(in_tt), [], lim)
            if found:
                break
    except _Budget:
        return None, "budget exhausted (heuristic result kept)"
    if not found:
        return None, "heuristic result is minimal"

    # ---- build gates ----
    names = list(design.inputs)
    sigs = list(in_tt)
    by_tt = {tt: o for o, tt in out_tt.items()}
    reserved = set(design.inputs) | set(design.outputs)
    gates, k = [], 0
    for (i, j) in found:
        v = f(sigs[i], sigs[j])
        if v in by_tt:
            nm = by_tt[v]
        else:
            while True:
                k += 1
                nm = f"n{k}"
                if nm not in reserved:
                    break
        gates.append(Gate(cell, [names[i], names[j]], nm))
        names.append(nm)
        sigs.append(v)
    return gates, f"improved {current_count} -> {len(gates)} gates"
