"""Authored algebra lessons with bounded, rule-based intermediate work.

This is presentation enrichment, not a replacement solver. Unsupported shapes
return None; in particular a successful SymPy simplification is not a proof
that a particular school-algebra rule was used.
"""

from __future__ import annotations

from itertools import product
from typing import Any

import sympy

from .ast import CoreNode
from .node_types import CoreNodeType as T
from .solver.base import SolveError, SolveResult, Step
from .solver.sympy_bridge import from_sympy, to_sympy


def _text(ru: str, en: str, arity: int = 0) -> dict[str, Any]:
    return {"arity": arity, "templates": {"ru": ru, "default": en}}


TEMPLATES = {
    "lesson_alg_expand": _text("Раскроем скобки", "Expand the brackets"),
    "lesson_alg_distribute": _text(
        "Умножим каждый член первой суммы на каждый член второй: a(b+c)=ab+ac.",
        "Multiply each term by every term in the other sum: a(b+c)=ab+ac.",
    ),
    "lesson_alg_repeat": _text(
        "Натуральная степень — произведение одинаковых множителей.",
        "A positive integer power is a product of equal factors.",
    ),
    "lesson_alg_collect": _text(
        "Вычислим произведения и сложим коэффициенты при одинаковых степенях.",
        "Evaluate products and add coefficients of like powers.",
    ),
    "lesson_alg_factor": _text("Разложим на множители", "Factor the polynomial"),
    "lesson_alg_common": _text(
        "Вынесем общий множитель ARG1: ab+ac=a(b+c).",
        "Take out the common factor ARG1: ab+ac=a(b+c).",
        1,
    ),
    "lesson_alg_split": _text(
        "Разделим средний член: сумма коэффициентов равна b, произведение равно ac.",
        "Split the middle term: the coefficients add to b and multiply to ac.",
    ),
    "lesson_alg_group": _text(
        "Сгруппируем члены и вынесем общий множитель из каждой пары.",
        "Group terms and take a common factor out of each pair.",
    ),
    "lesson_alg_binomial": _text(
        "Вынесем общую скобку из двух слагаемых.",
        "Take out the binomial shared by both terms.",
    ),
    "lesson_alg_fraction": _text(
        "Упростим алгебраическую дробь", "Simplify the algebraic fraction"
    ),
    "lesson_alg_domain": _text(
        "Сохраним условие исходной записи: ARG1. Оно остаётся после сокращения.",
        "Keep the original restriction: ARG1. It still applies after cancellation.",
        1,
    ),
    "lesson_alg_fraction_factor": _text(
        "Разложим числитель и знаменатель на множители, пока ничего не сокращая.",
        "Factor numerator and denominator without cancelling yet.",
    ),
    "lesson_alg_cancel": _text(
        "Сократим общий множитель ARG1; он ненулевой в исходной области определения.",
        "Cancel the common factor ARG1; it is nonzero on the original domain.",
        1,
    ),
    "lesson_alg_root": _text("Используем определение корня", "Use the definition of a root"),
    "lesson_alg_root_power": _text(
        "Представим подкоренное как точную степень; чётный корень неотрицателен.",
        "Write the radicand as an exact power; an even root is nonnegative.",
    ),
    "lesson_alg_extract": _text(
        "Извлечём полный множитель из корня; для чётного корня берём его модуль.",
        "Extract the perfect-power factor; use its absolute value for an even root.",
    ),
    "lesson_alg_rational_power": _text(
        "При положительном основании a^(p/q)=(q√a)^p, где q>0.",
        "For a positive base, a^(p/q)=(q√a)^p, with q>0.",
    ),
    "lesson_alg_log": _text("Применим определение логарифма", "Use the logarithm definition"),
    "lesson_alg_log_witness": _text(
        "Проверим степень: ARG1. Поэтому логарифм равен этому показателю.",
        "Check the power: ARG1. The logarithm is therefore this exponent.",
        1,
    ),
    "lesson_alg_log_substitute": _text(
        "Заменим аргумент равной ему степенью основания.",
        "Replace the argument with an equal power of the base.",
    ),
    "lesson_alg_log_finish": _text(
        "log_b(b^t)=t при b>0, b≠1 и действительном t.",
        "log_b(b^t)=t for b>0, b≠1 and real t.",
    ),
    "lesson_alg_trig": _text("Применим тригонометрическое правило", "Apply a trigonometric rule"),
    "lesson_alg_pythagorean_rule": _text(
        "Основное тождество: ARG1. Аргументы синуса и косинуса должны совпадать.",
        "Pythagorean identity: ARG1. Sine and cosine must have the same argument.",
        1,
    ),
    "lesson_alg_pythagorean_use": _text(
        "Подставим общий аргумент в sin²(u)+cos²(u)=1.",
        "Substitute the shared argument in sin²(u)+cos²(u)=1.",
    ),
    "lesson_alg_angle": _text(
        "Отделим целое число периодов: ARG1.",
        "Separate a whole number of periods: ARG1.",
        1,
    ),
    "lesson_alg_period": _text(
        "У sin и cos период 2π, у tan и cot — π. Целые периоды не меняют значение.",
        "Sine and cosine have period 2π; tangent and cotangent have period π.",
    ),
    "lesson_alg_radians": _text(
        "Переведём градусы в радианы: α°=α·π/180.",
        "Convert degrees to radians: α°=α·π/180.",
    ),
    "lesson_alg_parity": _text(
        "cos(−u)=cos(u); sin(−u)=−sin(u), tan(−u)=−tan(u), cot(−u)=−cot(u).",
        "cos(−u)=cos(u); sin(−u)=−sin(u), tan(−u)=−tan(u), cot(−u)=−cot(u).",
    ),
    "lesson_alg_table": _text(
        "Используем точное значение на единичной окружности; угол дан в радианах.",
        "Use the exact unit-circle value; the angle is in radians.",
    ),
    "lesson_alg_trig_equation": _text(
        "Выразим функцию и запишем все серии решений", "Isolate the function and find all families"
    ),
    "lesson_alg_isolate_trig": _text(
        "Вычтем постоянный член и разделим на ненулевой коэффициент функции.",
        "Subtract the constant term and divide by the nonzero function coefficient.",
    ),
    "lesson_alg_families": _text(
        "Запишем все углы с этим значением; параметр k — любое целое число.",
        "Write all angles with this value; k is any integer.",
    ),
    "lesson_alg_argument": _text(
        "В каждой серии вычтем сдвиг аргумента и разделим на его коэффициент; k∈ℤ.",
        "In each family subtract the argument shift and divide by its coefficient; k∈ℤ.",
    ),
    "lesson_alg_inequality": _text(
        "Разделим части неравенства", "Divide both sides of the inequality"
    ),
    "lesson_alg_divide_negative": _text(
        "Разделим обе части на ARG1<0 и обратим знак неравенства.",
        "Divide both sides by ARG1<0 and reverse the inequality sign.",
        1,
    ),
    "lesson_alg_divide_positive": _text(
        "Разделим обе части на ARG1>0; знак неравенства сохраняется.",
        "Divide both sides by ARG1>0; the inequality sign stays the same.",
        1,
    ),
    "lesson_alg_abs": _text("Раскроем модуль по случаям", "Split the absolute value into cases"),
    "lesson_alg_abs_nonnegative": _text(
        "Модуль неотрицателен, поэтому необходимо ARG1.",
        "An absolute value is nonnegative, so ARG1 is necessary.",
        1,
    ),
    "lesson_alg_abs_or": _text(
        "При неотрицательной правой части достаточно хотя бы одного из двух условий.",
        "For a nonnegative right side, at least one of these two conditions must hold.",
    ),
    "lesson_alg_abs_and": _text(
        "Оба условия должны выполняться одновременно.", "Both conditions must hold together."
    ),
}


def _article(ru: tuple[str, ...], en: tuple[str, ...]) -> dict[str, dict[str, str]]:
    fields = ("title", "summary", "formula", "conditions", "example", "mistake")
    return {"ru": dict(zip(fields, ru, strict=True)), "en": dict(zip(fields, en, strict=True))}


ARTICLES = {
    "algebra_distribution": _article(
        (
            "Раскрытие скобок",
            "Распределяем умножение по всем слагаемым.",
            r"a(b+c)=ab+ac",
            "Правило применимо к сумме и разности; учитывайте каждый знак.",
            "(x+2)(x−3)=x²−3x+2x−6=x²−x−6.",
            "Не пропускайте перекрёстные произведения.",
        ),
        (
            "Distributing products",
            "Multiply every term by every term in the other bracket.",
            r"a(b+c)=ab+ac",
            "The rule applies to sums and differences; retain all signs.",
            "(x+2)(x−3)=x²−3x+2x−6=x²−x−6.",
            "Do not omit the cross products.",
        ),
    ),
    "algebra_factoring": _article(
        (
            "Разложение на множители",
            "Распределительный закон работает и в обратную сторону.",
            r"ab+ac=a(b+c),\quad ax^2+bx+c=a(x-r_1)(x-r_2)",
            "Во второй формуле a≠0, а r₁ и r₂ — корни многочлена с учётом кратности.",
            "x²+5x+6=x²+2x+3x+6=x(x+2)+3(x+2)=(x+3)(x+2).",
            "Проверьте ответ обратным раскрытием скобок.",
        ),
        (
            "Factoring",
            "Read the distributive law in reverse.",
            r"ab+ac=a(b+c),\quad ax^2+bx+c=a(x-r_1)(x-r_2)",
            "In the second formula a≠0 and r₁,r₂ are polynomial roots counted with multiplicity.",
            "x²+5x+6=x²+2x+3x+6=x(x+2)+3(x+2)=(x+3)(x+2).",
            "Check the factorization by expanding it.",
        ),
    ),
    "algebra_fraction_domain": _article(
        (
            "Сокращение и область определения",
            "Сокращаем множители, а не слагаемые.",
            r"\frac{AC}{BC}=\frac AB\quad(B\ne0,\ C\ne0)",
            "Все исходные знаменатели остаются ненулевыми, даже если исчезли из ответа.",
            "(x²−1)/(x−1)=x+1 только при x≠1.",
            "Сокращение не возвращает исключённую точку в область определения.",
        ),
        (
            "Cancellation and domain",
            "Cancel common factors, not separate summands.",
            r"\frac{AC}{BC}=\frac AB\quad(B\ne0,\ C\ne0)",
            "Every original denominator must remain nonzero, even if absent from the result.",
            "(x²−1)/(x−1)=x+1 only for x≠1.",
            "Cancellation does not restore a previously excluded point.",
        ),
    ),
    "algebra_roots": _article(
        (
            "Корни и рациональные степени",
            "Корень обращает возведение в степень с выбором ветви.",
            r"\sqrt{a^2}=|a|,\quad a^{p/q}=(\sqrt[q]{a})^p\ (a>0)",
            "q — положительное целое. Для чётного корня подкоренное неотрицательно.",
            "16^(3/4)=(⁴√16)³=2³=8; √72=6√2.",
            "√(x²) — это |x|, а не всегда x. Отрицательные основания требуют отдельного анализа.",
        ),
        (
            "Roots and rational powers",
            "A root reverses a power with a specified branch.",
            r"\sqrt{a^2}=|a|,\quad a^{p/q}=(\sqrt[q]{a})^p\ (a>0)",
            "q is a positive integer. An even real root requires a nonnegative radicand.",
            "16^(3/4)=(⁴√16)³=2³=8; √72=6√2.",
            "√(x²) is |x|, not always x. Negative bases require separate analysis.",
        ),
    ),
    "algebra_logarithms": _article(
        (
            "Определение логарифма",
            "Логарифм — показатель степени заданного основания.",
            r"\log_b a=t\ \Longleftrightarrow\ b^t=a",
            "В действительных числах a>0, b>0 и b≠1.",
            "log₂8=log₂(2³)=3, потому что 2³=8.",
            "log(a+b) нельзя заменять на log(a)+log(b).",
        ),
        (
            "The logarithm definition",
            "A logarithm is an exponent for a specified base.",
            r"\log_b a=t\ \Longleftrightarrow\ b^t=a",
            "Over the reals, a>0, b>0 and b≠1.",
            "log₂8=log₂(2³)=3 because 2³=8.",
            "log(a+b) is not log(a)+log(b).",
        ),
    ),
    "algebra_trig_identity": _article(
        (
            "Основное тригонометрическое тождество",
            "Координаты единичной окружности дают сумму 1.",
            r"\sin^2 u+\cos^2 u=1",
            "Обе функции должны иметь один и тот же аргумент.",
            "sin²(3x)+cos²(3x)=1.",
            "sin²x+cos²(2x) не равно 1 тождественно.",
        ),
        (
            "Pythagorean trigonometric identity",
            "Unit-circle coordinates have squared sum 1.",
            r"\sin^2 u+\cos^2 u=1",
            "Both functions must have the same argument.",
            "sin²(3x)+cos²(3x)=1.",
            "sin²x+cos²(2x) is not identically 1.",
        ),
    ),
    "algebra_trig_values": _article(
        (
            "Точные значения и приведение угла",
            "Сначала используем чётность и периодичность.",
            r"\sin(-u)=-\sin u,\quad\cos(-u)=\cos u,\quad\sin(u+2\pi k)=\sin u",
            "k — целое; у тангенса и котангенса период π. Проверяйте область определения.",
            "sin(390°)=sin(30°)=1/2; cos(−π/3)=cos(π/3)=1/2.",
            "Угол без символа градусов измеряется в радианах.",
        ),
        (
            "Exact values and angle reduction",
            "Use parity and periodicity before a table lookup.",
            r"\sin(-u)=-\sin u,\quad\cos(-u)=\cos u,\quad\sin(u+2\pi k)=\sin u",
            "k is an integer; tangent and cotangent have period π. Check undefined arguments.",
            "sin(390°)=sin(30°)=1/2; cos(−π/3)=cos(π/3)=1/2.",
            "An angle without a degree symbol is measured in radians.",
        ),
    ),
    "algebra_trig_equations": _article(
        (
            "Общее решение тригонометрического уравнения",
            "Одного главного значения недостаточно.",
            r"\sin u=c:\ u=\arcsin c+2\pi k\ \text{or}\ u=\pi-\arcsin c+2\pi k",
            "Для sin и cos требуется −1≤c≤1; k∈ℤ. В линейном аргументе ax+b нужно a≠0.",
            "sin(2x)=1/2: x=π/12+πk или x=5π/12+πk.",
            "При делении аргумента делите и период каждой серии.",
        ),
        (
            "General trigonometric solutions",
            "A single principal value is not the full solution.",
            r"\sin u=c:\ u=\arcsin c+2\pi k\ \text{or}\ u=\pi-\arcsin c+2\pi k",
            "For sine and cosine, −1≤c≤1; k∈ℤ. An affine argument ax+b requires a≠0.",
            "sin(2x)=1/2: x=π/12+πk or x=5π/12+πk.",
            "When dividing the argument, divide the period in every family too.",
        ),
    ),
    "algebra_order": _article(
        (
            "Знак неравенства",
            "Умножение на отрицательное число меняет порядок.",
            r"a<b,\ c<0\ \Longrightarrow\ a/c>b/c",
            "Знак делителя должен быть известен. На нуль делить нельзя.",
            "−2x<6 ⇒ x>−3.",
            "Если знак делителя с переменной неизвестен, нужны случаи.",
        ),
        (
            "Inequality direction",
            "Multiplication by a negative number reverses order.",
            r"a<b,\ c<0\ \Longrightarrow\ a/c>b/c",
            "The divisor's sign must be known. Division by zero is forbidden.",
            "−2x<6 ⇒ x>−3.",
            "A variable divisor with unknown sign requires case splitting.",
        ),
    ),
    "algebra_absolute_cases": _article(
        (
            "Случаи для модуля",
            "Модуль — расстояние от нуля, поэтому он неотрицателен.",
            r"|u|=c\iff(u=c\ \text{or}\ u=-c),\ c\ge0",
            "Для |u|<c нужны оба условия −c<u и u<c. При c<0 равенство невозможно.",
            "|x−1|=2 ⇒ x−1=2 или x−1=−2 ⇒ x=3 или x=−1.",
            "При переменной правой части c(x) обязательно проверить c(x)≥0.",
        ),
        (
            "Absolute-value cases",
            "Absolute value is distance from zero, hence nonnegative.",
            r"|u|=c\iff(u=c\ \text{or}\ u=-c),\ c\ge0",
            "For |u|<c, both −c<u and u<c are required. Equality is impossible for c<0.",
            "|x−1|=2 ⇒ x−1=2 or x−1=−2 ⇒ x=3 or x=−1.",
            "A variable right side c(x) must satisfy c(x)≥0.",
        ),
    ),
    "algebra_formulas": _article(
        (
            "Формулы сокращённого умножения",
            "Типовые произведения записываются готовой формулой: скобки не надо раскрывать заново.",
            r"(a\pm b)^2=a^2\pm2ab+b^2,\quad a^2-b^2=(a-b)(a+b)",
            "Формулы верны для любых a и b; читайте их и слева направо (раскрыть), и справа налево "
            "(разложить).",
            "(x+3)² = x² + 2·x·3 + 3² = x² + 6x + 9.",
            "Средний член 2ab нельзя пропускать: (a+b)² не равно a² + b².",
        ),
        (
            "Special products",
            "Standard products have a ready formula, so brackets need not be multiplied out again.",
            r"(a\pm b)^2=a^2\pm2ab+b^2,\quad a^2-b^2=(a-b)(a+b)",
            "The formulas hold for all a and b; read them to expand or to factor.",
            "(x+3)² = x² + 2·x·3 + 3² = x² + 6x + 9.",
            "Do not drop the middle term 2ab: (a+b)² is not a² + b².",
        ),
    ),
    "algebra_powers": _article(
        (
            "Свойства степени",
            "Степень с нулевым показателем равна 1, с единичным — самому основанию.",
            r"a^0=1\ (a\ne0),\quad a^1=a,\quad 1^n=1,\quad (-a)^{2k}=a^{2k}",
            "Ноль в нулевой степени не определён. Чётная степень отрицательного числа > 0.",
            "5⁰ = 1, 7¹ = 7, (−2)² = 4.",
            "(−2)² = 4, но −2² = −4: скобки меняют основание степени.",
        ),
        (
            "Properties of powers",
            "A power with exponent 0 is 1; with exponent 1 it is the base itself.",
            r"a^0=1\ (a\ne0),\quad a^1=a,\quad 1^n=1,\quad (-a)^{2k}=a^{2k}",
            "Zero to the power zero is undefined. An even power of a negative number is positive.",
            "5⁰ = 1, 7¹ = 7, (−2)² = 4.",
            "(−2)² = 4 whereas −2² = −4: brackets change the base.",
        ),
    ),
    "algebra_signs": _article(
        (
            "Правило знаков",
            "Знак произведения и частного зависит только от числа отрицательных множителей.",
            r"(+)(+)=+,\ (-)(-)=+,\ (+)(-)=-,\ (-)(+)=-",
            "Одинаковые знаки дают плюс, разные — минус; модули перемножаются как обычно.",
            "(−3)·(−4) = 12, 2·(−5) = −10, (−12)/4 = −3.",
            "Вычитание отрицательного числа — это прибавление: 5 − (−2) = 7.",
        ),
        (
            "Sign rules",
            "The sign of a product or quotient depends only on the number of negative factors.",
            r"(+)(+)=+,\ (-)(-)=+,\ (+)(-)=-,\ (-)(+)=-",
            "Equal signs give plus, different signs give minus; multiply the absolute values.",
            "(−3)·(−4) = 12, 2·(−5) = −10, (−12)/4 = −3.",
            "Subtracting a negative number is adding: 5 − (−2) = 7.",
        ),
    ),
    "algebra_zero_product": _article(
        (
            "Произведение равно нулю",
            "Произведение равно нулю тогда и только тогда, когда нулю равен один из множителей.",
            r"AB=0\iff A=0\ \text{или}\ B=0",
            "Работает только для нуля: уравнение AB = 5 так решать нельзя.",
            "(x−2)(x+3)=0 ⇒ x=2 или x=−3.",
            "Нельзя сокращать на x, не проверив, что x ≠ 0: потеряется корень x = 0.",
        ),
        (
            "Zero-product property",
            "A product is zero exactly when at least one factor is zero.",
            r"AB=0\iff A=0\ \text{or}\ B=0",
            "It works only for zero: AB = 5 cannot be solved this way.",
            "(x−2)(x+3)=0 ⇒ x=2 or x=−3.",
            "Do not cancel x without checking x ≠ 0: the root x = 0 would be lost.",
        ),
    ),
}

RULE_TOPICS = {
    "using_factor": "algebra_formulas",
    "using_expand": "algebra_formulas",
    "extract_arg": "algebra_factoring",
    "root_square": "algebra_roots",
    "root_reduce": "algebra_roots",
    "rel_restrictions_find": "algebra_fraction_domain",
    "solve_by_factoring": "algebra_zero_product",
    "pow": "algebra_powers",
    "pow_with_zero": "algebra_powers",
    "pow_with_one": "algebra_powers",
    "pow_one": "algebra_powers",
    "pow_even": "algebra_powers",
    "mul": "algebra_signs",
    "div": "algebra_signs",
    "mul_pos_neg": "algebra_signs",
    "expand_msg": "algebra_distribution",
    "factorise_call": "algebra_factoring",
    "simplify": "algebra_fraction_domain",
    "root_simplify": "algebra_roots",
    "substitute_pythagorean_identity": "algebra_trig_identity",
    "trig_table_calc": "algebra_trig_values",
    "trig_rewrite_coterminal_pos": "algebra_trig_values",
    "trig_general_sol": "algebra_trig_equations",
    "ineq_linear_div": "algebra_order",
    "ineq_linear_div_neg": "algebra_order",
    "abs_separate": "algebra_absolute_cases",
    "eq_abs_branch": "algebra_absolute_cases",
    "ineq_separate_abs": "algebra_absolute_cases",
}
for _key in ("trig_neg_sin", "trig_neg_cos", "trig_neg_tan", "trig_neg_cot"):
    RULE_TOPICS[_key] = "algebra_trig_values"
for _topic, _suffixes in {
    "algebra_distribution": ("expand", "distribute", "repeat", "collect"),
    "algebra_factoring": ("factor", "common", "split", "group", "binomial"),
    "algebra_fraction_domain": ("fraction", "domain", "fraction_factor", "cancel"),
    "algebra_roots": ("root", "root_power", "extract", "rational_power"),
    "algebra_logarithms": ("log", "log_witness", "log_substitute", "log_finish"),
    "algebra_trig_identity": ("pythagorean_rule", "pythagorean_use"),
    "algebra_trig_values": ("trig", "angle", "period", "radians", "parity", "table"),
    "algebra_trig_equations": ("trig_equation", "isolate_trig", "families", "argument"),
    "algebra_order": ("inequality", "divide_negative", "divide_positive"),
    "algebra_absolute_cases": ("abs", "abs_nonnegative", "abs_or", "abs_and"),
}.items():
    for _suffix in _suffixes:
        RULE_TOPICS[f"lesson_alg_{_suffix}"] = _topic


def _n(value: object) -> CoreNode:
    return from_sympy(sympy.sympify(value))


def _bin(kind: T, a: CoreNode, b: CoreNode) -> CoreNode:
    return CoreNode.node(kind, a, b)


def _chain(kind: T, nodes: list[CoreNode]) -> CoreNode:
    result = nodes[0]
    for node in nodes[1:]:
        result = _bin(kind, result, node)
    return result


def _add(result: SolveResult, left: CoreNode, right: CoreNode, key: str, *args: CoreNode) -> bool:
    if left.structural_eq(right):
        return False
    result.add(Step(left, right, key, args=list(args)))
    return True


def _same(a: CoreNode, b: CoreNode) -> bool:
    return bool(sympy.simplify(to_sympy(a) - to_sympy(b)) == 0)


def _unwrap(node: CoreNode) -> CoreNode:
    while node.type in (T.BRACKET, T.POSITIVE) and len(node.children) == 1:
        node = node.children[0]
    return node


def _terms(node: CoreNode) -> list[CoreNode]:
    node = _unwrap(node)
    if node.type is T.ADD:
        return [term for child in node.children for term in _terms(child)]
    if node.type is T.SUBTRACT and len(node.children) == 2:
        return [
            *_terms(node.children[0]),
            *(CoreNode.node(T.NEGATIVE, term) for term in _terms(node.children[1])),
        ]
    return [node]


def _expand_once(node: CoreNode) -> tuple[CoreNode, str] | None:
    node = _unwrap(node)
    if node.type is T.NEGATIVE and len(node.children) == 1:
        terms = _terms(node.children[0])
        if len(terms) > 1:
            return (
                _chain(T.ADD, [CoreNode.node(T.NEGATIVE, term) for term in terms]),
                "lesson_alg_distribute",
            )
    if node.type is T.POWER and len(node.children) == 2:
        base, exponent = node.children
        power = to_sympy(exponent)
        if _unwrap(base).type in (T.ADD, T.SUBTRACT) and power.is_Integer and 2 <= power <= 6:
            return _chain(T.MULTIPLY, [base] * int(power)), "lesson_alg_repeat"
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        groups = [_terms(child) for child in node.children]
        count = 1
        for group in groups:
            count *= len(group)
        if 1 < count <= 32:
            distributed = [_chain(T.MULTIPLY, list(row)) for row in product(*groups)]
            return _chain(T.ADD, distributed), "lesson_alg_distribute"
    for index, child in enumerate(node.children):
        rewritten = _expand_once(child)
        if rewritten is not None:
            new_child, key = rewritten
            children = list(node.children)
            children[index] = new_child
            return CoreNode(type=node.type, value=node.value, children=children), key
    return None


def _expansion(step: Step, result: SolveResult) -> bool:
    assert step.left is not None and step.right is not None
    expression = to_sympy(step.left)
    if not isinstance(expression, sympy.Expr) or expression.is_polynomial() is not True:
        return False
    if not _same(step.left, step.right):
        return False
    current = step.left
    for _ in range(24):
        rewritten = _expand_once(current)
        if rewritten is None:
            break
        following, key = rewritten
        if sum(1 for _ in following.walk()) > 600:
            return False
        _add(result, current, following, key)
        current = following
    else:
        return False
    if not result:
        return False
    _add(result, current, step.right, "lesson_alg_collect")
    return True


def _factoring(step: Step, result: SolveResult) -> bool:
    assert step.left is not None and step.right is not None
    expression = to_sympy(step.left)
    if expression == to_sympy(step.right):
        return False
    if not isinstance(expression, sympy.Expr) or not expression.free_symbols:
        return False
    if expression.is_polynomial() is not True or not _same(step.left, step.right):
        return False
    expanded = sympy.expand(expression)
    # sympy distributes a numeric coefficient over a bracket, so compare after factor()
    if sympy.factor(to_sympy(step.right)) != sympy.factor(expanded):
        return False
    terms = sympy.Add.make_args(expanded)
    common = sympy.gcd_list(terms)
    if common not in (1, -1) and len(terms) > 1:
        quotient = sympy.cancel(expanded / common)
        factored = _bin(T.MULTIPLY, _n(common), _n(quotient))
        _add(result, step.left, factored, "lesson_alg_common", _n(common))
        # Do not hide a second, opaque factorization behind the common-factor rule.
        if sympy.factor(quotient) == quotient:
            return bool(result)
    if len(expression.free_symbols) != 1:
        return bool(result)
    symbol = next(iter(expression.free_symbols))
    polynomial = sympy.Poly(expanded, symbol)
    if polynomial.degree() != 2 or not all(c.is_Rational for c in polynomial.all_coeffs()):
        return bool(result)
    a, b, c = polynomial.all_coeffs()
    discriminant = b * b - 4 * a * c
    root = sympy.sqrt(discriminant)
    if root.is_Rational is not True:
        return bool(result)
    r, s = (-b - root) / (2 * a), (-b + root) / (2 * a)
    split = _chain(
        T.ADD, [_n(a * symbol**2), _n(-a * r * symbol), _n(-a * s * symbol), _n(a * r * s)]
    )
    start = list(result)[-1].right if result else step.left
    assert start is not None
    _add(result, start, split, "lesson_alg_split")
    bracket = _n(symbol - r)
    grouped = _bin(
        T.ADD, _bin(T.MULTIPLY, _n(a * symbol), bracket), _bin(T.MULTIPLY, _n(-a * s), bracket)
    )
    _add(result, split, grouped, "lesson_alg_group")
    _add(result, grouped, step.right, "lesson_alg_binomial")
    return bool(result)


def _fraction(step: Step, result: SolveResult) -> bool:
    assert step.left is not None and step.right is not None
    original = _unwrap(step.left)
    if original.type not in (T.FRACTION, T.DIVIDE) or len(original.children) != 2:
        return False
    numerator, denominator = original.children
    top, bottom = to_sympy(numerator), to_sympy(denominator)
    if not (top.is_polynomial() is True and bottom.is_polynomial() is True):
        return False
    if not bottom.free_symbols or not _same(original, step.right):
        return False
    common = sympy.gcd(top, bottom)
    if common in (1, -1) or common == 0:
        return False
    # Walk the original AST: translation may already have cancelled inner quotients.
    restrictions: list[CoreNode] = []
    for node in original.walk():
        if node.type in (T.FRACTION, T.DIVIDE) and len(node.children) == 2:
            restrictions.append(node.children[1])
        elif node.type is T.POWER and len(node.children) == 2:
            exponent = to_sympy(node.children[1])
            if exponent.is_negative is True:
                restrictions.append(node.children[0])
    seen: set[str] = set()
    for divisor in restrictions:
        condition = _bin(T.NOT_EQUALS, divisor, _n(0))
        signature = repr(condition.to_contract())
        if signature not in seen:
            result.add(Step(None, condition, "lesson_alg_domain", args=[condition]))
            seen.add(signature)
    factored = _bin(T.FRACTION, _n(sympy.factor(top)), _n(sympy.factor(bottom)))
    _add(result, original, factored, "lesson_alg_fraction_factor")
    reduced = _bin(T.FRACTION, _n(sympy.cancel(top / common)), _n(sympy.cancel(bottom / common)))
    _add(result, factored, reduced, "lesson_alg_cancel", _n(common))
    _add(result, reduced, step.right, "lesson_alg_collect")
    return True


def _roots(step: Step, result: SolveResult) -> bool:
    assert step.left is not None and step.right is not None
    node = _unwrap(step.left)
    if node.type is T.POWER and len(node.children) == 2:
        base, exponent = node.children
        a, power = to_sympy(base), to_sympy(exponent)
        if a.is_positive is not True or a.is_number is not True:
            return False
        if not isinstance(power, sympy.Rational) or power.q == 1 or power.q > 16:
            return False
        if not _same(node, step.right):
            return False
        root_node = CoreNode.node(T.ROOT, _n(power.q), base)
        middle = _bin(T.POWER, root_node, _n(power.p))
        _add(result, node, middle, "lesson_alg_rational_power")
        root_value = sympy.root(a, power.q)
        if root_value.is_Rational:
            evaluated = _bin(T.POWER, _n(root_value), _n(power.p))
            _add(result, middle, evaluated, "lesson_alg_extract")
            middle = evaluated
        _add(result, middle, step.right, "lesson_alg_collect")
        return True
    if node.type not in (T.ROOT2, T.ROOT):
        return False
    degree = sympy.Integer(2) if node.type is T.ROOT2 else to_sympy(node.children[0])
    radicand = node.children[-1]
    value = to_sympy(radicand)
    answer = to_sympy(step.right)
    if not degree.is_Integer or not 2 <= degree <= 16 or value.is_nonnegative is not True:
        return False
    if value.is_Rational is not True or not _same(node, step.right):
        return False
    if answer.is_Rational is True and answer.is_nonnegative is True:
        power_node = _bin(T.POWER, step.right, _n(degree))
        middle = (
            CoreNode.node(T.ROOT2, power_node)
            if node.type is T.ROOT2
            else CoreNode.node(T.ROOT, _n(degree), power_node)
        )
        _add(result, node, middle, "lesson_alg_root_power")
        _add(result, middle, step.right, "lesson_alg_extract")
        return True
    if value.is_Integer is not True or value <= 0 or value > 10**12:
        return False
    outside = sympy.Integer(1)
    inside = sympy.Integer(1)
    for prime, exponent in sympy.factorint(value).items():
        outside *= prime ** (exponent // int(degree))
        inside *= prime ** (exponent % int(degree))
    if outside == 1:
        return False
    power_node = _bin(T.MULTIPLY, _bin(T.POWER, _n(outside), _n(degree)), _n(inside))
    middle = (
        CoreNode.node(T.ROOT2, power_node)
        if node.type is T.ROOT2
        else CoreNode.node(T.ROOT, _n(degree), power_node)
    )
    _add(result, node, middle, "lesson_alg_root_power")
    _add(result, middle, step.right, "lesson_alg_extract")
    return True


def _logarithm(step: Step, result: SolveResult) -> bool:
    assert step.left is not None and step.right is not None
    node = _unwrap(step.left)
    if node.type not in (T.LOG, T.LOG10, T.LN):
        return False
    argument = node.children[0]
    base = node.children[1] if node.type is T.LOG else _n(10 if node.type is T.LOG10 else sympy.E)
    a, b, exponent = to_sympy(argument), to_sympy(base), to_sympy(step.right)
    if a.is_positive is not True or b.is_positive is not True or b == 1:
        return False
    if (
        exponent.is_real is not True
        or exponent.free_symbols
        or sympy.simplify(b**exponent - a) != 0
    ):
        return False
    power_node = _bin(T.POWER, base, step.right)
    witness = _bin(T.EQUALS, power_node, argument)
    result.add(Step(None, witness, "lesson_alg_log_witness", args=[witness]))
    middle = (
        CoreNode.node(T.LOG, power_node, base)
        if node.type is T.LOG
        else CoreNode.node(node.type, power_node)
    )
    _add(result, node, middle, "lesson_alg_log_substitute")
    _add(result, middle, step.right, "lesson_alg_log_finish")
    return True


def _identity(step: Step, result: SolveResult) -> bool:
    assert step.left is not None and step.right is not None
    terms = _terms(step.left)
    functions: dict[T, CoreNode] = {}
    for term in terms:
        term = _unwrap(term)
        if term.type is not T.POWER or len(term.children) != 2:
            return False
        function, exponent = term.children
        if function.type not in (T.SIN, T.COS) or to_sympy(exponent) != 2:
            return False
        functions[function.type] = function
    if len(terms) != 2 or set(functions) != {T.SIN, T.COS}:
        return False
    sine, cosine = functions[T.SIN], functions[T.COS]
    if len(sine.children) != 1 or len(cosine.children) != 1:
        return False
    if to_sympy(sine.children[0]) != to_sympy(cosine.children[0]):
        return False
    if to_sympy(sine.children[0]).has(sympy.zoo, sympy.nan, sympy.oo, -sympy.oo):
        return False
    if to_sympy(step.right) != 1:
        return False
    u = CoreNode.variable("u")
    rule = _bin(
        T.EQUALS,
        _bin(
            T.ADD,
            _bin(T.POWER, CoreNode.node(T.SIN, u), _n(2)),
            _bin(T.POWER, CoreNode.node(T.COS, u), _n(2)),
        ),
        _n(1),
    )
    result.add(Step(None, rule, "lesson_alg_pythagorean_rule", args=[rule]))
    _add(result, step.left, step.right, "lesson_alg_pythagorean_use")
    return True


_TRIG_FUNCTIONS = {T.SIN: sympy.sin, T.COS: sympy.cos, T.TAN: sympy.tan, T.COT: sympy.cot}


def _trig_value(step: Step, result: SolveResult) -> bool:
    assert step.left is not None and step.right is not None
    node = _unwrap(step.left)
    if node.type not in _TRIG_FUNCTIONS or len(node.children) != 1:
        return False
    angle = to_sympy(node.children[0])
    if not _same(node, step.right):
        return False
    if step.key.startswith("trig_neg_"):
        positive = -angle
        if not angle.could_extract_minus_sign():
            return False
        middle = CoreNode.node(node.type, _n(positive))
        if node.type is not T.COS:
            middle = CoreNode.node(T.NEGATIVE, middle)
        _add(result, node, middle, "lesson_alg_parity")
        if (
            not middle.structural_eq(step.right)
            and angle.is_number
            and sympy.denom(sympy.cancel(positive / sympy.pi)) in (1, 2, 3, 4, 6)
        ):
            _add(result, middle, step.right, "lesson_alg_table")
        return bool(result)
    coefficient = sympy.simplify(angle / sympy.pi)
    if coefficient.is_Rational is not True:
        return False
    period = sympy.pi if node.type in (T.TAN, T.COT) else 2 * sympy.pi
    reduced = sympy.Mod(coefficient, period / sympy.pi) * sympy.pi
    current = node
    if node.children[0].type is T.DEGREE:
        current = CoreNode.node(node.type, _n(angle))
        _add(result, node, current, "lesson_alg_radians")
    if reduced != angle:
        decomposition = _bin(T.EQUALS, _n(angle), _bin(T.ADD, _n(reduced), _n(angle - reduced)))
        result.add(Step(None, decomposition, "lesson_alg_angle", args=[decomposition]))
        following = CoreNode.node(node.type, _n(reduced))
        _add(result, current, following, "lesson_alg_period")
        current = following
    if step.key == "trig_rewrite_coterminal_pos":
        return bool(result)
    # A bounded table, not an explanation for arbitrary exact SymPy trig values.
    if sympy.denom(sympy.cancel(reduced / sympy.pi)) in (1, 2, 3, 4, 6):
        target = _n(_TRIG_FUNCTIONS[node.type](reduced))
        _add(result, current, target, "lesson_alg_table")
    return bool(result)


def _trig_equation(step: Step, result: SolveResult) -> bool:
    assert step.left is not None
    node = step.left
    if node.type is not T.EQUALS or len(node.children) != 2:
        return False
    expression = to_sympy(node.children[0]) - to_sympy(node.children[1])
    atoms = expression.atoms(sympy.sin, sympy.cos, sympy.tan, sympy.cot)
    if len(atoms) != 1 or len(expression.free_symbols) != 1:
        return False
    function = next(iter(atoms))
    symbol = next(iter(expression.free_symbols))
    if str(symbol) == "k":
        return False
    dummy = sympy.Dummy("f")
    polynomial = sympy.Poly(expression.xreplace({function: dummy}), dummy)
    if polynomial.degree() != 1:
        return False
    coefficient, constant = polynomial.all_coeffs()
    if coefficient.free_symbols or constant.free_symbols or coefficient.is_real is not True:
        return False
    value = sympy.simplify(-constant / coefficient)
    if value.is_real is not True:
        return False
    argument = function.args[0]
    affine = sympy.Poly(argument, symbol)
    if affine.degree() != 1:
        return False
    a, b = affine.all_coeffs()
    if a.is_real is not True or b.is_real is not True:
        return False
    k = sympy.Symbol("k")
    if function.func in (sympy.sin, sympy.cos):
        if (value >= -1) is sympy.false or (value <= 1) is sympy.false:
            return False
        if not (-1 <= value <= 1):
            return False
        if function.func is sympy.sin:
            alpha = sympy.asin(value)
            angles = [alpha + 2 * sympy.pi * k, sympy.pi - alpha + 2 * sympy.pi * k]
        else:
            alpha = sympy.acos(value)
            angles = [alpha + 2 * sympy.pi * k, -alpha + 2 * sympy.pi * k]
    else:
        alpha = sympy.atan(value) if function.func is sympy.tan else sympy.acot(value)
        angles = [alpha + sympy.pi * k]
    isolated = _bin(T.EQUALS, _n(function), _n(value))
    _add(result, node, isolated, "lesson_alg_isolate_trig")
    angle_cases = [_bin(T.EQUALS, _n(argument), _n(angle)) for angle in angles]
    cases = angle_cases[0] if len(angle_cases) == 1 else CoreNode.node(T.LIST, *angle_cases)
    _add(result, isolated, cases, "lesson_alg_families")
    answers = [_bin(T.EQUALS, _n(symbol), _n(sympy.expand((angle - b) / a))) for angle in angles]
    final = answers[0] if len(answers) == 1 else CoreNode.node(T.LIST, *answers)
    _add(result, cases, final, "lesson_alg_argument")
    result.set_solution(final)
    return True


def _inequality(step: Step, result: SolveResult) -> bool:
    assert step.left is not None and step.right is not None
    node = step.left
    flip = {
        T.LESS_THAN: T.GREATER_THAN,
        T.GREATER_THAN: T.LESS_THAN,
        T.LESS_THAN_EQUAL: T.GREATER_THAN_EQUAL,
        T.GREATER_THAN_EQUAL: T.LESS_THAN_EQUAL,
        T.NOT_EQUALS: T.NOT_EQUALS,
    }
    if node.type not in flip or len(node.children) != 2 or not step.args:
        return False
    divisor = to_sympy(step.args[0])
    if divisor.is_number is not True or divisor.is_real is not True or divisor == 0:
        return False
    negative = divisor.is_negative is True
    kind = flip[node.type] if negative else node.type
    divided = _bin(
        kind,
        _bin(T.FRACTION, node.children[0], step.args[0]),
        _bin(T.FRACTION, node.children[1], step.args[0]),
    )
    # Validate both parts; never bless a wrong pre-existing answer.
    if step.right.type is not kind or len(step.right.children) != 2:
        return False
    if not all(_same(a, b) for a, b in zip(divided.children, step.right.children, strict=True)):
        return False
    key = "lesson_alg_divide_negative" if negative else "lesson_alg_divide_positive"
    _add(result, node, divided, key, step.args[0])
    _add(result, divided, step.right, "lesson_alg_collect")
    return True


def _absolute(step: Step, result: SolveResult) -> bool:
    assert step.left is not None
    node = step.left
    if len(node.children) != 2:
        return False
    left, right = node.children
    if left.type is not T.ABS or len(left.children) != 1:
        if node.type is T.EQUALS and right.type is T.ABS and len(right.children) == 1:
            left, right = right, left
        else:
            return False
    value = to_sympy(right)
    if value.is_nonnegative is not True:
        return False
    argument = left.children[0]
    condition = _bin(T.GREATER_THAN_EQUAL, right, _n(0))
    if node.type is T.EQUALS:
        result.add(Step(None, condition, "lesson_alg_abs_nonnegative", args=[condition]))
        branches = [_bin(T.EQUALS, argument, right), _bin(T.EQUALS, argument, _n(-value))]
        key = "lesson_alg_abs_or"
    elif node.type in (T.LESS_THAN, T.LESS_THAN_EQUAL, T.GREATER_THAN, T.GREATER_THAN_EQUAL):
        less = node.type in (T.LESS_THAN, T.LESS_THAN_EQUAL)
        opposite = {
            T.LESS_THAN: T.GREATER_THAN,
            T.LESS_THAN_EQUAL: T.GREATER_THAN_EQUAL,
            T.GREATER_THAN: T.LESS_THAN,
            T.GREATER_THAN_EQUAL: T.LESS_THAN_EQUAL,
        }
        branches = [
            _bin(opposite[node.type], argument, _n(-value)),
            _bin(node.type, argument, right),
        ]
        key = "lesson_alg_abs_and" if less else "lesson_alg_abs_or"
    else:
        return False
    cases = CoreNode.node(T.LIST, *branches)
    _add(result, node, cases, key)
    result.set_solution(cases)
    return True


def enrich(step: Step) -> str | None:
    """Attach only derivable intermediate work, retaining the caller's step.

    Existing subresults are never replaced. Detail keys cannot trigger another
    enrichment, so recursive serializers and repeated calls are safe.
    """
    if step.subresult is not None or step.key.startswith("lesson_alg_") or step.left is None:
        return None
    result = SolveResult()
    title: str | None = None
    try:
        if step.key in ("abs_separate", "eq_abs_branch", "ineq_separate_abs"):
            if _absolute(step, result):
                title = "lesson_alg_abs"
        elif step.key == "trig_general_sol":
            if _trig_equation(step, result):
                title = "lesson_alg_trig_equation"
        elif step.right is not None:
            if step.key == "expand_msg" and _expansion(step, result):
                title = "lesson_alg_expand"
            elif step.key == "factorise_call" and _factoring(step, result):
                title = "lesson_alg_factor"
            elif step.key == "simplify" and _fraction(step, result):
                title = "lesson_alg_fraction"
            elif step.key in ("root_simplify", "calculate_short", "simplify"):
                if _roots(step, result):
                    title = "lesson_alg_root"
                elif _logarithm(step, result):
                    title = "lesson_alg_log"
            elif step.key == "substitute_pythagorean_identity" and _identity(step, result):
                title = "lesson_alg_trig"
            elif step.key in (
                "trig_table_calc",
                "trig_rewrite_coterminal_pos",
                "trig_neg_sin",
                "trig_neg_cos",
                "trig_neg_tan",
                "trig_neg_cot",
            ):
                if _trig_value(step, result):
                    title = "lesson_alg_trig"
            elif step.key in ("ineq_linear_div", "ineq_linear_div_neg") and _inequality(
                step, result
            ):
                title = "lesson_alg_inequality"
    except (SolveError, sympy.PolynomialError, ValueError, TypeError, ZeroDivisionError):
        # Unsupported presentation must never make a valid solver response fail.
        return None
    if title is None or not result:
        return None
    if result.solution is None:
        # A supported prefix is still useful; never label its last line with an
        # opaque, unproved remainder from the parent transformation.
        last = list(result)[-1].right
        if last is not None:
            result.set_solution(last)
    result.header = title
    step.subresult = result
    return title
