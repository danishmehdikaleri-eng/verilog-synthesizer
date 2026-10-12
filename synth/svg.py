import re
from html import escape

# ---------------------------------------------------------------------------
# Schematic renderer.
#
#  * real gate symbols (AND/OR body, inversion bubble, triangle for NOT/BUF)
#  * a NAND/NOR whose inputs are tied together is drawn as an inverter
#  * every net gets its own vertical "trunk" wire and its own colour, so
#    wires never merge into each other
#  * gates are ordered by the average position of their drivers and moved
#    away from long wires that run behind their column
# ---------------------------------------------------------------------------

PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e",
           "#17becf", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22"]

INPUT_X = 70
PORT_R = 24
ROW = 84
TOP = 110
TRUNK_STEP = 18


class _G:
    pass


def _classify(cell, ins, compact=False):
    c = cell.upper()
    base = re.sub(r"\d+$", "", c)
    if c in ("TIE0", "TIE1"):
        return "TIE", list(ins)
    if base in ("INV", "NOT"):
        return "NOT", list(ins)
    if base == "BUF":
        return "BUF", list(ins)
    if base in ("NAND", "NOR", "AND", "OR", "XOR", "XNOR"):
        if compact and len(ins) >= 2 and len(set(ins)) == 1:   # tied inputs
            return {"NAND": "NOT", "NOR": "NOT"}.get(base, "BUF"), [ins[0]]
        return base, list(ins)
    return "BOX", list(ins)


def _geometry(kind, n):
    """width, height, pin spacing, input-pin x offset"""
    sp = 22 if n == 2 else 18
    h = max(52, sp * (n - 1) + 20) if n > 1 else 52
    if kind in ("AND", "NAND"):
        return (64 + (10 if kind == "NAND" else 0)), h, sp, 0
    if kind in ("OR", "NOR", "XOR", "XNOR"):
        return (64 + (10 if kind in ("NOR", "XNOR") else 0)), h, sp, 10
    if kind == "NOT":
        return 50, 52, sp, 0
    if kind == "BUF":
        return 40, 52, sp, 0
    if kind == "TIE":
        return 44, 30, sp, 0
    return 90, max(52, h), sp, 0


def _symbol(kind, x0, y, w, h):
    """SVG elements of the gate body. x0 = left edge, y = centre."""
    t, b = y - h / 2, y + h / 2
    bubble = kind in ("NAND", "NOR", "XNOR", "NOT")
    bw = 10 if bubble else 0
    body = w - bw
    els = []
    if kind in ("AND", "NAND"):
        r = body / 2
        els.append(f'<path class="gate" d="M {x0} {t} H {x0+body-r*0.0-26} '
                   f'A 26 {h/2} 0 0 1 {x0+body-26+26} {y} '
                   f'A 26 {h/2} 0 0 1 {x0+body-26} {b} H {x0} Z"/>')
    elif kind in ("OR", "NOR", "XOR", "XNOR"):
        els.append(f'<path class="gate" d="M {x0} {t} Q {x0+body*0.6} {t} '
                   f'{x0+body} {y} Q {x0+body*0.6} {b} {x0} {b} '
                   f'Q {x0+18} {y} {x0} {t} Z"/>')
        if kind in ("XOR", "XNOR"):
            els.append(f'<path class="gate-line" d="M {x0-7} {t} '
                       f'Q {x0+11} {y} {x0-7} {b}"/>')
    elif kind in ("NOT", "BUF"):
        tw = body
        els.append(f'<path class="gate" d="M {x0} {y-18} L {x0+tw} {y} '
                   f'L {x0} {y+18} Z"/>')
    elif kind == "TIE":
        els.append(f'<rect class="gate" x="{x0}" y="{t}" width="{w}" '
                   f'height="{h}" rx="6"/>')
    else:
        els.append(f'<rect class="gate" x="{x0}" y="{t}" width="{w}" '
                   f'height="{h}" rx="8"/>')
    if bubble:
        els.append(f'<circle class="gate" cx="{x0+w-5}" cy="{y}" r="5"/>')
    return els


def write_svg(gates, inputs, outputs, width=1200, compact_inverters=False):
    """compact_inverters=False (default): every cell is drawn as the NAND/NOR
    symbol it really is; an inverter is a NAND/NOR with both inputs tied.
    True: draw tied-input NAND/NOR as a triangle-with-bubble inverter.
    BUF cells are never drawn: they are output aliases."""
    # ---------- aliases (BUF) ----------
    alias = {g.output: g.inputs[0] for g in gates
             if g.cell.upper().startswith("BUF") and g.inputs}

    def resolve(n):
        seen = set()
        while n in alias and n not in seen:
            seen.add(n)
            n = alias[n]
        return n

    # ---------- normalise gates, compute layers ----------
    gs = []
    for g in gates:
        if g.output in alias:
            continue
        o = _G()
        o.cell, o.out = g.cell, g.output
        o.kind, o.ins = _classify(g.cell, [resolve(x) for x in g.inputs],
                                  compact_inverters)
        gs.append(o)

    driver = {o.out: o for o in gs}
    layer_of = {n: 0 for n in inputs}
    done, ordered = set(), []

    def visit(o):
        if id(o) in done:
            return
        done.add(id(o))
        for s in o.ins:
            if s in driver:
                visit(driver[s])
        o.layer = 1 + max([layer_of.get(s, 0) for s in o.ins] or [0])
        layer_of[o.out] = o.layer
        ordered.append(o)

    for o in gs:
        visit(o)
    gs = ordered
    max_layer = max((o.layer for o in gs), default=1)
    port_layer = max_layer + 1
    out_net = {n: resolve(n) for n in outputs}
    out_ports = [n for n in outputs if out_net[n] in layer_of]

    # ---------- consumers per net ----------
    # cons[net] = list of (layer, consumer, pin_index)
    cons = {}
    for o in gs:
        for i, s in enumerate(o.ins):
            cons.setdefault(s, []).append((o.layer, o, i))
    for n in out_ports:
        cons.setdefault(out_net[n], []).append((port_layer, n, 0))
    last_use = {n: max(c[0] for c in v) for n, v in cons.items()}

    # ---------- geometry of gates ----------
    for o in gs:
        o.w, o.h, o.sp, o.pin_dx = _geometry(o.kind, len(o.ins))

    layers = {}
    for o in gs:
        layers.setdefault(o.layer, []).append(o)

    # ---------- vertical placement ----------
    ypos = {n: TOP + i * ROW for i, n in enumerate(inputs)}
    src_layer = {n: 0 for n in inputs}
    for L in range(1, max_layer + 1):
        group = layers.get(L, [])
        for o in group:
            ds = [ypos[s] for s in o.ins if s in ypos]
            o.want = sum(ds) / len(ds) if ds else TOP
        group.sort(key=lambda o: o.want)
        blocked = [ypos[n] for n in ypos
                   if src_layer[n] < L < last_use.get(n, 0)]
        prev = None
        for o in group:
            y = o.want if prev is None else max(o.want, prev + ROW)
            y = max(y, TOP)
            moved = True
            while moved:
                moved = False
                for b in blocked:
                    if abs(y - b) < o.h / 2 + 14:
                        y = b + o.h / 2 + 14
                        moved = True
            o.y = y
            prev = y
            ypos[o.out] = y
            src_layer[o.out] = L

    port_y = {}
    prev = None
    for n in sorted(out_ports, key=lambda n: ypos[out_net[n]]):
        yy = ypos[out_net[n]]
        y = yy if prev is None else max(yy, prev + 70)
        port_y[n] = y
        prev = y

    # ---------- trunks and columns ----------
    trunk_nets = {}                      # layer -> [net, ...]
    for n, lst in cons.items():
        for L in {c[0] for c in lst}:
            trunk_nets.setdefault(L, []).append(n)
    for L in trunk_nets:
        trunk_nets[L].sort(key=lambda n: (ypos.get(n, 0), n))

    def gap(L):
        return 60 + TRUNK_STEP * (len(trunk_nets.get(L, [])) + 1)

    prev_right = INPUT_X + PORT_R
    col_left, trunk_x = {}, {}
    for L in range(1, port_layer + 1):
        for k, n in enumerate(trunk_nets.get(L, [])):
            trunk_x[(L, n)] = prev_right + 30 + (k + 1) * TRUNK_STEP
        col_left[L] = prev_right + gap(L)
        if L <= max_layer:
            wcol = max([o.w for o in layers.get(L, [])] or [60])
            prev_right = col_left[L] + wcol
    port_left = col_left[port_layer]

    for o in gs:
        o.x0 = col_left[o.layer]

    # ---------- sources ----------
    def src_pos(n):
        if n in driver:
            o = driver[n]
            return o.x0 + o.w, o.y
        return INPUT_X + PORT_R, ypos[n]

    def pin_pos(L, consumer, i):
        if isinstance(consumer, str):
            return port_left, port_y[consumer]
        o = consumer
        off = (i - (len(o.ins) - 1) / 2) * o.sp
        return o.x0 + o.pin_dx, o.y + off

    colors = {}
    for i, n in enumerate(list(inputs) + [o.out for o in gs]):
        colors[n] = PALETTE[i % len(PALETTE)]

    # ---------- canvas size ----------
    all_y = list(ypos.values()) + list(port_y.values())
    height = max(380, max(all_y) + 110)
    width = max(width, port_left + PORT_R * 2 + 70)

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        """<style>
.title{font:bold 24px Arial,sans-serif;fill:#222}
.subtitle{font:14px Arial,sans-serif;fill:#666}
.gate{fill:#fff;stroke:#222;stroke-width:2}
.gate-line{fill:none;stroke:#222;stroke-width:2}
.kind{font:11px Arial,sans-serif;fill:#777;text-anchor:middle}
.net{font:11px Arial,sans-serif;fill:#555}
.tie{font:bold 15px Arial,sans-serif;fill:#222;text-anchor:middle}
.port{fill:#fff;stroke:#222;stroke-width:2}
.port-label{font:bold 16px Arial,sans-serif;fill:#222;text-anchor:middle}
.wire{fill:none;stroke-width:2.2;stroke-linejoin:round}
</style>""",
        '<rect width="100%" height="100%" fill="white"/>',
        '<text class="title" x="35" y="38">Synthesized Gate-Level Circuit</text>',
        '<text class="subtitle" x="35" y="62">'
        'Generated directly from technology-mapped gates</text>',
    ]

    # ---------- wires (drawn first, gates cover their ends) ----------
    dots = []
    for n, lst in cons.items():
        if n not in ypos:
            continue
        sx, sy = src_pos(n)
        col = colors.get(n, "#333")
        layers_used = sorted({c[0] for c in lst})
        last_tx = trunk_x[(layers_used[-1], n)]
        p.append(f'<path class="wire" stroke="{col}" d="M {sx} {sy} H {last_tx}"/>')
        for L in layers_used:
            tx = trunk_x[(L, n)]
            pins = [pin_pos(L, c, i) for (l2, c, i) in lst if l2 == L]
            ys = [sy] + [py for _, py in pins]
            vmin, vmax = min(ys), max(ys)
            if vmax > vmin:
                p.append(f'<path class="wire" stroke="{col}" '
                         f'd="M {tx} {vmin} V {vmax}"/>')
            for px, py in pins:
                p.append(f'<path class="wire" stroke="{col}" '
                         f'd="M {tx} {py} H {px}"/>')
            # junction dots
            is_last = L == layers_used[-1]
            for y in set(ys):
                cnt = 0
                cnt += 1 if y > vmin else 0
                cnt += 1 if y < vmax else 0
                if y == sy:
                    cnt += 1                                  # coming in
                    if (not is_last) or any(py == y for _, py in pins):
                        cnt += 1                              # going on
                else:
                    cnt += sum(1 for _, py in pins if py == y)
                if cnt >= 3:
                    dots.append((tx, y, col))
    for tx, y, col in dots:
        p.append(f'<circle cx="{tx}" cy="{y}" r="3.6" fill="{col}"/>')

    # ---------- gates ----------
    for o in gs:
        p += _symbol(o.kind, o.x0, o.y, o.w, o.h)
        if o.kind == "TIE":
            p.append(f'<text class="tie" x="{o.x0+o.w/2}" y="{o.y+5}">'
                     f'{escape(o.cell[-1])}</text>')
        else:
            p.append(f'<text class="kind" x="{o.x0+o.w/2}" '
                     f'y="{o.y+o.h/2+14}">{escape(o.cell)}</text>')
        p.append(f'<text class="net" x="{o.x0+o.w+6}" y="{o.y-7}">'
                 f'{escape(o.out)}</text>')

    # ---------- ports ----------
    for n in inputs:
        p.append(f'<circle class="port" cx="{INPUT_X}" cy="{ypos[n]}" r="{PORT_R}"/>')
        p.append(f'<text class="port-label" x="{INPUT_X}" y="{ypos[n]+6}">{escape(n)}</text>')
    for n in out_ports:
        cx = port_left + PORT_R
        p.append(f'<circle class="port" cx="{cx}" cy="{port_y[n]}" r="{PORT_R}"/>')
        p.append(f'<text class="port-label" x="{cx}" y="{port_y[n]+6}">{escape(n)}</text>')

    p.append("</svg>")
    return "\n".join(p)
