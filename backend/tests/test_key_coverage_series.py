"""Ключи карточек рядов и интегралов.

Заголовки шагов, признак Даламбера/Коши с убиранием модуля, интегральный
признак с полной цепочкой несобственного интеграла, радиус сходимости и шапки
определённого интеграла.

Каждый использованный ключ проверяется по словарю: он существует, арность
совпадает с шаблоном и число переданных аргументов равно арности.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from mymath_backend import load_explanations, service
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult, ResultGroupType
from mymath_backend.solver import solve

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


def _entries(
    source: str, command: str | None = None, args: tuple[str, ...] = ()
) -> list[CoreSolverVerticalResult]:
    node = parse_protocol(source)
    extra = [parse_protocol(arg) for arg in args]
    data = solve(node, command=command, args=extra or None)
    group = data.result.group(ResultGroupType.VERTICAL)
    assert group is not None
    return [
        CoreSolverVerticalResult.from_contract(entry.result)
        for entry in group.entries
        if entry.result and "steps" in entry.result
    ]


def _stages(entry: CoreSolverVerticalResult) -> list[tuple[list[str], list[str]]]:
    """Для каждого шага: заголовки и ключи подшагов."""
    stages: list[tuple[list[str], list[str]]] = []
    for step in entry.steps:
        headers = [header.type for header in step.step_headers]
        keys = [sub.description.type for sub in step.substeps if sub.description is not None]
        stages.append((headers, keys))
    return stages


# ── ряды: шапки карточек сумм ─────────────────────────────────────────


def test_sum_cards_carry_headers() -> None:
    formula, arithmetic, plain = _entries("{sigma_def({i},{1},{5},{i})}")
    assert formula.header is not None and formula.header.type == "series_find_sum_special"
    assert arithmetic.header is not None and arithmetic.header.type == "series_find_sum_arith"
    assert plain.header is not None and plain.header.type == "series_sigma_find_sub"

    squares = _entries("{sigma_def({i},{1},{4},{i^2})}")
    assert squares[0].header is not None and squares[0].header.type == "series_find_sum_special"

    geometric = _entries("{sigma_def({n},{0},{3},{2^n})}")
    assert geometric[0].header is not None and geometric[0].header.type == "series_find_sum_geom"
    assert geometric[1].header is not None and geometric[1].header.type == "series_sigma_find_sub"

    constant = _entries("{sigma_def({n},{1},{4},{3})}")
    assert constant[0].header is not None and constant[0].header.type == "series_find_sum_special"


def test_geometric_card_step_headers_are_rows() -> None:
    entry = _entries("{sigma_def({n},{0},{3},{2^n})}")[0]
    headers = [header.type for step in entry.steps for header in step.step_headers]
    assert headers[:3] == [
        "series_sigma_calc_n_simple",
        "calculate_short",
        "series_sigma_find_fst_ratio_simple",
    ]
    assert "series_sigma_geom_use_formula" in headers


# ── ряды: признаки сходимости ────────────────────────────────────────


def test_integral_test_writes_the_function_and_the_improper_chain() -> None:
    (entry,) = _entries("{sigma_def({n},{2},{inf},{frac({1},{n*ln({n})^2})})}", "integral_test")
    stages = _stages(entry)
    assert [keys for _headers, keys in stages] == [
        ["series_integral_test"],
        ["series_integral_test_write_as_fun"],
        ["series_integral_test_use"],
        ["integrate_imp_rewrite_using_lim"],
        ["integrate_def"],
        ["limit_solve"],
        ["integrate_imp_converges"],
        ["series_integral_test_converges"],
    ]
    headers = [headers for headers, _keys in stages]
    assert headers[1] == ["series_integral_test_write_as_fun_smpl"]
    assert headers[2] == ["series_integral_test_use_smpl"]
    assert headers[3] == ["integrate_imp_evaluate"]
    assert headers[4] == ["integrate_calc"]
    assert headers[5] == ["evaluate"]
    assert headers[6] == ["integrate_imp_converges_smpl"]
    assert headers[7] == ["series_test_converges"]
    # The nested chain of the definite integral uses the app's headings.
    nested = entry.steps[4].substeps[0].subresult
    assert nested is not None
    nested_headers = [header.type for step in nested.steps for header in step.step_headers]
    assert "integrate_def_bounds_short" in nested_headers


def test_the_integral_test_chain_substitutes_the_primitive() -> None:
    """``∫dx/(x ln x)``: ``t = ln x``, integrate, substitute back (the rows)."""
    (entry,) = _entries("{sigma_def({n},{2},{inf},{frac({1},{n*ln({n})})})}", "integral_test")
    nested = entry.steps[4].substeps[0].subresult
    assert nested is not None
    assert [sub.description.type for step in nested.steps for sub in step.substeps] == [
        "integrate_def_solve_undefined",
        "integrate_subs_subproc",
        "integrate_msg",
        "sub_msg_ret",
        "integrate_def_bounds",
        "integrate_def_msg_range",
        "simplify",
    ]
    assert [header.type for step in nested.steps for header in step.step_headers] == [
        "integrate",
        "trans_msg",
        "integrate_calc",
        "substitute_return_one_short",
        "integrate_def_bounds_short",
        "calculate_expressions",
        "simplify_msg",
    ]
    # The substitution itself is the nested screen of the rewrite row.
    derivation = nested.steps[1].substeps[0].subresult
    assert derivation is not None
    assert [header.type for step in derivation.steps for header in step.step_headers] == [
        "integrate_differential_sub"
    ]
    assert [sub.description.type for step in derivation.steps for sub in step.substeps] == [
        "integrate_subs_substep"
    ]


def test_divergent_integral_test_ends_with_the_divergent_row() -> None:
    (entry,) = _entries("{sigma_def({n},{2},{inf},{frac({1},{n*ln({n})})})}", "integral_test")
    stages = _stages(entry)
    assert stages[-2][1] == ["integrate_imp_diverges"]
    assert stages[-2][0] == ["integrate_imp_diverges_simple"]
    assert stages[-1] == (["series_test_diverges"], ["series_integral_test_diverges"])


def test_ratio_test_drops_the_absolute_value_before_the_limit() -> None:
    (entry,) = _entries("{sigma_def({n},{1},{inf},{frac({1},{2^n})})}", "ratio_test")
    assert [keys for _headers, keys in _stages(entry)] == [
        ["series_ratio_test"],
        ["series_ratio_test_use"],
        ["series_ratio_test_remove_abs"],
        ["series_ratio_test_lim_ltone"],
    ]
    assert _stages(entry)[2][0] == ["abs_remove_short"]
    assert _stages(entry)[3][0] == ["series_test_converges"]


def test_root_test_drops_the_absolute_value_before_the_limit() -> None:
    (entry,) = _entries("{sigma_def({n},{1},{inf},{frac({1},{2^n})})}", "root_test")
    assert [keys for _headers, keys in _stages(entry)] == [
        ["series_root_test"],
        ["series_root_test_use"],
        ["series_root_test_remove_abs"],
        ["series_root_test_lim_ltone"],
    ]


def test_alternating_test_checks_the_limit_and_the_second_condition() -> None:
    (entry,) = _entries("{sigma_def({n},{1},{inf},{frac({(-1)^n},{n})})}", "alt_test")
    assert [keys for _headers, keys in _stages(entry)] == [
        ["series_alt_test"],
        ["series_alt_test_check"],
        ["series_alt_test_snd_cond"],
        ["series_alt_test_snd_cond_true"],
        ["series_alt_test_converges"],
    ]
    assert _stages(entry)[3][0] == ["series_alt_test_snd_cond_true_smpl"]


def test_nth_term_with_a_zero_limit_is_inconclusive_not_an_error() -> None:
    (entry,) = _entries("{sigma_def({n},{1},{inf},{frac({1},{n^2})})}", "nth_term_test")
    assert _stages(entry)[-1] == (
        ["series_test_inconclusive"],
        ["series_nth_term_test_lim_zero"],
    )
    solution = service.solve_request(
        parse_protocol("{sigma_def({n},{1},{inf},{frac({1},{n^2})})}").to_contract(),
        action_data={"command": "nth_term_test", "args": []},
        locale="ru",
        render=True,
    )["result"]["solution"]
    assert solution["type"] == "TEXT"
    assert "ответа не даёт" in solution["value"].lower()


def test_convergence_starts_with_the_p_series_row() -> None:
    p_series = _entries("{sigma_def({n},{1},{inf},{frac({1},{n^2})})}", "convergence")[0]
    assert [keys for _headers, keys in _stages(p_series)] == [
        ["series_test_group"],
        ["series_pseries_test_use"],
        ["series_pseries_test_converges"],
    ]
    assert _stages(p_series)[1][0] == ["series_pseries_test_use_smpl"]
    assert _stages(p_series)[2][0] == ["series_test_converges"]
    harmonic = _entries("{sigma_def({n},{1},{inf},{frac({1},{n})})}", "convergence")[0]
    assert _stages(harmonic)[-1] == (
        ["series_test_diverges"],
        ["series_pseries_test_diverges"],
    )


# ── ряды: радиус сходимости ──────────────────────────────────────────


def test_convergence_checks_the_necessary_condition_before_the_integral_test() -> None:
    (entry,) = _entries("{sigma_def({n},{2},{inf},{frac({1},{n*ln({n})})})}", "convergence")
    stages = _stages(entry)
    assert [keys for _headers, keys in stages][:3] == [
        ["series_test_group"],
        ["series_nth_term_test_use"],
        ["series_nth_term_test_lim_zero"],
    ]
    assert stages[2][0] == ["series_test_inconclusive"]
    assert stages[3][1] == ["series_integral_test"]


def test_radius_finite_has_the_no_variable_row() -> None:
    (entry,) = _entries("{sigma_def({n},{0},{inf},{frac({x^n},{2^n})})}", "radius_of_convergence")
    assert [keys for _headers, keys in _stages(entry)] == [
        ["convergence_radius_find"],
        ["convergence_radius_limit"],
        ["convergence_radius_no_var"],
        ["convergence_radius_abs"],
        ["convergence_radius_conv"],
    ]
    assert _stages(entry)[3][0] == ["convergence_radius_abs_smpl"]
    assert _stages(entry)[4][0] == ["convergence_radius_conv_smpl"]


def test_radius_infinite_separates_the_factor_of_x() -> None:
    (entry,) = _entries(
        "{sigma_def({n},{0},{inf},{frac({x^n},{factorial({n})})})}",
        "radius_of_convergence",
    )
    assert [keys for _headers, keys in _stages(entry)] == [
        ["convergence_radius_find"],
        ["convergence_radius_limit"],
        ["convergence_radius_frac_sep"],
        ["convergence_radius_const_front"],
        ["series_root_test_remove_abs"],
        ["limit_solve"],
        ["mul_with_zero"],
        ["convergence_radius_conv_inf"],
    ]


# ── интегралы: шапки карточек ───────────────────────────────────────


def test_a_definite_integral_has_step_headers() -> None:
    entry = _entries("{integral_def({0},{1},{x})}")[1]
    headers = [header.type for step in entry.steps for header in step.step_headers]
    assert headers == [
        "integrate",
        "integrate_calc",
        "integrate_def_bounds_short",
        "calculate_expressions",
        "calculate_short",
    ]


def test_an_improper_integral_has_step_headers() -> None:
    entry = _entries("{integral_def({1},{inf},{frac({1},{x^2})})}")[1]
    headers = [header.type for step in entry.steps for header in step.step_headers]
    assert headers == ["integrate_imp_evaluate", "integrate_calc", "evaluate"]

    singular = _entries("{integral_def({0},{1},{frac({1},{root2({x})})})}")[1]
    headers = [header.type for step in singular.steps for header in step.step_headers]
    assert headers == ["integrate_imp_rewrite", "integrate_calc", "evaluate"]
    nested = singular.steps[0].substeps[0].subresult
    assert nested is not None
    assert (
        next(header.type for step in nested.steps for header in step.step_headers)
        == "integrate_imp_discon_lower_simple"
    )


def test_an_iterated_integral_has_the_inner_row() -> None:
    entry = _entries("{integral_def({0},{1},{integral_def({0},{2},{muli({x},{y^2})})})}")[0]
    stages = _stages(entry)
    assert [keys for _headers, keys in stages] == [
        ["integrate_iterated_inner"],
        ["integrate_def"],
    ]
    assert stages[0][0] == ["integrate_iterated_inner_smpl"]
    assert stages[1][0] == ["integrate_calc"]
    inner = entry.steps[0].substeps[0].subresult
    assert inner is not None
    assert [sub.description.type for step in inner.steps for sub in step.substeps] == [
        "integrate_def_solve_undefined",
        "integrate_msg",
        "integrate_def_bounds",
        "integrate_def_msg_range",
        "simplify",
    ]


# ── суммы с нижним пределом ≠ 1 ──────────────────────────────────────


def test_a_sum_from_two_rewrites_the_missing_first_term() -> None:
    formula, arithmetic, plain = _entries("{sigma_def({i},{2},{5},{i})}")
    assert formula.header is not None and formula.header.type == "series_find_sum_special"
    stages = _stages(formula)
    assert [keys for _headers, keys in stages] == [
        ["series_sigma_rewrite_start2"],
        ["series_formula_pos_int"],
        ["calculate_direct"],
    ]
    assert stages[0][0] == ["series_rewrite_sum"]
    assert stages[2][0] == ["calculate_short"]
    detail = formula.steps[2].substeps[0].subresult
    assert detail is not None
    assert [sub.description.type for step in detail.steps for sub in step.substeps] == [
        "add",
        "frac_reduce_frac_num",
        "mul",
        "sub",
    ]
    # The arithmetic card counts the terms first.
    assert [keys for _headers, keys in _stages(arithmetic)][:2] == [
        ["series_sigma_calc_n"],
        ["sum"],
    ]
    assert plain.header is not None and plain.header.type == "series_sigma_find_sub"


def test_a_sum_from_zero_drops_the_zero_term() -> None:
    formula, arithmetic, _plain = _entries("{sigma_def({i},{0},{5},{i})}")
    stages = _stages(formula)
    assert [keys for _headers, keys in stages][:2] == [
        ["series_sigma_rewrite_start0"],
        ["series_formula_pos_int"],
    ]
    assert stages[0][0] == ["series_rewrite_sum"]
    # (5 − 0) + 1 → 5 + 1 → 6 in the count row.
    count_detail = arithmetic.steps[1].substeps[0].subresult
    assert count_detail is not None
    assert [sub.description.type for step in count_detail.steps for sub in step.substeps] == [
        "add_with_zero",
        "add",
    ]


def test_a_sum_from_three_splits_off_a_prefix() -> None:
    formula, _arithmetic, _plain = _entries("{sigma_def({i},{3},{5},{i})}")
    stages = _stages(formula)
    assert [keys for _headers, keys in stages] == [
        ["series_sigma_rewrite_separate"],
        ["series_find_sum_pos_int", "series_find_sum_pos_int"],
        ["sub"],
    ]
    assert stages[0][0] == ["use_property_sum"]
    assert stages[1][0] == ["find_sum_pl"]
    assert stages[2][0] == ["calculate_short"]
    detail = formula.steps[1].substeps[0].subresult
    assert detail is not None
    assert [sub.description.type for step in detail.steps for sub in step.substeps] == [
        "series_formula_pos_int",
        "calculate_direct",
    ]


# ── площадь под кривой: карточка ───────────────────────────


def test_area_card_has_rows_and_headers() -> None:
    (entry,) = _entries("{integral_def({0},{2},{x^2})}", "area")
    assert entry.header is not None and entry.header.type == "total_area"
    assert [keys for _headers, keys in _stages(entry)] == [
        ["total_area_fun"],
        ["total_area_x_intercept"],
        ["total_area_endpoint_zero"],
        ["integrate_def"],
        ["abs_neg"],
        ["total_area_final"],
    ]
    headers = [headers for headers, _keys in _stages(entry)]
    assert headers[0] == ["total_area_fun_smpl"]
    assert headers[1] == ["total_area_x_intercept_smpl"]
    assert headers[2] == ["total_area_initial"]
    assert headers[3] == ["integrate_calc"]
    assert headers[5] == ["total_area_final_smpl"]


def test_area_splits_the_interval_at_an_interior_zero() -> None:
    (entry,) = _entries("{integral_def({-1},{1},{x^3})}", "area")
    assert [keys for _headers, keys in _stages(entry)] == [
        ["total_area_fun"],
        ["total_area_x_intercept"],
        ["total_area_sep_interval_zero"],
        ["total_area_create"],
        ["total_area_create"],
        ["integrate_def"],
        ["integrate_def"],
        ["abs_neg"],
        ["total_area_sum"],
        ["frac_add"],
        ["total_area_final"],
    ]
    headers = [headers for headers, _keys in _stages(entry)]
    assert headers[2] == ["total_area_sep_smpl"]
    assert headers[3] == ["total_area_define"]
    assert headers[5] == ["integrate_calc_plural"]
    assert headers[8] == ["integrate_parts_sub_smpl"]
    assert headers[10] == ["total_area_final_smpl"]


def test_area_without_real_zeros_uses_the_restriction_rows() -> None:
    (entry,) = _entries("{integral_def({1},{2},{1/x})}", "area")
    assert [keys for _headers, keys in _stages(entry)][2:4] == [
        ["total_area_no_zeros"],
        ["integrate_def"],
    ]
    detail = entry.steps[1].substeps[0].subresult
    assert detail is not None
    assert [sub.description.type for step in detail.steps for sub in step.substeps] == [
        "x_intercept_substitute",
        "rel_restrictions_range",
        "rel_swap_eq",
        "eq_linear_frac_zero",
        "rel_el_of_zero",
    ]


def test_a_definite_integral_offers_the_area_method() -> None:
    entries = _entries("{integral_def({0},{1},{x})}")
    assert [entry.header.type if entry.header else None for entry in entries] == [
        "lesson_calc_header_int_newton",
        None,
        "total_area",
    ]
    # A trigonometric integrand has no «find the total area» method.
    sine = _entries("{integral_def({0},{pi},{sin({x})})}")
    assert all(entry.header is None or entry.header.type != "total_area" for entry in sine)


# ── словарь: каждый ключ существует, арность совпадает ───────────────


CASES = [
    ("{sigma_def({i},{1},{5},{i})}", None, ()),
    ("{sigma_def({n},{0},{3},{2^n})}", None, ()),
    ("{sigma_def({n},{1},{4},{3})}", None, ()),
    ("{sigma_def({n},{1},{3},{2n+1})}", None, ()),
    ("{sigma_def({n},{1},{inf},{frac({1},{n})})}", "convergence", ()),
    ("{sigma_def({n},{1},{inf},{frac({1},{n^2})})}", "convergence", ()),
    (
        "{sigma_def({n},{2},{inf},{frac({1},{n*ln({n})^2})})}",
        "integral_test",
        (),
    ),
    ("{sigma_def({n},{1},{inf},{frac({1},{2^n})})}", "ratio_test", ()),
    ("{sigma_def({n},{1},{inf},{frac({1},{2^n})})}", "root_test", ()),
    ("{sigma_def({n},{1},{inf},{frac({(-1)^n},{n})})}", "alt_test", ()),
    ("{sigma_def({n},{1},{inf},{frac({1},{n^2})})}", "nth_term_test", ()),
    ("{sigma_def({n},{0},{inf},{frac({x^n},{2^n})})}", "radius_of_convergence", ()),
    (
        "{sigma_def({n},{0},{inf},{frac({x^n},{factorial({n})})})}",
        "radius_of_convergence",
        (),
    ),
    ("{integral_def({0},{1},{x})}", None, ()),
    ("{integral_def({1},{inf},{frac({1},{x^2})})}", None, ()),
    ("{integral_def({0},{1},{frac({1},{root2({x})})})}", None, ()),
    ("{integral_def({0},{1},{integral_def({0},{2},{muli({x},{y^2})})})}", None, ()),
    ("{integral_def({0},{2},{x^2})}", "area", ()),
    ("{integral_def({-1},{1},{x^3})}", "area", ()),
    ("{integral_def({1},{2},{1/x})}", "area", ()),
    ("{integral_def({0},{2*pi},{sin({x})})}", "area", ()),
    ("{sigma_def({i},{0},{5},{i})}", None, ()),
    ("{sigma_def({i},{2},{5},{i})}", None, ()),
    ("{sigma_def({i},{3},{5},{i})}", None, ()),
    ("{sigma_def({n},{2},{inf},{frac({1},{n*ln({n})})})}", "integral_test", ()),
]


def _all_keys(entry: CoreSolverVerticalResult) -> list[tuple[str, int]]:
    keys: list[tuple[str, int]] = []
    for step in entry.steps:
        for header in step.step_headers:
            keys.append((header.type, len(header.args)))
        for sub in step.substeps:
            assert sub.description is not None
            keys.append((sub.description.type, len(sub.description.args)))
            if sub.subresult is not None:
                keys.extend(_all_keys(sub.subresult))
    return keys


@pytest.mark.parametrize(("source", "command", "args"), CASES, ids=[c[0] for c in CASES])
def test_every_key_exists_with_matching_arity(
    source: str, command: str | None, args: tuple[str, ...]
) -> None:
    explanations = load_explanations(str(EXPLANATIONS))
    problems: list[str] = []
    for entry in _entries(source, command, args):
        keys = [(entry.header.type, len(entry.header.args))] if entry.header is not None else []
        keys.extend(_all_keys(entry))
        for key, arguments in keys:
            if key not in explanations:
                problems.append(f"{source}: ключа {key!r} нет в словаре")
                continue
            template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
            used = {int(match) for match in re.findall(r"ARG(\d+)", template)}
            declared = explanations.arity(key)
            if declared != max(used, default=0):
                problems.append(f"{source}: у {key!r} арность {declared}, шаблон использует {used}")
            if arguments != declared:
                problems.append(
                    f"{source}: у {key!r} передано {arguments} аргументов, нужно {declared}"
                )
    assert problems == []


@pytest.mark.parametrize(("source", "command", "args"), CASES, ids=[c[0] for c in CASES])
def test_rendered_texts_have_no_placeholders(
    source: str, command: str | None, args: tuple[str, ...]
) -> None:
    raw = re.compile(r"ARG\d|\?\?\s*step_|\bNone\b|\b[A-Z][A-Z_0-9]{2,}\(")
    parameters = {
        "action_data": (
            {"command": command, "args": [parse_protocol(a).to_contract() for a in args]}
            if command
            else None
        ),
        "locale": "ru",
        "render": True,
    }
    data = service.solve_request(parse_protocol(source).to_contract(), **parameters)
    leftovers = [text for text in _texts(data) if raw.search(text)]
    assert leftovers == [], source


def _texts(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        explanation = value.get("explanation")
        if isinstance(explanation, dict) and explanation.get("text"):
            yield explanation["text"]
        for child in value.values():
            yield from _texts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _texts(child)
