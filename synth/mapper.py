class Gate:
    def __init__(self, cell, inputs, output):
        self.cell = cell
        self.inputs = list(inputs)
        self.output = output


class BaseMapper:
    """
    Maps a ROBDD onto a single universal 2-input cell (NAND2 or NOR2).

    Signals are either net names (str) or Python constants 0 / 1.
    Constants are folded away while mapping, so TIE cells are only ever
    created when an *output* is itself a constant function.

    Optimizations:
      * constant propagation (x?1:l -> x|l, x?h:0 -> x&h, ...)
      * shared inverters (one NOT per net) and double-inversion removal
      * structural hashing of the primitive gate
      * dead-gate removal + output renaming (no buffer on the outputs)
    """

    CELL = None       # "NAND2" / "NOR2"
    ABSORB = None     # input value that forces the primitive's output

    def __init__(self, bdd, inputs=(), outputs=()):
        self.bdd = bdd
        self.inputs = list(inputs)
        self.output_names = list(outputs)
        self.reserved = set(self.inputs) | set(self.output_names)
        self.gates = []
        self.counter = 0
        self.cache = {}        # bdd node -> signal
        self.inv_cache = {}    # net -> its inverter output
        self.inv_src = {}      # inverter output -> original net
        self.prim_cache = {}   # (a, b) -> primitive output
        self.pending = []      # (output name, signal)

    # ---------- netlist helpers ----------
    def net(self):
        while True:
            self.counter += 1
            name = f"n{self.counter}"
            if name not in self.reserved:
                return name

    def add(self, cell, inputs, output=None):
        if output is None:
            output = self.net()
        self.gates.append(Gate(cell, inputs, output))
        return output

    # ---------- logic primitives ----------
    def inv(self, a):
        if a in (0, 1) and not isinstance(a, str):
            return 1 - a
        if a in self.inv_src:              # NOT(NOT(x)) = x
            return self.inv_src[a]
        if a in self.inv_cache:
            return self.inv_cache[a]
        out = self.add(self.CELL, [a, a])
        self.inv_cache[a] = out
        self.inv_src[out] = a
        return out

    @staticmethod
    def _is_const(a):
        return not isinstance(a, str)

    def prim(self, a, b):
        """The universal cell, with constant folding."""
        for x in (a, b):
            if self._is_const(x) and x == self.ABSORB:
                return 1 - self.ABSORB
        if self._is_const(a):            # a is the identity value
            return self.inv(b)
        if self._is_const(b):
            return self.inv(a)
        if a == b:
            return self.inv(a)
        key = tuple(sorted((a, b)))
        if key not in self.prim_cache:
            self.prim_cache[key] = self.add(self.CELL, [a, b])
        return self.prim_cache[key]

    def and_(self, a, b):
        raise NotImplementedError

    def or_(self, a, b):
        raise NotImplementedError

    def _fold_and(self, a, b):
        if (self._is_const(a) and a == 0) or (self._is_const(b) and b == 0):
            return 0
        if self._is_const(a) and a == 1:
            return b
        if self._is_const(b) and b == 1:
            return a
        if a == b:
            return a
        return None

    def _fold_or(self, a, b):
        if (self._is_const(a) and a == 1) or (self._is_const(b) and b == 1):
            return 1
        if self._is_const(a) and a == 0:
            return b
        if self._is_const(b) and b == 0:
            return a
        if a == b:
            return a
        return None

    def mux(self, x, high, low):
        """x ? high : low, built with as few cells as the constants allow."""
        if low == 0 and self._is_const(low):
            return self.and_(x, high)
        if high == 0 and self._is_const(high):
            return self.and_(self.inv(x), low)
        if low == 1 and self._is_const(low):
            return self.or_(self.inv(x), high)
        if high == 1 and self._is_const(high):
            return self.or_(x, low)
        return self.or_(self.and_(x, high), self.and_(self.inv(x), low))

    # ---------- expression tree -> gates (structural mapping) ----------
    def xor_(self, a, b):
        raise NotImplementedError

    def _fold_xor(self, a, b):
        # NOT(x) ^ y == NOT(x ^ y): pull inverters out of XOR operands
        if isinstance(a, str) and a in self.inv_src:
            return self.inv(self.xor_(self.inv_src[a], b))
        if isinstance(b, str) and b in self.inv_src:
            return self.inv(self.xor_(a, self.inv_src[b]))
        if self._is_const(a):
            return b if a == 0 else self.inv(b)
        if self._is_const(b):
            return a if b == 0 else self.inv(a)
        if a == b:
            return 0
        if self.inv_src.get(a) == b or self.inv_src.get(b) == a:
            return 1
        return None

    def map_expr(self, e, resolver):
        k = e.kind
        if k == "const":
            return int(bool(e.a))
        if k == "var":
            return resolver(e.a)
        if k == "not":
            return self.inv(self.map_expr(e.a, resolver))
        if k == "mux":
            c = self.map_expr(e.a, resolver)
            t = self.map_expr(e.b, resolver)
            f = self.map_expr(e.c, resolver)
            if self._is_const(c):
                return t if c else f
            if t == f:
                return t
            return self.mux(c, t, f)
        x = self.map_expr(e.a, resolver)
        y = self.map_expr(e.b, resolver)
        return {"AND": self.and_, "OR": self.or_, "XOR": self.xor_}[k](x, y)

    # ---------- BDD -> gates ----------
    def map_node(self, u):
        if u in (0, 1):
            return u
        if u in self.cache:
            return self.cache[u]
        n = self.bdd.nodes[u]
        y = self.mux(n.var, self.map_node(n.high), self.map_node(n.low))
        self.cache[u] = y
        return y

    def bind_output(self, name, signal):
        """Attach an already-mapped signal (net name or 0/1) to an output."""
        self.pending.append((name, signal))

    def map_output(self, name, node):
        self.pending.append((name, self.map_node(node)))

    # ---------- finalisation ----------
    def finalize(self):
        """Bind output names, drop dead gates, renumber internal nets."""
        taken = {}                      # internal net -> output name
        extra = []
        for name, sig in self.pending:
            if self._is_const(sig):
                extra.append(Gate(f"TIE{sig}", [], name))
            elif sig in self.inputs or sig in taken:
                # Output equals a primary input or another output: buffer it
                t = self.net()
                extra.append(Gate(self.CELL, [sig, sig], t))
                extra.append(Gate(self.CELL, [t, t], name))
            else:
                taken[sig] = name

        ren = lambda s: taken.get(s, s)
        for g in self.gates:
            g.inputs = [ren(s) for s in g.inputs]
            g.output = ren(g.output)
        # buffers/ties were created with original names; rename their inputs
        for g in extra:
            g.inputs = [ren(s) for s in g.inputs]
        self.gates += extra

        # dead-gate elimination
        driver = {g.output: g for g in self.gates}
        live, stack = set(), list(self.output_names)
        while stack:
            s = stack.pop()
            if s in live or s not in driver:
                continue
            live.add(s)
            stack.extend(driver[s].inputs)
        self.gates = [g for g in self.gates if g.output in live]

        # topological order (buffers/ties were appended at the end)
        driver = {g.output: g for g in self.gates}
        ordered, seen = [], set()

        def visit(g):
            if id(g) in seen:
                return
            seen.add(id(g))
            for sname in g.inputs:
                if sname in driver:
                    visit(driver[sname])
            ordered.append(g)

        for g in self.gates:
            visit(g)
        self.gates = ordered

        # renumber internal nets n1, n2, ... in order
        fixed = set(self.inputs) | set(self.output_names)
        mapping, k = {}, 0
        for g in self.gates:
            if g.output not in fixed and g.output not in mapping:
                k += 1
                while f"n{k}" in fixed:
                    k += 1
                mapping[g.output] = f"n{k}"
        for g in self.gates:
            g.inputs = [mapping.get(s, s) for s in g.inputs]
            g.output = mapping.get(g.output, g.output)

    # ---------- emitters ----------
    def emit_netlist(self):
        return "\n".join(
            f"{g.output} = {g.cell}({', '.join(g.inputs)})"
            for g in self.gates
        )

    def emit_verilog(self, module, inputs, outputs):
        ports = [f"    input {i}" for i in inputs] + \
                [f"    output {o}" for o in outputs]
        lines = [f"module {module}_{self.CELL.lower()[:-1]}(",
                 ",\n".join(ports), ");", ""]
        internal = [g.output for g in self.gates if g.output not in outputs]
        if internal:
            lines += ["wire " + ", ".join(internal) + ";", ""]
        for g in self.gates:
            if g.cell in ("TIE0", "TIE1"):
                pins = f".Y({g.output})"
            else:
                pin_names = ["A", "B", "C"]
                pairs = [f".{pin_names[i]}({s})" for i, s in enumerate(g.inputs)]
                pairs.append(f".Y({g.output})")
                pins = ", ".join(pairs)
            lines.append(f"{g.cell} u_{g.output} ({pins});")
        lines += ["", "endmodule", ""]
        return "\n".join(lines)

    def report(self, module, inputs, outputs, output_nodes):
        counts = {}
        for g in self.gates:
            counts[g.cell] = counts.get(g.cell, 0) + 1
        bdd_lines = [
            f"  {o}: root={n}, reduced BDD nodes={self.bdd.size(n)}"
            for o, n in output_nodes.items()
        ]
        lines = [
            "BDD / TECHNOLOGY-MAPPING REPORT",
            "================================",
            f"Input module: {module}",
            f"Inputs: {', '.join(inputs)}",
            f"Outputs: {', '.join(outputs)}",
            "",
            "BDD:",
            *bdd_lines,
            "",
            "Mapped cells:",
        ]
        for k in sorted(counts):
            lines.append(f"  {k}: {counts[k]}")
        lines += [
            f"  TOTAL: {len(self.gates)}",
            "",
            "Note: educational mapper (ROBDD + Shannon decomposition with",
            "constant folding and inverter sharing). Not an industrial tool.",
        ]
        return "\n".join(lines)


class NANDMapper(BaseMapper):
    CELL = "NAND2"
    ABSORB = 0           # NAND(0, x) = 1

    def and_(self, a, b):
        r = self._fold_and(a, b)
        if r is not None:
            return r
        return self.inv(self.prim(a, b))                 # AND = NOT(NAND)

    def or_(self, a, b):
        r = self._fold_or(a, b)
        if r is not None:
            return r
        return self.prim(self.inv(a), self.inv(b))       # OR = NAND(~a, ~b)

    def xor_(self, a, b):
        r = self._fold_xor(a, b)
        if r is not None:
            return r
        # 4-NAND XOR; n1 = NAND(a,b) is shared with AND(a,b) = NOT(n1)
        n1 = self.prim(a, b)
        return self.prim(self.prim(a, n1), self.prim(b, n1))


class NORMapper(BaseMapper):
    CELL = "NOR2"
    ABSORB = 1           # NOR(1, x) = 0

    def or_(self, a, b):
        r = self._fold_or(a, b)
        if r is not None:
            return r
        return self.inv(self.prim(a, b))                 # OR = NOT(NOR)

    def and_(self, a, b):
        r = self._fold_and(a, b)
        if r is not None:
            return r
        return self.prim(self.inv(a), self.inv(b))       # AND = NOR(~a, ~b)

    def xor_(self, a, b):
        r = self._fold_xor(a, b)
        if r is not None:
            return r
        # a^b = NOR( NOR(a,b), a&b ); a&b is shared with an AND output
        return self.prim(self.prim(a, b), self.and_(a, b))
