"""Random textbook ODEs through the phone protocol, checked with sympy.

    backend/.venv/bin/python tools/fuzz/odes.py SEED

Families: separable, first-order linear, Bernoulli, constant-coefficient
homogeneous (distinct, double, complex roots), a special right side with and
without resonance, and Cauchy problems typed as a system (one condition for a
first-order equation, two for a second-order one).

Each answer must satisfy ``sympy.checkodesol`` on the equation built from the
same protocol (``y`` becomes ``y(x)`` on both sides), carry as many free
constants as the order allows, and be found in under five seconds. A Cauchy
answer must have no constants and satisfy every condition.
"""

import random
import subprocess
import sys
import time

import sympy

from mymath_backend import service
from mymath_backend.ast import CoreNode
from mymath_backend.input import parse_protocol
from mymath_backend.node_types import CoreNodeType as T
from mymath_backend.solver.sympy_bridge import to_sympy

if len(sys.argv) > 2:
    # ``odes.py 1 2 3`` runs each seed as its own process, like three invocations.
    raise SystemExit(
        max(subprocess.call([sys.executable, __file__, seed]) for seed in sys.argv[1:])
    )

random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)

X = sympy.Symbol("x")
Y = sympy.Function("y")
DERIVATIVES = (T.PRIME, T.DERIVATION1, T.DERIVATION1_PRIME, T.DERIVATION2_PRIME)


def number(low=-3, high=3, skip=(0,)):
    values = [value for value in range(low, high + 1) if value not in skip]
    return random.choice(values)


def text_number(value):
    return str(value)


def linear_text(coefficient, body):
    """``coefficient*body`` in protocol text (``1*x`` stays readable)."""
    if coefficient == 1:
        return body
    if coefficient == -1:
        return f"-{body}"
    return f"{coefficient}*{body}"


def first_order_text(coefficient, body, rhs):
    """``y′ + coefficient·body = rhs`` (body is ``y`` or a function of it)."""
    if coefficient == 0:
        left = "prime({y})"
    elif coefficient > 0:
        left = f"prime({{y}})+{linear_text(coefficient, body)}"
    else:
        left = f"prime({{y}})-{linear_text(-coefficient, body)}"
    return "{=({" + left + "},{" + rhs + "})}"


def second_order_text(a, b, c, rhs):
    """``y″ + a·y′ + b·y = rhs``."""
    terms = ["derivation2_prime({y})"]
    if a:
        terms.append(("+" if a > 0 else "-") + linear_text(abs(a), "prime({y})"))
    if b:
        terms.append(("+" if b > 0 else "-") + linear_text(abs(b), "y"))
    return "{=({" + "".join(terms) + "},{" + rhs + "})}"


def polynomial_text(coefficients):
    """``c0 + c1·x + …`` in protocol text."""
    parts = []
    for degree, coefficient in enumerate(coefficients):
        if not coefficient:
            continue
        body = "1" if degree == 0 else ("x" if degree == 1 else f"x^{degree}")
        term = linear_text(coefficient, body)
        parts.append(term if not parts else ("+" if coefficient > 0 else "") + term)
    return "".join(parts) if parts else "0"


def separable():
    kind = random.choice(["xy", "y", "x2y", "cos", "xy2", "ratio"])
    a = number(-3, 3)
    if kind == "xy":
        return "{=({prime({y})},{" + linear_text(a, "x*y") + "})}", a * X * Y(X)
    if kind == "y":
        return "{=({prime({y})},{" + linear_text(a, "y") + "})}", a * Y(X)
    if kind == "x2y":
        return "{=({prime({y})},{" + linear_text(a, "x^2*y") + "})}", a * X**2 * Y(X)
    if kind == "cos":
        return (
            "{=({prime({y})},{" + linear_text(a, "cos({x})*y") + "})}",
            a * sympy.cos(X) * Y(X),
        )
    if kind == "xy2":
        return "{=({prime({y})},{" + linear_text(a, "x*y^2") + "})}", a * X * Y(X) ** 2
    return (
        "{=({prime({y})},{" + linear_text(a, "frac({y},{x})") + "})}",
        a * Y(X) / X,
    )


def linear_first_order():
    kind = random.choice(["constant", "exp", "power", "tan"])
    a = number(-3, 3)
    b = number(-3, 3)
    if kind == "constant":
        c = random.randint(-3, 3)
        return first_order_text(a, "y", polynomial_text([c, b]))
    if kind == "exp":
        k = number(-2, 2)
        return first_order_text(a, "y", linear_text(b, f"exp({{{k}*x}})"))
    if kind == "power":
        return first_order_text(a, "frac({y},{x})", linear_text(b, "x^3"))
    return first_order_text(1, "y*tan({x})", linear_text(b, "cos({x})"))


def bernoulli():
    kind = random.choice(["xy2", "yx2", "cube"])
    a = number(-3, 3)
    b = number(-3, 3)
    if kind == "xy2":
        return first_order_text(a, "y", linear_text(b, "x*y^2"))
    if kind == "yx2":
        return first_order_text(a, "frac({y},{x})", linear_text(b, "y^2"))
    return first_order_text(a, "y", linear_text(b, "y^3"))


def constant_homogeneous():
    kind = random.choice(["distinct", "double", "complex"])
    if kind == "distinct":
        first = number(-3, 3)
        second = number(-3, 3, skip=(first,))
        return second_order_text(0, -(first + second), first * second, "0")
    if kind == "double":
        root = number(-3, 3)
        return second_order_text(0, -2 * root, root**2, "0")
    real = number(-2, 2)
    imaginary = random.choice([1, 2, 3])
    return second_order_text(0, -2 * real, real**2 + imaginary**2, "0")


def special_right_side():
    kind = random.choice(["exp", "exp_resonance", "polynomial", "trig", "trig_resonance"])
    if kind in ("exp", "exp_resonance"):
        first = number(-2, 2)
        second = number(-2, 2, skip=(first,))
        roots = (first, second)
        k = random.choice(roots) if kind == "exp_resonance" else number(-3, 3, skip=roots)
        return second_order_text(0, -(first + second), first * second, f"exp({{{k}*x}})")
    if kind == "polynomial":
        return second_order_text(0, number(-3, 3), number(-3, 3), polynomial_text([1, -2]))
    if kind == "trig":
        return second_order_text(0, 0, 4, "cos({3*x})")
    return second_order_text(0, 0, 4, "cos({2*x})")


def cauchy():
    order = random.choice([1, 2])
    x_zero = random.randint(-2, 2)
    y_zero = random.randint(-3, 3)
    if order == 1:
        equation = first_order_text(number(-3, 3), "y", "x")
        condition = "{=({muli({y},{(%d)})},{%d})}" % (x_zero, y_zero)
        return f"{{system({equation},{condition})}}", 1
    equation = second_order_text(0, number(-3, 3), number(-3, 3), "0")
    first = "{=({muli({y},{(%d)})},{%d})}" % (x_zero, y_zero)
    second = "{=({muli({prime({y})},{(%d)})},{%d})}" % (
        x_zero,
        random.randint(-3, 3),
    )
    return f"{{system({equation},{first},{second})}}", 2


def subs_function(node, dep, ind):
    if node.type is T.VARIABLE and node.value == dep:
        return CoreNode(type=T.FUNCTION, value=dep, children=[CoreNode.variable(ind)])
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[subs_function(child, dep, ind) for child in node.children],
    )


def order_of(node):
    if node.type is T.DERIVATION2_PRIME:
        order = 2
    elif node.type in (T.PRIME, T.DERIVATION1, T.DERIVATION1_PRIME):
        order = 1
    else:
        return None
    if node.children:
        nested = order_of(node.children[0])
        if nested is not None:
            order += nested
    return order


def dependent(node):
    current = node
    while current.type in DERIVATIVES and current.children:
        current = current.children[0]
    return current.value if current.type in (T.VARIABLE, T.FUNCTION) else None


def problem(source):
    parsed = parse_protocol(source)
    conditions = []
    if parsed.type is T.SYSTEM:
        rows = list(parsed.children)
        equation_row = next(
            row
            for row in rows
            if any(node.type in DERIVATIVES for node in row.walk())
            and row.children[0].type is not T.MULTIPLY_IMPLICIT
        )
        for row in rows:
            if row is equation_row:
                continue
            lhs = row.children[0]
            part = lhs.children[0]
            point = lhs.children[1]
            if point.type is T.BRACKET:
                point = point.children[0]
            conditions.append(
                (0 if part.type is T.VARIABLE else order_of(part), to_sympy(point), to_sympy(row.children[1]))
            )
        parsed = equation_row
    derivatives = [node for node in parsed.walk() if node.type in DERIVATIVES]
    dep = next(name for name in (dependent(node) for node in derivatives) if name)
    order = max(value for value in (order_of(node) for node in derivatives) if value is not None)
    variables = [
        node.value
        for node in parsed.walk()
        if node.type is T.VARIABLE and node.value
    ]
    ind = next((name for name in variables if name != dep), "x")
    left = to_sympy(subs_function(parsed.children[0], dep, ind))
    right = to_sympy(subs_function(parsed.children[1], dep, ind))
    return sympy.Eq(sympy.together(left - right), 0), dep, order, ind, conditions


def answer_equations(solution, dep, ind):
    xsym = sympy.Symbol(ind)
    yfun = sympy.Function(dep)
    parts = solution.children if solution.type is T.LIST else [solution]
    for part in parts:
        value = to_sympy(part)
        yield sympy.Eq(
            value.lhs.subs(sympy.Symbol(dep), yfun(xsym)),
            value.rhs.subs(sympy.Symbol(dep), yfun(xsym)),
        )


def card_problems(result):
    """The card rules of the teaching steps, as readable problems.

    A fact stage has only ``left``; a transformation has ``left → right`` and
    consecutive transformations chain (``right(k) == left(k+1)``); no stage
    repeats itself; no text argument repeats the stage formula; two consecutive
    steps never carry the same heading.
    """
    problems = []
    for group in result.get("groups") or []:
        for entry in group.get("entries") or []:
            payload = entry.get("result") or {}
            previous_heading = None
            for step in payload.get("steps") or []:
                heading = tuple(header.get("type") for header in step.get("headers") or [])
                if heading and heading == previous_heading:
                    problems.append(f"two steps with the heading {heading}")
                previous_heading = heading
                problems.extend(stage_problems(step, "step"))
    return problems


def stage_problems(step, where):
    problems = []
    last_right = None
    for index, sub in enumerate(step.get("substeps") or []):
        left = sub.get("left")
        right = sub.get("right")
        tag = f"{where}[{index}] {((sub.get('description') or {}).get('type'))}"
        if left is None:
            continue
        left_node = CoreNode.from_contract(left)
        right_node = CoreNode.from_contract(right) if right is not None else None
        if right_node is None:
            last_right = None
        else:
            if left_node.structural_eq(right_node):
                problems.append(f"{tag}: left == right")
            if last_right is not None and not last_right.structural_eq(left_node):
                problems.append(f"{tag}: chain broken")
            last_right = right_node
        for argument in (sub.get("description") or {}).get("args") or []:
            argument_node = CoreNode.from_contract(argument)
            if argument_node.structural_eq(left_node):
                problems.append(f"{tag}: text repeats left")
            if right_node is not None and argument_node.structural_eq(right_node):
                problems.append(f"{tag}: text repeats right")
        nested = sub.get("subresult")
        if isinstance(nested, dict):
            for inner_index, inner in enumerate(nested.get("steps") or []):
                problems.extend(stage_problems(inner, f"{tag}.detail[{inner_index}]"))
    return problems


SECOND_ORDER_HEADERS = {
    "lesson_calc_ode_header_reduction",
    "lesson_calc_ode_header_constant",
    "lesson_calc_ode_header_special",
}
_CASE_KEYS = {
    "lesson_calc_ode_char_case_distinct",
    "lesson_calc_ode_char_case_double",
    "lesson_calc_ode_char_case_complex",
}
_STEP_HOMOGENEOUS = "lesson_calc_ode_step_homogeneous"
_STEP_PARTICULAR = "lesson_calc_ode_step_particular"
_STEP_GENERAL = "lesson_calc_ode_step_general"
_STEP_CONDITIONS = "lesson_calc_ode_step_conditions"


def second_order_problems(result, order, conditions):
    """The second-order card must name its method and keep the method stages."""
    if order != 2:
        return []
    problems = []
    cards = [
        entry
        for group in result.get("groups") or []
        for entry in group.get("entries") or []
    ]
    for entry in cards:
        payload = entry.get("result") or {}
        header = (payload.get("header") or {}).get("type")
        if header not in SECOND_ORDER_HEADERS:
            problems.append(f"second order: header {header}")
        steps = payload.get("steps") or []
        headings = [
            tuple(header.get("type") for header in step.get("headers") or [])
            for step in steps
        ]
        keys = [
            [
                (sub.get("description") or {}).get("type")
                for sub in step.get("substeps") or []
            ]
            for step in steps
        ]
        flat = [key for row in keys for key in row]
        for step in steps:
            for sub in step.get("substeps") or []:
                description = sub.get("description") or {}
                key = description.get("type")
                arguments = description.get("args") or []
                if key == "lesson_calc_ode_special_form_exp_resonance":
                    if len(arguments) != 3:
                        problems.append("second order: resonance arguments")
                    left = sub.get("left")
                    if left is None:
                        problems.append("second order: resonance has no form")
                    else:
                        form = CoreNode.from_contract(left)
                        if not any(
                            node.type is T.VARIABLE and node.value == "x"
                            for node in form.walk()
                        ):
                            problems.append("second order: resonance multiplier missing")
                elif key == "lesson_calc_ode_special_form_trig_resonance":
                    if len(arguments) != 1:
                        problems.append("second order: trig resonance arguments")
                    left = sub.get("left")
                    if left is None or not any(
                        node.type is T.VARIABLE and node.value == "x"
                        for node in CoreNode.from_contract(left).walk()
                    ):
                        problems.append("second order: trig multiplier missing")
                elif key == "lesson_calc_ode_special_form_poly_resonance":
                    if len(arguments) != 2:
                        problems.append("second order: polynomial resonance arguments")
                    left = sub.get("left")
                    if left is None or not any(
                        node.type is T.VARIABLE and node.value == "x"
                        for node in CoreNode.from_contract(left).walk()
                    ):
                        problems.append("second order: polynomial multiplier missing")
        if "diff_eq_write_general_sol" in flat:
            problems.append("second order: fell back to the short answer")
        step_headings = [heading[0] for heading in headings if heading]
        if _STEP_HOMOGENEOUS in step_headings:
            if step_headings[:3] != [
                _STEP_HOMOGENEOUS,
                _STEP_PARTICULAR,
                _STEP_GENERAL,
            ]:
                problems.append(f"second order: special steps {headings}")
            if not any(key and key.startswith("lesson_calc_ode_char_") for key in flat):
                problems.append("second order: no characteristic equation")
            if not _CASE_KEYS & set(flat):
                problems.append("second order: the root case is not named")
            if "lesson_calc_ode_special_substitute" not in flat:
                problems.append("second order: no substitution")
            if "lesson_calc_ode_special_particular" not in flat:
                problems.append("second order: no particular solution")
        elif "lesson_calc_ode_char_equation" in flat:
            if not _CASE_KEYS & set(flat):
                problems.append("second order: the root case is not named")
            if "lesson_calc_ode_char_general" not in flat:
                problems.append("second order: no general solution stage")
        elif "lesson_calc_ode_reduce_first" in flat:
            after = flat[flat.index("lesson_calc_ode_reduce_first") + 1 :]
            if after[:1] != ["lesson_calc_ode_reduce_second"]:
                problems.append("second order: the second integration is missing")
        elif "lesson_calc_ode_reduce_equation" in flat:
            if "lesson_calc_ode_reduce_integrate" not in flat:
                problems.append("second order: no return to y")
        if conditions:
            if not headings or headings[-1] != (_STEP_CONDITIONS,):
                problems.append(f"second order: Cauchy heading {headings[-1:]}")
            elif keys[-1] != [
                "lesson_calc_ode_conditions_system",
                "lesson_calc_ode_conditions_values",
                "lesson_calc_ode_conditions_answer",
            ]:
                problems.append(f"second order: Cauchy stages {keys[-1]}")
    return problems


ok = bad = errors = 0
for _ in range(120):
    source, order = random.choice(
        [
            lambda: (separable()[0], 1),
            lambda: (separable()[0], 1),
            lambda: (linear_first_order(), 1),
            lambda: (bernoulli(), 1),
            lambda: (constant_homogeneous(), 2),
            lambda: (special_right_side(), 2),
            cauchy,
        ]
    )()
    started = time.perf_counter()
    try:
        result = service.solve_request(parse_protocol(source).to_contract(), locale="ru")[
            "result"
        ]
        solution = result.get("solution")
        if not solution:
            raise AssertionError("нет ответа")
        elapsed = time.perf_counter() - started
        if elapsed >= 5:
            raise AssertionError(f"медленно: {elapsed:.1f} с")
        equation, dep, actual_order, ind, conditions = problem(source)
        if actual_order != order:
            raise AssertionError(f"порядок {actual_order}, ожидался {order}")
        node = CoreNode.from_contract(solution)
        for answer in answer_equations(node, dep, ind):
            checked = sympy.checkodesol(equation, answer, solve_for_func=False)
            if not checked[0]:
                positive = sympy.Symbol(ind, positive=True)
                checked = sympy.checkodesol(
                    equation.subs(sympy.Symbol(ind), positive),
                    answer.subs(sympy.Symbol(ind), positive),
                    solve_for_func=False,
                )
            if not checked[0]:
                raise AssertionError("not a solution")
            constants = {
                symbol.name
                for symbol in answer.free_symbols
                if isinstance(symbol, sympy.Symbol) and symbol.name.startswith("C")
            }
            expected = 0 if conditions else order
            if len(constants) != expected:
                raise AssertionError(f"постоянных {len(constants)}, ожидалось {expected}")
        if conditions:
            value = next(answer_equations(node, dep, ind))
            xsym = sympy.Symbol(ind)
            for derivative_order, x_zero, expected in conditions:
                derived = value.rhs
                if derivative_order:
                    derived = sympy.diff(derived, xsym, derivative_order)
                if sympy.simplify(derived.subs(xsym, x_zero) - expected) != 0:
                    raise AssertionError("условие не выполняется")
        problems = card_problems(result)
        problems.extend(second_order_problems(result, order, conditions))
        if problems:
            raise AssertionError("; ".join(problems[:3]))
        ok += 1
    except AssertionError as error:
        bad += 1
        print("BAD", source, repr(error)[:160])
    except Exception as error:  # noqa: BLE001 - фаззер сообщает о любой ошибке
        errors += 1
        print("ERR", source, repr(error)[:160])

print("ok", ok, "bad", bad, "err", errors)
