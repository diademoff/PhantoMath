# backend

Символьный решатель с пошаговым объяснением. Переписывание Photomath 7.10.0
по данным разбора APK.

Контракт ответа воспроизводит оригинальный — см. `truth/03-solver-contract.md`.
Что реализовано на этом этапе: типы AST, структура ответа, резолвер словаря
объяснений. Сам решатель (`POST /solve`) — следующий этап.

## Установка

```bash
uv sync --python 3.12
```

## Проверки

```bash
uv run pytest          # тесты
uv run ruff check .    # линтер
uv run ruff format .   # форматирование
uv run mypy mymath_backend
```

## Состав

| Модуль | Что внутри |
|---|---|
| `mymath_backend/node_types.py` | `CoreNodeType` — 143 типа узла, дословно из APK. **Генерируется**, не править руками |
| `mymath_backend/ast.py` | `CoreNode`, `CoreColoredNode`, `CoreAction`, `CoreRichText`; сериализация в формат контракта |
| `mymath_backend/results.py` | `CoreSolverData` и вся ветка вертикального результата: группы, шаги, подшаги |
| `mymath_backend/explanations.py` | Резолвер 3252 шаблонов объяснений на 9 языках |
| `scripts/gen_node_types.py` | Генератор `node_types.py` из `truth/data/enums.json` |

## Перегенерация типов

`node_types.py` собирается из данных разбора, а не пишется руками:

```bash
uv run python scripts/gen_node_types.py
```

Скрипт падает, если число значений перестало быть 143 или появилось имя,
непригодное как константа Python.

## Словарь объяснений

Данные лежат в `../truth/data/explanations.json` (3252 ключа × 9 языков).
Путь передаётся явно — бэкенд не должен зависеть от расположения файла:

```python
from mymath_backend import load_explanations

explanations = load_explanations("../truth/data/explanations.json")
rendered = explanations.render(
    "abs_const_long",
    args=[CoreNode.variable("x"), CoreNode.constant(7), CoreNode.constant(7)],
    locale="ru",
)
rendered.text  # "Поскольку x, абсолютное значение 7 равно 7"
rendered.links  # кликабельные ссылки «показать другой способ»
rendered.tail_label  # метка в конце строки, отделённая от текста
```

Ключ `CoreRichText.type` разрешается через цепочку `ru-RU -> ru -> default`.
Отсутствующий ключ не поднимает исключение, а даёт `missing_key=True` и
текст `?? step_<ключ> ??` — так дефект виден в логах, а не роняет запрос.

Аргументы рендерит вызывающий: по умолчанию используется текстовый вывод для
логов, фронт подставит свои отрендеренные узлы.

## Тесты

33 теста. Из них часть работает на полном корпусе объяснений и падает при
расхождении с APK:

- все 143 имени узла совпадают с `truth/data/enums.json`;
- у всех 3252 ключей есть английский шаблон;
- арность каждого ключа совпадает с максимальным `ARGn` в шаблоне;
- все 3020 ключей из `assets/keys.txt` присутствуют (тест пропускается, если
  APK не распакован).

## Чего ещё нет

- `POST /solve` — сам решатель (этап 3 в `truth/06-plan.md`).
- Парсер входного формата.
- Рендер формул — на стороне фронта (`flutter_math`).
- Анимации — вариант B, микро-анимации через `CoreColoredNode`.

## Источник истины

Всё поведение типов и контракта выведено из APK. Документация — в `../truth/`,
индекс в `../truth/00-INDEX.md`. Код, расходящийся с ней, — ошибка.
