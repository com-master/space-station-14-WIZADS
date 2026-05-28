// door_lock.v — Контроллер шлюза для SS14
//
// Логика: шлюз открывается только при одновременном выполнении условий:
//   - id_valid   : карточка доступа распознана (ID-сканер → InputA)
//   - no_intruder: нет сигнала тревоги (датчик движения → InputA)
//   - power_ok   : есть питание (PowerSensor → InputA)
//
// Тревога включается когда: есть нарушитель И шлюз открыт.
//
// Подключение выходов в SS14:
//   unlock → порт "Open" шлюза
//   alarm  → порт "Toggle" сирены
//
// Сборка в SS14:
//   ~5× пустой circuit (по 3× SteelSheet)
//   ~10× Cable
module door_lock (
    input  wire id_valid,
    input  wire intruder,
    input  wire power_ok,
    output wire unlock,
    output wire alarm
);
    wire no_intruder = ~intruder;               // NOT  → NAND(A,A)
    wire authorized  = id_valid & no_intruder;  // AND
    assign unlock    = authorized & power_ok;   // AND

    wire no_power    = ~power_ok;               // NOT  → NAND(A,A)
    assign alarm     = intruder & no_power;     // AND  (тревога без питания)
endmodule
