from dataclasses import dataclass
import re


@dataclass
class Design:
    module: str
    inputs: list
    outputs: list
    assignments: dict


# Tokenizer for a useful combinational Verilog subset:
# identifiers, &, |, ^, ~, !, parentheses, constants 0/1, and ?:
TOKEN_RE = re.compile(
    r"""
    (?P<WS>\s+)
  | (?P<COMMENT>//[^\n]*|/\*.*?\*/)
  | (?P<OP>===|!==|==|!=|&&|\|\||[&|^~!?:(),;=])
  | (?P<NUM>1'b[01]|1'h[0-9a-fA-F]+|[01])
  | (?P<ID>[A-Za-z_][A-Za-z0-9_$]*)
    """,
    re.VERBOSE | re.DOTALL,
)


def tokenize(s):
    pos = 0
    out = []
    while pos < len(s):
        m = TOKEN_RE.match(s, pos)
        if not m:
            raise SyntaxError(f"Cannot tokenize near: {s[pos:pos+40]!r}")
        pos = m.end()
        if m.lastgroup in ("WS", "COMMENT"):
            continue
        out.append(m.group(m.lastgroup))
    return out


class Expr:
    def __init__(self, kind, a=None, b=None, c=None):
        self.kind, self.a, self.b, self.c = kind, a, b, c

    def __str__(self):
        k = self.kind
        if k == "var":
            return self.a
        if k == "const":
            return str(self.a)
        if k == "not":
            return f"(~{self.a})"
        if k == "mux":
            return f"({self.a}?{self.b}:{self.c})"
        return f"({self.a} {k} {self.b})"


class Parser:
    def __init__(self, tokens):
        self.t = tokens
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self, x=None):
        v = self.peek()
        if v is None:
            raise SyntaxError("Unexpected end of expression")
        if x is not None and v != x:
            raise SyntaxError(f"Expected {x}, got {v}")
        self.i += 1
        return v

    def expr(self):
        return self.ternary()

    def ternary(self):
        a = self.or_expr()
        if self.peek() == "?":
            self.take("?")
            b = self.ternary()
            self.take(":")
            c = self.ternary()
            return Expr("mux", a, b, c)
        return a

    def or_expr(self):
        x = self.xor_expr()
        while self.peek() in ("|", "||"):
            op = self.take()
            y = self.xor_expr()
            x = Expr("OR", x, y)
        return x

    def xor_expr(self):
        x = self.and_expr()
        while self.peek() == "^":
            self.take("^")
            y = self.and_expr()
            x = Expr("XOR", x, y)
        return x

    def and_expr(self):
        x = self.unary()
        while self.peek() in ("&", "&&"):
            self.take()
            y = self.unary()
            x = Expr("AND", x, y)
        return x

    def unary(self):
        if self.peek() in ("~", "!"):
            self.take()
            return Expr("not", self.unary())
        if self.peek() == "(":
            self.take("(")
            x = self.expr()
            self.take(")")
            return x
        v = self.take()
        if v in ("0", "1"):
            return Expr("const", int(v))
        if re.fullmatch(r"1'b[01]", v):
            return Expr("const", int(v[-1]))
        if re.fullmatch(r"1'h[0-9a-fA-F]+", v):
            return Expr("const", int(v[-1], 16) & 1)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", v):
            return Expr("var", v)
        raise SyntaxError(f"Unexpected token {v}")


def parse_verilog(text):
    # Remove comments and simple preprocessor lines.
    text = re.sub(r"`[^\n]*", "", text)
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)

    mm = re.search(r"\bmodule\s+([A-Za-z_]\w*)\b", text)
    if not mm:
        raise SyntaxError("No module declaration found")
    module = mm.group(1)

    # Collect ANSI/non-ANSI one-bit ports.
    inputs = []
    outputs = []

    for m in re.finditer(r"\binput\b\s+([^;)]*?)(?=\binput\b|\boutput\b|\))", text):
        chunk = re.sub(r"\[[^]]+\]", "", m.group(1))
        inputs += [x for x in re.findall(r"[A-Za-z_]\w*", chunk)
                   if x not in ("wire", "reg", "logic", "input", "output")]

    for m in re.finditer(r"\boutput\b\s+([^;)]*?)(?=\binput\b|\boutput\b|\))", text):
        chunk = re.sub(r"\[[^]]+\]", "", m.group(1))
        outputs += [x for x in re.findall(r"[A-Za-z_]\w*", chunk)
                    if x not in ("wire", "reg", "logic", "input", "output")]

    inputs = list(dict.fromkeys(inputs))
    outputs = list(dict.fromkeys(outputs))

    # assign lhs = rhs;
    assignments = {}
    for m in re.finditer(
        r"\bassign\s+([A-Za-z_]\w*)\s*=\s*(.*?);", text, flags=re.S
    ):
        lhs, rhs = m.group(1), m.group(2).strip()
        assignments[lhs] = Parser(tokenize(rhs)).expr()

    # A simple always_comb/always @* form: only a single blocking assignment
    # per block is intentionally supported.
    for m in re.finditer(
        r"\balways(?:_comb|\s*@\s*\(\s*\*\s*\)|\s*@\s*\*)\s*begin(.*?)end",
        text, flags=re.S
    ):
        block = m.group(1)
        for a in re.finditer(
            r"([A-Za-z_]\w*)\s*=\s*(.*?);", block, flags=re.S
        ):
            lhs, rhs = a.group(1), a.group(2).strip()
            assignments[lhs] = Parser(tokenize(rhs)).expr()

    if not inputs:
        raise SyntaxError("No input ports found")
    if not outputs:
        raise SyntaxError("No output ports found")
    if not assignments:
        raise SyntaxError("No continuous/combinational assignment found")

    # Ensure output signals have expressions. If output is driven through an
    # intermediate wire, resolve it later in main.py.
    return Design(module, inputs, outputs, assignments)
