"""Детерминированный драйвер телефона/эмулятора для студенческих тестов.

Все нажатия идут по центрам элементов из `uiautomator dump`, а не по
фиксированным координатам: раскладка клавиатуры зависит от ширины и высоты
экрана, поэтому координаты читаются с устройства перед каждым действием.

Запуск:
  ANDROID_SERIAL=<serial> python3 tools/device/drive.py TASKS.json OUTDIR \\
      [--only id,id] [--install APK] [--no-shots]

Устройство задаётся `ANDROID_SERIAL`; каждый вызов adb идёт через один
помощник `adb()`, который подставляет `-s <serial>`, поэтому телефон и
эмулятор можно запускать одновременно (два процесса, два OUTDIR).

Каждый `shot` пишет ещё и видимые подписи экрана (text и content-desc
сверху вниз) в `OUTDIR/<id>/NN_<name>.txt`; все они по порядку попадают в
`OUTDIR/transcript_<id>.md`. С `--no-shots` скриншоты и контактный лист не
делаются, остаются только текстовые дампы.

Формат TASKS.json — список {"id", "note", "actions"}; действия описаны в
`apply()` ниже, пример — `tools/device/example_tasks.json`. Необязательное
поле `expect_answer` (подстрока LaTeX) сверяет ответ с content-desc карточки
ответа после решения; строка лога кончается `ok` или `mismatch: <got>`.

Самопроверка без устройства (фикстура `tools/device/tests/labels.xml`):
  python3 tools/device/drive.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path

APP_ID = "com.mymath.mymath_app"
ACTIVITY = f"{APP_ID}/.MainActivity"

#: Серийник устройства; заполняется в main() из ANDROID_SERIAL.
SERIAL = ""
#: Безопасный серийник для имён файлов.
TAG = ""
#: Каталог запуска (OUTDIR).
OUTDIR = Path(".")
#: Каталог текущей задачи (OUTDIR/<id>).
TASK_DIR = Path(".")
#: Файл с видимыми текстами текущей задачи.
TEXTS = None
#: Номер следующего скриншота в задаче.
SHOT_NO = 0
#: Что сейчас выполняется (заголовок блока в texts.txt).
STEP = "старт"
#: Сколько всего скриншотов сделано в задаче.
SHOTS = 0
#: Лог запуска (по серийнику).
LOG = None
#: Подробный лог нажатий (STUDENT_DRIVE_DEBUG=1).
DEBUG = bool(os.environ.get("STUDENT_DRIVE_DEBUG"))
#: Без скриншотов: только текстовые дампы (`--no-shots`).
NO_SHOTS = False
#: Экраны текущей задачи: (имя снимка, строки подписей) для transcript_<id>.md.
TRANSCRIPT: list[tuple[str, list[str]]] = []


class ActionError(RuntimeError):
    """Действие не удалось: задача помечается ошибкой, драйвер идёт дальше."""


# ─────────────────────────────────────────────────────────────── adb и дампы


def adb(*args, binary: bool = False, timeout: int = 120):
    """Единственная точка вызова adb: всегда с `-s <serial>`."""
    cmd = ["adb"] + (["-s", SERIAL] if SERIAL else []) + [str(a) for a in args]
    try:
        result = subprocess.run(cmd, capture_output=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ActionError(f"adb {' '.join(map(str, args))}: таймаут {timeout} с")
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", "replace")


def device_serials() -> list[str]:
    """Подключённые устройства в состоянии `device`."""
    out = subprocess.run(
        ["adb", "devices"], capture_output=True, check=False, text=True, timeout=60
    ).stdout
    found = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            found.append(parts[0])
    return found


def wait_boot(timeout: float = 300) -> None:
    """Дождаться загрузки устройства (`sys.boot_completed` = 1)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if adb("shell", "getprop", "sys.boot_completed").strip() == "1":
            return
        time.sleep(2)
    raise ActionError(f"устройство {SERIAL} не загрузилось за {timeout:.0f} с")


def wait_device(timeout: float = 120) -> None:
    """Дождаться, пока устройство появится в `adb devices`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if SERIAL in device_serials():
            return
        time.sleep(1.5)
    raise ActionError(f"устройство {SERIAL} не найдено в `adb devices`")


def _dump_paths() -> tuple[str, Path]:
    """Файл дампа на устройстве и на хосте — оба по серийнику."""
    return f"/sdcard/student_drive_{TAG}.xml", OUTDIR / f"_ui_{TAG}.xml"


def dump(record: bool = True) -> ET.Element:
    """Снять дерево доступности и (по умолчанию) записать его тексты."""
    dev_path, host_path = _dump_paths()
    last = ""
    for attempt in range(6):
        # Неудачный dump оставляет прошлый файл: без rm читали бы старый экран.
        adb("shell", "rm", "-f", dev_path)
        adb("shell", "uiautomator", "dump", dev_path)
        xml = adb("shell", "cat", dev_path)
        host_path.write_text(xml, encoding="utf-8")
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as err:  # uiautomator иногда пишет пустой файл
            last = str(err)
            time.sleep(1.5)
            continue
        if record:
            record_texts(root)
        return root
    raise ActionError(f"дамп не читается (попытка {attempt + 1}): {last}")


def nodes(root: ET.Element):
    """Узлы с валидными bounds: (узел, центр)."""
    for node in root.iter("node"):
        bounds = [int(v) for v in re.findall(r"\d+", node.get("bounds", ""))]
        if len(bounds) != 4:
            continue
        yield node, ((bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2)


def labels(node: ET.Element) -> list[str]:
    """Подписи узла: text и content-desc."""
    return [v for v in (node.get("text"), node.get("content-desc")) if v]


def label_lines(root: ET.Element) -> list[str]:
    """Видимые подписи сверху вниз: `y,x kind value` (text раньше desc).

    Один узел может нести и `text`, и `content-desc`; показываем обе подписи,
    на одной позиции text идёт первой. Так `uiautomator dump` читается как
    экран: заголовок, формула, текст этапа.
    """
    rows = []
    for node, _ in nodes(root):
        bounds = [int(v) for v in re.findall(r"\d+", node.get("bounds", ""))]
        if len(bounds) != 4:
            continue
        y, x = bounds[1], bounds[0]
        for order, kind, value in (
            (0, "text", node.get("text")),
            (1, "desc", node.get("content-desc")),
        ):
            if value:
                rows.append((y, x, order, kind, value))
    rows.sort(key=lambda row: (row[0], row[1], row[2]))
    return [
        f"{y:5},{x:<5} {kind:4} {value}".replace("\n", "\\n")
        for y, x, _, kind, value in rows
    ]


def _matches(label: str, needle: str) -> bool:
    """Подпись совпадает с искомой целиком или начинается с неё и перевода строки.

    Flutter склеивает подпись `Semantics` с подписью детей через `\\n`:
    «Определитель\\n| |», «7\\n7». Поэтому сравнение идёт с `needle + "\\n"`,
    а не «начинается с»: цифра 7 в поле ввода (подпись «7») не путается с
    клавишей 7 (подпись «7\\n7»).
    """
    return label == needle or label.startswith(needle + "\n")


def find(root: ET.Element, needle: str):
    """Центр первого узла с подписью needle; кликабельные узлы в приоритете."""
    fallback = None
    for node, center in nodes(root):
        if not any(_matches(lab, needle) for lab in labels(node)):
            continue
        if node.get("clickable") == "true":
            return center
        if fallback is None:
            fallback = center
    return fallback


def find_key(root: ET.Element, needle: str):
    """Центр клавиши клавиатуры.

    Клавиша с глифом подписана «описание\\nглиф» («7\\n7», «x\\nx»), поэтому
    её нельзя искать простым совпадением подписи: ячейка матрицы в поле ввода
    тоже подписана «7», и нажатие ушло бы в редактор вместо клавиатуры.
    Служебные клавиши без глифа («Удалить», «Новая строка») подписаны ровно
    своим описанием — их берём точным совпадением, но только для имён длиннее
    одного символа.
    """
    exact = None
    for node, center in nodes(root):
        labs = labels(node)
        if any(lab.startswith(needle + "\n") for lab in labs):
            return center
        if len(needle) > 1 and needle in labs:
            if node.get("clickable") == "true":
                return center
            if exact is None:
                exact = center
    return exact


def find_text(root: ET.Element, needle: str):
    """Центр узла, чья подпись содержит needle (для сообщений об ошибке)."""
    for node, center in nodes(root):
        for lab in labels(node):
            if needle in lab:
                return center
    return None


def foreground_package() -> str:
    """Пакет окна в фокусе (`mCurrentFocus`)."""
    out = adb("shell", "dumpsys window | grep -m1 -i mCurrentFocus")
    match = re.search(r"u0 ([A-Za-z0-9_.]+)/", out)
    return match.group(1) if match else ""


def assert_app_running(where: str = "") -> None:
    """Проверить, что приложение всё ещё на экране.

    Если устройство занято другим прогоном (или кто-то нажал «домой»), команда
    «не сработала» так же, как сработала бы: экран просто меняется на чужой.
    Без этой проверки задача молча получала бы «ok» и скриншот чужого экрана.
    """
    package = foreground_package()
    if package and package != APP_ID:
        raise ActionError(f"приложение не на экране (в фокусе {package}){where and ' ' + where}")


def tap_xy(x: int, y: int, wait: float = 0.35) -> None:
    if DEBUG:
        log(f"tap {x},{y}")
    adb("shell", "input", "tap", x, y)
    if wait:
        time.sleep(wait)


def long_press_xy(x: int, y: int, wait: float = 0.8) -> None:
    """Долгое нажатие в точке: `input swipe` без смещения, 800 мс."""
    if DEBUG:
        log(f"long press {x},{y}")
    adb("shell", "input", "swipe", x, y, x, y, 800)
    if wait:
        time.sleep(wait)


def tap_label(label: str, wait: float = 0.4, root: ET.Element | None = None) -> bool:
    """Нажать узел с подписью label; False, если такого нет."""
    root = dump() if root is None else root
    center = find(root, label)
    if center is None:
        return False
    tap_xy(*center, wait=wait)
    return True


def tap_label_or_fail(label: str, wait: float = 0.4) -> None:
    if not tap_label(label, wait=wait):
        raise ActionError(f"не найден элемент {label!r}")


def screen_size() -> tuple[int, int]:
    out = adb("shell", "wm", "size")
    match = re.search(r"Override size: (\d+)x(\d+)", out) or re.search(
        r"Physical size: (\d+)x(\d+)", out
    )
    if not match:
        return 1080, 2340
    return int(match.group(1)), int(match.group(2))


def swipe_up(times: int = 1) -> None:
    """Прокрутить текущий список вверх (пальцем вверх).

    Шаг меньше высоты шторки: элемент не проскакивает между дампами, поэтому
    «Ранг» в длинном списке действий находится за один проход.
    """
    width, height = screen_size()
    for _ in range(times):
        adb(
            "shell",
            "input",
            "swipe",
            width // 2,
            int(height * 0.70),
            width // 2,
            int(height * 0.40),
            300,
        )
        time.sleep(0.4)


def _label_set(root: ET.Element) -> tuple[str, ...]:
    """Мультимножество подписей экрана — для ожидания «экран успокоился»."""
    return tuple(sorted(lab for node, _ in nodes(root) for lab in labels(node)))


def wait_settle(before: tuple[str, ...], timeout: float = 90,
                unchanged_after: float = 8) -> None:
    """Дождаться, пока экран изменится и перестанет меняться.

    Нужно после действия, которое запускает пересчёт (команда в шторке):
    старый результат успевает стабилизироваться, поэтому ждём сначала смены
    набора подписей, потом — двух одинаковых дампов подряд. Если нажатие
    законно ничего не меняет (команда отвергла ввод), не ждём таймаут целиком.
    """
    global STEP
    started = time.time()
    deadline = started + timeout
    changed = False
    previous = None
    while time.time() < deadline:
        root = dump(record=False)
        current = _label_set(root)
        if previous == current and (changed or time.time() - started > unchanged_after):
            STEP = "после действия"
            record_texts(root)
            assert_app_running("после действия")
            return
        if current != before:
            changed = True
        previous = current
        time.sleep(0.8)
    raise ActionError("экран не стабилизировался за 90 с")


def tap_text(needle: str, scrolls: int = 8, wait: float = 0.5,
             settle: bool = True) -> None:
    """Нажать текст, при необходимости прокручивая список (шторка действий)."""
    for attempt in range(scrolls + 1):
        root = dump()
        center = find(root, needle)
        if center is not None:
            before = _label_set(root)
            tap_xy(*center, wait=wait)
            if settle:
                wait_settle(before)
            return
        if attempt < scrolls:
            swipe_up()
    raise ActionError(f"не найден текст {needle!r}")


# ─────────────────────────────────────────────────────── клавиатура и тексты

#: Код оператора → подпись клавиши на устройстве (`PhKey.description`).
KEY_LABELS = {
    # служебный ряд
    "HELPER_SHOW_SECONDARY_SHEET": "Функции",
    "HELPER_XYZ_SHEET": "Буквы",
    "CONTROL_MOVE_LEFT": "Курсор влево",
    "CONTROL_MOVE_RIGHT": "Курсор вправо",
    "CONTROL_NEW_LINE": "Новая строка",
    "CONTROL_DELETE": "Удалить",
    # базовый экран
    "OPERATOR_LEFT_BRACKET": "Открывающая скобка",
    "OPERATOR_RIGHT_BRACKET": "Закрывающая скобка",
    "OPERATOR_ROOT_TWO": "Корень",
    "OPERATOR_POWER_TWO": "Квадрат",
    "OPERATOR_FRACTION": "Дробь",
    "VARIABLE_X_LOW": "x",
    "BASIC_INFIX_OPERATOR_DIVIDE": "Разделить",
    "CONSTANT_PI": "Пи",
    "BASIC_INFIX_OPERATOR_MULTIPLY": "Умножить",
    "BASIC_INFIX_OPERATOR_PERCENTAGE": "Процент",
    "BASIC_INFIX_OPERATOR_MINUS": "Вычесть",
    "BASIC_INFIX_OPERATOR_EQUALS": "Равно",
    "DIGIT_DOT": "Десятичный разделитель",
    "BASIC_INFIX_OPERATOR_PLUS": "Сложить",
    # расширенный экран
    "BASIC_INFIX_OPERATOR_LESS_THAN": "Меньше",
    "BASIC_INFIX_OPERATOR_GREATER_THAN": "Больше",
    "OPERATOR_FUNCTION_F": "Функция f(x)",
    "OPERATOR_SIGMA_DEFINITE": "Сумма: начало, конец, слагаемое",
    "OPERATOR_MATRIX": "Матрица",
    "OPERATOR_DETERMINANT": "Определитель",
    "OPERATOR_LOG10": "Логарифм",
    "OPERATOR_INTEGRAL_INDEFINITE": "Интеграл",
    "OPERATOR_DERIVATIVE_X": "Производная",
    "OPERATOR_PRIME": "Штрих",
    "CONSTANT_INFINITY": "Бесконечность",
    "CONSTANT_I": "Мнимая единица",
    "OPERATOR_SIN": "Синус",
    "OPERATOR_COS": "Косинус",
    "OPERATOR_ABS": "Модуль",
    "OPERATOR_PARTIAL_PERMUTATION": "Размещений",
    "CONSTANT_E": "Число Эйлера",
    "BASIC_INFIX_OPERATOR_DEGREE": "Градусы",
    "OPERATOR_TAN": "Тангенс",
    "OPERATOR_COT": "Котангенс",
    "OPERATOR_LIMIT": "Предел",
    "VARIABLE_AN": "Члены последовательности",
    "BASIC_INFIX_OPERATOR_FACTORIAL": "Факториал",
    "OPERATOR_SIGN": "Знак",
    "OPERATOR_SEC": "Секанс",
    "OPERATOR_CSC": "Косеканс",
    # буквы
    "VARIABLE_ALPHA": "\\alpha",
    "VARIABLE_BETA": "\\beta",
    "VARIABLE_THETA": "\\theta",
}

_DIGITS = {
    "0": "ZERO",
    "1": "ONE",
    "2": "TWO",
    "3": "THREE",
    "4": "FOUR",
    "5": "FIVE",
    "6": "SIX",
    "7": "SEVEN",
    "8": "EIGHT",
    "9": "NINE",
}
for _ch, _name in _DIGITS.items():
    KEY_LABELS[f"DIGIT_{_name}"] = _ch
for _letter in "abcdefghijklmnopqrstuvwxyz":
    KEY_LABELS[f"VARIABLE_{_letter.upper()}_LOW"] = _letter

#: Символ из `type` → код оператора.
TYPE_CODES = {ch: f"DIGIT_{name}" for ch, name in _DIGITS.items()}
TYPE_CODES.update(
    {
        ".": "DIGIT_DOT",
        "-": "BASIC_INFIX_OPERATOR_MINUS",
        "+": "BASIC_INFIX_OPERATOR_PLUS",
        "*": "BASIC_INFIX_OPERATOR_MULTIPLY",
        "/": "BASIC_INFIX_OPERATOR_DIVIDE",
        "=": "BASIC_INFIX_OPERATOR_EQUALS",
        "(": "OPERATOR_LEFT_BRACKET",
        ")": "OPERATOR_RIGHT_BRACKET",
    }
)
for _letter in "abcdefghijklmnopqrstuvwxyz":
    TYPE_CODES[_letter] = f"VARIABLE_{_letter.upper()}_LOW"
    TYPE_CODES[_letter.upper()] = f"VARIABLE_{_letter.upper()}_LOW"

#: Кнопки «решить» на экране ввода (`_solveLabel` в main.dart).
SOLVE_LABELS = (
    "Шаги решения",
    "Вычислить",
    "Решить уравнение",
    "Решить",
    "Упростить",
    "Найти производную",
    "Найти интеграл",
    "Вычислить интеграл",
    "Найти предел",
)

#: Подписи, которыми приложение сообщает об ошибке решателя.
ERROR_MARKERS = (
    "не переводится",
    "Не удалось",
    "Выражение не закончено",
    "Введите выражение",
    "Неподдерживаем",
)

#: Ответы, которые не являются ошибкой: предел может не существовать.
#: Такой текст завершает ожидание наравне с экраном шагов.
ANSWER_MARKERS = ("не существует", "не определён", "не определена")

#: Кнопка «Далее» в поле ввода.
NEXT_LABEL = "Далее"

#: Перебор переключателей экранов (служебный ряд).
#:
#: «Функции» и «Буквы» — переключатели-тумблеры: нажатие на активный экран
#: возвращает к цифрам. Двух нажатий «Функции» хватает, чтобы из букв попасть
#: на цифры (алфавит → функции → цифры), поэтому набор покрывает все три
#: экрана, в том числе возврат с букв после `y` к `+` или `=`.
SHEET_TOGGLES = (
    "123 · Цифры",
    "Функции",
    "Функции",
    "Буквы",
    "Буквы",
    "Буквы",
)


def tap_key(code: str) -> None:
    """Нажать клавишу по коду оператора, при необходимости сменив экран.

    Как `_key` в `app/test/app_test.dart`: если клавиши нет на текущем экране,
    нажимаем переключатель экранов. Перебор переключателей (цифры, расширенный,
    буквы, снова расширенный) покрывает все три экрана и не зависит от того,
    на каком экране клавиатура осталась после прошлой клавиши.
    """
    label = KEY_LABELS.get(code, code)
    root = dump()
    center = find_key(root, label)
    if center is not None:
        tap_xy(*center)
        return
    # «Цифры» видна только на других экранах, поэтому отсутствующий переключатель пропускаем.
    for toggle in SHEET_TOGGLES:
        if not tap_label(toggle):
            continue
        root = dump()
        center = find_key(root, label)
        if center is not None:
            tap_xy(*center)
            return
    # Клавиатура могла быть скрыта кнопкой в тулбаре.
    if tap_label("Показать клавиатуру"):
        root = dump()
        center = find_key(root, label)
        if center is not None:
            tap_xy(*center)
            return
    raise ActionError(f"на клавиатуре нет клавиши {code!r} ({label!r})")


# ─────────────────────────────────────────────────────────── тексты и снимки


def record_texts(root: ET.Element) -> None:
    """Записать видимые подписи экрана в texts.txt текущей задачи."""
    if TEXTS is None:
        return
    TEXTS.write(f"--- {STEP}\n")
    for node, _ in nodes(root):
        for label in labels(node):
            TEXTS.write(label.replace("\n", "\\n") + "\n")
    TEXTS.flush()


def shot(name: str) -> Path | None:
    """Снимок `OUTDIR/<id>/NN_<name>.png` и подписи экрана в `NN_<name>.txt`.

    С `--no-shots` PNG не снимается, но текстовый дамп делается всё равно:
    именно он заменяет просмотр скриншотов оператором.
    """
    global SHOT_NO, SHOTS
    SHOT_NO += 1
    SHOTS += 1
    safe = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_.-]+", "_", name).strip("_") or "shot"
    stem = f"{SHOT_NO:02d}_{safe}"
    path = TASK_DIR / f"{stem}.png"
    if not NO_SHOTS:
        path.write_bytes(adb("exec-out", "screencap", "-p", binary=True))
    # `record=False`: texts.txt ведёт record_texts() на действиях, как раньше;
    # подписи снимка живут в своём .txt и в transcript.
    root = dump(record=False)
    rows = label_lines(root)
    (TASK_DIR / f"{stem}.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    TRANSCRIPT.append((safe, rows))
    return None if NO_SHOTS else path


def log(message: str) -> None:
    """Строка в лог запуска (OUTDIR/run_<serial>.log) и в stderr."""
    line = f"[{time.strftime('%H:%M:%S')}] {message}"
    print(line, file=sys.stderr)
    if LOG is not None:
        LOG.write(line + "\n")
        LOG.flush()


# ──────────────────────────────────────────────────────────────── приложение


def _startup_ready(root: ET.Element) -> bool:
    """Решатель поднялся (индикатор «Подготавливаем решатель…» исчез)."""
    return find(root, "Подготавливаем решатель…") is None


def _keyboard_ready(root: ET.Element) -> bool:
    """Клавиатура видна: на экране есть цифровые клавиши («7\\n7»)."""
    return find_key(root, "7") is not None and find_key(root, "0") is not None


def restart_app(timeout: float = 90, settle: float = 0.8) -> None:
    """Force-stop + start; ждём клавиатуру (первые нажатия после старта теряются)."""
    global STEP
    STEP = "запуск приложения"
    adb("shell", "am", "force-stop", APP_ID)
    adb("shell", "am", "start", "-n", ACTIVITY)
    deadline = time.time() + timeout
    while time.time() < deadline:
        root = dump(record=False)
        if _keyboard_ready(root):
            break
        if find(root, "Показать клавиатуру") is not None:
            tap_label("Показать клавиатуру")
            continue
        time.sleep(0.5)
    else:
        raise ActionError(f"клавиатура не появилась за {timeout:.0f} с")
    # Индикатор готовности решателя: ждём, но не дольше 60 с — решатель всё
    # равно поднимается внутри `_solve` (см. `ensureReady` в main.dart).
    deadline = time.time() + 60
    while time.time() < deadline:
        if _startup_ready(dump(record=False)):
            break
        time.sleep(1.0)
    time.sleep(settle)


def _error_text(root: ET.Element) -> str | None:
    for node, _ in nodes(root):
        for label in labels(node):
            for marker in ERROR_MARKERS:
                if marker in label:
                    return label.strip()
    return None


def _answer_text(root: ET.Element) -> str | None:
    """Текст ответа «предел не существует» — это ответ, а не ошибка."""
    for node, _ in nodes(root):
        for label in labels(node):
            for marker in ANSWER_MARKERS:
                if marker in label:
                    return label.strip()
    return None


def action_solve() -> None:
    """Нажать кнопку решения и дождаться экрана шагов."""
    global STEP
    deadline = time.time() + 120
    while True:
        root = dump(record=False)
        center = None
        for label in SOLVE_LABELS:
            center = find(root, label)
            if center is not None:
                break
        if center is not None:
            record_texts(root)
            break
        if time.time() > deadline:
            raise ActionError("кнопка решения не появилась за 120 с")
        time.sleep(0.6)
    tap_xy(*center, wait=0.6)
    deadline = time.time() + 240
    while time.time() < deadline:
        root = dump(record=False)
        if find(root, "Шаги по решению") is not None:
            STEP = "экран шагов"
            record_texts(root)
            return
        answer = _answer_text(root)
        if answer:
            # «Предел не существует» — ответ, а не ошибка: не ждём 240 с.
            STEP = "экран ответа"
            record_texts(root)
            if DEBUG:
                log(f"ответ без шагов: {answer}")
            return
        error = _error_text(root)
        if error:
            STEP = "экран шагов"
            record_texts(root)
            raise ActionError(f"решатель: {error}")
        assert_app_running("на экране шагов")
        time.sleep(0.8)
    raise ActionError("экран шагов не появился за 240 с")


def _dialog_value(root: ET.Element, group: str) -> int:
    """Текущее значение строки диалога размера («Размер»/«Строки»/«Столбцы»)."""
    plus = find(root, f"Увеличить {group}")
    minus = find(root, f"Уменьшить {group}")
    if plus is None:
        raise ActionError(f"в диалоге нет строки «{group}»")
    best = None
    for node, center in nodes(root):
        label = (node.get("text") or node.get("content-desc") or "").strip()
        if not re.fullmatch(r"\d+", label):
            continue
        if abs(center[1] - plus[1]) > 60 or center[0] >= plus[0]:
            continue
        if minus is not None and center[0] <= minus[0]:
            continue
        if best is None or center[0] > best[0]:
            best = (center[0], int(label))
    if best is None:
        raise ActionError(f"в диалоге не видно значения «{group}»")
    return best[1]


def _set_dimension(group: str, target: int) -> None:
    """Довести строку диалога до target кнопками «−»/«+»."""
    root = dump()
    value = _dialog_value(root, group)
    if value == target:
        return
    label = ("Увеличить " if target > value else "Уменьшить ") + group
    center = find(root, label)
    if center is None:
        raise ActionError(f"кнопка {label!r} недоступна")
    for _ in range(abs(target - value)):
        tap_xy(*center, wait=0.3)
    if _dialog_value(dump(), group) != target:
        raise ActionError(f"размер «{group}» не стал {target}")


def action_dialog(spec) -> None:
    """Диалог размера матрицы/определителя: выставить размер и «Вставить»."""
    if not isinstance(spec, dict) or not spec:
        raise ActionError("dialog: нужен {'size': N} или {'rows': R, 'cols': C}")
    plan = []
    if "size" in spec:
        plan.append(("Размер", int(spec["size"])))
    if "rows" in spec:
        plan.append(("Строки", int(spec["rows"])))
    if "cols" in spec:
        plan.append(("Столбцы", int(spec["cols"])))
    if not plan:
        raise ActionError("dialog: нужен {'size': N} или {'rows': R, 'cols': C}")
    for _ in range(3):
        if find(dump(), "Вставить") is not None:
            break
        time.sleep(0.5)
    else:
        raise ActionError("диалог размера не открылся (нет кнопки «Вставить»)")
    for group, target in plan:
        _set_dimension(group, target)
    tap_label_or_fail("Вставить", wait=0.8)


def action_long_press(code: str) -> None:
    """Долгое нажатие клавиши: открывает лист её вариантов.

    `{"long_press": "OPERATOR_LIMIT"}` + `{"tap_text": "Предел справа"}`.
    Клавишу ищем на текущем экране, затем переключаем экраны как `tap_key`.
    """
    label = KEY_LABELS.get(code, code)
    center = find_key(dump(), label)
    if center is None:
        for toggle in SHEET_TOGGLES:
            if not tap_label(toggle):
                continue
            center = find_key(dump(), label)
            if center is not None:
                break
    if center is None:
        raise ActionError(f"для долгого нажатия не найдена клавиша {code!r}")
    long_press_xy(*center)


def action_next(count: int) -> None:
    """Нажать «Далее» count раз."""
    global STEP
    for done in range(int(count)):
        STEP = "Далее"
        if not tap_label(NEXT_LABEL, wait=0.5):
            raise ActionError(
                f"«Далее» исчезла после {done} из {int(count)} нажатий"
            )


def action_type(text: str) -> None:
    """Набрать строку клавишами клавиатуры."""
    unknown = [ch for ch in text if ch not in TYPE_CODES]
    if unknown:
        raise ActionError(f"type: нет клавиши для {unknown!r}")
    for ch in text:
        tap_key(TYPE_CODES[ch])


def _find_field(root: ET.Element):
    """Поле ввода в текущем экране: (узел, центр) или (None, None)."""
    for node, center in nodes(root):
        if "EditText" in (node.get("class") or ""):
            return node, center
    return None, None


def action_input(value) -> None:
    """Ввести текст в поле ввода (adb shell input text).

    `{"input": "4,6;2,1"}` — просто набрать (как в описании задачи).
    `{"input": {"text": "4,6;2,1", "clear": true}}` — сначала стереть то, что
    уже стоит в поле: поле шторки матрицы открывается с текстом «5,6;7,8».
    """
    if isinstance(value, dict):
        text = str(value.get("text", ""))
        replace = bool(value.get("clear") or value.get("replace"))
    else:
        text, replace = str(value), False
    node, center = _find_field(dump())
    if center is None:
        raise ActionError("input: не найдено поле ввода на экране")
    tap_xy(*center, wait=0.4)
    if replace:
        current = node.get("text") or ""
        if current:
            adb("shell", "input", "keyevent", "123")  # MOVE_END
            for _ in range(len(current)):
                adb("shell", "input", "keyevent", "67")  # DEL
            time.sleep(0.3)
    # `input text`: пробел — только как %s, остальное прячем в кавычки, чтобы
    # `;` не разрезала команду в оболочке устройства.
    payload = text.replace(" ", "%s")
    quoted = "'" + payload.replace("'", "'\\''") + "'"
    adb("shell", "input", "text", quoted)
    time.sleep(0.4)


def action_tour(spec) -> None:
    """Экран шагов: снимок карточки, «Подробнее», «Далее»."""
    stages = int(spec.get("stages", 1))
    details = int(spec.get("details", 0))
    shot("tour_00_шаг")
    for index in range(1, details + 1):
        if not tap_label("Подробнее", wait=1.0):
            break
        shot(f"tour_00_подробнее_{index}")
        adb("shell", "input", "keyevent", "4")
        time.sleep(1.0)
    for index in range(1, stages + 1):
        # «Далее» закреплена внизу экрана и не уезжает с карточкой.
        if not tap_label("Далее", wait=1.0):
            break
        shot(f"tour_{index:02d}_этап")


def action_clear() -> None:
    """Кнопка ⊗ «Очистить»."""
    if not tap_label("Очистить", wait=0.5):
        log("clear: поле уже пустое, «Очистить» нет")


def action_back(count: int) -> None:
    """Системная кнопка «назад» count раз."""
    for _ in range(int(count)):
        adb("shell", "input", "keyevent", "4")
        time.sleep(0.7)


# ──────────────────────────────────────────────────────────────── диспетчер


def apply(action, index: int) -> None:
    """Выполнить одно действие из TASKS.json."""
    global STEP
    if not isinstance(action, dict) or len(action) != 1:
        raise ActionError(f"действие #{index}: нужен словарь из одного ключа")
    (name, value), = action.items()
    STEP = f"{index:02d} {name}"
    if name == "key":
        tap_key(str(value))
    elif name == "long_press":
        action_long_press(str(value))
    elif name == "type":
        action_type(str(value))
    elif name == "next":
        action_next(int(value))
    elif name == "dialog":
        action_dialog(value)
    elif name == "tap_text":
        tap_text(str(value))
    elif name == "input":
        action_input(value)
    elif name == "solve":
        action_solve()
    elif name == "shot":
        shot(str(value))
    elif name == "tour":
        action_tour(value or {})
    elif name == "back":
        action_back(int(value))
    elif name == "clear":
        action_clear()
    elif name == "wait":
        time.sleep(float(value))
    else:
        raise ActionError(f"неизвестное действие {name!r}")


def run_task(task: dict, seen: set[str]) -> tuple[str, float, int, str]:
    """Выполнить задачу; вернуть (id, секунды, скриншоты, статус)."""
    global TASK_DIR, TEXTS, SHOT_NO, SHOTS, STEP, TRANSCRIPT
    task_id = str(task.get("id") or f"task{len(seen) + 1}")
    if task_id in seen:
        raise SystemExit(f"повторяющийся id задачи: {task_id}")
    seen.add(task_id)
    TASK_DIR = OUTDIR / task_id
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    for old in TASK_DIR.glob("*.png"):
        old.unlink()
    for old in TASK_DIR.glob("texts.txt"):
        old.unlink()
    SHOT_NO = 0
    SHOTS = 0
    STEP = "старт"
    TRANSCRIPT = []
    started = time.time()
    error = ""
    TEXTS = (TASK_DIR / "texts.txt").open("w", encoding="utf-8")
    try:
        log(f"{task_id}: старт ({task.get('note', '')})")
        restart_app()
        actions = task.get("actions") or []
        if not actions:
            raise ActionError("в задаче нет действий")
        for index, action in enumerate(actions, 1):
            apply(action, index)
        status = "ok"
    except ActionError as err:
        error = str(err)
        status = f"error: {error}"
    except Exception as err:  # неожиданное — тоже ошибка задачи, а не крах
        error = f"{type(err).__name__}: {err}"
        status = f"error: {error}"
        log(traceback.format_exc())
    finally:
        TEXTS.close()
        TEXTS = None
    if error:
        STEP = f"ошибка: {error}"
        try:
            shot("error")
        except Exception as err:  # скриншот ошибки не должен ронять прогон
            log(f"{task_id}: скриншот ошибки не снят: {err}")
        log(f"{task_id}: ошибка — {error}")
    expect = task.get("expect_answer")
    if expect and status == "ok":
        try:
            status = check_answer(str(expect))
        except Exception as err:  # noqa: BLE001  сверка ответа — не повод падать
            status = f"error: {type(err).__name__}: {err}"
    write_transcript(task_id, task.get("note", ""))
    seconds = time.time() - started
    if not NO_SHOTS:
        sheet = OUTDIR / f"sheet_{task_id}.png"
        montage(TASK_DIR, sheet)
    return task_id, seconds, SHOTS, status


def check_answer(expect: str) -> str:
    """Сверить `expect_answer` с content-desc формул на всех экранах задачи.

    Формулы приложения несут LaTeX в content-desc (см. Semantics в
    `vertical_result.dart` и `solution_preview.dart`). Сравнение без скобок,
    пробелов и `\\left`/`\\right`: `{x}^{2} + 1` и `x^{2}+1` — одно и то же.
    Берутся все снятые экраны, а не последний: к концу обхода ответ уже
    прокручен за край. Если подстроки нет, показываем content-desc после «Ответ».
    """
    def flat(text: str) -> str:
        return re.sub(r"\\left|\\right|[{}\s]", "", text)

    descs = []
    for _name, rows in TRANSCRIPT:
        for row in rows:
            parts = row.split(None, 2)
            if len(parts) == 3 and parts[1] == "desc":
                descs.append(parts[2])
    if any(flat(expect) in flat(value) for value in descs):
        return "ok"
    after = [descs[i + 1] for i, value in enumerate(descs[:-1]) if value == "Ответ"]
    got = (after or [value for value in descs if "=" in value] or ["—"])[0]
    return f"mismatch: {got}"


def write_transcript(task_id: str, note: str) -> None:
    """`OUTDIR/transcript_<id>.md` — все экраны задачи по порядку."""
    lines = [f"# {task_id}"]
    if note:
        lines += ["", str(note)]
    for name, rows in TRANSCRIPT:
        lines += ["", f"## {name}", ""]
        lines += rows
    (OUTDIR / f"transcript_{task_id}.md").write_text(
        "\n".join(lines).rstrip() + "\n", encoding="utf-8"
    )


def montage(folder: Path, sheet: Path) -> None:
    """Склеить снимки задачи в один лист 6×N."""
    files = sorted(str(p) for p in folder.glob("*.png"))
    if not files:
        log(f"montage: в {folder} нет снимков")
        return
    if shutil.which("montage") is None:
        log("montage: ImageMagick не установлен, лист не собран")
        return
    result = subprocess.run(
        ["montage", *files, "-tile", "6x", "-geometry", "270x585+4+4", str(sheet)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        log(f"montage: код {result.returncode}: {result.stderr.decode(errors='replace')}")


# ───────────────────────────────────────────────────────────────────── main


def self_test() -> int:
    """Проверка чтения экрана без устройства: порядок подписей и transcript."""
    global OUTDIR, TRANSCRIPT
    fixture = Path(__file__).resolve().parent / "tests" / "labels.xml"
    root = ET.fromstring(fixture.read_text(encoding="utf-8"))
    rows = [tuple(line.split(None, 2)) for line in label_lines(root)]
    expected = [
        ("100,44", "text", "Ответ"),
        ("200,44", "desc", "y = C e^{x}"),
        ("400,44", "text", "Шаг 1"),
        ("500,44", "desc", "2"),
        ("500,200", "text", "1/5. Положим"),
    ]
    assert rows == expected, f"порядок подписей:\n{rows}\nожидался:\n{expected}"

    old_out, old_transcript = OUTDIR, TRANSCRIPT
    with tempfile.TemporaryDirectory() as tmp:
        OUTDIR = Path(tmp)
        TRANSCRIPT = [("first", ["line1", "line2"])]
        write_transcript("t1", "заметка")
        text = (OUTDIR / "transcript_t1.md").read_text(encoding="utf-8")
        assert "## first" in text and "line2" in text and "заметка" in text, text
    TRANSCRIPT = [
        ("answer", ["100,44 desc Ответ", "200,44 desc y = {x}^{2} + 1"]),
        ("tour", ["100,44 desc Шаг 1"]),
    ]
    assert check_answer("x^{2} + 1") == "ok"  # all screens, braces ignored
    assert check_answer("x^{3}") == "mismatch: y = {x}^{2} + 1"
    OUTDIR, TRANSCRIPT = old_out, old_transcript
    print(f"self-test ok: {len(rows)} подписей, порядок и transcript")
    return 0


def main(argv: list[str]) -> int:
    global SERIAL, TAG, OUTDIR, LOG, NO_SHOTS
    if "--self-test" in argv:
        return self_test()
    parser = argparse.ArgumentParser(description="Драйвер mymath для телефона/эмулятора")
    parser.add_argument("tasks", type=Path, help="TASKS.json")
    parser.add_argument("outdir", type=Path, help="каталог результатов")
    parser.add_argument("--only", default="", help="id,id — только эти задачи")
    parser.add_argument("--install", type=Path, help="APK, который поставить перед прогоном")
    parser.add_argument(
        "--no-shots",
        action="store_true",
        help="без скриншотов и контактного листа: только текстовые дампы",
    )
    args = parser.parse_args(argv)
    NO_SHOTS = args.no_shots

    SERIAL = os.environ.get("ANDROID_SERIAL", "").strip()
    if not SERIAL:
        devices = device_serials()
        if len(devices) != 1:
            parser.error(
                "задайте ANDROID_SERIAL (подключено устройств: "
                f"{len(devices)}: {', '.join(devices) or '—'})"
            )
        SERIAL = devices[0]
        print(f"ANDROID_SERIAL не задан, беру единственное устройство {SERIAL}",
              file=sys.stderr)
    TAG = re.sub(r"[^0-9A-Za-z]+", "_", SERIAL) or "device"
    OUTDIR = args.outdir
    OUTDIR.mkdir(parents=True, exist_ok=True)
    LOG = (OUTDIR / f"run_{TAG}.log").open("a", encoding="utf-8")
    LOG.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} {SERIAL} =====\n")
    LOG.flush()

    tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        parser.error("TASKS.json должен быть списком задач")
    only = [part.strip() for part in args.only.split(",") if part.strip()]
    if only:
        known = {str(task.get("id")) for task in tasks}
        for missing in [item for item in only if item not in known]:
            print(f"--only: неизвестный id {missing!r}", file=sys.stderr)
        tasks = [task for task in tasks if str(task.get("id")) in only]

    wait_device()
    wait_boot()
    if args.install:
        log(f"install: {args.install}")
        out = adb("install", "-r", str(args.install), timeout=900)
        if "Success" not in out:
            raise SystemExit(f"APK не установился: {out.strip()}")
        log("install: Success")

    seen: set[str] = set()
    results = []
    for task in tasks:
        task_id, seconds, shots, status = run_task(task, seen)
        print(f"{task_id}\t{seconds:.1f} с\tснимков: {shots}\t{status}", flush=True)
        results.append((task_id, status))
    LOG.write(f"итог: {len(results)} задач\n")
    LOG.close()
    return 0 if all(status == "ok" for _, status in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
