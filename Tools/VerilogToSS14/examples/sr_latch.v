// sr_latch.v — SR-триггер на NOR-вентилях
//
// Классическая схема из двух NOR-вентилей.
// В SS14 это 2× LogicGateNor с перекрёстными связями.
//
// Таблица истинности:
//   S=0 R=0 → Q сохраняется (память)
//   S=1 R=0 → Q=1, Qn=0  (Set)
//   S=0 R=1 → Q=0, Qn=1  (Reset)
//   S=1 R=1 → запрещённое состояние
//
// Сборка в SS14:
//   2× пустой circuit + 4× Cable
//   Нужно включить MemoryCell — смотри ниже.
//
// ВАЖНО: Yosys распознаёт эту схему как latch и выдаёт
//        MemoryCell (D-Latch), что правильно для SS14.
module sr_latch (
    input  wire S,   // Set    — SignalSwitch "On"
    input  wire R,   // Reset  — SignalSwitch "Off"
    output wire Q,
    output wire Qn
);
    // Описание через комбинационный цикл — Yosys синтезирует как защёлку
    assign Q  = ~(R | Qn);
    assign Qn = ~(S | Q);
endmodule
