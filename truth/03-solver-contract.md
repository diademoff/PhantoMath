# 03. Контракт решателя — то, что мы должны воспроизвести

Источник: `com/microblink/photomath/core/results/**` (декомпиляция JADX 1.5.6).

Вызов: `CoreEngine.nativeProcessExpression(long ctx, String expression) -> String`,
возвращаемая строка парсится Gson'ом в `CoreSolverData`.

Ниже — полный контракт. Это и есть спецификация нашего Python-бэкенда.

---

## 3.1 Корень ответа

```jsonc
{
  "diagnostics": {                       // CoreSolverDiagnosticsData, опционально
    "solverRequestTime":     1701,       // мс, epoch-подобное (SystemClock)
    "solverEvaluationTime":    3,
    "animationRequestTime":  1705,
    "evaluationTime":           4
  },
  "normalizedInput": {                   // CoreNormalizedInput
    "node":   { /* CoreNode */ },
    "action": { "command": "…", "args": [ /* CoreNode */ ] }
  },
  "normalizedInputNodeStr": "2x+3=7",    // каноническая строка ввода
  "result": {                            // CoreSolverResult
    "problem": { /* CoreNode */ },       // исходное условие
    "solution": { /* CoreNode */ },      // итоговый ответ
    "groups": [ /* CoreSolverGroup */ ]
  }
}
```

`CoreResult` (обёртка) добавляет `extractor` (результат распознавания кадра —
**нам не нужен, камера вне scope**) и `diagnostics` верхнего уровня.

---

## 3.2 CoreNode — AST выражения

```jsonc
{
  "type": "FRACTION",        // CoreNodeType, 143 значения, имя как в enum
  "value": "2",              // строка; null у не-терминалов
  "children": [ /* CoreNode */ ]
}
```

`CoreColoredNode` расширяет его двумя полями (JSON-наследование):

```jsonc
{ "type":"ADD", "value":null, "children":[...],
  "color": 16711680,         // Integer ARGB, nullable
  "crossed": true }          // Boolean, зачёркивание (завершение примеров)
```

Полный список `CoreNodeType` (143) — в `truth/data/enums.json` → `node_types`.
Ключевые группы:

- константы/переменные: `CONSTANT`, `VARIABLE`, `PI`→`CONSTANT`, `EMPTY`, `STRING`
- арифметика: `ADD`, `SUBTRACT`, `MULTIPLY`, `MULTIPLY_IMPLICIT`, `DIVIDE`, `POWER`
- сравнение: `EQUALS`, `NOT_EQUALS`, `LESS_THAN`, `GREATER_THAN`, `APPROXIMATE`
- функции: `SIN`…`ACSCH` (34 шт.), `ROOT`, `ROOT2`, `LOG`, `LOG10`, `LN`, `EXP`
- исчисления: `INTEGRAL`, `INTEGRAL_DEFINITE`, `DERIVATION`, `DERIVATION1`, `LIMIT*`
- структуры: `SYSTEM`, `MATRIX`, `MATRIX_ROW`, `DETERMINANT*`, `PIECEWISE_DEFINITION`
- множества: `UNION`, `INTERSECTION`, `SUBSET_OR_EQUALS`, `ELEMENT_OF`, `LIST`
- оформление: `FRACTION`, `BRACKET`, `ROOT`, `TEXT`, `TEXT_KEY`, `SET`, `IMAGINARY`
- вычисление: `EVALUATE_EXPRESSION`, `CONDITIONAL_EXPRESSION`, `FACTORIAL`, `SIGN`

`CoreNodeType` сериализуется **именем enum** (Gson по умолчанию). Подтверждено
по `CoreNodeDeserializer`/`CoreColoredNodeDeserializer` (отдельные адаптеры есть
только из-за полиморфизма `CoreNode` ↔ `CoreColoredNode`).

---

## 3.3 CoreRichText — локализуемый фрагмент

```jsonc
{ "type": "abs_const_long", "args": [ /* CoreNode[] */ ] }
```

`type` **не** имя ресурса, а ключ. Разрешается в рантайме как
`getString(getIdentifier("step_" + type, "string", pkg))` —
см. `c/a/a/l/g/c0.java:29-42`. Шаблон подставляет `ARG1…ARGn` отрендеренными
`args` (индекс `ARGk` ← `args[k-1]`). Подробности — `04-explanations.md`.

---

## 3.4 CoreSolverGroup — ветки результата

```jsonc
{
  "type": "VERTICAL",          // ResultGroupType: VERTICAL | ANIMATION | GRAPH | BOOKPOINT
  "description":     { /* CoreRichText */ },
  "selectMethodText":{ /* CoreRichText */ },   // «показать другой способ»
  "entries": [
    { "action": { "command":"…", "args":[ /* CoreNode */ ] },
      "result": { /* тип зависит от type группы */ } }
  ]
}
```

Тип `entries[].result` определяется полем `type` (полиморфный адаптер
`CoreSolverGroupSerializerDeserializer`):

| `type` | `entries[].result` |
|---|---|
| `VERTICAL` | `CoreSolverVerticalResult` |
| `ANIMATION` | `CoreAnimationCommandResult` |
| `GRAPH` | `CoreGraphResult` |
| `BOOKPOINT` | — (вне scope) |

**Важно:** `ANIMATION` отдаёт не готовую анимацию, а *запрос команды*
(`CoreAnimationCommandResult`). Саму сцену строит визуальный скрипт из
`model.json`. См. `05-animation.md`.

---

## 3.5 VERTICAL — пошаговое объяснение (наш основной вывод)

```jsonc
// CoreSolverVerticalResult
{
  "header":   { /* CoreRichText */ },     // из CoreSolverBaseResult
  "solution": { /* CoreNode */ },          // финальный ответ
  "steps": [ /* CoreSolverVerticalStep */ ]
}

// CoreSolverVerticalStep
{
  "stepHeaders": [ { /* CoreRichText */ } ],   // заметь: поле называется stepHeaders
  "substeps":    [ /* CoreSolverVerticalSubstep */ ]
}

// CoreSolverVerticalSubstep
{
  "description":  { /* CoreRichText */ },
  "left":         { /* CoreColoredNode */ },   // «было»  (может быть null)
  "right":        { /* CoreColoredNode */ },   // «стало» (может быть null)
  "subanimations":[ /* CoreAnimationCommandResult */ ],
  "subresult":    { /* CoreSolverVerticalResult */ }   // вложенный результат, nullable
}
```

Семантика (по `CoreSolverVerticalStep.a()`): `substeps[0].left` — это
`CoreNode`, отображаемый как «строка шага» (строка слева от стрелки).
`subresult != null` → `substep` раскрывается в отдельный результат
(нажатие раскрывает под-решение). `subanimations[i]` — анимация, если есть.

Это ровно та семантика, которую Photomath показывает пользователю:
`left` → `right`, подпись `description`, необязательные вложенные раскрытия.

**Для Flutter это идеальная модель**: список шагов, у каждого —
`(left, "→", right, description, children[], animation?)`.

---

## 3.6 ANIMATION — запрос анимации

```jsonc
// CoreAnimationCommandResult  (наследует CoreSolverBaseResult → header)
{
  "command":    "ADD",          // строка; ключ потока в model.json (НЕ проверено)
  "type":       "ADD",          // CoreAnimationResultType.toUpperCase()
  "parameters": [ { "name": "…", "value": { /* CoreNode */ } } ],
  "error":      null,
  "diagnostics": { /* CoreAnimationDiagnosticsData */ },
  "result": {                              // CoreAnimationResult
    "header":         { /* CoreRichText */ },
    "subresultType":  "ADD",
    "animation":      { /* CoreAnimation */ },
    "previewAnimation": { /* CoreAnimation */ }
  }
}
```

`CoreAnimation` (готовая сцена, если уже построена):

```jsonc
{
  "size": { /* CoreSize: width/height */ },
  "objects": [ /* CoreAnimationObject */ ],
  "steps":   [ /* CoreAnimationStep */ ]
}
```

- `CoreAnimationObject`: `{ id:int, type:"char", position:{x,y}, size:{…}, alpha:float }`
  + подтип (`Char`, `Circle`, `CircleSector`, `Curve`, `DecimalSign`,
  `LeftBracket`, `Rectangle`, `RightBracket`, `Tooltip`).
  **Значение `type` — lowercase из `getType()`**, не имя enum
  (подтверждено `CoreAnimationObjectSerializerDeserializer`: сравнение с
  `CoreAnimationObjectType.CHAR.getType()`).
- `CoreAnimationStep`: `{ description: CoreRichText, duration: float, actions: [...] }`
- `CoreAnimationAction`: `{ type, objectId:int, start:float, duration:float,
  interpolator:{…} }`, `type` ∈ `changeAlpha`, `changeBorderColor`,
  `changeColor`, `changeFillColor`, `changeRadius`, `changeSize`, `move`,
  `percentageAppear`, `percentageDisappear` (lowercase из `getType()`).

---

## 3.7 GRAPH

```jsonc
// CoreGraphResult
{
  "header":   { /* CoreRichText */ },
  "frame":    { /* RectF */ },
  "maxFrame": { /* RectF */ },
  "xAxis":    { /* CoreGraphAxis */ },
  "yAxis":    { /* CoreGraphAxis */ },
  "info":     { /* CoreGraphInfo */ },
  "plot": {
    "plotArea": { /* CoreGraphPlotArea */ },
    "plotGroups": [ /* CoreGraphPlotGroup */ ],
    "plotCurves": [ /* CoreGraphPlotCurve */ ],
    "plotPoints": [ /* CoreGraphPlotPoint */ ]
  }
}
```

Графики в `data/`. Не разобраны детально (см. `07-open-questions.md`).
Для MVP их можно отложить: Flutter умеет строить графики сам.

---

## 3.8 Вход: InternalCoreInput / действие

```jsonc
// c.a.a.m.k.a — «действие»
{ "command": "solve", "args": [ /* CoreNode[] */ ] }
```

Путь получения:
`CoreEngine.nativeCommandToNodeActionJson(ctx, str)` → `InternalCoreInput`:

```jsonc
{
  "node":   { "type":"…", "value":"…", "children":[ /* InternalCoreNode */ ] },
  "action": { "command":"…", "args":[ /* CoreNode */ ] }
}
```

`InternalCoreNode.type` — **строка**, не enum (в отличие от `CoreNode.type`).
Это единственное место, где тип узла сериализуется строкой; при миграции
нужно быть внимательным.

**НЕ ВОССТАНОВЛЕНО:** точная строка `str`, которую редактор передаёт в
`nativeProcessExpression`. Это отдельная задача (см. `06-plan.md`, этап 0).
Промежуточные детали: редактор оперирует enum операторов
`c.a.a.a.t.a.c` (128 значений, `truth/data/enums.json` → `editor_operators`)
и сериализует дерево через `c.a.a.a.u.a.e` → writer `c.a.a.a.u.a.b`.

---

## 3.9 Чек-лист для Python-бэкенда

| Что реализовать | Приоритет | Сложность |
|---|---|---|
| `CoreNode` + 143 типа | P0 | средняя (AST + рендер) |
| Парсер ввода (LaTeX/наш собственный формат) → `CoreNode` | P0 | средняя |
| `CoreSolverVerticalResult` (шаги) | P0 | высокая (алгоритмы объяснений) |
| `CoreRichText` → текст из `explanations.json` | P0 | низкая |
| `CoreColoredNode` (цвет/зачёркивание) | P1 | низкая |
| Вложенные `subresult` | P1 | низкая |
| `CoreAnimationCommandResult` + `model.json` | P2 | **очень высокая** |
| `CoreGraphResult` | P3 | средняя (или свой рендер) |
| `CoreNormalizedInput` / `normalizedInputNodeStr` | P1 | низкая |
| `diagnostics` | P4 | тривиально |

**Честная оценка объёма:** P0 — это ~3000 сценариев пошаговых объяснений
(алгебра, анализ, матрицы) по 2-5 ключей на шаг. P2 (анимации) — отдельная
подсистема, по объёму сопоставимая со всем остальным вместе взятым.
Разумная стратегия — P0/P1 + простой рендер анимаций по шагам.