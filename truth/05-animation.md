# 05. Анимации и визуальный скрипт

## Два уровня

1. **Решатель** отдаёт `CoreAnimationCommandResult` — **запрос**: имя команды
   + параметры (`CoreNode[]`).
2. **Визуальный скрипт** (`assets/resources/model.json`) превращает запрос в
   сцену: `CoreAnimation { size, objects[], steps[] }`, где `steps[i]` —
   `{ description, duration, actions[] }`.

Анимация, таким образом, **не захардкожена в решателе**: она генерируется
графом из `model.json` по параметрам команды.

## model.json

Node-RED-подобный формат. **51 поток**, 2515 узлов, 9 категорий.

```jsonc
{
  "id": "67", "name": "Encircle", "group": "action", "version": 2,
  "category": "action",             // data | object | action | event
  "inputs": [3], "outputs": [7],
  "variables": [ … ],               // локальные переменные потока
  "instances": [                    // узлы графа
    { "node": { "name":"Input Number", "identifier":"input.number" },
      "position": { "x": 616.0, "y": -81.2 },
      "externals": [ { "pin": { "name":"Activate","identifier":"output.activate" },
                       "kind":"output", "variable":0 } ],
      "parameters": [ … ] }
  ],
  "connections": [ … ]
}
```

Индекс всех 51 потока — `truth/data/animation-flows.json`.

### Реестр потоков (выборочно)

| id | Категория | Имя | Узлов |
|---|---|---|---|
| 16 | data | Additive Inverse | 3 |
| 18 | data | Distance Between 2 Points | 11 |
| 21 | data | Midpoint | 10 |
| 55 | data | Round to Nearest Whole | 19 |
| 59 | data | Exponentiation | 27 |
| 67 | action | Encircle | 16 |
| 93 | action | Initial Alignment | 26 |
| 189 | data | Is Prime | 20 |
| 253 | action | Switch Objects | 12 |
| 322 | action | Move Along Axes | 37 |
| 401 | object | Create Brackets around Object | 18 |
| 428 | action | Replace Object | 12 |
| 496 | event | While | 6 |
| 550 | data | Prime Factorization | 26 |
| 617 | action | Slide Appear | 79 |
| 385 | object | Create Alternating Repeated Multiplication | 272 |
| 100 | — | Write in Standard Form | 285 |
| 151 | object | Create Number in American notation | 249 |

Заметен контраст: простые команды — 3-6 узлов, сложные рендеры — 150-285.

### Топ-типы узлов графа

`Create Text` (185), `Object Variable` (179), `Number Variable` (157),
`Branch` (153), `Set Number Variable` (136), `Change Alpha` (111),
`Add To Object Variable` (96), `Move Relative` (84), `Input Number` (73),
`Equal` (73), `Get Object Bounds` (63), `Change Color` (63), `Loop` (42),
`Bounce` (30), `Output Object` (32), `Make Point` (24) …

Всего 123 различных типа узлов. Это полноценный императивный DSL внутри JSON:
есть циклы (`Loop`), ветвления (`Branch`), арифметика (`Add Values`,
`Subtract Values`, `Multiply Values`, `Divide Values`), работа с объектами
(`Get Sub-Object`, `Get Object Bounds`, `Output Object`).

## Сцена

```jsonc
{
  "size": { "width": 0, "height": 0 },              // CoreSize
  "objects": [
    { "id": 7, "type": "char", "position": {"x":10,"y":20},
      "size": {"width":12,"height":24}, "alpha": 1.0
      /* + поля подтипа, напр. value/angle/radius */ }
  ],
  "steps": [
    { "description": { /* CoreRichText */ },
      "duration": 300.0,
      "actions": [
        { "type":"move", "objectId":7, "start":0.0, "duration":300.0,
          "interpolator": { /* … */ } }
      ] }
  ]
}
```

### Типы объектов (9) — значение `type` в lowercase

`char`, `circle`, `circleSector`, `curve`, `decimalSign`, `leftBracket`,
`rectangle`, `rightBracket`, `tooltip`

Подтипы добавляют поля: `CoreAnimationCharObject` (символ/шрифт),
`CoreAnimationCircleSectorObject` (углы сектора), `CoreAnimationCurveObject`
(кривая Безье), `CoreAnimationTooltipObject` (выноска с текстом),
`CoreAnimationRectangleObject` (скругления, заливка, обводка).

### Типы действий (9)

`changeAlpha`, `changeBorderColor`, `changeColor`, `changeFillColor`,
`changeRadius`, `changeSize`, `move`, `percentageAppear`, `percentageDisappear`

Каждое: `{ type, objectId, start, duration, interpolator }`.

### Типы результата анимации (30, `CoreAnimationResultType`)

`ADD`, `SUB`, `ADD_INT_CHIPS`, `MUL_US`, `MUL_LTR`, `MUL_RTL`, `DIV_US`,
`DIV_RU`, `DIV_STANDARD`, `POLY_DIV_*`, `FRAC_TO_DEC_*`, `ALG_TILE_ADD_SUB`,
`ALG_TILE_MUL`, `EQUIV_FRAC_USING_MULTIPLIC`, `EQUIV_FRAC_USING_DIVISION`,
`REPR_FRAC_MODEL_RECT`, `REPR_FRAC_MODEL_CIRC`, `ROUND_INT_TEN`,
`ROUND_INT_HUNDRED`, `ROUND_INT_THOUSAND`, `ROUND_DEC_HUNDREDTH`,
`ROUND_DEC_TENTH`, `ROUND_DEC_WHOLE`

Это «как именно показать» операцию: `MUL_LTR` vs `MUL_RTL` — умножение
слева направо или справа налево; `DIV_US` vs `DIV_RU` — деление углом сверху
снизу или снизу вверх. **UX-семантика зашита в имена.**

## NodeRuntime.js (308 KB)

Минифицированный JS-рантайм (core-js-подобные хелперы, `globalThis`/`window`
полифилл, `__require`). В Java-коде ссылок нет (`grep` по `NodeRuntime` —
пусто), значит загружается нативно. Вероятно — исполнение JS-логики решателя
в изоляции. Для переписки **не требуется**.

## Что делать нам

Рекомендация по приоритету:

| Вариант | Что даёт | Объём работы |
|---|---|---|
| **A. Игнорировать анимации** | Шаги показываются списком, как `VERTICAL` | нулевой |
| **B. Микро-анимации из шагов** | `left → right` с подсветкой/зачёркиванием через `CoreColoredNode` | небольшой |
| **C. Исполнить model.json** | Полный паритет анимаций | сопоставим со всем остальным проектом |

**Выбор: B для MVP.** `CoreColoredNode` уже несёт `color` и `crossed` —
этого достаточно для «было → стало» с визуальным акцентом. Переход к C
возможен позже, потому что `model.json` — это данные, а не код: интерпретатор
можно написать, если будет нужен паритет.

Важно: анимации **не** несут семантику решения — она целиком в `VERTICAL`-шагах
и в `CoreRichText`. Поэтому их отсутствие не ломает объяснение.