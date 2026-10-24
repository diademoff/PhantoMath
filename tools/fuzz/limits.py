import random, sys, sympy
from mymath_backend import service
from mymath_backend.input import parse_json, parse_protocol
from mymath_backend.solver.sympy_bridge import to_sympy

random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
x = sympy.Symbol("x")


def poly(degree, low=1, high=5):
    """A polynomial of the given degree with a nonzero leading coefficient."""
    coeffs = [random.randint(-high, high) for _ in range(degree + 1)]
    coeffs[-1] = random.choice([-1, 1]) * random.randint(low, high)
    return sum(c * x**i for i, c in enumerate(coeffs))


def src(expression):
    """Protocol text for a sympy expression (``**`` is not in the protocol)."""
    return sympy.sstr(sympy.expand(expression)).replace("**", "^")


def request(source):
    return service.solve_request(parse_protocol(source).to_contract(), locale="ru")["result"]


bad = n = err = 0

def equivalents_ratio():
    """A 0/0 ratio of equivalent infinitesimals and its value."""
    kind = random.choice(["tan_sin", "sin_linear", "x_sin", "sin_square", "exp_linear"])
    if kind == "tan_sin":
        k, m = random.randint(1, 5), random.randint(1, 5)
        return (
            "{lim({0},{frac({tan({%dx})},{sin({%dx})})})}" % (k, m),
            sympy.Rational(k, m),
        )
    if kind == "sin_linear":
        k, m = random.randint(1, 5), random.randint(2, 6)
        return (
            "{lim({0},{frac({sin({%dx})},{%dx})})}" % (k, m),
            sympy.Rational(k, m),
        )
    if kind == "x_sin":
        k = random.randint(1, 5)
        return (
            "{lim({0},{frac({%dx},{sin({%dx})})})}" % (k, k),
            sympy.Integer(1),
        )
    if kind == "sin_square":
        return "{lim({0},{frac({sin({x^2})},{x})})}", sympy.Integer(0)
    a = random.randint(1, 4)
    return (
        "{lim({0},{frac({\\e^(%dx)-1},{x})})}" % a,
        sympy.Integer(a),
    )


for _ in range(120):
    kind = random.choice(["00", "00", "inf", "inf", "sin", "sin", "second", "equiv", "equiv"])
    try:
        if kind == "00":
            a = random.randint(-3, 3)
            top = (x - a) * poly(random.randint(0, 2))
            bottom = (x - a) * poly(random.randint(0, 2))
            if sympy.simplify(top) == 0 or sympy.simplify(bottom) == 0:
                continue
            reduced = sympy.cancel(top / bottom)
            if sympy.fraction(reduced)[1].subs(x, a) == 0:
                continue  # the reduced limit diverges: not a finite 0/0 case
            source = "{lim({%d},{frac({%s},{%s})})}" % (a, src(top), src(bottom))
            want = sympy.limit(top / bottom, x, a)
        elif kind == "inf":
            top = poly(random.randint(1, 3))
            bottom = poly(random.randint(1, 3))
            source = "{lim({inf},{frac({%s},{%s})})}" % (src(top), src(bottom))
            want = sympy.limit(top / bottom, x, sympy.oo)
        elif kind == "sin":
            k, m = random.randint(1, 5), random.randint(1, 5)
            argument = "x" if k == 1 else "%dx" % k
            denominator = "x" if m == 1 else "%dx" % m
            source = "{lim({0},{frac({sin({%s})},{%s})})}" % (argument, denominator)
            want = sympy.Rational(k, m)
        elif kind == "equiv":
            source, want = equivalents_ratio()
        else:
            a, b = random.randint(1, 4), random.randint(1, 4)
            exponent = "x" if b == 1 else "%dx" % b
            source = "{lim({inf},{(1+frac({%d},{x}))^(%s)})}" % (a, exponent)
            want = sympy.exp(a * b)
    except Exception as problem:  # noqa: BLE001 - a generator miss is not a solver bug
        print("SKIP", kind, repr(problem)[:80])
        continue

    n += 1
    try:
        result = request(source)
        solution = result.get("solution")
        if not solution:
            err += 1
            print("NOSOL", source)
            continue
        got = to_sympy(parse_json(solution))
    except Exception as problem:  # noqa: BLE001 - the solver answer is data here
        err += 1
        print("ERR", source, repr(problem)[:100])
        continue

    if want in (sympy.oo, -sympy.oo):
        ok = got == want
    else:
        ok = sympy.simplify(got - want) == 0
    if ok:
        pass
    else:
        bad += 1
        print("BAD", source, "got", got, "want", want)

print("ok", n - bad - err, "bad", bad, "err", err)
