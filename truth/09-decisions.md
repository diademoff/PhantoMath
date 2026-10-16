# 09. Принятые решения

Единый журнал решений по проекту: что выбрано и почему. Отдельные решения
разбросаны по документам (`06-plan.md`, `05-animation.md`, `08-input-protocol.md`),
здесь — сводка. Формат: решение, обоснование, где видно в коде.

Правило: **архитектурные и продуктовые решения принимает пользователь.**
Этот файл — только запись уже принятого, а не место для новых решений.

## Продукт

| # | Решение | Обоснование |
|---|---|---|
| 1 | Камера/OCR **вне scope** | Решение пользователя; самая тяжёлая и наименее переиспользуемая часть |
| 2 | Вне scope: bookpoint, professor, subscription, авторизация | Не относятся к «решить и объяснить» |
| 3 | **Языки только русский и английский** | Решение пользователя. Оригинал знал 9 языков (de/es/fr/it/pl/pt/ru/uk + `default` = английский); остальные 7 не поддерживаем |
| 4 | Целевая платформа — **Android** | Решение пользователя; сборка проверена debug-APK |
| 5 | Блокнот (`notebook`) — **опционально**, не в первой версии | Вторичная ценность |
| 6 | Анимации — **вариант B** (микро-анимации из шагов), не C | Полный паритет анимаций сопоставим по объёму со всем проектом |

### Языки: как это записано в данных

В `truth/data/explanations.json` английский — это язык `default` (ключа `en`
там нет). Русский — `ru`; у 420 ключей русского текста нет, срабатывает
откат `ru → default`. На уровне **сервиса** (`mymath_backend/api.py`) любой
запрошенный язык, кроме `ru`/`en`, приводится к английскому — так решение
«только ru/en» действует и для старых клиентов. Сам файл данных не режем:
он остаётся исследовательским артефактом разбора APK.

## Архитектура

| # | Решение | Где в коде |
|---|---|---|
| 7 | Бэкенд — **FastAPI**, зависимости через **uv**, локальный venv, без Docker | `backend/pyproject.toml` |
| 8 | Математика — **sympy** (там, где нужны символьные преобразования) | `backend/mymath_backend/solver/` |
| 9 | Рендер формул во Flutter — **flutter_math** (свой наборщик формул отклонён) | `app/lib/src/render/latex.dart` |
| 10 | Формат входа решателя — **AST-JSON, повторяющий `CoreNode`** | `POST /api/v1/solve` |
| 11 | Репозиторий: `backend/` + `app/` + `truth/`; APK не коммитим | `.gitignore` |
| 12 | Проверки: backend — pytest + ruff + mypy strict; app — `flutter analyze` + `flutter test` | `backend/pyproject.toml`, `app/analysis_options.yaml` |
| 13 | Не указывать сроки и оценки времени — только приоритеты и сложность | все документы |
| 14 | Действия над выражением — **`CoreAction`** (`POST /solve.action`): `solve`, `factor`, `expand`, `simplify`; имена команд наши | `solver/commands.py`, `api.py` |
| 15 | Способы решения — **несколько записей** вертикальной ветки + `selectMethodText`; клиент переключает локально, без повторного запроса | `solver/base.py`, `solver/equations.py` |
| 16 | Ссылки `[label\|uuid]` возвращаются как **`{label, uuid, definition}`**; определения — наш короткий глоссарий (`concepts.py`), не из APK | `api.py`, `concepts.py`, `app/lib/main.dart` |
| 17 | Комплексные числа: мнимая единица — **`CONSTANT "i"`**; `Re`/`Im`/сопряжение — типы `REAL`/`IMAGINARY`/`CONJUGATE`, арифметика с `i` — через sympy | `solver/complex.py`, `sympy_bridge.py` |
| 18 | **Векторы — наше представление**: вектор = узел `LIST` с компонентами; операции — команды с вторым операндом в `CoreAction.args` (в контракте типа вектора нет) | `solver/vectors.py`, `api.py` |
| 19 | Тождество и противоречие — **ответ без узла**: шаг `solutions_inf_many` / `false_statement_solve`, `solution = null`; отдельного узла «все/ни одного» не вводим | `solver/equations.py` |
| 20 | Графики — **своё семплирование**: эндпоинт `/api/v1/graph` (sympy) + `CustomPainter`; `CoreGraphResult` Photomath не воспроизводим | `graph.py`, `app/lib/src/render/graph_view.dart` |
| 21 | Блокнот — **локальный файл** в каталоге приложения (`path_provider`); нет диска — работаем в памяти | `app/lib/src/notebook/notebook.dart` |
| 54 | **Модели контракта — dataclasses, не pydantic**: ядро не тянет `pydantic-core` (Rust) и годится для встраивания CPython на устройстве; `pydantic`/`fastapi` — только HTTP-слой (extra `api`) | `ast.py`, `results.py`, `pyproject.toml` |
| 55 | **Логика сервиса — в `service.py`** без фреймворка; FastAPI (`api.py`) и локальный сервер устройства (`device.py`, stdlib `http.server`) — тонкие обёртки над ней | `service.py`, `api.py`, `device.py` |
| 56 | **Python на устройстве — `serious_python`** (CPython 3.12 в APK); `app/python/main.py` поднимает сервер на `127.0.0.1:8770`, приложение ходит HTTP | `app/python/`, `app/lib/src/api/embedded_backend.dart` |
| 57 | **Сборка/раздача — `Makefile`** (`icon`, `python-bundle`, `apk`, `serve`, …); APK раздаётся по tailnet (статика на tailnet-IP) | `Makefile` |
| 58 | **Launcher-иконка — из `app/logo.png`** (`flutter_launcher_icons`), adaptive-фон `#B80730` из лого; splash и лого в UI не добавлялись | `app/pubspec.yaml` |

## Ввод: редактор и клавиатура

| # | Решение | Где в коде |
|---|---|---|
| 14 | **Структурный редактор**: своё дерево `ENode` + курсор-путь, не текст | `app/lib/src/editor/model.dart` |
| 15 | Рендер ввода — **дерево виджетов** (`Text` + композиции `Row`/`Column`) с мигающим курсором и тапом по элементу | `app/lib/src/editor/editor_view.dart` |
| 16 | Клавиатура — **базовый экран + доп. панели** из `editor_operators` (128), по частям | `app/lib/src/editor/keyboard.dart` |
| 17 | Шаблоны-конструкции (дробь, степень, корень, модуль, скобки) **поглощают предыдущий операнд**; функции/исчисление вставляются пустыми | `ENodeKind.absorbsPrevious` |

## Ответ и объяснения

| # | Решение | Где в коде |
|---|---|---|
| 18 | Контракт ответа — **`CoreSolverData`** Photomath, поле в поле | `backend/mymath_backend/results.py` |
| 19 | Словарь объяснений берём из APK для исследования; **для релиза тексты переписать** | `truth/04-explanations.md` |

## Тригонометрия

| # | Решение | Где в коде |
|---|---|---|
| 22 | Единицы угла — **узлы-обёртки `DEGREE`/`RADIAN`** (постфиксные, один ребёнок), как в оригинале (`BASIC_INFIX_OPERATOR_DEGREE`/`_RADIAN`); аргумент без обёртки — **радианы** | `solver/trigonometry.py`, `sympy_bridge.py` (`to_sympy`), `app/lib/src/editor/kind.dart` |
| 23 | Точное значение даёт **sympy**; аргумент без точного значения **остаётся символьным** (`sin(1)`), как `√2` | `solver/trigonometry.py` |
| 24 | Шаг точного значения — ключ **`trig_table_calc`**; неопределённое значение — ошибка с ключом **`trig_err_undef`** | `solver/trigonometry.py` |
| 25 | Обратные функции возвращают **π-кратные** (радианы): `arcsin(1/2) = π/6` | `solver/trigonometry.py` |
| 26 | Объём: прямые → обратные → гиперболические → обратные гиперболические (сделано); упрощения — чётность, периодичность, тождества, формулы (сделано); уравнения с линейным аргументом и промежутком (сделано) | `truth/06-plan.md` |
| 27 | **Чётность/нечётность** — вынос знака аргумента: `sin(-x) = -sin(x)`, `cos(-x) = cos(x)`; ключи `trig_neg_*` / `trig_hyp_neg_*`, для обратных — общие `trig_neg`/`trig_hyp_neg` | `solver/trigonometry.py` |
| 28 | **Периодичность** — числовой угол приводится к наименьшему положительному котерминальному (`sin 390° = sin 30°`); у `tan`/`cot` период вдвое короче; ключ `trig_rewrite_coterminal_pos` | `solver/trigonometry.py` |
| 29 | **Тождества** — автоматический запасной проход `sympy.simplify`, когда обычная маршрутизация не справилась (`sin²x + cos²x = 1`, `sin x·cos x = sin 2x/2`); арифметику не перехватывает | `solver/__init__.py` |
| 30 | **Формулы углов** — раскрытие командой «Раскрыть» через `sympy.expand(trig=True)`: `sin 2x = 2 sin x cos x` | `solver/commands.py` |
| 31 | **Тригонометрические уравнения** — общее решение **сериями** (`x = π/6 + 2πk`, `x = 5π/6 + 2πk`), параметр — переменная `k`; серии строит `sympy.solveset` | `solver/trig_equations.py` |
| 32 | **Промежуток** — необязательное поле запроса `interval {min, max}` (границы — узлы `CoreNode`, чтобы допускать `π/2`); из серий отбираются корни; в приложении — кнопка «Промежуток» с диалогом ввода границ | `api.py`, `solver/trig_equations.py`, `app/lib/main.dart`, `app/lib/src/api/solver_api.dart` |
| 33 | Уравнение считается тригонометрическим, если в нём есть прямая функция и **одна** свободная переменная; обе стороны могут быть функциями (`sin x = cos x`). Параметры (`sin(ax+b)`) не поддерживаются | `solver/trig_equations.py` |
| 34 | **Тёмная тема** — Material 3, светлая и тёмная схемы, `themeMode: system` | `app/lib/main.dart` |
| 35 | **Доступность** — словесные метки клавиш (`ENodeKind.description`) и редактора; локализация интерфейса не делается (решение пользователя) | `app/lib/src/editor/kind.dart`, `keyboard.dart` |
| 36 | **Микро-анимации (вариант B)** — `color`/`crossed` объявлены в базовом `CoreNode` (переживают сериализацию контракта), рендер оборачивает формулу в `\textcolor`/`\cancel`; решатель помечает сокращаемую дробь | `ast.py`, `solver/fractions.py`, `app/lib/src/render/latex.dart` |
| 37 | **Формулы:** рендер выдаёт «сырой» LaTeX без `$…$` — `flutter_math` (KaTeX) не принимает `$` внутри формулы | `app/lib/src/render/latex.dart` |
| 38 | **Модуль/знак/пол** — `ABS`/`SIGN`/`FLOOR` через sympy; структурные правила для заведомо неотрицательного аргумента (`\|x²\| = x²`, `sgn(x²) = 1` вне нуля); ключи `abs`/`abs_pos`, `find_sign`, `calculate_floor` | `solver/absolute.py` |
| 39 | **Простейшие уравнения с модулем** `\|f(x)\| = a` — две ветви (`f(x)=a`, `f(x)=-a`), корни объединяются; при `a<0` решений нет; ключи `eq_abs_branch`, `quad_final_single` | `solver/absolute.py` |
| 40 | **Матрицы** — представление `MATRIX` со строками `MATRIX_ROW` (как в APK); операции командами (второй операнд в `args`): `matrix_add`/`matrix_subtract`, `matrix_multiply`, `matrix_scale`, `matrix_transpose`, `matrix_inverse`, `matrix_determinant` | `solver/matrices.py`, `sympy_bridge.py` |
| 41 | **Ввод матриц** — шаблоны 2×2/3×3 в редакторе (`ENodeKind.matrix2/3` → `MATRIX` со строками), рендер `pmatrix`; шторка «Матрица…» с операциями и вторым операндом строкой `1,2;3,4` | `app/lib/src/editor/`, `app/lib/main.dart`, `app/lib/src/render/latex.dart` |

## Тестовый корпус

| # | Решение | Где в коде |
|---|---|---|
| 42 | **Тестовый корпус** — JSON по файлу на модуль в `backend/tests/corpus/`, 167 задач по всем 19 модулям; раннер автодискаверит файлы | `backend/tests/test_corpus.py` |
| 43 | Что проверяет корпус — **структура ответа** (`structural_eq`) **плюс порядок ключей** подшагов; каждый ключ обязан быть в словаре с верной арностью | `test_corpus.py` |
| 44 | Ввод в корпусе — **строка протокола**; команда/аргументы/промежуток/индекс способа — отдельными необязательными полями | `corpus/*.json` |
| 45 | Эталоны корпуса — **ручные** (по математике и словарю), а не сняты с решателя; расхождение считается дефектом решателя | `truth/07-open-questions.md` |
| 46 | Дефект конвейера `_final_value`/`route` (Q10) исправлен; кейсы возвращены в корпус | `solver/__init__.py`, `solver/powers.py` |
| 50 | **Ответ — значение `route()`**, а не последний шаг (`_final_value` удалён) | `solver/__init__.py` |
| 51 | **`fold_semantically`** — свёртка подвыражения в служебном контексте с переносом шагов при успехе; модуль, оставляющий узел, возвращает его со свёрнутыми детьми (`√(2+3)` → `√5`) | `solver/base.py`, `solver/powers.py` |
| 52 | Тригонометрия сворачивает аргумент **после** чётности и периодичности (`sin(1+1)` → `sin(2)`; `sin(-1)` → `-sin(1)`); дроби в корпусе — узлом `frac` | `solver/trigonometry.py` |

## Протокол ввода: константы и обёртки

| # | Решение | Где в коде |
|---|---|---|
| 47 | **π и ∞** — константы протокола: `pi`/`\pi`/`π` → `CONSTANT "π"`, `inf`/`infty`/`\infty`/`∞` → `CONSTANT "∞"` (иначе `pi` распадалось на `p·i`) | `input.py` (`CONSTANT_NAMES`) |
| 48 | **Мнимая единица** — явный токен `\i` → `CONSTANT "i"` (как `CONSTANT_I` в редакторе); обычная `i` остаётся переменной | `input.py` |
| 53 | **Число Эйлера** — явный токен `\e` → `CONSTANT "e"` (как `CONSTANT_E`); обычная `e` остаётся переменной; мост sympy уже знал `e`. Теперь `ln(e) = 1` | `input.py` |
| 49 | **Единицы угла и комплексные** в протоколе: `deg`/`radian`/`real`/`imag`/`conj` → `DEGREE`/`RADIAN`/`REAL`/`IMAGINARY`/`CONJUGATE` (токены есть в нативном словаре) | `input.py` (`KEYWORD_TO_TYPE`) |

## Профиль и интерфейс (по списку пользователя)

Реализовано по прямому указанию пользователя; источник поведения — APK.

| # | Решение | Где в коде |
|---|---|---|
| 59 | **Раскрываемое углублённое пояснение шага** — контрактное поле `subresult` (вложение `CoreSolverVerticalResult`); генерируется для вычисления значения (`EVALUATE_EXPRESSION`), производной (почленно для суммы/произведения) и корней квадратного уравнения (дискриминант + итог); показывается блоком «Подробнее» | `solver/evaluate.py`, `solver/derivatives.py`, `solver/equations.py`, `service.py` (`attach_text` рекурсирует в `subresult`), `app/lib/src/api/solver_api.dart`, `app/lib/main.dart` |
| 69 | **Узел `FUNCTION`/`FUNCTION_INVERSE`** — функция как объект: имя в `value`, аргумент в детях (для этих типов `value` и дети сосуществуют); `to_sympy`/`from_sympy` знают их, модуль нормализует аргумент (`f(2+3)` → `f(5)`), сам узел остаётся символьным | `solver/functions.py`, `solver/sympy_bridge.py`, `ast.py`, `app/lib/src/model/core_node.dart`, `app/lib/src/render/latex.dart`, `app/lib/src/editor/kind.dart` |
| 70 | **Определения функций** `f(x) = тело`: приходят с запросом (`definitions`, список узлов `EQUALS(FUNCTION(f, параметры…), тело)`), живут только в пределах запроса — сервер **без состояния**; перед решением вызовы `f(…)` заменяются телом (с подстановкой аргументов), `f⁻¹(a)` — решением `тело = a`. Само определение возвращается как ответ (шаг `function`) | `solver/functions.py` (`parse_definition`/`inline`/`inverse_of`), `solver/__init__.py`, `service.py`, `api.py`, `device.py` |
| 71 | **Хранилище определений в приложении** (`FunctionStore`): `f(x) = …` распознаётся на «Решить» и запоминается (не решается), определения уходят в каждом запросе и показываются чипами с возможностью убрать; добавлены клавиши `f⁻¹(x)`/`g⁻¹(x)` | `app/lib/src/functions/function_store.dart`, `app/lib/main.dart`, `app/lib/src/api/solver_api.dart`, `app/lib/src/editor/kind.dart` |
| 72 | **Условное выражение** `CONDITIONAL_EXPRESSION` — дети `[условие, ветвь «да», ветвь «нет»]`; при решаемом условии берётся ветвь (шаг `true`/`false`), иначе узел символьный и переводится в `Piecewise`; отношение-условие (`<`, `≤`, `>`, `≥`, `≠`) переводится в sympy | `solver/conditional.py`, `solver/sympy_bridge.py` |
| 73 | **Кусочная функция как объект**: `PIECEWISE_DEFINITION` зарегистрирована (символьный узел, значение — командой `piecewise_value`); график семплирует её по ветвям и отдаёт признак `piecewise` | `solver/piecewise.py`, `graph.py` |
| 74 | **Опорные точки графика в приложении**: `GraphData` несёт `annotations` (корни, пересечение с осью y, экстремумы, асимптоты, `piecewise`), `GraphView` их рисует | `app/lib/src/api/solver_api.dart`, `app/lib/src/render/graph_view.dart` |
| 75 | **Геометрия APK — реализована** (решение пользователя; снимает прежнее исключение): в движке есть только `line_segment`/`line_segment_length`, поэтому реализованы типы `LINE_SEGMENT` (обозначение отрезка, символьный) и `LINE_SEGMENT_LENGTH` (длина): расстояние между координатными точками `√Σ(xᵢ−yᵢ)²` или `|a−b|` на числовой прямой; иначе узел символьный. Отдельного решателя геометрии (площади, периметры, фигуры) в APK **нет** — не выдумываем. Все 143 типа узлов теперь зарегистрированы | `solver/geometry.py`, `input.py` (`segment`/`length`), `app/lib/src/model/core_node.dart`, `app/lib/src/render/latex.dart`, `app/lib/src/editor/kind.dart` |
| 60 | **Копировать результат** — LaTeX ответа (или текст шага) в буфер обмена | `app/lib/main.dart` (`_copyResult`, `_copyFormula`) |
| 61 | **Выбор способа решения — общий механизм**: провайдеры способов регистрируются по типу узла, `solve` не знает про конкретные типы | `solver/methods.py`, `solver/equations.py`, `solver/systems.py`, `solver/__init__.py` |
| 62 | **Блокнот: метаданные задачи** (uuid, version, source, command, locale, methodIndex) повторяют `ResultItemMetadata` APK; **очистка обратима** («История очищена»/«Отменить») | `app/lib/src/notebook/notebook.dart`, `app/lib/src/notebook/notebook_page.dart` |
| 63 | **Десятичный разделитель** (`.`/`,`) из профиля (`DecimalSeparator`): влияет на вывод чисел в формулах и в редакторе | `app/lib/src/settings/settings.dart`, `app/lib/src/render/latex.dart`, `app/lib/src/editor/editor_view.dart` |
| 64 | **Нотация биномиального коэффициента** (`BinomialType`: этажная / `C(n,k)`) | `app/lib/src/settings/settings.dart`, `app/lib/src/render/latex.dart` |
| 65 | **Метод умножения/деления** (`MUL_US/LTR/RTL`, `DIV_US/RU/STANDARD`) — сохраняется в настройках; рендер столбиков не входит (анимации вне scope) | `app/lib/src/settings/settings.dart`, `app/lib/src/settings/settings_page.dart` |
| 66 | **128 операторов редактора** — каталог всех `editor_operators` APK с сопоставлением действию либо причиной недоступности; добавлены быстрые клавиши `1½`, `x²`, `x³`, `∛`, `log₂` | `app/lib/src/editor/operators.dart`, `app/lib/src/editor/kind.dart`, `app/lib/src/editor/convert.dart`, `app/lib/src/editor/keyboard.dart` |
| 67 | **Предпросмотр ввода** — текущее дерево редактора показывается набором (`flutter_math`) над клавиатурой | `app/lib/main.dart` (`_preview`) |
| 68 | Экран **настроек** — десятичный знак, биномиальный коэффициент, методы умножения/деления | `app/lib/src/settings/settings_page.dart` |

Не поддержано (помечено в каталоге с причиной): `±` (`ADD_SUBTRACT`), подстрочный индекс (`a_n`), `π/2`, `π/3`, многострочный ввод.

`f(x)`/`g(x)` теперь доступны: узел `FUNCTION` реализован (#69), а определение
`f(x) = …` (#70) даёт `f(2)`, `f′(x)` и `f⁻¹(a)`. Для функции **без**
определения `d/dx f(x)` по-прежнему не выражается.

## Следующее (открыто)

- Векторы: в контракте есть `LINE_SEGMENT` / `LINE_SEGMENT_LENGTH`, но их
  семантика не сведена — своё представление (`LIST`) уже работает.
- Для релиза переписать тексты объяснений (взяты из APK для исследования).
- Полный паритет анимаций (вариант C) — по желанию.
