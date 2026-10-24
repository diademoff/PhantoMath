"""Ряды: суммы до бесконечности и сходимость признаком сравнения.

Каждая задача проверяется независимо от решателя: сумму считает ``sympy``,
сходимость — ``Sum.is_convergent`` (для сдвинутого логарифма — сравнение с
``Σ1/(n·ln n)``, которое sympy исследовать не умеет).
"""

from __future__ import annotations

import sympy

from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import solve
from mymath_backend.solver.sympy_bridge import to_sympy

INDEX = sympy.Symbol("n")


def _vertical(source: str, command: str | None = None) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command=command).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical


def _keys(vertical: CoreSolverVerticalResult) -> list[str]:
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


def _answer(vertical: CoreSolverVerticalResult) -> sympy.Expr:
    return sympy.simplify(to_sympy(vertical.solution))


def _converges(vertical: CoreSolverVerticalResult) -> bool:
    value = vertical.solution.children[0].value
    assert value in ("true", "false")
    return value == "true"


SUMS = [
    ("{sigma_def({n},{1},{inf},{frac({2*3^n+4^n},{6^n})})}", 1),
    ("{sigma_def({n},{0},{inf},{frac({8^n-3^(n+1)},{10^n})})}", 0),
    ("{sigma_def({n},{1},{inf},{frac({1},{(2n+1)*(2n+3)})})}", 1),
    ("{sigma_def({n},{1},{inf},{frac({1},{(5n-4)*(5n+1)})})}", 1),
    ("{sigma_def({n},{1},{inf},{frac({6},{9n^2+12n-5})})}", 1),
    ("{sigma_def({n},{2},{inf},{frac({2},{n^2-1})})}", 2),
    ("{sigma_def({n},{3},{inf},{frac({3n-1},{n^3-n})})}", 3),
    ("{sigma_def({n},{1},{inf},{frac({1},{n^3+3n^2+2n})})}", 1),
]

TELESCOPE_KEYS = [
    "series_sigma_telescope_apart",
    "series_sigma_telescope_partial",
    "series_sigma_telescope_limit",
]

GEOMETRIC_KEYS = [
    "series_sigma_inf_split",
    "series_sigma_inf_geom_use",
    "series_sigma_inf_geom_use",
    "calculate_direct",
    "add",
]


def test_geometric_series_are_split_into_progressions() -> None:
    source = "{sigma_def({n},{1},{inf},{frac({2*3^n+4^n},{6^n})})}"
    vertical = _vertical(source)
    assert _answer(vertical) == sympy.Integer(4)
    assert _keys(vertical) == GEOMETRIC_KEYS
    term = (2 * 3**INDEX + 4**INDEX) / 6**INDEX
    assert sympy.summation(term, (INDEX, 1, sympy.oo)) == 4


def test_geometric_series_starting_at_zero() -> None:
    source = "{sigma_def({n},{0},{inf},{frac({8^n-3^(n+1)},{10^n})})}"
    vertical = _vertical(source)
    assert _answer(vertical) == sympy.Rational(5, 7)
    assert _keys(vertical) == GEOMETRIC_KEYS
    term = (8**INDEX - 3 ** (INDEX + 1)) / 10**INDEX
    assert sympy.summation(term, (INDEX, 0, sympy.oo)) == sympy.Rational(5, 7)


def test_telescoping_sums_match_sympy() -> None:
    for source, low in SUMS[2:]:
        vertical = _vertical(source)
        assert _keys(vertical) == TELESCOPE_KEYS
        term = to_sympy(parse_protocol(source).children[3])
        expected = sympy.summation(term, (INDEX, low, sympy.oo))
        assert _answer(vertical) == sympy.simplify(expected)


def test_logarithm_of_a_fraction_telescopes() -> None:
    source = "{sigma_def({n},{2},{inf},{ln({1-frac({1},{n^2})})})}"
    vertical = _vertical(source)
    assert _answer(vertical) == -sympy.log(2)
    assert _keys(vertical) == [
        "series_sigma_log_factor",
        "series_sigma_log_partial",
        "series_sigma_telescope_limit",
    ]
    # Независимая проверка: произведение первых членов стремится к 1/2.
    big = sympy.Symbol("N", positive=True)
    product = sympy.product((INDEX - 1) * (INDEX + 1) / INDEX**2, (INDEX, 2, big))
    assert sympy.limit(sympy.log(sympy.simplify(product)), big, sympy.oo) == -sympy.log(2)


REFERENCE_VERDICTS = {
    "series_pseries_test_converges",
    "series_pseries_test_diverges",
    "series_compare_log_converges",
    "series_compare_log_diverges",
}


def _check_comparison_keys(vertical: CoreSolverVerticalResult, conclusion: str) -> None:
    keys = _keys(vertical)
    assert keys[0] == "series_test_group"
    assert keys[1] == "series_compare_reference"
    assert keys[2] in REFERENCE_VERDICTS
    assert keys[3:5] == ["series_compare_ratio", "limit_solve"]
    assert keys[-1] == conclusion


CONVERGENT = [
    ("{sigma_def({n},{1},{inf},{frac({5n-1},{3n^4+2n^2+7})})}", 1),
    ("{sigma_def({n},{1},{inf},{frac({1},{n^(4/3)+2*ln({n})})})}", 1),
    ("{sigma_def({n},{1},{inf},{frac({5},{n^3+sin({factorial({n})})^2})})}", 1),
    ("{sigma_def({n},{1},{inf},{frac({tan({frac({pi},{4n})})},{n})})}", 1),
    ("{sigma_def({n},{1},{inf},{frac({1},{3n*ln({n+2})^2})})}", 1),
]

DIVERGENT = [
    ("{sigma_def({n},{1},{inf},{frac({1},{n+cos({n})})})}", 1),
    ("{sigma_def({n},{1},{inf},{sin({frac({n},{n^2+1})})})}", 1),
]


def test_convergence_by_comparison_matches_sympy() -> None:
    for source, low in CONVERGENT:
        vertical = _vertical(source, "convergence")
        assert _converges(vertical) is True
        _check_comparison_keys(vertical, "series_limit_test_converges")
        term = to_sympy(parse_protocol(source).children[3])
        assert sympy.Sum(term, (INDEX, low, sympy.oo)).is_convergent() is sympy.true


def test_divergence_by_comparison_matches_sympy() -> None:
    for source, low in DIVERGENT:
        vertical = _vertical(source, "convergence")
        assert _converges(vertical) is False
        _check_comparison_keys(vertical, "series_limit_test_diverges")
        term = to_sympy(parse_protocol(source).children[3])
        assert sympy.Sum(term, (INDEX, low, sympy.oo)).is_convergent() is sympy.false


def test_oscillating_ratio_is_still_a_comparison() -> None:
    source = "{sigma_def({n},{2},{inf},{frac({2+cos({3n+2})},{n-1})})}"
    vertical = _vertical(source, "convergence")
    assert _converges(vertical) is False
    assert _keys(vertical) == [
        "series_test_group",
        "series_compare_reference",
        "series_pseries_test_diverges",
        "series_compare_bounded",
        "series_compare_bounded_diverges",
    ]
    term = (2 + sympy.cos(3 * INDEX + 2)) / (INDEX - 1)
    assert sympy.Sum(term, (INDEX, 2, sympy.oo)).is_convergent() is sympy.false


def test_shifted_logarithm_diverges_like_the_harmonic_logarithmic_series() -> None:
    source = "{sigma_def({n},{2},{inf},{frac({1},{(n-1)*ln({2n+3})})})}"
    vertical = _vertical(source, "convergence")
    assert _converges(vertical) is False
    assert _keys(vertical) == [
        "series_test_group",
        "series_compare_reference",
        "series_compare_log_diverges",
        "series_compare_ratio",
        "limit_solve",
        "series_limit_test_diverges",
    ]
    # Независимая проверка: члены эквивалентны членам расходящегося Σ1/(n·ln n).
    term = 1 / ((INDEX - 1) * sympy.log(2 * INDEX + 3))
    ratio = sympy.limit(term * INDEX * sympy.log(INDEX), INDEX, sympy.oo)
    assert ratio.is_finite is True and ratio > 0
    harmonic_log = sympy.Sum(1 / (INDEX * sympy.log(INDEX)), (INDEX, 2, sympy.oo))
    assert harmonic_log.is_convergent() is sympy.false


def test_shifted_log_square_converges() -> None:
    source = "{sigma_def({n},{1},{inf},{frac({1},{3n*ln({n+2})^2})})}"
    vertical = _vertical(source, "convergence")
    assert _converges(vertical) is True
    assert _keys(vertical) == [
        "series_test_group",
        "series_compare_reference",
        "series_compare_log_converges",
        "series_compare_ratio",
        "limit_solve",
        "series_limit_test_converges",
    ]
    term = to_sympy(parse_protocol(source).children[3])
    assert sympy.Sum(term, (INDEX, 1, sympy.oo)).is_convergent() is sympy.true


def _term(source: str) -> sympy.Expr:
    return to_sympy(parse_protocol(source).children[3])


def _check_verdict(source: str, command: str, expected: bool) -> CoreSolverVerticalResult:
    vertical = _vertical(source, command)
    assert _converges(vertical) is expected
    term = _term(source)
    truth = sympy.Sum(term, (INDEX, sympy.S.Zero, sympy.oo)).is_convergent()
    assert truth is (sympy.true if expected else sympy.false)
    return vertical


def test_limit_comparison_covers_rational_and_radical_terms() -> None:
    cases = [
        ("{sigma_def({n},{1},{inf},{frac({1},{n^2+n+2})})}", True),
        ("{sigma_def({n},{2},{inf},{frac({1},{n^2-n})})}", True),
        ("{sigma_def({n},{1},{inf},{frac({1},{root2({3n+1})})})}", False),
        ("{sigma_def({n},{1},{inf},{frac({root2({n+1})-root2({n-1})},{n})})}", True),
        ("{sigma_def({n},{1},{inf},{root2({n})-root2({n-1})})}", False),
    ]
    for source, expected in cases:
        vertical = _check_verdict(source, "convergence", expected)
        keys = _keys(vertical)
        assert keys[:2] == ["series_test_group", "series_compare_reference"]
        assert keys[3:5] == ["series_compare_ratio", "limit_solve"]
        assert keys[-1] == (
            "series_limit_test_converges" if expected else "series_limit_test_diverges"
        )


def test_logarithm_of_a_term_decides_by_comparison() -> None:
    cases = [
        ("{sigma_def({n},{1},{inf},{ln({1+frac({3},{n^2})})})}", True),
        ("{sigma_def({n},{1},{inf},{ln({1+frac({2},{n})})})}", False),
    ]
    for source, expected in cases:
        vertical = _check_verdict(source, "convergence", expected)
        assert _keys(vertical)[1] == "series_compare_reference"


def test_oscillating_term_is_decided_by_the_root_test() -> None:
    # Предел модуля члена в корне n-й степени ограниченно колеблется:
    # решает верхняя граница, она меньше единицы.
    source = "{sigma_def({n},{1},{inf},{frac({2*sin({frac({n},{3})})^2},{3^n})})}"
    vertical = _check_verdict(source, "convergence", True)
    assert _keys(vertical) == [
        "series_test_group",
        "series_nth_term_test_use",
        "series_nth_term_test_lim_zero",
        "series_root_test",
        "series_root_test_use",
        "series_root_test_lim_ltone",
    ]


def test_nonzero_term_limit_decides_without_a_closed_sum() -> None:
    sources = [
        # arctg(√(3n+2)/√(n+1)) → π/3
        "{sigma_def({n},{1},{inf},{atan({frac({root2({3n+2})},{root2({n+1})})})})}",
        # ((2n−1)/(3n+2) · 3/2)ⁿ → e^(−7/6)
        "{sigma_def({n},{1},{inf},{frac({2n-1},{3n+2})^n*(frac({3},{2}))^n})}",
        # nⁿ·sin(π/2ⁿ)/n! растёт неограниченно
        "{sigma_def({n},{1},{inf},{frac({n^n*sin({frac({pi},{2^n})})},{factorial({n})})})}",
    ]
    for source in sources:
        vertical = _check_verdict(source, "convergence", False)
        assert _keys(vertical) == [
            "series_test_group",
            "series_nth_term_test_use",
            "series_nth_term_test_lim_nozero",
        ]


def test_ratio_test_with_factorials() -> None:
    cases = [
        ("{sigma_def({n},{1},{inf},{frac({factorial({n})^3},{factorial({3n})})})}", True),
        ("{sigma_def({n},{2},{inf},{frac({2^n*factorial({n})},{factorial({n-1})^2})})}", True),
    ]
    for source, expected in cases:
        vertical = _check_verdict(source, "ratio_test", expected)
        assert _keys(vertical)[-1] == "series_ratio_test_lim_ltone"


def test_ratio_test_of_one_falls_back_to_the_term_test() -> None:
    # Отношение членов стремится к 1, признак Даламбера ответа не даёт,
    # но член растёт как √n, поэтому необходимый признак решает.
    source = "{sigma_def({n},{1},{inf},{frac({n^(n+1)},{factorial({n})*\\e^n})})}"
    vertical = _check_verdict(source, "ratio_test", False)
    assert _keys(vertical) == [
        "series_ratio_test",
        "series_ratio_test_use",
        "series_ratio_test_remove_abs",
        "series_ratio_test_lim_one",
        "series_nth_term_test_use",
        "series_nth_term_test_lim_nozero",
    ]


def test_root_test_of_one_falls_back_to_the_term_test() -> None:
    # |n^(1/n)|^(1/n) → 1, а сам член стремится к 1: ряд расходится.
    source = "{sigma_def({n},{1},{inf},{n^(1/n)})}"
    vertical = _check_verdict(source, "root_test", False)
    assert _keys(vertical) == [
        "series_root_test",
        "series_root_test_use",
        "series_root_test_remove_abs",
        "series_root_test_lim_one",
        "series_nth_term_test_use",
        "series_nth_term_test_lim_nozero",
    ]


def test_term_test_reports_no_answer_when_it_cannot_prove_divergence() -> None:
    # Нулевой предел и сходящийся эталон: доказать расходимость нельзя,
    # поэтому честный ответ — «признак ответа не даёт».
    source = "{sigma_def({n},{1},{inf},{frac({1},{n^2})})}"
    vertical = _vertical(source, "nth_term_test")
    assert vertical.solution is not None
    assert vertical.solution.children[0].value == "inconclusive"
    assert _keys(vertical) == [
        "series_nth_term_test",
        "series_nth_term_test_use",
        "series_nth_term_test_lim_zero",
    ]


def test_term_test_continues_with_a_divergent_reference() -> None:
    # Предел члена равен нулю, но члены не меньше 1/n: расходимость доказана.
    cases = [
        (
            "{sigma_def({n},{2},{inf},{frac({1},{ln({n})})})}",
            [
                "series_nth_term_test",
                "series_nth_term_test_use",
                "series_nth_term_test_lim_zero",
                "series_pseries_test_diverges",
                "series_compare_dominates",
                "series_direct_comp_test_diverges",
            ],
        ),
        (
            "{sigma_def({n},{1},{inf},{frac({n-1},{root2({2n^4-n+5})})})}",
            [
                "series_nth_term_test",
                "series_nth_term_test_use",
                "series_nth_term_test_lim_zero",
                "series_compare_reference",
                "series_pseries_test_diverges",
                "series_compare_ratio",
                "limit_solve",
                "series_limit_test_diverges",
            ],
        ),
    ]
    for source, keys in cases:
        vertical = _check_verdict(source, "nth_term_test", False)
        assert _keys(vertical) == keys


def test_slower_than_harmonic_decay_is_decided_by_comparison() -> None:
    # ln n / n^(1/5): показатель 1/5 не попадает на сетку эталонов,
    # но n·aₙ → ∞, поэтому члены больше 1/n.
    sources = [
        "{sigma_def({n},{1},{inf},{frac({ln({n})},{n^(1/5)})})}",
        "{sigma_def({n},{2},{inf},{frac({1},{ln({n})})})}",
    ]
    for source in sources:
        vertical = _check_verdict(source, "convergence", False)
        assert _keys(vertical) == [
            "series_test_group",
            "series_pseries_test_diverges",
            "series_compare_dominates",
            "series_direct_comp_test_diverges",
        ]
