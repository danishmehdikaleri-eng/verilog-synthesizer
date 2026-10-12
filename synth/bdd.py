from dataclasses import dataclass


class BDDLimit(Exception):
    """Raised when a BDD grows beyond the allowed number of nodes."""


@dataclass(frozen=True)
class Node:
    var: str | None
    low: int | None
    high: int | None


class BDDManager:
    """
    Reduced Ordered BDD (ROBDD).
    Variable order is fixed by the list supplied at construction.
    """

    def __init__(self, variables, max_nodes=None):
        self.max_nodes = max_nodes
        self.variables = list(variables)
        self.level = {v: i for i, v in enumerate(self.variables)}
        self.nodes = {
            0: Node(None, None, None),  # False
            1: Node(None, None, None),  # True
        }
        self.unique = {}
        self.next_id = 2

    def mk(self, var, low, high):
        if low == high:
            return low
        key = (var, low, high)
        if key in self.unique:
            return self.unique[key]
        if self.max_nodes is not None and self.next_id >= self.max_nodes:
            raise BDDLimit
        n = self.next_id
        self.next_id += 1
        self.nodes[n] = Node(var, low, high)
        self.unique[key] = n
        return n

    def var(self, name):
        if name not in self.level:
            raise ValueError(f"Signal {name!r} is not a primary input")
        return self.mk(name, 0, 1)

    def neg(self, u, memo=None):
        memo = {} if memo is None else memo
        if u in memo:
            return memo[u]
        if u == 0:
            return 1
        if u == 1:
            return 0
        n = self.nodes[u]
        r = self.mk(n.var, self.neg(n.low, memo), self.neg(n.high, memo))
        memo[u] = r
        return r

    def apply(self, op, u, v, memo=None):
        memo = {} if memo is None else memo
        key = (op, u, v)
        if key in memo:
            return memo[key]

        if op == "AND":
            if u == 0 or v == 0:
                r = 0
            elif u == 1:
                r = v
            elif v == 1:
                r = u
            elif u == v:
                r = u
            else:
                r = self._apply_rec(op, u, v, memo)

        elif op == "OR":
            if u == 1 or v == 1:
                r = 1
            elif u == 0:
                r = v
            elif v == 0:
                r = u
            elif u == v:
                r = u
            else:
                r = self._apply_rec(op, u, v, memo)

        elif op == "XOR":
            if u == 0:
                r = v
            elif v == 0:
                r = u
            elif u == v:
                r = 0
            elif u == 1:
                r = self.neg(v)
            elif v == 1:
                r = self.neg(u)
            else:
                r = self._apply_rec(op, u, v, memo)
        else:
            raise ValueError(op)

        memo[key] = r
        return r

    def _apply_rec(self, op, u, v, memo):
        nu = self.nodes[u].var
        nv = self.nodes[v].var
        lu = self.level[nu] if nu is not None else 10**9
        lv = self.level[nv] if nv is not None else 10**9
        top = nu if lu <= lv else nv

        if nu == top:
            u0, u1 = self.nodes[u].low, self.nodes[u].high
        else:
            u0 = u1 = u

        if nv == top:
            v0, v1 = self.nodes[v].low, self.nodes[v].high
        else:
            v0 = v1 = v

        low = self.apply(op, u0, v0, memo)
        high = self.apply(op, u1, v1, memo)
        return self.mk(top, low, high)

    def build(self, expr, resolver):
        k = expr.kind
        if k == "const":
            return int(bool(expr.a))
        if k == "var":
            return resolver(expr.a)
        if k == "not":
            return self.neg(self.build(expr.a, resolver))
        if k == "AND":
            return self.apply("AND", self.build(expr.a, resolver),
                              self.build(expr.b, resolver))
        if k == "OR":
            return self.apply("OR", self.build(expr.a, resolver),
                              self.build(expr.b, resolver))
        if k == "XOR":
            return self.apply("XOR", self.build(expr.a, resolver),
                              self.build(expr.b, resolver))
        if k == "mux":
            c = self.build(expr.a, resolver)
            t = self.build(expr.b, resolver)
            f = self.build(expr.c, resolver)
            # c ? t : f = (c&t) | (~c&f)
            return self.apply(
                "OR",
                self.apply("AND", c, t),
                self.apply("AND", self.neg(c), f),
            )
        raise ValueError(f"Unsupported expression node {k}")

    def reachable(self, root):
        seen = set()
        def walk(u):
            if u in seen or u in (0, 1):
                return
            seen.add(u)
            walk(self.nodes[u].low)
            walk(self.nodes[u].high)
        walk(root)
        return seen

    def size(self, root):
        return len(self.reachable(root))
