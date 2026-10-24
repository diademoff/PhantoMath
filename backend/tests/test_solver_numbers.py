"""Тесты числовых утилит (R5): gcd/lcm/mod, простые множители, округление до разряда."""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def run(source: str, command: str, args: list[str] | None = None) -> tuple[list[str], CoreNode]:
    vertical = solve(
        parse_protocol(source),
        command=command,
        args=[parse_protocol(arg) for arg in args or []],
    ).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestGcdLcmMod:
    def test_gcd(self) -> None:
        keys, solution = run("{gcd({12},{18})}", "gcd")
        assert keys == ["calculate_short"]
        assert solution.value == "6"

    def test_lcm(self) -> None:
        assert run("{lcm({4},{6})}", "lcm")[1].value == "12"

    def test_mod(self) -> None:
        assert run("{mod({7},{3})}", "mod")[1].value == "1"

    def test_mod_zero(self) -> None:
        with pytest.raises(SolveError):
            run("{mod({7},{0})}", "mod")


class TestPrimeFactorization:
    def test_composite(self) -> None:
        keys, solution = run("{360}", "prime_factorization")
        assert keys == ["factorise_call"]
        assert solution.type is T.MULTIPLY

    def test_prime(self) -> None:
        assert run("{17}", "prime_factorization")[1].value == "17"

    def test_one(self) -> None:
        with pytest.raises(SolveError):
            run("{1}", "prime_factorization")


class TestRoundPlace:
    def test_tens(self) -> None:
        keys, solution = run("{1234}", "round_place", ["{1}"])
        assert keys == ["round"]
        assert solution.value == "1230"

    def test_hundreds(self) -> None:
        assert run("{1234}", "round_place", ["{2}"])[1].value == "1200"
