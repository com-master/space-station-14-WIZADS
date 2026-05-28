// full_adder.v — Полный сумматор (5 вентилей)
//
// Сборка в SS14:
//   5× пустой circuit (по 3× SteelSheet)
//   10× Cable
//
// Результат: 2x LogicGateXor + 2x LogicGateAnd + 1x LogicGateOr
module full_adder (
    input  wire a,
    input  wire b,
    input  wire cin,
    output wire sum,
    output wire cout
);
    wire s1 = a ^ b;        // [G?] XOR
    wire c1 = a & b;        // [G?] AND
    assign sum  = s1 ^ cin; // [G?] XOR
    wire c2     = s1 & cin; // [G?] AND
    assign cout = c1 | c2;  // [G?] OR
endmodule
