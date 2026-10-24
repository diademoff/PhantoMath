"""``from_sympy`` and ``to_sympy`` must be inverse: a lost or doubled sign changes the answer."""

from __future__ import annotations

import random

import sympy

from mymath_backend.solver.sympy_bridge import from_sympy, to_sympy

x = sympy.Symbol("x")
_ATOMS = [x, x**2, sympy.sqrt(x), sympy.sin(x), sympy.exp(x), sympy.log(x), sympy.pi, sympy.sqrt(2)]


def _random_expression(rng: random.Random, depth: int = 0) -> sympy.Expr:
    if depth > 2 or rng.random() < 0.3:
        return rng.choice(
            [
                *_ATOMS,
                sympy.Integer(rng.randint(-9, 9)),
                sympy.Rational(rng.randint(-9, 9), rng.randint(1, 7)),
            ]
        )
    left, right = _random_expression(rng, depth + 1), _random_expression(rng, depth + 1)
    return rng.choice(
        [left + right, left - right, left * right, left / (right + 5), -left, left**2 / 3]
    )


def test_from_sympy_round_trips_random_expressions() -> None:
    rng = random.Random(20261018)
    for _ in range(400):
        expression = _random_expression(rng)
        if expression.has(sympy.zoo, sympy.nan) or expression == 0:
            continue
        back = to_sympy(from_sympy(expression))
        for point in (0.7, 1.9, 3.3):
            a = complex(sympy.N(expression.subs(x, point)))
            b = complex(sympy.N(back.subs(x, point)))
            assert abs(a - b) < 1e-8 * (1 + abs(a)), (expression, back)


def test_negative_fractions_keep_exactly_one_minus_sign() -> None:
    assert sympy.simplify(to_sympy(from_sympy(-3 / (x + 1) ** 2)) + 3 / (x + 1) ** 2) == 0
