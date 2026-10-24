"""Random derivatives through both phone and protocol inputs, checked with sympy.diff.

    cd backend && .venv/bin/python ../tools/fuzz/derivatives.py 1

Each case is solved twice: ``{derivation_prime({f})}`` (what the phone sends) and
``{derivation_diff({x},{f})}`` (the parity protocol). Both answers must satisfy
``simplify(ours - sympy.diff(f, x)) == 0``.
"""

import random
import sys

import sympy

from mymath_backend import service
from mymath_backend.input import parse_json, parse_protocol
from mymath_backend.solver.sympy_bridge import to_sympy

random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
x = sympy.Symbol("x")


def poly(degree, low=1, high=5):
    """Protocol text and sympy value of a polynomial of the given degree."""
    terms, value = [], sympy.Integer(0)
    for power in range(degree, -1, -1):
        coefficient = random.randint(-high, high)
        if power == degree and coefficient == 0:
            coefficient = random.choice([-1, 1]) * random.randint(low, high)
        if coefficient == 0:
            continue
        sign = "+" if coefficient > 0 else "-"
        magnitude = abs(coefficient)
        if power == 0:
            body = str(magnitude)
        elif power == 1:
            body = "x" if magnitude == 1 else "%dx" % magnitude
        else:
            body = "x^%d" % power if magnitude == 1 else "%dx^%d" % (magnitude, power)
        terms.append(sign + body)
        value += coefficient * x**power
    text = "".join(terms).lstrip("+") or "0"
    return text, value


def atom():
    """A polynomial, a table function of a polynomial, or a power of one."""
    kind = random.choice(["poly", "poly", "sin", "cos", "exp", "ln", "root", "power"])
    if kind == "poly":
        return poly(random.randint(1, 3))
    inner, value = poly(random.randint(1, 2))
    if kind == "sin":
        return "sin({%s})" % inner, sympy.sin(value)
    if kind == "cos":
        return "cos({%s})" % inner, sympy.cos(value)
    if kind == "exp":
        return "\\e^(%s)" % inner, sympy.exp(value)
    if kind == "ln":
        return "ln({%s})" % inner, sympy.log(value)
    if kind == "root":
        return "root2({%s})" % inner, sympy.sqrt(value)
    degree = random.randint(2, 4)
    return "(%s)^%d" % (inner, degree), value**degree


def expression(depth=0):
    """A random protocol expression and its sympy value (sums, products, quotients)."""
    if depth > 0:
        return atom()
    kind = random.choice(["atom", "sum", "sub", "product", "quotient"])
    if kind == "atom":
        return atom()
    left, a = atom()
    right, b = atom()
    if kind in ("sum", "sub"):
        return (
            "(%s)%s(%s)" % (left, "+" if kind == "sum" else "-", right),
            a + b if kind == "sum" else a - b,
        )
    if kind == "product":
        return "(%s)*(%s)" % (left, right), a * b
    if b == 0:
        return left, a
    return "frac({%s},{%s})" % (left, right), a / b


def request(source):
    return service.solve_request(parse_protocol(source).to_contract(), locale="ru")["result"]


def same(got, want):
    """``simplify(ours − want) == 0``; a trig identity sympy cannot collapse is
    confirmed numerically at generic points (away from its poles)."""
    if sympy.simplify(got - want) == 0:
        return True
    checked = 0
    for point in (0.3, 0.7, 1.4, 2.1, -0.6, -1.9, 3.3, 4.6):
        try:
            difference = complex(sympy.N((got - want).subs(x, point)))
            scale = complex(sympy.N(want.subs(x, point)))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if difference != difference or abs(scale) > 1e12:  # nan/inf
            continue
        checked += 1
        if abs(difference) > 1e-7 * (1 + abs(scale)):
            return False
    return checked >= 3


bad = n = err = 0

for _ in range(80):
    text, value = expression()
    try:
        parse_protocol("{%s}" % text)
    except Exception as problem:  # noqa: BLE001 - a generator miss is not a solver bug
        print("SKIP", text[:60], repr(problem)[:60])
        continue
    want = sympy.diff(value, x)
    for source in (
        "{derivation_prime({%s})}" % text,
        "{derivation_diff({x},{%s})}" % text,
    ):
        n += 1
        try:
            result = request(source)
            solution = result.get("solution")
            if not solution:
                err += 1
                print("NOSOL", source[:80])
                continue
            got = to_sympy(parse_json(solution))
        except Exception as problem:  # noqa: BLE001 - the solver answer is data here
            err += 1
            print("ERR", source[:80], repr(problem)[:100])
            continue
        if same(got, want):
            continue
        bad += 1
        print("BAD", source[:100], "got", got, "want", want)

print("ok", n - bad - err, "bad", bad, "err", err)
