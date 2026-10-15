"""Тестовый корпус: задачи с эталонными ответом и ключами шагов.

Корпус лежит в ``backend/tests/corpus/*.json`` — по файлу на модуль решателя.
Каждая задача описывает вход строкой протокола Photomath и эталон ручной
работы:

* ``solution`` — ожидаемый ответ структурой узла в формате контракта
  (``type``/``value``/``children``); ``null`` означает «ответа-узла нет»
  (тождество или противоречие — текст шага и есть ответ). Сравнение —
  структурное (:meth:`CoreNode.structural_eq`), устойчивое к форматированию.
* ``steps`` — ключи подшагов по порядку (``CoreRichText.type``).

Дополнительно раннер проверяет, что каждый ключ шага есть в словаре
объяснений и что его арность совпадает с шаблоном (максимальный ``ARGn``).

Необязательные поля задачи:

* ``command`` — действие (``CoreAction``): ``factor``/``expand``/``simplify``
  и векторные/матричные команды;
* ``args`` — аргументы команды, строки протокола;
* ``interval`` — промежуток ``{"min": …, "max": …}`` (строки протокола)
  для отбора корней тригонометрического уравнения;
* ``method`` — индекс способа решения в вертикальной ветке (по умолчанию 0).

Эталоны составлены вручную по математике и словарю объяснений, а не сняты
с решателя: если ожидание расходится с выводом — это дефект решателя, а не
повод переписать эталон. Корпус, в частности, зафиксировал регрессию по
дефекту Q10 (``truth/07-open-questions.md``): ``√(2+3)`` -> ``√5``, а не
``5``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from mymath_backend import CoreNode, load_explanations
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult, ResultGroupType
from mymath_backend.solver import solve

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"


def _load_tasks() -> list[tuple[str, dict[str, Any]]]:
    """Все задачи корпуса как ``(модуль/идентификатор, задача)``."""
    tasks: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(CORPUS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        module = data["module"]
        for task in data["tasks"]:
            tasks.append((f"{module}/{task['id']}", task))
    return tasks


def _vertical_entries(data: Any) -> list[CoreSolverVerticalResult]:
    """Способы решения из вертикальной ветки, по порядку."""
    group = data.result.group(ResultGroupType.VERTICAL)
    assert group is not None, "нет вертикальной ветки"
    return [
        CoreSolverVerticalResult.from_contract(entry.result)
        for entry in group.entries
        if entry.result and "steps" in entry.result
    ]


def _parse_interval(task: dict[str, Any]) -> tuple[CoreNode, CoreNode] | None:
    interval = task.get("interval")
    if interval is None:
        return None
    return parse_protocol(interval["min"]), parse_protocol(interval["max"])


def _expected_solution(task: dict[str, Any]) -> CoreNode | None:
    raw = task.get("solution")
    if raw is None:
        return None
    return CoreNode.from_contract(raw)


def _step_keys(vertical: CoreSolverVerticalResult) -> list[str]:
    keys: list[str] = []
    for step in vertical.steps:
        for sub in step.substeps:
            assert sub.description is not None, "подшаг без пояснения"
            keys.append(sub.description.type)
    return keys


def _arity_problem(explanations: Any, key: str) -> str | None:
    """Проверить ключ по словарю; ``None`` — всё хорошо."""
    if key not in explanations:
        return f"ключа {key!r} нет в словаре объяснений"
    template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
    used = {int(m) for m in re.findall(r"ARG(\d+)", template)}
    highest = max(used) if used else 0
    declared = explanations.arity(key)
    if declared != highest:
        return f"у {key!r} арность {declared}, а шаблон использует {highest}"
    return None


TASKS = _load_tasks()


@pytest.mark.parametrize(("name", "task"), TASKS, ids=[name for name, _ in TASKS])
def test_corpus_task(name: str, task: dict[str, Any]) -> None:
    """Проверить один эталонный кейс корпуса."""
    node = parse_protocol(task["input"])
    args = [parse_protocol(arg) for arg in task.get("args", [])]
    data = solve(
        node,
        command=task.get("command"),
        args=args,
        interval=_parse_interval(task),
    )

    entries = _vertical_entries(data)
    method = task.get("method", 0)
    assert method < len(entries), f"{name}: нет способа решения с индексом {method}"
    vertical = entries[method]

    expected = _expected_solution(task)
    if expected is None:
        assert vertical.solution is None, (
            f"{name}: ожидался ответ без узла, получено "
            f"{vertical.solution.to_contract() if vertical.solution else None}"
        )
    else:
        assert vertical.solution is not None, f"{name}: ожидался ответ, получено null"
        assert vertical.solution.structural_eq(expected), (
            f"{name}: ответ {vertical.solution.to_contract()} != эталон {expected.to_contract()}"
        )

    assert _step_keys(vertical) == task["steps"], (
        f"{name}: ключи шагов {_step_keys(vertical)} != эталон {task['steps']}"
    )


def test_all_corpus_keys_exist_with_matching_arity() -> None:
    """Каждый ключ каждого кейса обязан быть в словаре с верной арностью."""
    explanations = load_explanations(str(EXPLANATIONS))
    problems: list[str] = []
    for name, task in TASKS:
        node = parse_protocol(task["input"])
        data = solve(
            node,
            command=task.get("command"),
            args=[parse_protocol(arg) for arg in task.get("args", [])],
            interval=_parse_interval(task),
        )
        vertical = _vertical_entries(data)[task.get("method", 0)]
        for key in _step_keys(vertical):
            if problem := _arity_problem(explanations, key):
                problems.append(f"{name}: {problem}")
    assert problems == []


def test_corpus_covers_every_module() -> None:
    """Файл корпуса есть у каждого модуля решателя, перечисленного в плане."""
    modules = {
        json.loads(path.read_text(encoding="utf-8"))["module"] for path in CORPUS_DIR.glob("*.json")
    }
    expected = {
        "arithmetic",
        "fractions",
        "powers",
        "trigonometry",
        "absolute",
        "equations",
        "inequalities",
        "systems",
        "intervals",
        "sets",
        "comparison",
        "domain",
        "rational",
        "radical",
        "transcendental",
        "polynomial_high",
        "ineq_quad",
        "ineq_rational",
        "ineq_transcendental",
        "ineq_compound",
        "ineq_system",
        "restrictions",
        "system_nxn",
        "sequences",
        "percentage",
        "periodic",
        "rewrite",
        "area",
        "prove",
        "evaluate",
        "even_odd",
        "extrema",
        "inflection",
        "intercepts",
        "range",
        "asymptotes",
        "conic",
        "convergence",
        "diff_eq",
        "angle",
        "vertex",
        "rationalize",
        "polar",
        "matrices",
        "matrix_ops",
        "matrix_eq",
        "derivatives",
        "limits",
        "integrals",
        "series",
        "combinatorics",
        "complex",
        "trig_equations",
        "vectors",
        "vertical",
        "commands",
    }
    assert expected <= modules
