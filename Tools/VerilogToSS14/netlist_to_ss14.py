#!/usr/bin/env python3
"""
netlist_to_ss14.py — Convert Yosys JSON netlist to an SS14 circuit build guide.

After running verilog_to_ss14.ys (or the .tcl wrapper), this script reads
the generated output_netlist.json and prints a step-by-step build guide
that tells you which SS14 logic gate entities to place and how to wire them.

Usage:
    python3 netlist_to_ss14.py output_netlist.json
    python3 netlist_to_ss14.py output_netlist.json --yaml
    python3 netlist_to_ss14.py output_netlist.json --module half_adder

Options:
    --yaml              Also write a <module>_spawn.yaml entity list
    --module <name>     Process only the named Verilog module

SS14 entity reference:
    LogicGateAnd  — AND  (2-input, cycle mode with screwdriver)
    LogicGateOr   — OR   (default mode)
    LogicGateXor  — XOR
    LogicGateNand — NAND
    LogicGateNor  — NOR
    LogicGateXnor — XNOR
    MemoryCell    — D-Latch (D=MemoryInput, EN=MemoryEnable)
    NOTE: No NOT entity in SS14 — implemented as NAND with InputA=InputB.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ── SS14 Cell Library ─────────────────────────────────────────────────────────

# Yosys primitive → (SS14 entity ID, short label, {yport: (direction, ss14_port)})
CELL_MAP: dict = {
    "$_AND_":      ("LogicGateAnd",  "AND",       {"A": ("in", "InputA"), "B": ("in", "InputB"), "Y": ("out", "Output")}),
    "$_OR_":       ("LogicGateOr",   "OR",        {"A": ("in", "InputA"), "B": ("in", "InputB"), "Y": ("out", "Output")}),
    "$_XOR_":      ("LogicGateXor",  "XOR",       {"A": ("in", "InputA"), "B": ("in", "InputB"), "Y": ("out", "Output")}),
    "$_NAND_":     ("LogicGateNand", "NAND",      {"A": ("in", "InputA"), "B": ("in", "InputB"), "Y": ("out", "Output")}),
    "$_NOR_":      ("LogicGateNor",  "NOR",       {"A": ("in", "InputA"), "B": ("in", "InputB"), "Y": ("out", "Output")}),
    "$_XNOR_":     ("LogicGateXnor", "XNOR",      {"A": ("in", "InputA"), "B": ("in", "InputB"), "Y": ("out", "Output")}),
    # NOT → SS14 NAND gate with both inputs tied to the same net
    "$_NOT_":      ("LogicGateNand", "NOT→NAND",  {"A": ("in", "InputA"),                         "Y": ("out", "Output")}),
    # D-Latch (positive enable) — natively supported as MemoryCell
    "$_DLATCH_P_": ("MemoryCell",    "D-LATCH",   {"D": ("in", "MemoryInput"), "E": ("in", "MemoryEnable"), "Q": ("out", "Output")}),
    # D flip-flop approximated as D-Latch (edge-triggered → level-triggered warning)
    "$_DFF_P_":    ("MemoryCell",    "DFF→LATCH", {"D": ("in", "MemoryInput"), "C": ("in", "MemoryEnable"), "Q": ("out", "Output")}),
    "$_DFF_N_":    ("MemoryCell",    "DFF→LATCH", {"D": ("in", "MemoryInput"), "C": ("in", "MemoryEnable"), "Q": ("out", "Output")}),
}

# Material cost per SS14 entity (including the 3× SteelSheet empty circuit base)
MATERIALS: dict = {
    "LogicGateAnd":  {"SteelSheet": 3, "Cable": 2},
    "LogicGateOr":   {"SteelSheet": 3, "Cable": 2},
    "LogicGateXor":  {"SteelSheet": 3, "Cable": 2},
    "LogicGateNand": {"SteelSheet": 3, "Cable": 2},
    "LogicGateNor":  {"SteelSheet": 3, "Cable": 2},
    "LogicGateXnor": {"SteelSheet": 3, "Cable": 2},
    "MemoryCell":    {"SteelSheet": 3, "Cable": 2, "Micromanipulator": 2},
}

# ── Net name helpers ──────────────────────────────────────────────────────────

_CONST_LABELS = {0: "GND", "0": "GND", 1: "VCC", "1": "VCC", "x": "X", "z": "Z"}


def bit_label(bit, names: dict) -> str:
    """Return a human-readable label for a single netlist bit."""
    if bit in _CONST_LABELS:
        return _CONST_LABELS[bit]
    try:
        return names.get(int(bit), f"net{bit}")
    except (TypeError, ValueError):
        return str(bit)


def build_bit_names(netnames: dict) -> dict:
    """Map each integer bit ID to the best available net name.

    User-defined names (hide_name=0) are preferred over auto-generated ones.
    """
    result: dict = {}
    for priority in (0, 1):
        for name, info in netnames.items():
            if info.get("hide_name", 0) != priority:
                continue
            for b in info["bits"]:
                if isinstance(b, int) and b not in result:
                    result[b] = name
    return result


# ── Module processing ─────────────────────────────────────────────────────────

def process_module(module_name: str, module: dict, want_yaml: bool) -> None:
    ports    = module.get("ports", {})
    cells    = module.get("cells", {})
    netnames = module.get("netnames", {})
    names    = build_bit_names(netnames)

    inputs  = [n for n, p in ports.items() if p["direction"] == "input"]
    outputs = [n for n, p in ports.items() if p["direction"] == "output"]

    warnings: list = []
    gates:    list = []
    unsupported: set = set()

    # ── Parse cells into gate descriptors ─────────────────────────────────
    for idx, (cname, cell) in enumerate(cells.items(), 1):
        ctype = cell["type"]
        if ctype not in CELL_MAP:
            unsupported.add(ctype)
            continue

        entity, label, portspec = CELL_MAP[ctype]
        conns = cell.get("connections", {})

        # Build per-port list: (direction, ss14_port, net_label)
        port_rows: list = []
        for yport, (direction, ss14_port) in portspec.items():
            bits = conns.get(yport, [])
            net  = bit_label(bits[0], names) if bits else "?"
            port_rows.append((direction, ss14_port, net))

        # NOT gate: tie InputB to the same net as InputA (NAND(A,A) = NOT A)
        is_not = ctype == "$_NOT_"
        if is_not:
            a_bits = conns.get("A", [])
            a_net  = bit_label(a_bits[0], names) if a_bits else "?"
            port_rows.append(("in", "InputB", f"{a_net}  ← tie to InputA"))

        if ctype in ("$_DFF_P_", "$_DFF_N_"):
            warnings.append(
                f"  Gate G{idx} ('{cname}'): edge-triggered DFF mapped to MemoryCell"
                " (D-Latch).\n"
                "    For true edge-triggering, add an EdgeDetector on the clock input."
            )

        gates.append({
            "id":        f"G{idx}",
            "yname":     cname,
            "ctype":     ctype,
            "entity":    entity,
            "label":     label,
            "ports":     port_rows,
            "raw_conns": conns,
        })

    for u in sorted(unsupported):
        warnings.append(
            f"  Unsupported cell '{u}' — skipped."
            " Check that abc used only AND/OR/XOR/NAND/NOR/XNOR."
        )

    # ── Count entities & materials ────────────────────────────────────────
    entity_counts: dict = defaultdict(int)
    for g in gates:
        entity_counts[g["entity"]] += 1

    mat_totals: dict = defaultdict(int)
    for entity, count in entity_counts.items():
        for mat, qty in MATERIALS.get(entity, {}).items():
            mat_totals[mat] += qty * count

    # ── Build net connection map ──────────────────────────────────────────
    # net_label → {"sources": [str, ...], "sinks": [str, ...]}
    nets: dict = defaultdict(lambda: {"sources": [], "sinks": []})

    for pname, pinfo in ports.items():
        for b in pinfo["bits"]:
            n = bit_label(b, names)
            if pinfo["direction"] == "input":
                nets[n]["sources"].append(f"INPUT  '{pname}'")
            else:
                nets[n]["sinks"].append(f"OUTPUT '{pname}'")

    for gate in gates:
        for direction, ss14_port, net in gate["ports"]:
            # Skip constants and the tie annotation
            if net in ("GND", "VCC", "X", "Z") or "←" in net:
                continue
            entry = f"[{gate['id']}:{gate['label']}] .{ss14_port}"
            if direction == "out":
                nets[net]["sources"].append(entry)
            else:
                nets[net]["sinks"].append(entry)

        # NOT gate: register the extra InputB sink on the same net
        if gate["ctype"] == "$_NOT_":
            a_bits = gate["raw_conns"].get("A", [])
            if a_bits:
                n = bit_label(a_bits[0], names)
                nets[n]["sinks"].append(f"[{gate['id']}:NOT→NAND] .InputB  (tied=InputA)")

    # ── Formatted output ──────────────────────────────────────────────────
    total = sum(entity_counts.values())
    W = 66

    print()
    print("╔" + "═" * (W - 2) + "╗")
    title = f"  SS14 CIRCUIT BUILD GUIDE  —  {module_name}"
    print(f"║{title:<{W-2}}║")
    print("╚" + "═" * (W - 2) + "╝")

    print(f"\n  INPUTS  : {', '.join(inputs) or '—'}")
    print(f"  OUTPUTS : {', '.join(outputs) or '—'}")

    print(f"\n  COMPONENTS  ({total} gate{'s' if total != 1 else ''}):")
    for entity, count in sorted(entity_counts.items()):
        print(f"    {count:3}×  {entity}")

    if warnings:
        print("\n  ⚠  NOTES:")
        for w in warnings:
            print(f"     {w}")

    print(f"\n  GATE LIST:")
    hdr = f"    {'Gate':<22}  {'SS14 Port':<18}  Dir  Signal"
    print(hdr)
    print("    " + "─" * (len(hdr) - 4))
    for gate in gates:
        first = True
        for direction, ss14_port, net in gate["ports"]:
            tag = f"[{gate['id']}] {gate['label']}" if first else ""
            arr = "← " if direction == "in" else "→ "
            print(f"    {tag:<22}  {ss14_port:<18}  {arr}  {net}")
            first = False

    print(f"\n  WIRE LIST  (connect each source to all its sinks):")
    for net, roles in sorted(nets.items()):
        srcs = roles["sources"]
        snks = roles["sinks"]
        if not srcs and not snks:
            continue
        print(f"    ┌ net \"{net}\"")
        for s in srcs:
            print(f"    │  source: {s}")
        for s in snks:
            print(f"    │    sink: {s}")
        print(f"    └")

    print(f"\n  MATERIALS:")
    for mat, qty in sorted(mat_totals.items()):
        print(f"    {qty:3}×  {mat}")

    print(f"\n  BUILD STEPS:")
    step = 1
    print(f"    {step}. Gather all materials listed above.")
    step += 1
    print(f"    {step}. For each gate: craft an empty circuit (3× SteelSheet),")
    print(f"       then add the required components using a wrench/screwdriver.")
    step += 1
    print(f"    {step}. Adjust gate modes with a screwdriver (default mode is OR;")
    print(f"       cycle with screwdriver until the label matches the gate type below).")
    step += 1
    for gate in gates:
        note = ""
        if gate["entity"] == "MemoryCell":
            note = "  [no mode change — MemoryCell is built directly]"
        elif gate["ctype"] == "$_NOT_":
            note = "  [wire InputA and InputB to the SAME source signal]"
        print(f"    {step}. Place [{gate['id']}] {gate['entity']}  mode={gate['label']}{note}")
        step += 1
    print(f"    {step}. Wire all connections as shown in WIRE LIST.")
    step += 1
    if inputs:
        print(f"    {step}. Place input devices (SignalSwitch / SignalButton) for: {', '.join(inputs)}")
        step += 1
    if outputs:
        print(f"    {step}. Connect output ports to actuators: {', '.join(outputs)}")
    print()

    # ── Optional YAML spawn list ──────────────────────────────────────────
    if want_yaml:
        out_path = Path(f"{module_name}_spawn.yaml")
        lines = [
            f"# SS14 entity spawn list — module: {module_name}",
            "# Spawn each entity with the admin 'spawn' command, then wire as per build guide.",
            "entities:",
        ]
        for g in gates:
            lines.append(f"  - type: {g['entity']}")
            lines.append(f"    # {g['id']} ({g['label']})  from Verilog cell '{g['yname']}'")
        out_path.write_text("\n".join(lines) + "\n")
        print(f"  → YAML spawn list written: {out_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if not args or "-h" in args or "--help" in args:
        print(__doc__)
        sys.exit(0)

    netlist_path = args[0]
    want_yaml = "--yaml" in args

    module_filter: Optional[str] = None
    if "--module" in args:
        i = args.index("--module")
        if i + 1 < len(args):
            module_filter = args[i + 1]

    try:
        data = json.loads(Path(netlist_path).read_text())
    except FileNotFoundError:
        print(f"ERROR: file not found: {netlist_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in {netlist_path}: {e}", file=sys.stderr)
        sys.exit(1)

    modules = data.get("modules", {})
    if not modules:
        print("ERROR: no modules found in netlist.", file=sys.stderr)
        sys.exit(1)

    if module_filter and module_filter not in modules:
        print(
            f"ERROR: module '{module_filter}' not found.\n"
            f"Available: {', '.join(modules)}",
            file=sys.stderr,
        )
        sys.exit(1)

    for mname, mdata in modules.items():
        if module_filter and mname != module_filter:
            continue
        process_module(mname, mdata, want_yaml)


if __name__ == "__main__":
    main()
