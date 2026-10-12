import itertools
import random


def _eval_expr(e, env, design, memo):
    k = e.kind
    if k == "const":
        return int(e.a)
    if k == "var":
        n = e.a
        if n in env:
            return env[n]
        if n not in memo:
            memo[n] = _eval_expr(design.assignments[n], env, design, memo)
        return memo[n]
    if k == "not":
        return 1 - _eval_expr(e.a, env, design, memo)
    a = _eval_expr(e.a, env, design, memo)
    if k == "mux":
        return _eval_expr(e.b if a else e.c, env, design, memo)
    b = _eval_expr(e.b, env, design, memo)
    return {"AND": a & b, "OR": a | b, "XOR": a ^ b}[k]


def _eval_netlist(gates, env, outputs):
    driver = {g.output: g for g in gates}
    memo = dict(env)

    def val(net):
        if net in memo:
            return memo[net]
        g = driver[net]
        if g.cell == "TIE0":
            r = 0
        elif g.cell == "TIE1":
            r = 1
        else:
            x = [val(s) for s in g.inputs]
            r = 1 - (x[0] & x[1]) if g.cell == "NAND2" else 1 - (x[0] | x[1])
        memo[net] = r
        return r

    return {o: val(o) for o in outputs}


def check_equivalence(design, gates, exhaustive_limit=16, samples=1 << 16):
    """Compare the original design with the mapped netlist.
    Exhaustive up to `exhaustive_limit` inputs, random sampling above."""
    n = len(design.inputs)
    if n <= exhaustive_limit:
        vectors = itertools.product((0, 1), repeat=n)
        mode, total = "exhaustive", 1 << n
    else:
        rnd = random.Random(1)
        vectors = (tuple(rnd.getrandbits(1) for _ in range(n))
                   for _ in range(samples))
        mode, total = "random sampling", samples
    for vec in vectors:
        env = dict(zip(design.inputs, vec))
        memo = {}
        want = {o: _eval_expr(design.assignments[o], env, design, memo)
                if o in design.assignments else env[o]
                for o in design.outputs}
        got = _eval_netlist(gates, env, design.outputs)
        if want != got:
            return False, mode, total, env
    return True, mode, total, None


def is_self_dual(design, limit=12):
    """True if every output satisfies f(~x) == ~f(x).  For such functions a
    NAND network turns into a NOR network by just swapping the cells."""
    n = len(design.inputs)
    if n > limit:
        return False
    for vec in itertools.product((0, 1), repeat=n):
        env = dict(zip(design.inputs, vec))
        nenv = {k: 1 - v for k, v in env.items()}
        for o in design.outputs:
            if o not in design.assignments:
                return False
            a = _eval_expr(design.assignments[o], env, design, {})
            b = _eval_expr(design.assignments[o], nenv, design, {})
            if a != 1 - b:
                return False
    return True
