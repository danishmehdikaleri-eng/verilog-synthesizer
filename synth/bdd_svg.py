from pathlib import Path
from html import escape


def _node_key(bdd, node_id):
    n = bdd.nodes[node_id]
    return (bdd.level.get(n.var, 10**9), node_id)


def _collect_nodes(bdd, root):
    seen = set()
    stack = [root]

    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)

        node = bdd.nodes[node_id]
        if node.var is not None:
            stack.append(node.low)
            stack.append(node.high)

    return seen


def _order_level_nodes(bdd, nodes_by_level, edges):
    """
    Reduce visual crossings using a few barycenter sweeps.
    Variable levels remain fixed; only nodes within a level move.
    """
    levels = sorted(nodes_by_level)

    order = {
        level: sorted(nodes_by_level[level], key=lambda n: _node_key(bdd, n))
        for level in levels
    }

    def index_map(level):
        return {n: i for i, n in enumerate(order[level])}

    # Downward / upward sweeps.
    for _ in range(8):
        for li in range(1, len(levels)):
            level = levels[li]
            prev = levels[li - 1]
            prev_idx = index_map(prev)

            scored = []
            for n in order[level]:
                parents = edges.get(("parents", n), [])
                pos = [prev_idx[p] for p in parents if p in prev_idx]
                score = sum(pos) / len(pos) if pos else order[level].index(n)
                scored.append((score, n))

            order[level] = [n for _, n in sorted(scored)]

        for li in range(len(levels) - 2, -1, -1):
            level = levels[li]
            nxt = levels[li + 1]
            nxt_idx = index_map(nxt)

            scored = []
            for n in order[level]:
                children = edges.get(("children", n), [])
                pos = [nxt_idx[c] for c in children if c in nxt_idx]
                score = sum(pos) / len(pos) if pos else order[level].index(n)
                scored.append((score, n))

            order[level] = [n for _, n in sorted(scored)]

    return order


def write_bdd_svg(
    bdd,
    root,
    title="ROBDD",
    width_per_node=150,
    level_gap=125,
    side_margin=100,
    top_margin=115,
    bottom_margin=120,
):
    """
    Render the actual ROBDD stored in BDDManager.

    Style:
      - one vertical column per BDD variable
      - low/0 edge = dashed
      - high/1 edge = solid
      - terminals at the bottom
      - crossing-reduced node ordering
      - no fake/manual BDD structure
    """

    reachable = _collect_nodes(bdd, root)

    # Terminal-only BDD.
    nonterminals = [
        n for n in reachable if bdd.nodes[n].var is not None
    ]

    # Group by BDD variable level.
    nodes_by_level = {}
    for node_id in nonterminals:
        var = bdd.nodes[node_id].var
        level = bdd.level[var]
        nodes_by_level.setdefault(level, []).append(node_id)

    levels = sorted(nodes_by_level)

    # Build parent/child relations for ordering.
    edges = {}
    for node_id in nonterminals:
        node = bdd.nodes[node_id]

        for child in (node.low, node.high):
            if child in reachable:
                edges.setdefault(("parents", child), []).append(node_id)
                edges.setdefault(("children", node_id), []).append(child)

    order = _order_level_nodes(bdd, nodes_by_level, edges)

    # Every variable level gets a column even if the ROBDD skips it.
    max_level = max(levels, default=-1)
    level_to_y = {
        level: top_margin + level * level_gap
        for level in range(max_level + 1)
    }

    # Terminal level.
    terminal_y = (
        top_margin + (max_level + 1) * level_gap
        if max_level >= 0
        else top_margin + level_gap
    )

    # Spread each level independently.
    max_nodes_in_level = max(
        [len(order[level]) for level in levels] + [2]
    )

    # Include terminal pair in width calculation.
    canvas_width = max(
        900,
        side_margin * 2 + max_nodes_in_level * width_per_node,
        side_margin * 2 + 2 * width_per_node,
    )

    positions = {}

    for level in levels:
        nodes = order[level]
        count = len(nodes)

        usable_width = canvas_width - 2 * side_margin
        if count == 1:
            xs = [canvas_width / 2]
        else:
            step = usable_width / (count - 1)
            xs = [side_margin + i * step for i in range(count)]

        for x, node_id in zip(xs, nodes):
            positions[node_id] = (x, level_to_y[level])

    # Put terminals at bottom.
    terminal_center = canvas_width / 2
    terminal_offset = min(190, canvas_width / 4)

    positions[0] = (
        terminal_center - terminal_offset,
        terminal_y,
    )
    positions[1] = (
        terminal_center + terminal_offset,
        terminal_y,
    )

    canvas_height = terminal_y + bottom_margin

    def esc(value):
        return escape(str(value), quote=True)

    def curve(x1, y1, x2, y2):
        mid_y = (y1 + y2) / 2
        return (
            f"M {x1:.1f},{y1:.1f} "
            f"C {x1:.1f},{mid_y:.1f} "
            f"{x2:.1f},{mid_y:.1f} "
            f"{x2:.1f},{y2:.1f}"
        )

    # BDDManager stores the variable ordering in bdd.level.
    # Lower level number means earlier variable in the ROBDD order.
    variable_order = sorted(
        bdd.level.keys(),
        key=lambda v: bdd.level[v]
    )

    svg = []

    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{canvas_width:.0f}" height="{canvas_height:.0f}" '
        f'viewBox="0 0 {canvas_width:.0f} {canvas_height:.0f}">'
    )

    svg.append("""
<style>
    .title {
        font-family: Arial, sans-serif;
        font-size: 24px;
        font-weight: bold;
        fill: #222;
    }

    .subtitle {
        font-family: Arial, sans-serif;
        font-size: 13px;
        fill: #666;
    }

    .level-label {
        font-family: Arial, sans-serif;
        font-size: 13px;
        font-weight: bold;
        fill: #555;
    }

    .node {
        fill: white;
        stroke: #222;
        stroke-width: 2;
    }

    .node-text {
        font-family: Arial, sans-serif;
        font-size: 15px;
        font-weight: bold;
        fill: #222;
        text-anchor: middle;
        dominant-baseline: middle;
    }

    .terminal {
        fill: white;
        stroke: #222;
        stroke-width: 2;
        rx: 10;
    }

    .terminal-text {
        font-family: Arial, sans-serif;
        font-size: 14px;
        font-weight: bold;
        text-anchor: middle;
        dominant-baseline: middle;
    }

    .edge {
        fill: none;
        stroke: #555;
        stroke-width: 2;
    }

    .low-edge {
        stroke-dasharray: 7 5;
    }

    .edge-label {
        font-family: Arial, sans-serif;
        font-size: 12px;
        font-weight: bold;
        fill: #444;
    }

    .root-label {
        font-family: Arial, sans-serif;
        font-size: 12px;
        font-weight: bold;
        fill: #555;
    }

    .level-line {
        stroke: #e5e5e5;
        stroke-width: 1;
        stroke-dasharray: 4 6;
    }

    .legend {
        font-family: Arial, sans-serif;
        font-size: 12px;
        fill: #555;
    }
</style>
""")

    svg.append(
        f'<rect width="100%" height="100%" fill="white"/>'
    )

    svg.append(
        f'<text x="{canvas_width/2:.1f}" y="38" '
        f'class="title" text-anchor="middle">{esc(title)}</text>'
    )

    svg.append(
        f'<text x="{canvas_width/2:.1f}" y="61" '
        f'class="subtitle" text-anchor="middle">'
        f'ROBDD • {len(nonterminals)} decision nodes • '
        f'variable order: {esc(", ".join(variable_order))}'
        f'</text>'
    )

    # Variable level guides and labels.
    for level in levels:
        y = level_to_y[level]
        var_names = [
            n for n in variable_order
            if bdd.level[n] == level
        ]
        var_name = var_names[0] if var_names else f"L{level}"

        svg.append(
            f'<line x1="35" y1="{y:.1f}" '
            f'x2="{canvas_width-35:.1f}" y2="{y:.1f}" '
            f'class="level-line"/>'
        )

        svg.append(
            f'<text x="48" y="{y-10:.1f}" '
            f'class="level-label">{esc(var_name)}</text>'
        )

    # Draw edges first.
    for node_id in nonterminals:
        node = bdd.nodes[node_id]
        x1, y1 = positions[node_id]

        for child, branch in (
            (node.low, "0"),
            (node.high, "1"),
        ):
            if child not in positions:
                continue

            x2, y2 = positions[child]
            path = curve(x1, y1, x2, y2)

            cls = "edge low-edge" if branch == "0" else "edge"

            svg.append(
                f'<path d="{path}" class="{cls}"/>'
            )

            # Edge label near upper third of curve.
            lx = x1 * 0.68 + x2 * 0.32
            ly = y1 * 0.68 + y2 * 0.32

            # Small side offset prevents labels sitting directly on wires.
            offset = -9 if branch == "0" else 9

            svg.append(
                f'<text x="{lx + offset:.1f}" y="{ly:.1f}" '
                f'class="edge-label">{branch}</text>'
            )

    # Root marker.
    if root in positions:
        rx, ry = positions[root]
        svg.append(
            f'<text x="{rx:.1f}" y="{ry-35:.1f}" '
            f'class="root-label" text-anchor="middle">ROOT</text>'
        )

    # Draw decision nodes.
    radius = 25

    for node_id in nonterminals:
        node = bdd.nodes[node_id]
        x, y = positions[node_id]

        svg.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" '
            f'class="node"/>'
        )

        svg.append(
            f'<text x="{x:.1f}" y="{y:.1f}" '
            f'class="node-text">{esc(node.var)}</text>'
        )

    # Terminals.
    for terminal, label in ((0, "FALSE (0)"), (1, "TRUE (1)")):
        x, y = positions[terminal]

        svg.append(
            f'<rect x="{x-58:.1f}" y="{y-23:.1f}" '
            f'width="116" height="46" class="terminal"/>'
        )

        svg.append(
            f'<text x="{x:.1f}" y="{y:.1f}" '
            f'class="terminal-text">{label}</text>'
        )

    # Legend.
    legend_y = canvas_height - 32

    svg.append(
        f'<line x1="45" y1="{legend_y}" x2="90" y2="{legend_y}" '
        f'class="edge low-edge"/>'
    )
    svg.append(
        f'<text x="100" y="{legend_y+4}" class="legend">'
        f'0 / LOW</text>'
    )

    svg.append(
        f'<line x1="175" y1="{legend_y}" x2="220" y2="{legend_y}" '
        f'class="edge"/>'
    )
    svg.append(
        f'<text x="230" y="{legend_y+4}" class="legend">'
        f'1 / HIGH</text>'
    )

    svg.append("</svg>")

    return "\n".join(svg)


def save_bdd_svg(bdd, root, path, title="ROBDD"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    svg = write_bdd_svg(
        bdd,
        root,
        title=title,
    )

    path.write_text(svg, encoding="utf-8")
    return path
