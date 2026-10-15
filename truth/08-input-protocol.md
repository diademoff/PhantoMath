# 08. Протокол входа решателя — ВОССТАНОВЛЕН

**Статус: закрыт.** Формат строки, которую редактор передаёт в
`nativeProcessExpression(ctx, str)`, восстановлена полностью и подтверждена
двумя независимыми источниками: кодом (Java) и строковой таблицей нативного
парсера.

## Формат

Инфиксная строка, построенная как **S-выражение с фигурными скобками**.

```
{<узел>,<узел>,…}          группа узлов одной строки (скобки = порядок чтения)
<функция>(<арг1>,<арг2>)   узел с аргументами
<буква>/<цифры>/<символ>    лист
```

Пустые группы отбрасываются. Несколько строк (система уравнений) оборачиваются:

```
 system({строка1},{строка2}) 
```

Обратите внимание на ведущий и завершающий пробелы — они есть в оригинале
(`b.e()`, строки `" system("` и `") "`).

## Точки кода

| Что | Где |
|---|---|
| Точка входа | `CoreEngine.nativeProcessExpression(long, String)` |
| Сборка строки | `c/a/a/a/u/a/b.java:220` — `String e()`, в комментарии Kotlin: `editorModel.infixRepresentation` |
| Обёртка строки | `c/a/a/a/u/a/i/a.java` — `f(StringBuilder)`: `'{' … '}'` |
| Узел с аргументами | `c/a/a/a/u/a/j/c/a/f.java` — `j(StringBuilder)`: `M(` арг`,`…`)` |
| Символьный узел | `c/a/a/a/u/a/j/c/c/a.java` — `j(StringBuilder)`: `sb.append(toString())` |
| Словарь операторов | `M()` у классов в `c/a/a/a/u/a/j/c/a/*.java` |

Цепочка вызовов:
`EditorFragment.w()` → `editorModel.infixRepresentation` → `a.c(String)`
(реализация `InterfaceC0007b`) → `c.a.a.w.s.a.c(str, callback)` →
`CoreEngine.nativeProcessExpression`.

## Словарь операторов (из Java)

Значения `M()` — это ровно те строки, которые уходят в нативный парсер:

| Токен | Узел | Смысл |
|---|---|---|
| `^` | `j/c/a/k` | степень |
| `_` | `j/c/a/p` | нижний индекс (подстрочный) |
| `abs` | `j/c/a/a` | модуль |
| `frac` / `mixedfrac` | `j/c/a/e` | дробь / смешанная дробь |
| `root` / `root2` | `j/c/a/m`, `o` | корень n-й / квадратный |
| `log` | `j/c/a/i` | логарифм |
| `lim` | `j/c/a/h` | предел |
| `integral` / `definiteintegral` | `j/c/a/g` | интеграл / определённый |
| `derivation` | `j/c/a/d` | производная |
| `definitesigma` | `j/c/a/n` | сумма |
| `choose` / `choose_lsub_rsub` | `j/c/a/c`, `b` | сочетания |
| `partial_permutation_lsub_rsub` | `j/c/a/j` | размещения |
| `variation` | `j/c/a/r`, `s` | размещения без повторов |
| `function` | `j/c/a/q` | пользовательская функция |
| `㎭` | `j/c/a/l` | знак квадратного корня |

Плюс из `j/c/c/`:

| Токен | Класс | Смысл |
|---|---|---|
| `(` | `c` | открывающая скобка |
| `)` | `e` | закрывающая скобка |
| `<имя>(` | `d` | именованная функция (`sin(`, `log(`…) |
| `<строка>` | `f` | литерал (число, переменная) |

## Подтверждение нативным парсером

В `libPhotoMathDist.so` по смещению **8996458–8997690** лежит
**отсортированная по алфавиту таблица литералов парсера** — 156 ключевых слов
и 19 пунктуационных токенов. Полный список: `truth/data/input-protocol.json`.

Знаки: `" + "`, `" - "`, `" * "`, `" : "`, `" = "`, `" < "`, `" <= "`, `" > "`,
`">= "`, `"("`, `"+"`, `"-"`, `"^"`, `"!"`, `"%"`, `" != "`, `"{"`, `"}"`, `"-0"`.

Ключевые слова (выборка):

```
abs acos acosh acot acoth acsc acsch add add_sub add_sub_sign alt_form
animation animation_cmd approx approx_sign asec asech asin asinh atan atanh
big_int bracket call ccint ceil choose coint cond_expr conj const_tmpl
const_var cos cosh cot coth csc csch deg deg_min deg_min_sec derivation
derivation_diff derivation_prime det det2..det5 diff differential div
elem_not_of elem_of eq eval_expr extension factorial float floor fr_one
frac fun fun_inv gcd graph gt gte imag int integral integral_def
integralrightdash inverse lcm length lim_both lim_left lim_right list ln
log log10 lt lte mat mat_row math_const max mean mfrac min mod mul muli
neg neq order percent periodic permutation pos pow prime radian real root
root2 rooti sec sech sequence set sigma_def sign sin sinh sub system
system_flat tan tanh text text_key union var var_tmpl variation vert_list
```

Ключевые слова из Java-словаря (`abs`, `frac`, `mixedfrac`, `root`, `root2`,
`log`, `lim`, `integral`, `definiteintegral`, `derivation`, `choose`, `variation`,
`system`, `function`) присутствуют в нативной таблице — **совпадение точное**.

### Что ещё видно из таблицы

- `ccint`, `coint`, `ocint`, `ooint` — «целые коэффициенты / обычные целые»,
  то есть решатель различает режимы приведения к целому виду.
- `BIG_INT_`, `big_int` — арифметика целых произвольной точности.
- `hd_del`, `hlist`, `changeset`, `changeset_ignore`, `sanitize_block`,
  `search_block`, `no_reduce` — внутренние служебные узлы решателя.
- `periodic_solution` — решения периодических уравнений.
- `derivation_prime`, `derivation2_prime`, `nderivation` — производные
  высших порядков и обратная производная (интегрирование).
- `graph`, `graph_header`, `step_header`, `alt_form`, `animation`,
  `animation_cmd` — узлы, соответствующие типам групп результата
  (`GRAPH`, шаги, альтернативная форма, анимация).
- `text`, `text_key`, `var_tmpl`, `const_tmpl` — шаблонные узлы (то, что
  превращается в `CoreRichText`).

## Побочная находка: duktape

Сразу за таблицей парсера (смещение **8997681**) идёт исходный код **duktape** —
встраиваемого JS-движка (`duk_api_buffer.c`, `duk_lexer.c`, `duk_js_compiler.c`
и т.д.), со строкой сборки `ll p nl p2 a8 arm32 android clang`.

Это и есть рантайм для `assets/resources/NodeRuntime.js` (308 КБ). То есть
часть логики решателя (видимо, визуальный скрипт `model.json`) исполняется
на JavaScript.

**Для переписки:** JS-часть нам не нужна — `model.json` помечен P2.
Но если придётся воспроизводить анимации, duktape — готовая reference-реализация
семантики этого скрипта.

## Пример

Выражение `2x + 3 = 7`:

```
{=,{2,x,+,3},{7}}
```

Система `{x+1=3, x-1=1}`:

```
 system({=,{x,+,1},{3}},{=,{x,-,1},{1}}) 
```

(с ведущим и завершающим пробелом — как в оригинале).

## Значение для проекта

Мы приняли формат входа **AST-JSON, повторяющий `CoreNode`**. Восстановленный
протокол Photomath этого не меняет, но даёт:

1. **Критерий полноты.** Список из 156 ключевых слов — это чек-лист: наш AST
   должен покрывать те же понятия. Прямое сопоставление:
   `frac`→`FRACTION`, `derivation`→`DERIVATION`, `det3s`→`DETERMINANT3_SARRUS`,
   `mat_row`→`MATRIX_ROW`, `vert_list`→`VERTICAL_LIST`, `alt_form`→
   `ALTERNATIVE_FORM`, `approx_sign`→`APPROXIMATE_SIGN`.
2. **Ответ на вопрос «а как же Photomath».** Если понадобится паритет вывода —
   формат известен.
3. **Уверенность**, что `CoreNodeType` (143) — это внешнее представление
   примерно того же набора из 156 внутренних узлов. Расхождение ~13 узлов —
   внутренние служебные.

## Что осталось неясным

- Точная грамматика (BNF) парсера: как именно `{…}` и `name(…)` соотносятся,
  где допустимы пустые аргументы, как кодируются отрицательные числа (`-0`).
  Восстановимо только исполнением на устройке.
- Кодировка текстовых аргументов (экранирование запятых и скобок в `text`).
- Поведение при ошибке разбора: `nativeProcessExpression` возвращает `null`
  → `CoreResult` с `coreSolverData == null` → приложение показывает ошибку.
  Формат сообщения не восстановлен.

См. также `03-solver-contract.md` (контракт ответа) и
`07-open-questions.md`.