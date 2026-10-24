"""Our authored teaching copy and offline theory, written for this project.

The wire contract keeps its description keys; these templates supplement the
artifact dictionary. Theory is additive presentation metadata, never a solver.
"""

from __future__ import annotations

from typing import Any


def _text(ru: str, en: str, arity: int = 0) -> dict[str, Any]:
    return {"arity": arity, "templates": {"ru": ru, "default": en}}


TEMPLATES = {
    "ineq_poly_roots": _text(
        "Приравняем многочлен к нулю: корни разбивают числовую прямую на промежутки.",
        "Set the polynomial to zero: the roots split the number line into intervals.",
    ),
    "ineq_poly_sign_chart": _text(
        "Определим знак многочлена на каждом промежутке и выберем те, где неравенство верно.",
        "Find the sign of the polynomial on each interval and keep those where it holds.",
    ),
    "eq_quad_coeff_identify": _text(
        "В стандартном виде ax² + bx + c = 0 коэффициенты равны: a = ARG1, b = ARG2, c = ARG3.",
        "In ax² + bx + c = 0 the coefficients are a = ARG1, b = ARG2, c = ARG3.",
        3,
    ),
    # The formula ``D = b² − 4ac`` is the stage's own left side, so the text
    # does not repeat it (the card would otherwise show it twice).
    "eq_quad_disc": _text(
        "Подставим коэффициенты вместе с их знаками в формулу дискриминанта.",
        "Insert the signed coefficients into the discriminant formula.",
    ),
    "eq_quad_disc_calculate": _text(
        "Вычислим значение дискриминанта: D = ARG1. "
        "По его знаку определяем число действительных корней.",
        "Calculate the discriminant: D = ARG1. Its sign determines the number of real roots.",
        1,
    ),
    "eq_quad_solve_in_r": _text(
        "Подставим дискриминант в формулу корней. Вычислим ветви со знаком минус и плюс; "
        "при ARG1 они совпадают.",
        "Insert the discriminant in the quadratic formula. Calculate the minus and plus branches; "
        "for ARG1 they coincide.",
        1,
    ),
    "lesson_standard": _text(
        "Приведём уравнение к стандартному виду", "Write the equation in standard form"
    ),
    "lesson_discriminant": _text("Найдём дискриминант", "Find the discriminant"),
    "lesson_roots": _text("Найдём корни", "Find the roots"),
    "lesson_root_substitute": _text("Подставим значения в формулу", "Substitute in the formula"),
    "lesson_root_minus": _text("Вычислим корень со знаком минус", "Calculate the minus branch"),
    "lesson_root_plus": _text("Вычислим корень со знаком плюс", "Calculate the plus branch"),
    "lesson_isolate": _text("Соберём члены с неизвестным", "Collect the variable terms"),
    "lesson_divide": _text("Выразим неизвестное", "Isolate the variable"),
    "lesson_fraction": _text("Сократим дробь", "Reduce the fraction"),
    "lesson_fraction_sum": _text("Выполним действие с дробями", "Combine the fractions"),
    "lesson_fraction_product": _text("Умножим или разделим дроби", "Multiply or divide fractions"),
    "lesson_fraction_reciprocal": _text(
        "Заменим деление умножением на обратную дробь. Делитель не должен равняться нулю.",
        "Replace division with multiplication by the reciprocal. The divisor must be nonzero.",
    ),
    "lesson_fraction_multiply": _text(
        "Перемножим числители и отдельно знаменатели. При необходимости сократим результат.",
        "Multiply the numerators and the denominators separately, then reduce if needed.",
    ),
    "lesson_normalize": _text(
        "Вычтем правую часть из левой и приведём подобные члены. Правая часть равна нулю.",
        "Subtract the right side and collect like terms. The right side is zero.",
    ),
    "lesson_collect": _text(
        "Приведём подобные члены в каждой части уравнения.", "Collect like terms on each side."
    ),
    "lesson_balance": _text(
        "Выполним одинаковое действие с обеими частями: вычтем ARG1.",
        "Apply the same operation to both sides: subtract ARG1.",
        1,
    ),
    "lesson_simplify": _text(
        "Вычислим и приведём подобные члены, не меняя равенства.",
        "Calculate and collect like terms without changing the equality.",
    ),
    "lesson_ode_homogeneous": _text(
        "Однородное уравнение: подставим y = u·x и сведём его к уравнению "
        "с разделяющимися переменными.",
        "Homogeneous equation: substitute y = u·x to reduce it to a separable equation.",
    ),
    "lesson_ode_exact": _text(
        "Уравнение в полных дифференциалах: найдём потенциал F(x, y), "
        "и решение запишется как F(x, y) = C.",
        "Exact equation: find the potential F(x, y); the solution is F(x, y) = C.",
    ),
    "lesson_ode_reduction_of_order": _text(
        "Понизим порядок уравнения заменой ARG1.",
        "Reduce the order with the substitution ARG1.",
        1,
    ),
    "lesson_ode_constant_coeff_homogeneous": _text(
        "Однородное уравнение с постоянными коэффициентами: составим "
        "характеристическое уравнение и найдём его корни.",
        "Homogeneous equation with constant coefficients: write the characteristic "
        "equation and find its roots.",
    ),
    "lesson_ode_constant_coeff_special": _text(
        "Неоднородное уравнение с постоянными коэффициентами: частное решение "
        "подберём по виду правой части.",
        "Nonhomogeneous equation with constant coefficients: choose the particular "
        "solution from the form of the right side.",
    ),
    "lesson_ode_variation_of_constants": _text(
        "Найдём общее решение однородного уравнения, а постоянные определим "
        "методом вариации постоянных.",
        "Find the general solution of the homogeneous equation and determine the "
        "constants by variation of parameters.",
    ),
    "lesson_ode_solution_with_condition": _text(
        "Решение с учётом условия", "Solution satisfying the condition"
    ),
    # ``y = 0`` is the stage's own formula; the sentence must not repeat it.
    "lesson_ode_singular_solution": _text(
        "Особое решение (потеряно при делении на y).",
        "Singular solution (lost when dividing by y).",
    ),
    "lesson_divide_sides": _text(
        "Разделим обе части на ненулевое число ARG1.",
        "Divide both sides by the nonzero number ARG1.",
        1,
    ),
    "lesson_disc_square": _text(
        "Сначала возведём коэффициент b в квадрат. Скобки сохраняют знак отрицательного числа.",
        "First square b. Parentheses preserve the sign of a negative coefficient.",
    ),
    "lesson_disc_product": _text(
        "Вычислим произведение 4ac, учитывая знаки коэффициентов.",
        "Calculate 4ac, keeping the signs of the coefficients.",
    ),
    "lesson_disc_subtract": _text(
        "Вычтем 4ac из b². Полученное число — дискриминант D.",
        "Subtract 4ac from b² to obtain the discriminant D.",
    ),
    "lesson_root_formula": _text(
        "Используем формулу корней для ARG1, где ARG2.",
        "Use the quadratic formula for ARG1, with ARG2.",
        2,
    ),
    "lesson_root_sqrt": _text(
        "Упростим квадратный корень из дискриминанта; иррациональное значение оставим точным.",
        "Simplify the square root of the discriminant; keep irrational values exact.",
    ),
    "lesson_root_numerator": _text(
        "Вычислим числитель этой ветви формулы.",
        "Calculate the numerator for this branch of the formula.",
    ),
    "lesson_root_denominator": _text(
        "Вычислим знаменатель 2a. Он не равен нулю.",
        "Calculate the denominator 2a, which is nonzero.",
    ),
    "lesson_root_reduce": _text(
        "Упростим полученную дробь и запишем корень.", "Simplify the fraction to obtain the root."
    ),
    "lesson_factor_zero": _text(
        "Произведение равно нулю, когда хотя бы один множитель равен нулю.",
        "A product is zero when at least one factor is zero.",
    ),
    "lesson_gcd": _text(
        "Общий делитель числителя и знаменателя: ARG1. Разделим оба числа на него.",
        "A common divisor of numerator and denominator is ARG1. Divide both by it.",
        1,
    ),
    "lesson_fraction_divide": _text(
        "Делим числитель и знаменатель на одно и то же ненулевое число.",
        "Divide the numerator and denominator by the same nonzero number.",
    ),
    "lesson_common_denominator": _text(
        "Выберем общий знаменатель ARG1 и умножим числитель и знаменатель "
        "каждой дроби на одинаковое число.",
        "Choose the common denominator ARG1 and multiply each numerator and denominator "
        "by the same number.",
        1,
    ),
    "lesson_combine_numerators": _text(
        "Знаменатели одинаковы: выполним действие с числителями, сохранив знаменатель.",
        "The denominators match: combine the numerators and keep the denominator.",
    ),
    "lesson_fraction_finish": _text(
        "Вычислим числитель и сократим результат, если есть общий делитель.",
        "Calculate the numerator and reduce the result if there is a common divisor.",
    ),
    "det_expand_equation": _text(
        "Раскроем определитель: получим уравнение относительно неизвестного.",
        "Expand the determinant: this gives an equation in the unknown.",
    ),
    "matrix_transpose": _text(
        "Строки становятся столбцами: (Aᵀ)ᵢⱼ = aⱼᵢ.",
        "Rows become columns: (Aᵀ)ᵢⱼ = aⱼᵢ.",
    ),
    "system_param_solve": _text("Решить систему с параметром", "Solve the system with a parameter"),
    "system_matrix_inv_det": _text(
        "Определитель матрицы коэффициентов не равен нулю, поэтому обратная матрица существует.",
        "The determinant of the coefficient matrix is non-zero, so the inverse matrix exists.",
    ),
    "system_param_det": _text(
        "Система содержит параметр ARG1: её коэффициенты зависят от него. Вычислим "
        "определитель матрицы коэффициентов.",
        "The system contains the parameter ARG1: its coefficients depend on it. "
        "Work out the determinant of the coefficient matrix.",
        1,
    ),
    "system_param_unique": _text(
        "При ARG1 определитель не равен нулю, поэтому решение единственно; выразим "
        "неизвестные через параметр по формулам Крамера.",
        "For ARG1 the determinant is non-zero, so the solution is unique; express "
        "the unknowns through the parameter by Cramer's rule.",
        1,
    ),
    "system_param_unique_always": _text(
        "Определитель не зависит от параметра и не равен нулю, поэтому система имеет "
        "единственное решение при всех его значениях (формулы Крамера).",
        "The determinant does not depend on the parameter and is non-zero, so the "
        "system has a unique solution for every parameter value (Cramer's rule).",
    ),
    "system_param_special": _text(
        "При ARG1 = ARG2 определитель обращается в нуль: подставим это значение и "
        "разберём получившуюся числовую систему отдельно.",
        "For ARG1 = ARG2 the determinant vanishes: substitute that value and treat "
        "the resulting numerical system separately.",
        2,
    ),
}

# Text, formulas and examples below are authored for this app and bundled offline.
ARTICLES: dict[str, dict[str, dict[str, str]]] = {
    "balance": {
        "ru": {
            "title": "Равносильные преобразования уравнения",
            "summary": "Равенство сохраняется, если к обеим частям прибавить "
            "или из обеих вычесть одно и то же выражение.",
            "formula": r"A=B\quad\Longleftrightarrow\quad A-C=B-C",
            "conditions": "При делении число должно быть ненулевым. При работе с выражениями "
            "нужно сохранять область определения.",
            "example": "2x + 3 = 7: вычтем 3 с обеих сторон → 2x = 4; "
            "разделим обе части на 2 → x = 2.",
            "mistake": "Нельзя изменить только одну часть равенства. «Перенос со сменой знака» — "
            "сокращённая запись действия с обеими частями.",
        },
        "en": {
            "title": "Equivalent equations",
            "summary": "Adding or subtracting the same expression on both sides "
            "preserves equality.",
            "formula": r"A=B\quad\Longleftrightarrow\quad A-C=B-C",
            "conditions": "Divide only by a nonzero quantity and preserve the original domain.",
            "example": "2x + 3 = 7: subtract 3 on both sides → 2x = 4; "
            "divide both sides by 2 → x = 2.",
            "mistake": "Changing only one side does not preserve equality.",
        },
    },
    "discriminant": {
        "ru": {
            "title": "Дискриминант квадратного уравнения",
            "summary": "Дискриминант определяет число действительных корней квадратного уравнения.",
            "formula": r"ax^2+bx+c=0,\quad D=b^2-4ac",
            "conditions": "a ≠ 0. Если D > 0, есть два действительных корня; если D = 0 — один; "
            "если D < 0 — действительных корней нет.",
            "example": "x² − 5x + 6 = 0: a = 1, b = −5, c = 6. D = (−5)² − 4·1·6 = 25 − 24 = 1.",
            "mistake": "Для отрицательного b возводите в квадрат число вместе со знаком: "
            "(−5)² = 25, но −5² = −25.",
        },
        "en": {
            "title": "The discriminant",
            "summary": "The discriminant determines the number of real roots "
            "of a quadratic equation.",
            "formula": r"ax^2+bx+c=0,\quad D=b^2-4ac",
            "conditions": "a ≠ 0. D > 0 gives two real roots; D = 0 gives one; "
            "D < 0 gives no real roots.",
            "example": "x² − 5x + 6 = 0: D = (−5)² − 4·1·6 = 1.",
            "mistake": "Square the signed coefficient: (−5)² = 25, whereas −5² = −25.",
        },
    },
    "quadratic": {
        "ru": {
            "title": "Формула корней",
            "summary": "После вычисления дискриминанта подставим его в формулу. "
            "Знаки плюс и минус задают две ветви вычисления.",
            "formula": r"x_{1,2}=\frac{-b\pm\sqrt{D}}{2a}",
            "conditions": "Для действительных корней нужны a ≠ 0 и D ≥ 0. "
            "При D = 0 обе ветви дают одно число.",
            "example": "При a = 1, b = −5, D = 1: (5 − 1)/2 = 2 и (5 + 1)/2 = 3.",
            "mistake": "Знаменатель 2a относится ко всему числителю −b ± √D, а не только к корню.",
        },
        "en": {
            "title": "The quadratic formula",
            "summary": "Insert the discriminant. The minus and plus signs give the two branches.",
            "formula": r"x_{1,2}=\frac{-b\pm\sqrt{D}}{2a}",
            "conditions": "Real roots require a ≠ 0 and D ≥ 0. For D = 0 both branches coincide.",
            "example": "a = 1, b = −5, D = 1: (5 − 1)/2 = 2 and (5 + 1)/2 = 3.",
            "mistake": "The denominator 2a divides the entire numerator.",
        },
    },
    "fractions": {
        "ru": {
            "title": "Основное свойство дроби",
            "summary": "Значение дроби не меняется, если числитель и знаменатель "
            "умножить или разделить на одно и то же ненулевое число.",
            "formula": r"\frac{a}{b}=\frac{ak}{bk},\quad b\ne0,\ k\ne0",
            "conditions": "Для сокращения целочисленной дроби делитель должен делить "
            "и числитель, и знаменатель. Удобно выбрать НОД.",
            "example": "6/8 = (6 ÷ 2)/(8 ÷ 2) = 3/4. А 1/3 + 1/6 = 2/6 + 1/6 = 3/6 = 1/2.",
            "mistake": "Нельзя складывать знаменатели: 1/3 + 1/6 не равно 2/9. "
            "Нельзя сокращать отдельные слагаемые суммы.",
        },
        "en": {
            "title": "Equivalent fractions",
            "summary": "Multiplying or dividing the numerator and denominator "
            "by the same nonzero number preserves the value.",
            "formula": r"\frac{a}{b}=\frac{ak}{bk},\quad b\ne0,\ k\ne0",
            "conditions": "To reduce an integer fraction, divide both parts by a common divisor, "
            "preferably their greatest common divisor.",
            "example": "6/8 = (6 ÷ 2)/(8 ÷ 2) = 3/4. 1/3 + 1/6 = 2/6 + 1/6 = 1/2.",
            "mistake": "Do not add denominators or cancel individual terms in a sum.",
        },
    },
}


def theory(key: str, locale: str) -> dict[str, str] | None:
    """Only offer Why when an actual relevant offline article exists."""
    topic = None
    # Only the discriminant's own steps open the discriminant article: the discrete
    # pack also names its steps ``lesson_disc_*`` (determinants, matrices, vectors, …)
    # and those must reach their own article, not this one.
    if key.startswith("eq_quad_disc") or key in {
        "eq_quad_coeff_identify",
        "lesson_discriminant",
        "lesson_disc_square",
        "lesson_disc_product",
        "lesson_disc_subtract",
    }:
        topic = "discriminant"
    elif key.startswith(
        ("eq_quad_solve", "lesson_root", "quad_formula", "quad_separate", "quad_sqrt")
    ):
        topic = "quadratic"
    elif key in {
        "move",
        "eq_linar_divide_both_sides",
        "eq_linear",
        "eq_linear_div",
        "divide_both_sides",
        "multiply_both_sides",
        "eq_mul_direct",
        "remove_opposites",
        "lesson_balance",
        "lesson_divide_sides",
        "lesson_collect",
        "lesson_normalize",
    } or key.startswith(("rel_move_", "rel_swap_", "sum_suffix")):
        topic = "balance"
    elif key.startswith(
        (
            "frac_reduce",
            "frac_sum",
            "frac_mul_join",
            "frac_div_",
            "lesson_fraction",
            "lesson_gcd",
            "lesson_common_denominator",
            "lesson_combine_numerators",
        )
    ):
        topic = "fractions"
    return {"id": topic, **ARTICLES[topic]["ru" if locale == "ru" else "en"]} if topic else None
