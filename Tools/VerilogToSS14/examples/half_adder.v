// half_adder.v — Полусумматор (2 вентиля)
//
// Сборка в SS14:
//   2× пустой circuit (по 3× SteelSheet)
//   4× Cable
//
// Результат: 1x LogicGateXor + 1x LogicGateAnd
module half_adder (
    input  wire a,
    input  wire b,
    output wire sum,
    output wire carry
);
    assign sum   = a ^ b;  // XOR
    assign carry = a & b;  // AND
endmodule
