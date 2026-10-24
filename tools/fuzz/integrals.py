"""Random indefinite integrals through the phone protocol, checked with sympy.

    cd backend && .venv/bin/python ../tools/fuzz/integrals.py 1

Each case is a table entry, a table entry with a linear argument, a linear
combination of table entries, or a substitution ``f(g(x))·g'(x)``. The answer
must satisfy ``simplify(diff(ours − C, x) − f) == 0`` (the constant drops out;
``ln|u|`` and ``ln u`` share the derivative).
"""

import random
import sys

import sympy

from mymath_backend import service
from mymath_backend.ast import CoreNode
from mymath_backend.input import parse_json, parse_protocol
from mymath_backend.solver.sympy_bridge import to_sympy

random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
x = sympy.Symbol("x")


def number(low=1, high=4):
    value = random.randint(low, high)
    return random.choice([-1, 1]) * value


def linear():
    """``kx + b`` with a nonzero integer ``k`` and its sympy value."""
    k = random.choice([-4, -3, -2, 2, 3, 4])
    b = random.randint(-3, 3)
    text = "%dx" % k if k > 0 else "%dx" % k
    if b:
        text += "%+d" % b
    return text, k * x + b


def table():
    """One table integrand: ``(text, sympy value, answer may need substitution)``."""
    kind = random.choice(["power", "recip", "exp", "aexp", "sin", "cos", "sec2", "atan", "asin"])
    if kind == "power":
        n = random.randint(2, 5)
        return "x^%d" % n, x**n
    if kind == "recip":
        return "frac({1},{x})", 1 / x
    if kind == "exp":
        return "exp({x})", sympy.exp(x)
    if kind == "aexp":
        base = random.choice([2, 3])
        return "%d^x" % base, base**x
    if kind == "sin":
        return "sin({x})", sympy.sin(x)
    if kind == "cos":
        return "cos({x})", sympy.cos(x)
    if kind == "sec2":
        return "frac({1},{cos({x})^2})", 1 / sympy.cos(x) ** 2
    if kind == "atan":
        return "frac({1},{1+x^2})", 1 / (1 + x**2)
    return "frac({1},{root2({1-x^2})})", 1 / sympy.sqrt(1 - x**2)


def linear_argument():
    """``f(kx+b)`` for a table ``f``: the rule ``F(kx+b)/k`` applies."""
    inner_text, inner = linear()
    kind = random.choice(["sin", "cos", "exp", "recip"])
    if kind == "sin":
        return "sin({%s})" % inner_text, sympy.sin(inner)
    if kind == "cos":
        return "cos({%s})" % inner_text, sympy.cos(inner)
    if kind == "exp":
        return "exp({%s})" % inner_text, sympy.exp(inner)
    return "frac({1},{%s})" % inner_text, 1 / inner


def linearity():
    """A signed sum of table terms."""
    text_terms, value = [], sympy.Integer(0)
    for degree in random.sample([0, 1, 2, 3], random.randint(2, 3)):
        coefficient = number()
        if degree == 0:
            body = ""
            term_value = sympy.Integer(coefficient)
        else:
            body = "x" if degree == 1 else "x^%d" % degree
            term_value = coefficient * x**degree
        sign = "+" if coefficient > 0 else "-"
        magnitude = "" if abs(coefficient) == 1 and degree else str(abs(coefficient))
        text_terms.append("%s%s%s" % (sign, magnitude, body))
        value += term_value
    return "".join(text_terms).lstrip("+"), value


def substitution():
    """``f(g(x))·g'(x)``: the factor ``g'`` is what makes the substitution work."""
    kind = random.choice(["xexp", "sincos", "log", "rational", "root"])
    if kind == "xexp":
        return "x*exp({x^2})", x * sympy.exp(x**2)
    if kind == "sincos":
        return "sin({x})*cos({x})^2", sympy.sin(x) * sympy.cos(x) ** 2
    if kind == "log":
        return "frac({ln({x})},{x})", sympy.log(x) / x
    if kind == "rational":
        c = random.randint(1, 4)
        return "frac({x},{x^2+%d})" % c, x / (x**2 + c)
    return "x*root2({x+1})", x * sympy.sqrt(x + 1)


def new_substitution_family():
    """The INT2 follow-up families: ``f(g(x))·g'(x)`` for four textbook ``g``."""
    choice = random.choice(["ln", "exp", "sin", "cube"])
    if choice == "ln":
        return random.choice(
            [
                ("frac({1},{x*ln({x})})", 1 / (x * sympy.log(x))),
                ("frac({ln({x})^3},{x})", sympy.log(x) ** 3 / x),
            ]
        )
    if choice == "exp":
        return "frac({exp({x})},{1+exp({x})})", sympy.exp(x) / (1 + sympy.exp(x))
    if choice == "sin":
        return "cos({x})*exp({sin({x})})", sympy.cos(x) * sympy.exp(sympy.sin(x))
    return "frac({x^2},{x^3+1})", x**2 / (x**3 + 1)


def poly_text(expression):
    """A polynomial as phone-protocol text (``x^2 - 3*x + 2``)."""
    return str(sympy.expand(expression)).replace("**", "^").replace(" ", "")


def xn_exp():
    """``xⁿ·e^{ax}``: parts, applied as many times as the degree needs."""
    n = random.randint(1, 3)
    a = random.choice([-2, -1, 1, 2])
    argument = "x" if a == 1 else ("-x" if a == -1 else "%dx" % a)
    return "x^%d*exp({%s})" % (n, argument), x**n * sympy.exp(a * x)


def xn_sin():
    """``xⁿ·sin(ax)``: parts with ``u = xⁿ``."""
    n = random.randint(1, 3)
    a = random.choice([1, 2])
    argument = "x" if a == 1 else "%dx" % a
    return "x^%d*sin({%s})" % (n, argument), x**n * sympy.sin(a * x)


def xn_ln():
    """``xⁿ·ln x``: ``u = ln x``, ``dv = xⁿ dx``."""
    n = random.randint(1, 3)
    return "x^%d*ln({x})" % n, x**n * sympy.log(x)


def exp_sin():
    """``e^{ax}·sin(bx)``: the cyclic case, ``2I = …``."""
    a = random.choice([1, 2, -1])
    b = random.choice([1, 2, 3])
    first = "x" if a == 1 else ("-x" if a == -1 else "%dx" % a)
    second = "x" if b == 1 else "%dx" % b
    return (
        "exp({%s})*sin({%s})" % (first, second),
        sympy.exp(a * x) * sympy.sin(b * x),
    )


def partial_distinct():
    """Distinct linear factors: ``P/((x−a)(x−b))``."""
    roots = random.sample([-3, -2, -1, 1, 2, 3, 4], random.choice([2, 3]))
    denominator = sympy.prod(x - root for root in roots)
    degree = len(roots) - 1
    numerator = sum(number() * x**power for power in range(degree + 1))
    return (
        "frac({%s},{%s})" % (poly_text(numerator), poly_text(denominator)),
        numerator / denominator,
    )


def partial_repeated():
    """A repeated linear factor: ``P/(x(x+a)²)`` or ``P/((x−a)²(x−b))``."""
    first = random.choice([-3, -2, -1, 1, 2, 3])
    second = random.choice([root for root in [-3, -2, -1, 1, 2, 3] if root != first])
    if random.random() < 0.5:
        denominator = x * (x - first) ** 2
    else:
        denominator = (x - first) ** 2 * (x - second)
    numerator = number() * x**2 + number() * x + number()
    return (
        "frac({%s},{%s})" % (poly_text(numerator), poly_text(denominator)),
        numerator / denominator,
    )


def partial_quadratic():
    """An irreducible quadratic: ``(Ax+B)/(x²+bx+c)`` with ``b²−4c < 0``."""
    b = random.choice([-3, -2, -1, 0, 1, 2, 3])
    c = random.randint(b * b // 4 + 1, b * b // 4 + 5)
    denominator = x**2 + b * x + c
    numerator = random.choice([1, -1, 2]) * x + random.randint(-3, 3)
    return (
        "frac({%s},{%s})" % (poly_text(numerator), poly_text(denominator)),
        numerator / denominator,
    )


def request(source):
    return service.solve_request(parse_protocol(source).to_contract(), locale="ru")["result"]


def stray_abs(node, parent=None):
    """An ``ABS`` node that is not the argument of ``LN`` (a split must not add |·|)."""
    if not isinstance(node, dict):
        return False
    kind = node.get("type")
    if kind == "ABS" and parent != "LN":
        return True
    return any(stray_abs(child, kind) for child in node.get("children") or [])


def screen_problems(card):
    """No repeated formula, no repeated heading, no text arg echoing the formula."""
    problems = []
    previous = None
    previous_header = None
    for step in card.get("steps") or []:
        header = tuple(item.get("type") for item in step.get("headers") or [])
        if previous_header is not None and header == previous_header:
            # One step per card: a column of identical «Вычислите интеграл» rows.
            problems.append(("HEADER", header))
        previous_header = header
        for sub in step.get("substeps") or []:
            description = sub.get("description") or {}
            key = description.get("type")
            left, right = sub.get("left"), sub.get("right")
            # |·| belongs to ln|·| only: a stage formula never wraps a piece in ABS.
            if stray_abs(left) or stray_abs(right):
                problems.append(("ABS", key))
            for arg in description.get("args") or []:
                if stray_abs(arg):
                    problems.append(("ABS-ARG", key))
                arg_node = CoreNode.from_contract(arg)
                if left is not None and arg_node.structural_eq(CoreNode.from_contract(left)):
                    problems.append(("ARG-LEFT", key))
                if right is not None and arg_node.structural_eq(CoreNode.from_contract(right)):
                    problems.append(("ARG-RIGHT", key))
            if left is not None and right is not None:
                left_node = CoreNode.from_contract(left)
                if left_node.structural_eq(CoreNode.from_contract(right)):
                    problems.append(("SAME", key))
                if previous is not None and not CoreNode.from_contract(previous).structural_eq(
                    left_node
                ):
                    problems.append(("CHAIN", key))
                previous = right
            nested = sub.get("subresult")
            if isinstance(nested, dict):
                problems.extend(screen_problems(nested))
    return problems


def card_problems(result):
    """Check the lesson card (the verified card keeps its own rows)."""
    entries = (result.get("groups") or [{}])[0].get("entries") or []
    if not entries:
        return []
    card = entries[0].get("result") or {}
    header = str((card.get("header") or {}).get("type") or "")
    if not header.startswith("lesson_calc_header_int"):
        return []
    return screen_problems(card)


def definite_limits(value):
    """Random integer limits on which ``value`` is continuous."""
    from sympy.calculus.util import continuous_domain

    for _ in range(12):
        lower = random.randint(-3, 2)
        upper = lower + random.randint(1, 3)
        interval = sympy.Interval(lower, upper)
        try:
            domain = continuous_domain(value, x, interval)
        except (TypeError, ValueError, NotImplementedError):
            continue
        if domain == interval:
            return lower, upper
    return None


def same(got, want):
    """``simplify(ours − want) == 0``; fall back to generic real points."""
    if sympy.simplify(got - want) == 0:
        return True
    checked = 0
    for point in (0.3, 0.7, 1.4, 2.1, 3.3, -0.6, -1.9, -2.4):
        try:
            difference = complex(sympy.N((got - want).subs(x, point)))
            scale = complex(sympy.N(want.subs(x, point)))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if difference != difference or abs(scale) > 1e12:
            continue
        checked += 1
        if abs(difference) > 1e-7 * (1 + abs(scale)):
            return False
    return checked >= 3


def antiderivative(solution):
    """The answer without ``+ C`` and without ``|·|`` (same derivative)."""
    node = parse_json(solution)
    if node.type.value == "LIST":
        node = node.children[0]
        if node.type.value == "ADD" and len(node.children) == 2:
            first, second = node.children
            node = first if second.value == "C" else second if first.value == "C" else node
    value = sympy.sympify(to_sympy(node))
    return value - sympy.Symbol("C") if value.has(sympy.Symbol("C")) else value


def stray_constant(solution):
    """A free numeric addend before ``+ C``: the arbitrary constant already covers it."""
    node = parse_json(solution)
    if node.type.value == "LIST":
        node = node.children[0]
    terms = []

    def collect(item):
        if item.type.value in ("ADD", "SUBTRACT") and item.children:
            for child in item.children:
                collect(child)
        else:
            terms.append(item)

    collect(node)
    for term in terms:
        if term.type.value == "CONSTANT" and term.value != "C":
            return term.value
        if term.type.value == "NEGATIVE" and term.children:
            inner = term.children[0]
            if inner.type.value == "CONSTANT":
                return "-" + str(inner.value)
    return None


def book_kind(result):
    """``textbook`` for our lesson card, ``legacy`` for the verified card."""
    entries = (result.get("groups") or [{}])[0].get("entries") or []
    if not entries:
        return "legacy"
    header = (entries[0].get("result") or {}).get("header") or {}
    return (
        "textbook"
        if str(header.get("type") or "").startswith("lesson_calc_header_int")
        else "legacy"
    )


bad = n = err = 0
textbook = legacy = 0
substitution_legacy = 0

CASES = [
    (table, False),
    (table, False),
    (linear_argument, False),
    (linearity, False),
    (substitution, True),
    (new_substitution_family, True),
    (xn_exp, False),
    (xn_sin, False),
    (xn_ln, False),
    (exp_sin, False),
    (partial_distinct, False),
    (partial_repeated, False),
    (partial_quadratic, False),
]

for _ in range(4):
    for generator, expect_substitution in CASES:
        text, value = generator()
        source = "{integral({%s})}" % text
        try:
            parse_protocol(source)
        except Exception as problem:  # noqa: BLE001 - a generator miss is not a solver bug
            print("SKIP", source[:70], repr(problem)[:60])
            continue
        n += 1
        try:
            result = request(source)
            solution = result.get("solution")
            if not solution:
                err += 1
                print("NOSOL", source[:80])
                continue
            kind = book_kind(result)
            if kind == "textbook":
                textbook += 1
            else:
                legacy += 1
                if expect_substitution:
                    substitution_legacy += 1
                    print("LEGACY-SUB", source[:100])
            problems = card_problems(result)
            if problems:
                bad += 1
                print("CARD", source[:100], problems[:3])
                continue
            stray = stray_constant(solution)
            if stray is not None:
                bad += 1
                print("STRAY", source[:100], "constant", stray)
                continue
            got = antiderivative(solution)
        except Exception as problem:  # noqa: BLE001 - the solver answer is data here
            err += 1
            print("ERR", source[:80], repr(problem)[:100])
            continue
        got = got.replace(lambda node: isinstance(node, sympy.Abs), lambda node: node.args[0])
        want = value.replace(lambda node: isinstance(node, sympy.Abs), lambda node: node.args[0])
        real = {symbol: sympy.Symbol(str(symbol), real=True) for symbol in got.free_symbols}
        real |= {x: sympy.Symbol("x", real=True)}
        if same(sympy.diff(got.subs(real), sympy.Symbol("x", real=True)), want.subs(real)):
            continue
        bad += 1
        print("BAD", source[:100], "got", got, "want", value)

# Definite integrals: a textbook integrand on continuous integer limits.
for _ in range(4):
    for generator in (table, linearity, linear_argument, substitution):
        text, value = generator()
        limits = definite_limits(value)
        if limits is None:
            continue
        lower, upper = limits
        source = "{integral_def({%d},{%d},{%s})}" % (lower, upper, text)
        try:
            parse_protocol(source)
        except Exception as problem:  # noqa: BLE001 - a generator miss is not a solver bug
            print("SKIP", source[:70], repr(problem)[:60])
            continue
        n += 1
        try:
            result = request(source)
            solution = result.get("solution")
            if not solution:
                err += 1
                print("NOSOL", source[:80])
                continue
            kind = book_kind(result)
            if kind == "textbook":
                textbook += 1
            else:
                legacy += 1
            problems = card_problems(result)
            if problems:
                bad += 1
                print("CARD", source[:100], problems[:3])
                continue
            got = sympy.sympify(to_sympy(parse_json(solution)))
            want = sympy.integrate(value, (x, lower, upper))
        except Exception as problem:  # noqa: BLE001 - the solver answer is data here
            err += 1
            print("ERR", source[:80], repr(problem)[:100])
            continue
        if want.has(sympy.Integral) or want in (sympy.oo, -sympy.oo, sympy.zoo, sympy.nan):
            n -= 1  # a divergent case is not part of this family
            continue
        if same(got, want):
            continue
        bad += 1
        print("BAD", source[:100], "got", got, "want", want)

print(
    "ok",
    n - bad - err,
    "bad",
    bad,
    "err",
    err,
    "textbook",
    textbook,
    "legacy",
    legacy,
    "substitution-legacy",
    substitution_legacy,
)
if bad or err or substitution_legacy:
    raise SystemExit(1)
