#!/usr/bin/env -S yosys -c
# ============================================================
#  verilog_to_ss14.tcl — Tcl entry point for yosys -c
#  Wraps verilog_to_ss14.ys with argument handling.
# ============================================================
#
# Usage:
#   yosys -c verilog_to_ss14.tcl -- design.v
#   yosys -c verilog_to_ss14.tcl -- design.v TopModule
#
# Arguments:
#   design.v    Path to the Verilog source file (required)
#   TopModule   Top-level module name (optional, auto-detected if omitted)
#
# After synthesis, run:
#   python3 netlist_to_ss14.py output_netlist.json
# ─────────────────────────────────────────────────────────────

if {$argc < 1} {
    puts stderr ""
    puts stderr "  Usage: yosys -c verilog_to_ss14.tcl -- <design.v> \[TopModule\]"
    puts stderr ""
    exit 1
}

set verilog_file [lindex $argv 0]
set top_module   [expr {$argc >= 2 ? [lindex $argv 1] : ""}]

if {![file exists $verilog_file]} {
    puts stderr "ERROR: file not found: $verilog_file"
    exit 1
}

puts ""
puts "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
puts "  Verilog → SS14  synthesis"
puts "  Input : $verilog_file"
if {$top_module ne ""} {
    puts "  Top   : $top_module"
} else {
    puts "  Top   : (auto-detect)"
}
puts "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
puts ""

# Read the Verilog file (SystemVerilog syntax also accepted)
yosys read_verilog -sv $verilog_file

# Elaborate
if {$top_module ne ""} {
    yosys hierarchy -check -top $top_module
} else {
    yosys hierarchy -check -auto-top
}

# ── Synthesis passes (mirrors verilog_to_ss14.ys) ────────────
yosys proc
yosys opt
yosys flatten
yosys opt
yosys memory -nomap
yosys opt
yosys techmap
yosys opt -fast
yosys abc -g AND,OR,XOR,NAND,NOR,XNOR
yosys simplemap
yosys opt_clean -purge

# ── Report & output ──────────────────────────────────────────
yosys tee -o synthesis_report.txt stat
yosys write_json output_netlist.json

puts ""
puts "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
puts "  Synthesis complete!"
puts ""
puts "  Next step:"
puts "    python3 netlist_to_ss14.py output_netlist.json"
puts "    python3 netlist_to_ss14.py output_netlist.json --yaml"
puts "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
puts ""
