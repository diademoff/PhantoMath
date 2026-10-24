"""Original, bounded calculus lessons built from verifiable intermediate work.

Derivative cards apply only explicit elementary rules, one named rule with its
formula per stage, and every answer is checked against ``sympy.diff`` before it
is offered. Unsupported methods deliberately retain their existing details
instead of presenting a CAS answer as a derivation.
"""

from __future__ import annotations

from typing import TypedDict

import sympy

from .ast import CoreNode
from .node_types import CoreNodeType as T
from .solver.base import SolveError, SolveResult, Step


class _Template(TypedDict):
    arity: int
    templates: dict[str, str]


class _Article(TypedDict):
    title: str
    summary: str
    formula: str
    conditions: str
    example: str
    mistake: str


_TEXT = {
    "derivative": ("Вычисление производной", "Evaluate the derivative"),
    "integral": ("Вычисление интеграла", "Evaluate the integral"),
    "limit": ("Вычисление предела", "Evaluate the limit"),
    "sigma": ("Вычисление конечной суммы", "Evaluate the finite sum"),
    "sum_rule": ("Примените правило суммы или разности", "Apply the sum or difference rule"),
    "product_rule": ("Примените правило произведения", "Apply the product rule"),
    "quotient_rule": ("Примените правило частного", "Apply the quotient rule"),
    "chain_rule": ("Примените правило цепочки", "Apply the chain rule"),
    "power_rule": ("Примените правило степени", "Apply the power rule"),
    "basic_derivative": ("Вычислите табличную производную", "Evaluate the basic derivative"),
    "compose": ("Подставьте вычисленные производные", "Insert the computed derivatives"),
    "simplify": ("Упростите выражение", "Simplify the expression"),
    "domain": ("Сохраните ограничение области определения", "Keep the domain restriction"),
    "power_integral": ("Интегрируйте одночлен по правилу степени", "Integrate the monomial"),
    "linear_integral": (
        "Примените табличный интеграл и разделите на производную линейного аргумента",
        "Use the basic integral and divide by the derivative of the linear argument",
    ),
    "integral_sum": ("Сложите первообразные слагаемых", "Add the term antiderivatives"),
    "constant": (
        "Добавьте произвольную постоянную: её производная равна нулю",
        "Add an arbitrary constant: its derivative is zero",
    ),
    "check_primitive": (
        "Проверьте первообразную производной",
        "Differentiate to check the primitive",
    ),
    "newton": ("Примените формулу Ньютона — Лейбница", "Apply the fundamental theorem"),
    "upper": ("Подставьте верхний предел", "Substitute the upper bound"),
    "lower": ("Подставьте нижний предел", "Substitute the lower bound"),
    "subtract": ("Вычтите значение на нижнем пределе", "Subtract the lower-bound value"),
    "factor": ("Разложите числитель и знаменатель", "Factor numerator and denominator"),
    "cancel": (
        "Сократите общий множитель вне исключённых точек",
        "Cancel the common factor away from excluded points",
    ),
    "substitute": ("Подставьте предельное значение", "Substitute the limiting value"),
    "term": ("Подставьте значение индекса", "Substitute the index value"),
    "expand": ("Раскройте конечную сумму", "Expand the finite sum"),
    # Limits: textbook cards (CALC1). The first card names the method and its formula.
    "header_factor": (
        "Неопределённость 0/0: разложение и сокращение",
        "0/0 indeterminate form: factor and cancel",
    ),
    "header_inf": (
        "Неопределённость ∞/∞: деление на старшую степень",
        "∞/∞ indeterminate form: divide by the highest power",
    ),
    "header_sequence_root": (
        "Последовательность n^(1/n)",
        "The sequence n^(1/n)",
    ),
    "header_remarkable": ("Первый замечательный предел", "The first remarkable limit"),
    "header_conjugate": ("Умножение на сопряжённое", "Multiply by the conjugate"),
    "header_second_remarkable": (
        "Второй замечательный предел",
        "The second remarkable limit",
    ),
    "header_one_sided": ("Односторонний предел", "One-sided limit"),
    "header_dne": ("Предел не существует", "The limit does not exist"),
    "uncertainty_00": (
        "Неопределённость 0/0: и числитель, и знаменатель стремятся к нулю.",
        "0/0 indeterminate form: both numerator and denominator tend to zero.",
    ),
    "uncertainty_inf": (
        "Неопределённость ∞/∞: числитель и знаменатель неограниченно возрастают.",
        "∞/∞ indeterminate form: numerator and denominator both grow without bound.",
    ),
    "uncertainty_inf_minus_inf": (
        "Неопределённость ∞ − ∞: оба слагаемых неограниченно возрастают.",
        "∞ − ∞ indeterminate form: both terms grow without bound.",
    ),
    "uncertainty_inf_0": (
        "Неопределённость ∞^0: основание растёт, а показатель стремится к нулю.",
        "∞^0 indeterminate form: the base grows while the exponent tends to zero.",
    ),
    "uncertainty_1_inf": (
        "Неопределённость 1^∞: основание стремится к 1, а показатель — к бесконечности.",
        "1^∞ indeterminate form: the base tends to 1 and the exponent to infinity.",
    ),
    "cancel_factor": (
        "Сократим общий множитель ARG1 — это законно, поскольку ARG2.",
        "Cancel the common factor ARG1; this is legal because ARG2.",
    ),
    "divide_highest": (
        "Разделим числитель и знаменатель на старшую степень ARG1.",
        "Divide numerator and denominator by the highest power ARG1.",
    ),
    "inf_deg_lt": (
        "Степень числителя меньше степени знаменателя, поэтому предел равен 0.",
        "The numerator's degree is lower, so the limit is 0.",
    ),
    "inf_deg_eq": (
        "Степени равны, поэтому предел равен отношению старших коэффициентов: ARG1.",
        "The degrees are equal, so the limit is the ratio of the leading coefficients: ARG1.",
    ),
    "inf_deg_gt": (
        "Степень числителя больше степени знаменателя, поэтому предел равен ∞.",
        "The numerator's degree is higher, so the limit is ∞.",
    ),
    "inf_terms_zero": (
        "Слагаемые с 1/x^k стремятся к нулю, остаётся предел старших членов.",
        "The 1/x^k terms tend to zero; the limit of the leading terms remains.",
    ),
    "first_remarkable": ("Первый замечательный предел: ARG1.", "The first remarkable limit: ARG1."),
    "equivalents": (
        "Эквивалентные бесконечно малые при u → 0: sin u ~ u, tg u ~ u, "
        "1 − cos u ~ u²/2, ln(1 + u) ~ u, e^u − 1 ~ u.",
        "Equivalent infinitesimals as u → 0: sin u ~ u, tan u ~ u, "
        "1 − cos u ~ u²/2, ln(1 + u) ~ u, e^u − 1 ~ u.",
    ),
    "second_remarkable": (
        "Второй замечательный предел: ARG1.",
        "The second remarkable limit: ARG1.",
    ),
    "conjugate_multiply": (
        "Умножим числитель и знаменатель на сопряжённое выражение ARG1.",
        "Multiply numerator and denominator by the conjugate expression ARG1.",
    ),
    "conjugate_simplify": (
        "После умножения на сопряжённое и сокращения получаем:",
        "After multiplying by the conjugate and cancelling we get:",
    ),
    "abs_right": (
        "При подходе справа ARG1 > 0, поэтому |ARG1| = ARG1.",
        "Approaching from the right, ARG1 > 0, so |ARG1| = ARG1.",
    ),
    "abs_left": (
        "При подходе слева ARG1 < 0, поэтому |ARG1| = −ARG1.",
        "Approaching from the left, ARG1 < 0, so |ARG1| = −ARG1.",
    ),
    "one_sided_sign_right": (
        "При подходе справа знаменатель ARG1 положителен, поэтому дробь "
        "неограниченно возрастает: предел равен +∞.",
        "From the right the denominator ARG1 is positive, so the fraction grows "
        "without bound: the limit is +∞.",
    ),
    "one_sided_sign_left": (
        "При подходе слева знаменатель ARG1 отрицателен, поэтому дробь "
        "неограниченно убывает: предел равен −∞.",
        "From the left the denominator ARG1 is negative, so the fraction decreases "
        "without bound: the limit is −∞.",
    ),
    "limit_result": ("Значение предела: ARG1.", "The value of the limit is ARG1."),
    "limit_result_exp": ("Значение предела: e^ARG1.", "The value of the limit is e^ARG1."),
    "limit_oscillation": (
        "Функция ARG1 не стремится ни к какому числу: при ARG2 → ARG3 она колеблется.",
        "The function ARG1 approaches no number: as ARG2 → ARG3 it oscillates.",
    ),
    "sequence_root": (
        "Запишем n^(1/n) = e^(ln n / n).",
        "Write n^(1/n) = e^(ln n / n).",
    ),
    "log_over_n": (
        "ln n / n → 0: степень растёт быстрее логарифма, поэтому показатель стремится к 0.",
        "ln n / n → 0: the power grows faster than the logarithm, so the exponent tends to 0.",
    ),
    # Derivatives: the card names its method and every stage names one rule with its formula.
    "header_deriv_sum": ("Производная суммы", "Derivative of a sum"),
    "header_deriv_difference": ("Производная разности", "Derivative of a difference"),
    "header_deriv_constant_factor": ("Постоянный множитель", "Constant factor"),
    "header_deriv_power": ("Производная степени", "Derivative of a power"),
    "header_deriv_product": ("Производная произведения", "Derivative of a product"),
    "header_deriv_quotient": ("Производная частного", "Derivative of a quotient"),
    "header_deriv_chain": ("Производная сложной функции", "Derivative of a composite function"),
    "header_deriv_table": ("Табличная производная", "Table derivative"),
    "header_deriv_exponential": (
        "Производная показательной функции",
        "Derivative of an exponential function",
    ),
    "header_deriv_log": ("Логарифмическое дифференцирование", "Logarithmic differentiation"),
    "header_deriv_second": ("Вторая производная", "Second derivative"),
    "rule_sum": ("Производная суммы: ARG1.", "Derivative of a sum: ARG1."),
    "rule_difference": ("Производная разности: ARG1.", "Derivative of a difference: ARG1."),
    "rule_constant_factor": (
        "Постоянный множитель выносится за знак производной: ARG1.",
        "A constant factor comes out of the derivative: ARG1.",
    ),
    "rule_power": ("Правило степени: ARG1.", "Power rule: ARG1."),
    "rule_sqrt": ("Производная квадратного корня: ARG1.", "Derivative of a square root: ARG1."),
    "rule_reciprocal": (
        "Производная обратной величины: ARG1.",
        "Derivative of a reciprocal: ARG1.",
    ),
    "rule_product": ("Правило произведения: ARG1.", "Product rule: ARG1."),
    "rule_quotient": ("Правило частного: ARG1.", "Quotient rule: ARG1."),
    "rule_chain": (
        "Правило сложной функции: ARG1, где ARG2; ARG3.",
        "Chain rule: ARG1, where ARG2; ARG3.",
    ),
    "rule_table": ("Табличная производная: ARG1.", "Table derivative: ARG1."),
    "rule_exponential": (
        "Производная показательной функции: ARG1.",
        "Derivative of an exponential function: ARG1.",
    ),
    "part_first": (
        "Найдём производную первой части.",
        "Find the derivative of the first part.",
    ),
    "part_second": (
        "Найдём производную второй части.",
        "Find the derivative of the second part.",
    ),
    "part_rest": (
        "Найдём производную следующей части.",
        "Find the derivative of the next part.",
    ),
    "part_numerator": (
        "Найдём производную числителя.",
        "Find the derivative of the numerator.",
    ),
    "part_denominator": (
        "Найдём производную знаменателя.",
        "Find the derivative of the denominator.",
    ),
    "part_argument": (
        "Найдём производную внутренней функции.",
        "Find the derivative of the inner function.",
    ),
    "compose_derivatives": (
        "Подставим найденные производные.",
        "Insert the computed derivatives.",
    ),
    "simplify_result": ("Упростим результат.", "Simplify the result."),
    "log_take": (
        "Логарифмируем обе части: ARG1.",
        "Take the logarithm of both sides: ARG1.",
    ),
    "log_differentiate": (
        "Дифференцируем обе части: ARG1.",
        "Differentiate both sides: ARG1.",
    ),
    "log_solve": (
        "Умножим на y и подставим y = ARG1.",
        "Multiply by y and substitute y = ARG1.",
    ),
    "second_first": (
        "Сначала найдём первую производную — со всеми её правилами.",
        "First find the derivative, with all of its rules.",
    ),
    "second_again": (
        "Вторая производная — производная первой: ARG1.",
        "The second derivative is the derivative of the first: ARG1.",
    ),
    "header_equivalents": (
        "Эквивалентные бесконечно малые",
        "Equivalent infinitesimals",
    ),
    "equivalents_replace": (
        "Заменим каждый множитель эквивалентным: ARG1.",
        "Replace every factor by its equivalent: ARG1.",
    ),
    # Integrals: the first card names the textbook method and shows its formula.
    "header_int_table": ("Табличный интеграл", "Basic (table) integral"),
    "header_int_linear": ("Линейная замена", "Linear substitution"),
    "header_int_sum": ("Линейность интеграла", "Linearity of the integral"),
    "header_int_substitution": ("Замена переменной", "Integration by substitution"),
    "header_int_half_angle": ("Формула половинного угла", "Half-angle formula"),
    "header_int_identity": ("Тождество и замена", "Identity and substitution"),
    "header_int_parts": ("Интегрирование по частям", "Integration by parts"),
    "header_int_parts_first": (
        "Первое интегрирование по частям",
        "First integration by parts",
    ),
    "header_int_parts_second": (
        "Второе интегрирование по частям",
        "Second integration by parts",
    ),
    "header_int_parts_next": (
        "Следующее интегрирование по частям",
        "Next integration by parts",
    ),
    "header_int_frac": (
        "Разложение на простейшие дроби",
        "Decomposition into partial fractions",
    ),
    # A stage whose formula already shows the fact carries no ARG: the text
    # only names the move, the formula under it is the statement.
    "int_table_rule": ("Табличный интеграл.", "Basic integral."),
    "int_linear_rule": ("Линейный аргумент.", "Linear argument."),
    "int_sum_rule": ("Линейность интеграла.", "Linearity of the integral."),
    "int_expand": ("Сначала раскроем числитель.", "First expand the numerator."),
    "int_substitute": ("Сделаем замену.", "Make the substitution."),
    "int_differential": ("Найдём дифференциал.", "Find the differential."),
    "int_rewrite": (
        "Перепишем интеграл в новой переменной.",
        "Rewrite the integral in the new variable.",
    ),
    "int_inner_table": ("Табличный интеграл.", "Basic integral."),
    "int_term_table": ("Табличный интеграл.", "Basic integral."),
    "int_back_sub": ("Вернёмся к переменной x.", "Back-substitute."),
    # These two chips show the identity itself, which the stage formula (an
    # integral before and after) does not contain: the ARG is not a repeat.
    "int_identity": ("Применим тождество: ARG1.", "Apply the identity: ARG1."),
    "int_half_angle": (
        "Применим формулу половинного угла: ARG1.",
        "Apply the half-angle formula: ARG1.",
    ),
    "int_sine_half_angle": (
        "Выразим sin x через t.",
        "Express sin x in terms of t.",
    ),
    "int_dx_expr": ("Выразим dx.", "Express dx."),
    "int_from_substitution": ("Выразим x из замены.", "Express x from the substitution."),
    # Integration by parts: the formula, the choice of u and dv, du and v.
    "int_parts_formula": (
        "Формула интегрирования по частям.",
        "Integration by parts.",
    ),
    "int_parts_choose": ("Выберем u и dv.", "Choose u and dv."),
    "int_parts_differential": ("Найдём du и v.", "Find du and v."),
    "int_parts_apply": ("Применим формулу.", "Apply the formula."),
    "int_parts_answer": (
        "Приведём ответ к виду учебника.",
        "Bring the answer to the textbook form.",
    ),
    "int_parts_remainder": (
        "Осталось вычислить последний интеграл.",
        "Evaluate the remaining integral.",
    ),
    "int_parts_cyclic_define": (
        "Обозначим искомый интеграл через I.",
        "Name the unknown integral I.",
    ),
    "int_parts_cyclic_equation": (
        "Подставим второе применение в первое.",
        "Insert the second application into the first.",
    ),
    "int_parts_cyclic_move": (
        "Перенесём интеграл влево.",
        "Move the integral to the left.",
    ),
    "int_parts_cyclic_value": ("Отсюда найдём I.", "Hence find I."),
    # Rational functions: division, factoring, the decomposition, its coefficients.
    "int_frac_divide": (
        "Выделим целую часть.",
        "Divide the polynomials first.",
    ),
    "int_frac_factor": ("Разложим знаменатель.", "Factor the denominator."),
    "int_frac_form": (
        "Ищем разложение на простейшие дроби.",
        "Write the partial-fraction decomposition.",
    ),
    "int_frac_equations": (
        "Приравняем числители (подставим корни знаменателя).",
        "Equate the numerators (substitute the roots of the denominator).",
    ),
    "int_frac_coeffs": ("Найдём коэффициенты.", "Find the coefficients."),
    "int_frac_numbers": (
        "Разложение с коэффициентами.",
        "The decomposition with numbers.",
    ),
    "int_answer": (
        "Запишем ответ в порядке учебника.",
        "Write the answer in textbook order.",
    ),
    "int_simplify": ("Упростим результат.", "Simplify the result."),
    "int_frac_square": ("Выделим полный квадрат.", "Complete the square."),
    "int_frac_split": ("Разобьём числитель.", "Split the numerator."),
    "int_frac_ln": (
        "Замена ARG1: числитель — производная знаменателя.",
        "Substitution ARG1: the numerator is the derivative of the denominator.",
    ),
    "header_int_square": ("Выделение полного квадрата", "Completing the square"),
    "header_int_nonelementary": (
        "Первообразная не элементарна",
        "Non-elementary antiderivative",
    ),
    "int_nonelementary": (
        "Первообразная не выражается через элементарные функции (это следует из теоремы Лиувилля).",
        "The antiderivative is not an elementary function (Liouville's theorem).",
    ),
    # Definite integrals: Newton–Leibniz, parity, improper integrals.
    "header_int_newton": ("Формула Ньютона — Лейбница", "Fundamental theorem of calculus"),
    "header_int_parity": ("Чётность и симметрия отрезка", "Parity on a symmetric interval"),
    "header_int_improper": ("Несобственный интеграл", "Improper integral"),
    "header_int_diverges": ("Интеграл расходится", "The integral diverges"),
    "header_int_euler_poisson": (
        "Интеграл Эйлера — Пуассона",
        "The Euler–Poisson integral",
    ),
    "header_int_subst_limits": (
        "Замена переменной и новые пределы",
        "Substitution with new bounds",
    ),
    "int_newton_formula": (
        "Формула Ньютона — Лейбница.",
        "The fundamental theorem of calculus.",
    ),
    "int_newton_primitive": ("Найдём первообразную.", "Find an antiderivative."),
    "int_newton_bounds": ("Подставим пределы.", "Substitute the bounds."),
    "int_newton_subst": ("Раскроем разность.", "Expand the difference."),
    "int_newton_upper": (
        "Значение на верхнем пределе.",
        "Value at the upper bound.",
    ),
    "int_newton_lower": (
        "Значение на нижнем пределе.",
        "Value at the lower bound.",
    ),
    "int_newton_calc": ("Вычислим разность.", "Evaluate the difference."),
    "int_newton_sub_limits": ("Новые пределы.", "The new bounds."),
    "int_newton_sub_diff": (
        "Подставим новые пределы.",
        "Substitute the new bounds.",
    ),
    "int_newton_sub_rewrite": (
        "Перейдём к переменной t.",
        "Change to the variable t.",
    ),
    "int_imp_formula": (
        "Несобственный интеграл: перейдём к пределу.",
        "Improper integral: pass to a limit.",
    ),
    "int_imp_rewrite": ("Перейдём к пределу.", "Pass to the limit."),
    "int_imp_primitive": ("Первообразная в пределе.", "The primitive under the limit."),
    "int_imp_value": ("Вычислим предел.", "Evaluate the limit."),
    "int_imp_diverges": (
        "Предел бесконечен, поэтому интеграл расходится.",
        "The limit is infinite, so the integral diverges.",
    ),
    "int_parity_odd": (
        "Проверим нечётность функции.",
        "Check that the function is odd.",
    ),
    "int_parity_even": (
        "Проверим чётность функции.",
        "Check that the function is even.",
    ),
    "int_parity_even_calc": ("Вычислим.", "Evaluate."),
    "int_parity_zero": (
        "Интеграл нечётной функции по симметричному отрезку равен нулю.",
        "An odd function integrates to zero on a symmetric interval.",
    ),
    "int_euler_poisson": (
        "Интеграл Эйлера — Пуассона.",
        "The Euler–Poisson integral.",
    ),
    # First-order differential equations (ODE3): the header names the method,
    # every stage names one move; formulas are the stage's own left/right.
    "ode_header_separable": (
        "Уравнение с разделяющимися переменными",
        "Separable equation",
    ),
    "ode_header_homogeneous": ("Однородное уравнение", "Homogeneous equation"),
    "ode_header_linear": (
        "Линейное уравнение первого порядка",
        "First-order linear equation",
    ),
    "ode_header_bernoulli": ("Уравнение Бернулли", "Bernoulli equation"),
    "ode_header_exact": (
        "Уравнение в полных дифференциалах",
        "Exact differential equation",
    ),
    "ode_condition_header": ("Начальное условие", "Initial condition"),
    "ode_header_integrals": (
        "Вычислите интегралы",
        "Evaluate the integrals",
    ),
    # The two cards of «Подробнее» name their side, not the same heading twice.
    "ode_integral_left": ("Интеграл левой части", "Integral of the left side"),
    "ode_integral_right": ("Интеграл правой части", "Integral of the right side"),
    "ode_sep_derivative": (
        "Запишем производную как отношение дифференциалов.",
        "Write the derivative as a ratio of differentials.",
    ),
    "ode_sep_separate": ("Разделим переменные.", "Separate the variables."),
    "ode_sep_integrate": (
        "Проинтегрируем обе части.",
        "Integrate both sides.",
    ),
    "ode_sep_primitive": ("Вычислим интегралы.", "Evaluate the integrals."),
    "ode_sep_implicit": (
        "Вычислим интегралы и оставим ответ в неявном виде.",
        "Evaluate the integrals and keep the answer implicit.",
    ),
    "ode_sep_express": ("Выразим y.", "Express y."),
    "ode_sep_express_log": (
        "Выразим y; постоянная C = ±ARG1.",
        "Express y; the constant C = ±ARG1.",
    ),
    "ode_sep_express_rename": (
        "Выразим y, переобозначив постоянную.",
        "Express y, renaming the constant.",
    ),
    "ode_sep_express_p": ("Выразим p.", "Express p."),
    "ode_sep_express_log_p": (
        "Выразим p; постоянная C₁ = ±ARG1.",
        "Express p; the constant C₁ = ±ARG1.",
    ),
    "ode_sep_express_rename_p": (
        "Выразим p, переобозначив постоянную.",
        "Express p, renaming the constant.",
    ),
    "ode_hom_form": (
        "Правая часть зависит только от y/x.",
        "The right side depends only on y/x.",
    ),
    # The formula of a sentence is a part (the card passes the node), not typed text.
    "ode_hom_substitute": ("Положим ARG1.", "Set ARG1."),
    "ode_hom_equation": (
        "Подставим y и y′ в уравнение.",
        "Substitute y and y′ into the equation.",
    ),
    "ode_hom_reduce": ("Приведём подобные.", "Collect like terms."),
    "ode_hom_separate": ("Разделим переменные.", "Separate the variables."),
    "ode_hom_integrate": ("Проинтегрируем обе части.", "Integrate both sides."),
    "ode_hom_primitive": ("Вычислим интегралы.", "Evaluate the integrals."),
    "ode_hom_back": (
        "Вернёмся к y/x и запишем ответ.",
        "Substitute back y/x and write the answer.",
    ),
    "ode_lin_substitute": ("Положим ARG1.", "Set ARG1."),
    "ode_lin_substitute_z": ("Положим ARG1.", "Set ARG1."),
    "ode_lin_insert": (
        "Подставим y и y′ в уравнение.",
        "Substitute y and y′ into the equation.",
    ),
    "ode_lin_insert_z": (
        "Подставим z и z′ в уравнение.",
        "Substitute z and z′ into the equation.",
    ),
    "ode_lin_choose_v": (
        "Выберем v так, чтобы ARG1.",
        "Choose v so that ARG1.",
    ),
    "ode_lin_v": ("Решим уравнение для v.", "Solve the equation for v."),
    "ode_lin_v_value": ("Запишем найденное v.", "Write the found v."),
    "ode_lin_u_equation": (
        "Останется уравнение для u.",
        "The equation for u remains.",
    ),
    "ode_lin_u": ("Найдём u.", "Find u."),
    "ode_lin_u_value": ("Запишем найденное u.", "Write the found u."),
    # The stage shows ``y = uv → …`` itself: the text must not repeat the formula.
    "ode_lin_back": ("Подставим найденные u и v.", "Substitute the found u and v."),
    "ode_lin_back_z": ("Подставим найденные u и v.", "Substitute the found u and v."),
    "ode_lin_simplify": (
        "Упростим произведение и запишем ответ.",
        "Simplify the product and write the answer.",
    ),
    "ode_bern_divide": (
        "Разделим уравнение на yⁿ.",
        "Divide the equation by yⁿ.",
    ),
    "ode_bern_substitute": (
        "Положим ARG1.",
        "Set ARG1.",
    ),
    "ode_bern_linear": (
        "Получим линейное уравнение для z.",
        "Obtain a linear equation for z.",
    ),
    "ode_bern_back": (
        "Вернёмся к ARG1.",
        "Substitute back to ARG1.",
    ),
    "ode_ex_differential": (
        "Запишем уравнение в дифференциалах.",
        "Write the equation in differentials.",
    ),
    "ode_ex_pq": ("Запишем P и Q.", "Write P and Q."),
    "ode_ex_check": ("Проверим условие точности.", "Check the exactness condition."),
    "ode_ex_potential": ("Найдём потенциал U(x, y).", "Find the potential U(x, y)."),
    "ode_ex_answer": ("Запишем решение.", "Write the solution."),
    "ode_condition": (
        "Подставим начальное условие.",
        "Substitute the initial condition.",
    ),
    "ode_condition_substitute": (
        "Подставим x₀ в общее решение.",
        "Substitute x₀ into the general solution.",
    ),
    "ode_condition_value": ("Найдём постоянную.", "Find the constant."),
    "ode_condition_answer": (
        "Подставим постоянную в решение.",
        "Substitute the constant into the solution.",
    ),
    # Second-order equations (ODE4): headers, step headings and stages.
    "ode_header_reduction": ("Понижение порядка", "Reduction of order"),
    "ode_header_constant": (
        "Линейное однородное уравнение с постоянными коэффициентами",
        "Linear homogeneous equation with constant coefficients",
    ),
    "ode_header_special": (
        "Неоднородное уравнение со специальной правой частью",
        "Nonhomogeneous equation with a special right side",
    ),
    "ode_header_characteristic": (
        "Характеристическое уравнение",
        "Characteristic equation",
    ),
    "ode_step_homogeneous": (
        "Общее решение однородного уравнения",
        "General solution of the homogeneous equation",
    ),
    "ode_step_particular": ("Частное решение", "Particular solution"),
    "ode_step_general": ("Общее решение", "General solution"),
    "ode_step_conditions": (
        "Подставим начальные условия",
        "Substitute the initial conditions",
    ),
    "ode_reduce_first": (
        "Проинтегрируем обе части по x.",
        "Integrate both sides with respect to x.",
    ),
    "ode_reduce_second": ("Проинтегрируем ещё раз.", "Integrate once more."),
    "ode_reduce_substitute": ("Положим ARG1.", "Set ARG1."),
    "ode_reduce_equation": (
        "Получим уравнение первого порядка для p.",
        "Obtain a first-order equation for p.",
    ),
    "ode_reduce_solution": (
        "Запишем решение уравнения для p.",
        "Write the solution for p.",
    ),
    "ode_reduce_integrate": (
        "Вернёмся к ARG1 и проинтегрируем.",
        "Return to ARG1 and integrate.",
    ),
    "ode_char_equation": (
        "Составим характеристическое уравнение.",
        "Write the characteristic equation.",
    ),
    "ode_char_roots": (
        "Найдём корни характеристического уравнения.",
        "Find the roots of the characteristic equation.",
    ),
    "ode_char_discriminant": ("Вычислим дискриминант.", "Calculate the discriminant."),
    "ode_char_complex_roots": (
        "Запишем комплексные корни.",
        "Write the complex roots.",
    ),
    "ode_char_case_distinct": (
        "Корни действительные и различные: фундаментальная система решений.",
        "The roots are real and distinct: the fundamental system.",
    ),
    "ode_char_case_double": (
        "Кратный корень: фундаментальная система решений.",
        "A double root: the fundamental system.",
    ),
    "ode_char_case_complex": (
        "Корни комплексные: α = ARG1, β = ARG2 — фундаментальная система решений.",
        "Complex roots: α = ARG1, β = ARG2 — the fundamental system.",
    ),
    "ode_char_general": (
        "Общее решение — линейная комбинация фундаментальной системы.",
        "The general solution is a linear combination of the fundamental system.",
    ),
    "ode_special_form": (
        "Подберём частное решение по виду правой части.",
        "Choose a particular solution by the form of the right side.",
    ),
    "ode_special_form_exp_resonance": (
        "Подберём частное решение по виду правой части: α = ARG1 — корень характеристического "
        "уравнения кратности ARG2, поэтому множитель ARG3.",
        "Choose a particular solution by the form of the right side: α = ARG1 is a root of the "
        "characteristic equation of multiplicity ARG2, hence the factor ARG3.",
    ),
    "ode_special_form_trig_resonance": (
        "Подберём частное решение по виду правой части: числа ±ARG1 — корни характеристического "
        "уравнения, поэтому множитель x.",
        "Choose a particular solution by the form of the right side: the numbers ±ARG1 are roots "
        "of the characteristic equation, hence the factor x.",
    ),
    "ode_special_form_poly_resonance": (
        "Подберём частное решение по виду правой части: 0 — корень характеристического уравнения "
        "кратности ARG1, поэтому множитель ARG2.",
        "Choose a particular solution by the form of the right side: 0 is a root of the "
        "characteristic equation of multiplicity ARG1, hence the factor ARG2.",
    ),
    "ode_special_derivatives": ("Найдём производные.", "Find the derivatives."),
    "ode_special_substitute": (
        "Подставим ỹ, ỹ′ и ỹ″ в уравнение.",
        "Substitute ỹ, ỹ′ and ỹ″ into the equation.",
    ),
    "ode_special_equate": (
        "Приравняем коэффициенты при одинаковых функциях.",
        "Equate the coefficients of like terms.",
    ),
    "ode_special_solve": (
        "Решим систему для коэффициентов.",
        "Solve the system for the coefficients.",
    ),
    "ode_special_particular": (
        "Запишем частное решение.",
        "Write the particular solution.",
    ),
    "ode_special_general": (
        "Общее решение — сумма решения однородного уравнения и частного решения.",
        "The general solution is the homogeneous solution plus the particular one.",
    ),
    "ode_conditions_system": (
        "Подставим начальные условия в общее решение и в его производную.",
        "Substitute the initial conditions into the general solution and its derivative.",
    ),
    "ode_conditions_values": ("Найдём постоянные.", "Find the constants."),
    "ode_conditions_answer": (
        "Подставим постоянные в общее решение.",
        "Substitute the constants into the general solution.",
    ),
}

_ARITY = {
    # A sentence names its formula as a part (the card builds the node).
    "ode_hom_substitute": 1,
    "ode_lin_substitute": 1,
    "ode_lin_substitute_z": 1,
    "ode_lin_choose_v": 1,
    "ode_bern_substitute": 1,
    "ode_bern_back": 1,
    "ode_reduce_substitute": 1,
    "ode_reduce_integrate": 1,
    "limit_result_exp": 1,
    "cancel_factor": 2,
    "divide_highest": 1,
    "inf_deg_eq": 1,
    "first_remarkable": 1,
    "second_remarkable": 1,
    "conjugate_multiply": 1,
    "abs_right": 1,
    "abs_left": 1,
    "one_sided_sign_right": 1,
    "one_sided_sign_left": 1,
    "limit_result": 1,
    "limit_oscillation": 3,
    "rule_sum": 1,
    "rule_difference": 1,
    "rule_constant_factor": 1,
    "rule_power": 1,
    "rule_sqrt": 1,
    "rule_reciprocal": 1,
    "rule_product": 1,
    "rule_quotient": 1,
    "rule_chain": 3,
    "rule_table": 1,
    "rule_exponential": 1,
    "log_take": 1,
    "log_differentiate": 1,
    "log_solve": 1,
    "second_again": 1,
    "equivalents_replace": 1,
    # Every chip is now arg-free: the stage formula is the statement, the rule
    # itself lives in the stage's theory article (the chip must not run off the
    # phone edge with a long formula).
    "int_identity": 1,
    "int_half_angle": 1,
    # The substitution stage names the polynomial t = Q: a short fact, not a rule.
    "int_frac_ln": 1,
    # Two parameters of the complex root α ± βi.
    "ode_char_case_complex": 2,
    # α, its multiplicity and the resonance factor.
    "ode_special_form_exp_resonance": 3,
    # The root ωi of ±ωi.
    "ode_special_form_trig_resonance": 1,
    # e^(C₀) of C = ±e^(C₀).
    "ode_sep_express_log": 1,
    "ode_sep_express_log_p": 1,
    # The multiplicity of the zero root and the resonance factor.
    "ode_special_form_poly_resonance": 2,
}

TEMPLATES: dict[str, _Template] = {
    f"lesson_calc_{key}": {
        "arity": _ARITY.get(key, 0),
        "templates": {"ru": ru, "default": en},
    }
    for key, (ru, en) in _TEXT.items()
}


def _article(
    title: str, summary: str, formula: str, conditions: str, example: str, mistake: str
) -> _Article:
    return {
        "title": title,
        "summary": summary,
        "formula": formula,
        "conditions": conditions,
        "example": example,
        "mistake": mistake,
    }


ARTICLES: dict[str, dict[str, _Article]] = {
    "calculus_derivative_sum": {
        "ru": _article(
            "Производная суммы",
            "Дифференцируйте каждое слагаемое по одной переменной.",
            "(u ± v)' = u' ± v'",
            "Обе функции дифференцируемы в рассматриваемой точке.",
            "d(x² + 3x)/dx = 2x + 3",
            "Не заменяйте производную суммы произведением.",
        ),
        "en": _article(
            "Derivative of a sum",
            "Differentiate each term with respect to the same variable.",
            "(u ± v)' = u' ± v'",
            "Both terms must be differentiable at the point.",
            "d(x² + 3x)/dx = 2x + 3",
            "Do not turn a sum into a product of derivatives.",
        ),
    },
    "calculus_derivative_product": {
        "ru": _article(
            "Правило произведения",
            "По очереди дифференцируйте каждый множитель.",
            "(uv)' = u'v + uv'",
            "Множители дифференцируемы; остальные сохраняются.",
            "d(x sin x)/dx = sin x + x cos x",
            "Ответ u'v' неверен: нужны два слагаемых.",
        ),
        "en": _article(
            "Product rule",
            "Differentiate one factor at a time and keep the other factors.",
            "(uv)' = u'v + uv'",
            "The factors must be differentiable.",
            "d(x sin x)/dx = sin x + x cos x",
            "u'v' is not the derivative of uv.",
        ),
    },
    "calculus_derivative_quotient": {
        "ru": _article(
            "Правило частного",
            "В числителе вычитайте произведения в правильном порядке.",
            "(u/v)' = (u'v − uv')/v²",
            "v ≠ 0; обе функции дифференцируемы.",
            "d(x/(x+1))/dx = 1/(x+1)², x ≠ −1",
            "Не меняйте порядок вычитания.",
        ),
        "en": _article(
            "Quotient rule",
            "Subtract the cross products in the stated order.",
            "(u/v)' = (u'v − uv')/v²",
            "v must be nonzero; both functions differentiable.",
            "d(x/(x+1))/dx = 1/(x+1)², x ≠ −1",
            "Reversing the subtraction changes the sign.",
        ),
    },
    "calculus_derivative_chain": {
        "ru": _article(
            "Правило цепочки",
            "Производную внешней функции умножьте на производную внутренней.",
            "d f(g(x))/dx = f'(g(x))g'(x)",
            "Обе нужные производные существуют.",
            "d sin(x²)/dx = cos(x²)·2x",
            "Не теряйте множитель g'(x).",
        ),
        "en": _article(
            "Chain rule",
            "Multiply the outer derivative by the inner derivative.",
            "d f(g(x))/dx = f'(g(x))g'(x)",
            "Both required derivatives must exist.",
            "d sin(x²)/dx = cos(x²)·2x",
            "Do not omit g'(x).",
        ),
    },
    "calculus_derivative": {
        "ru": _article(
            "Переменная дифференцирования",
            "В записи d/dx остальные переменные постоянны.",
            "d(xⁿ)/dx = nxⁿ⁻¹; dc/dx = 0",
            "Правило степени действует в области функции.",
            "d(yx²)/dx = 2yx",
            "d(y)/dx = 0, если y не зависит от x.",
        ),
        "en": _article(
            "Differentiation variable",
            "In d/dx, independent other variables are constants.",
            "d(xⁿ)/dx = nxⁿ⁻¹; dc/dx = 0",
            "Use the power rule within the function's domain.",
            "d(yx²)/dx = 2yx",
            "d(y)/dx is zero when y is independent of x.",
        ),
    },
    "calculus_integral": {
        "ru": _article(
            "Первообразная многочлена",
            "Интегрируйте одночлены и добавьте постоянную.",
            "∫ axⁿ dx = axⁿ⁺¹/(n+1) + C",
            "Для многочлена n — целое неотрицательное число.",
            "∫ (3x² + 2) dx = x³ + 2x + C",
            "Не забывайте делить на новую степень.",
        ),
        "en": _article(
            "Polynomial antiderivative",
            "Integrate the monomials and add a constant.",
            "∫ axⁿ dx = axⁿ⁺¹/(n+1) + C",
            "For polynomials n is a nonnegative integer.",
            "∫ (3x² + 2) dx = x³ + 2x + C",
            "Divide by the new exponent, not the old one.",
        ),
    },
    "calculus_integral_table": {
        "ru": _article(
            "Таблица интегралов",
            "Табличные интегралы и их линейные комбинации — основа всех замен.",
            "∫ xⁿ dx = xⁿ⁺¹/(n+1) + C (n ≠ −1); ∫ dx/x = ln|x| + C; "
            "∫ eˣ dx = eˣ + C; ∫ sin x dx = −cos x + C; ∫ cos x dx = sin x + C; "
            "∫ dx/(1+x²) = arctg x + C",
            "n ≠ −1; знаменатель не равен нулю; под логарифмом — модуль аргумента.",
            "∫ (3x² + 2 sin x) dx = x³ − 2 cos x + C",
            "Не забывайте модуль в ln|x| и + C.",
        ),
        "en": _article(
            "Table of integrals",
            "The standard integrals and their linear combinations underlie every substitution.",
            "∫ xⁿ dx = xⁿ⁺¹/(n+1) + C (n ≠ −1); ∫ dx/x = ln|x| + C; "
            "∫ eˣ dx = eˣ + C; ∫ sin x dx = −cos x + C; ∫ cos x dx = sin x + C; "
            "∫ dx/(1+x²) = arctg x + C",
            "n ≠ −1; denominators are nonzero; a logarithm takes the absolute value.",
            "∫ (3x² + 2 sin x) dx = x³ − 2 cos x + C",
            "Keep the absolute value in ln|x| and the + C.",
        ),
    },
    "calculus_integral_linearity": {
        "ru": _article(
            "Линейность интеграла",
            "Интеграл суммы равен сумме интегралов, постоянный множитель выносят за знак "
            "интеграла.",
            "∫ (f(x) + g(x)) dx = ∫ f(x) dx + ∫ g(x) dx; ∫ c f(x) dx = c ∫ f(x) dx",
            "Оба интеграла существуют; c — постоянная.",
            "∫ (3x² + 2 sin x) dx = ∫ 3x² dx + ∫ 2 sin x dx = x³ − 2 cos x + C",
            "Множитель выносят целиком: ∫ 2f dx = 2∫ f dx, а не ∫ 2f dx = 2x ∫ f dx.",
        ),
        "en": _article(
            "Linearity of the integral",
            "The integral of a sum is the sum of the integrals; a constant factor moves "
            "outside the integral sign.",
            "∫ (f(x) + g(x)) dx = ∫ f(x) dx + ∫ g(x) dx; ∫ c f(x) dx = c ∫ f(x) dx",
            "Both integrals exist; c is a constant.",
            "∫ (3x² + 2 sin x) dx = ∫ 3x² dx + ∫ 2 sin x dx = x³ − 2 cos x + C",
            "Move the whole factor: ∫ 2f dx = 2∫ f dx, not ∫ 2f dx = 2x ∫ f dx.",
        ),
    },
    "calculus_integral_substitution": {
        "ru": _article(
            "Замена переменной",
            "Введите t = g(x); тогда dt = g′(x) dx и интеграл сводится к табличному.",
            "∫ f(g(x))g′(x) dx = ∫ f(t) dt, t = g(x)",
            "g дифференцируема; в определённом интеграле пересчитайте пределы.",
            "∫ 2x cos(x²) dx = ∫ cos t dt = sin t + C = sin(x²) + C",
            "Не забудьте вернуться к x (или пересчитать пределы).",
        ),
        "en": _article(
            "Substitution",
            "Let t = g(x); then dt = g′(x) dx and the integral becomes a table entry.",
            "∫ f(g(x))g′(x) dx = ∫ f(t) dt, t = g(x)",
            "g is differentiable; in a definite integral also change the bounds.",
            "∫ 2x cos(x²) dx = ∫ cos t dt = sin t + C = sin(x²) + C",
            "Do not forget to return to x (or to change the bounds).",
        ),
    },
    "calculus_integral_parts": {
        "ru": _article(
            "Интегрирование по частям",
            "Формула переносит интеграл на более простой. За u берут то, что упрощается при "
            "дифференцировании: ln x, arctg x, многочлен; dv — оставшуюся часть.",
            "∫ u dv = uv − ∫ v du",
            "u и v дифференцируемы; остающийся интеграл должен быть проще исходного.",
            "∫ x eˣ dx = x eˣ − ∫ eˣ dx = eˣ(x − 1) + C",
            "Знак минус перед ∫v du.",
        ),
        "en": _article(
            "Integration by parts",
            "The formula moves the integral to a simpler one. Take u to be what differentiation "
            "simplifies: ln x, arctg x, a polynomial; dv is the rest.",
            "∫ u dv = uv − ∫ v du",
            "u and v are differentiable; the remaining integral must be simpler.",
            "∫ x eˣ dx = x eˣ − ∫ eˣ dx = eˣ(x − 1) + C",
            "Mind the minus sign before ∫v du.",
        ),
    },
    "calculus_integral_fractions": {
        "ru": _article(
            "Простейшие дроби",
            "Правильную дробь раскладывают на A/(x−a) + B/(x−b). Если степень числителя "
            "не меньше степени знаменателя, сначала делят уголком.",
            "P(x)/Q(x) = S(x) + A/(x−a) + B/(x−b), deg P < deg Q",
            "Знаменатель разложен на линейные множители; у кратного корня добавляют "
            "слагаемые A/(x−a)² и т. д.",
            "x²/(x−1) = x + 1 + 1/(x−1), поэтому ∫ = x²/2 + x + ln|x−1| + C",
            "Сначала деление, если степень числителя не меньше степени знаменателя.",
        ),
        "en": _article(
            "Partial fractions",
            "Decompose a proper fraction into A/(x−a) + B/(x−b). If the numerator degree "
            "reaches the denominator degree, divide first.",
            "P(x)/Q(x) = S(x) + A/(x−a) + B/(x−b), deg P < deg Q",
            "The denominator is factored into linear factors; a repeated root adds "
            "terms A/(x−a)² and so on.",
            "x²/(x−1) = x + 1 + 1/(x−1), so ∫ = x²/2 + x + ln|x−1| + C",
            "Divide first when the numerator degree reaches the denominator degree.",
        ),
    },
    "calculus_improper_integral": {
        "ru": _article(
            "Несобственный интеграл",
            "Бесконечный предел интегрирования или разрыв раскрывают через предел; "
            "интеграл сходится, если предел конечен.",
            "∫ₐ^∞ f(x) dx = lim_{b→∞} ∫ₐᵇ f(x) dx; ∫ₐ^b f(x) dx = lim_{ε→0+} ∫_{a+ε}^b f(x) dx",
            "f непрерывна на [a, ∞) или на [a, b) соответственно.",
            "∫₁^∞ dx/x² = lim_{b→∞} (1 − 1/b) = 1",
            "∞ — не число, а предел: подставлять его напрямую нельзя.",
        ),
        "en": _article(
            "Improper integral",
            "An infinite bound or a discontinuity is handled through a limit; "
            "the integral converges when the limit is finite.",
            "∫ₐ^∞ f(x) dx = lim_{b→∞} ∫ₐᵇ f(x) dx; ∫ₐ^b f(x) dx = lim_{ε→0+} ∫_{a+ε}^b f(x) dx",
            "f is continuous on [a, ∞) or on [a, b) respectively.",
            "∫₁^∞ dx/x² = lim_{b→∞} (1 − 1/b) = 1",
            "∞ is a limit, not a number you can substitute.",
        ),
    },
    "calculus_integral_parity": {
        "ru": _article(
            "Чётность и симметричный отрезок",
            "На отрезке [−a, a] интеграл нечётной функции равен нулю, а интеграл чётной "
            "функции удваивается.",
            "f(−x) = −f(x) ⇒ ∫_{−a}^{a} f(x) dx = 0; "
            "f(−x) = f(x) ⇒ ∫_{−a}^{a} f(x) dx = 2∫₀ᵃ f(x) dx",
            "f интегрируема на симметричном отрезке [−a, a].",
            "∫₋₁¹ x³ dx = 0; ∫₋₁¹ x² dx = 2∫₀¹ x² dx = 2/3",
            "Свойство действует только на симметричном отрезке.",
        ),
        "en": _article(
            "Parity and a symmetric interval",
            "On [−a, a] the integral of an odd function is zero, and the integral of an even "
            "function doubles.",
            "f(−x) = −f(x) ⇒ ∫_{−a}^{a} f(x) dx = 0; "
            "f(−x) = f(x) ⇒ ∫_{−a}^{a} f(x) dx = 2∫₀ᵃ f(x) dx",
            "f is integrable on the symmetric interval [−a, a].",
            "∫₋₁¹ x³ dx = 0; ∫₋₁¹ x² dx = 2∫₀¹ x² dx = 2/3",
            "The rule applies only to a symmetric interval.",
        ),
    },
    "calculus_definite_integral": {
        "ru": _article(
            "Формула Ньютона — Лейбница",
            "Найдите первообразную и вычтите значения на границах.",
            "∫ₐᵇ f(x) dx = F(b) − F(a)",
            "f непрерывна на отрезке, F' = f.",
            "∫₁² x² dx = 8/3 − 1/3 = 7/3",
            "Вычитайте нижнее значение из верхнего; C сокращается.",
        ),
        "en": _article(
            "Fundamental theorem of calculus",
            "Evaluate an antiderivative at both bounds.",
            "∫ₐᵇ f(x) dx = F(b) − F(a)",
            "f is continuous on the interval and F' = f.",
            "∫₁² x² dx = 8/3 − 1/3 = 7/3",
            "Use upper minus lower; the arbitrary constant cancels.",
        ),
    },
    "calculus_linear_integral": {
        "ru": _article(
            "Интеграл с линейным аргументом",
            "Линейная замена даёт постоянный множитель.",
            "∫ sin(ax+b) dx = −cos(ax+b)/a + C; ∫ exp(ax+b) dx = exp(ax+b)/a + C",
            "a и b постоянны, a ≠ 0; d(ax+b)/dx = a.",
            "∫ cos(3x+1) dx = sin(3x+1)/3 + C",
            "При интегрировании делите на a; при дифференцировании умножайте на a.",
        ),
        "en": _article(
            "Integrals with a linear argument",
            "A linear substitution gives a constant factor.",
            "∫ sin(ax+b) dx = −cos(ax+b)/a + C; ∫ exp(ax+b) dx = exp(ax+b)/a + C",
            "a and b are constant, a ≠ 0; d(ax+b)/dx = a.",
            "∫ cos(3x+1) dx = sin(3x+1)/3 + C",
            "Divide by a when integrating; multiply by a when differentiating.",
        ),
    },
    "calculus_limit": {
        "ru": _article(
            "Подстановка и сокращение в пределе",
            "Непрерывность позволяет подставить точку.",
            "limₓ→ₐ f(x) = f(a) для непрерывной f",
            "Сокращение допустимо только там, где сокращаемый множитель не равен нулю.",
            "limₓ→₁ (x²−1)/(x−1) = limₓ→₁ (x+1) = 2",
            "0/0 — неопределённость, не число; исходная функция при x=1 не определена.",
        ),
        "en": _article(
            "Substitution and cancellation in limits",
            "Continuity permits direct substitution.",
            "limₓ→ₐ f(x) = f(a) when f is continuous at a",
            "Cancel a factor only where it is nonzero, retaining the original domain.",
            "limₓ→₁ (x²−1)/(x−1) = limₓ→₁ (x+1) = 2",
            "0/0 is indeterminate, not a number; the original function is undefined at 1.",
        ),
    },
    "calculus_sigma": {
        "ru": _article(
            "Конечная сумма",
            "Подставьте каждый целый индекс от нижней до верхней границы.",
            "Σₖ₌ₐᵇ f(k) = f(a) + … + f(b)",
            "Границы целые, a ≤ b; все члены определены.",
            "Σₖ₌₁³ k² = 1 + 4 + 9 = 14",
            "Обе границы включены: членов b−a+1.",
        ),
        "en": _article(
            "Finite summation",
            "Substitute every integer index between the two bounds.",
            "Σₖ₌ₐᵇ f(k) = f(a) + … + f(b)",
            "Integer bounds, a ≤ b; every term must be defined.",
            "Σₖ₌₁³ k² = 1 + 4 + 9 = 14",
            "Include both bounds: there are b−a+1 terms.",
        ),
    },
    "calculus_ode_separable": {
        "ru": _article(
            "Уравнение с разделяющимися переменными",
            "Запишем производную как dy/dx и разнесём y к dy, а x к dx.",
            "dy/g(y) = f(x) dx,  y′ = f(x)·g(y)",
            "g(y) ≠ 0 там, где делят; корни g(y) = 0 дают особые решения.",
            "y′ = xy: dy/y = x dx, ln|y| = x²/2 + C, y = Ce^(x²/2)",
            "После интегрирования нужна постоянная C: без неё получено одно частное решение.",
        ),
        "en": _article(
            "Separable equation",
            "Write the derivative as dy/dx and move y to dy and x to dx.",
            "dy/g(y) = f(x) dx,  y′ = f(x)·g(y)",
            "g(y) ≠ 0 where you divide; roots of g(y) = 0 give singular solutions.",
            "y′ = xy: dy/y = x dx, ln|y| = x²/2 + C, y = Ce^(x²/2)",
            "Integrating needs the constant C; without it you have one particular solution.",
        ),
    },
    "calculus_ode_homogeneous": {
        "ru": _article(
            "Однородное уравнение",
            "Правая часть зависит только от y/x: подстановка y = ux сводит"
            " уравнение к разделяющемуся.",
            "y = ux,  y′ = u′x + u",
            "Ищем решение при x ≠ 0; после возврата u = y/x проверяем особые случаи.",
            "y′ = (x + y)/x: u′x = 1, u = ln|x| + C, y = x(ln|x| + C)",
            "Не потеряйте x: y′ = u′x + u, а не только u′.",
        ),
        "en": _article(
            "Homogeneous equation",
            "The right side depends only on y/x; y = ux reduces it to a separable equation.",
            "y = ux,  y′ = u′x + u",
            "Work where x ≠ 0; after substituting u = y/x check the singular cases.",
            "y′ = (x + y)/x: u′x = 1, u = ln|x| + C, y = x(ln|x| + C)",
            "Do not drop x: y′ = u′x + u, not u′ alone.",
        ),
    },
    "calculus_ode_linear": {
        "ru": _article(
            "Линейное уравнение первого порядка",
            "Ищем решение в виде y = uv; часть с v выбирают так, чтобы она обнулилась.",
            "y′ + p(x)y = q(x),  y = uv,  v = e^(−∫p dx),  u = ∫q/v dx + C",
            "v ≠ 0; постоянная C находится из начального условия.",
            "y′ + y = x: v = e^(−x), u′ = xe^x, u = (x − 1)e^x + C, y = x − 1 + Ce^(−x)",
            "u и v не независимы: ответ — произведение uv, а не сумма.",
        ),
        "en": _article(
            "First-order linear equation",
            "Look for y = uv and choose the v-part so that it vanishes.",
            "y′ + p(x)y = q(x),  y = uv,  v = e^(−∫p dx),  u = ∫q/v dx + C",
            "v ≠ 0; the constant C comes from the initial condition.",
            "y′ + y = x: v = e^(−x), u′ = xe^x, u = (x − 1)e^x + C, y = x − 1 + Ce^(−x)",
            "u and v are not independent: the answer is the product uv, not a sum.",
        ),
    },
    "calculus_ode_bernoulli": {
        "ru": _article(
            "Уравнение Бернулли",
            "Деление на yⁿ и подстановка z = y^(1−n) дают линейное уравнение.",
            "y′ + p(x)y = q(x)yⁿ,  z = y^(1−n),  z′ = (1−n)y^(−n)y′",
            "y ≠ 0 при делении; y = 0 — отдельное решение, его указывают.",
            "y′ + y = xy²: z′ − z = −x, z = x + 1 + Ce^x, y = 1/(x + 1 + Ce^x)",
            "После решения для z нужна обратная замена y = z^(1/(1−n)).",
        ),
        "en": _article(
            "Bernoulli equation",
            "Dividing by yⁿ and substituting z = y^(1−n) gives a linear equation.",
            "y′ + p(x)y = q(x)yⁿ,  z = y^(1−n),  z′ = (1−n)y^(−n)y′",
            "y ≠ 0 where you divide; y = 0 is a separate solution to state.",
            "y′ + y = xy²: z′ − z = −x, z = x + 1 + Ce^x, y = 1/(x + 1 + Ce^x)",
            "After solving for z, substitute back y = z^(1/(1−n)).",
        ),
    },
    "calculus_ode_exact": {
        "ru": _article(
            "Уравнение в полных дифференциалах",
            "Если ∂P/∂y = ∂Q/∂x, левая часть — полный дифференциал потенциала U.",
            "P dx + Q dy = 0,  ∂P/∂y = ∂Q/∂x,  dU = P dx + Q dy,  U = C",
            "P и Q непрерывно дифференцируемы в односвязной области.",
            "2xy dx + (x² + 3y²) dy = 0: U = x²y + y³, ответ x²y + y³ = C",
            "Проверяйте именно перекрёстные производные: ∂P/∂x и ∂Q/∂y ничего не дают.",
        ),
        "en": _article(
            "Exact differential equation",
            "If ∂P/∂y = ∂Q/∂x, the left side is the total differential of a potential U.",
            "P dx + Q dy = 0,  ∂P/∂y = ∂Q/∂x,  dU = P dx + Q dy,  U = C",
            "P and Q are continuously differentiable on a simply connected domain.",
            "2xy dx + (x² + 3y²) dy = 0: U = x²y + y³, answer x²y + y³ = C",
            "Check the cross derivatives: ∂P/∂x and ∂Q/∂y prove nothing.",
        ),
    },
    "calculus_ode_reduction": {
        "ru": _article(
            "Понижение порядка",
            "Если уравнение не содержит y, порядок понижают интегрированием; если в нём "
            "нет y, но есть y′, подставляют p = y′.",
            "y″ = f(x): y′ = ∫f(x) dx + C₁, y = ∫y′ dx + C₂; "
            "y″ = f(x, y′): p = y′, p′ = f(x, p), y = ∫p dx + C₂",
            "После первого интегрирования появляется C₁, после второго — C₂.",
            "y″ = sin x: y′ = −cos x + C₁, y = −sin x + C₁x + C₂",
            "Не теряйте x при обратной замене: y = ∫p dx, а не y = p.",
        ),
        "en": _article(
            "Reduction of order",
            "An equation without y is integrated twice; an equation without y but with y′ "
            "uses p = y′.",
            "y″ = f(x): y′ = ∫f(x) dx + C₁, y = ∫y′ dx + C₂; "
            "y″ = f(x, y′): p = y′, p′ = f(x, p), y = ∫p dx + C₂",
            "The first integration introduces C₁, the second one C₂.",
            "y″ = sin x: y′ = −cos x + C₁, y = −sin x + C₁x + C₂",
            "Do not lose x on the way back: y = ∫p dx, not y = p.",
        ),
    },
    "calculus_ode_constant": {
        "ru": _article(
            "Линейное однородное уравнение с постоянными коэффициентами",
            "По уравнению составляют характеристическое уравнение и по его корням "
            "выбирают вид фундаментальной системы решений.",
            "λ² + aλ + b = 0; корни r₁ ≠ r₂: y = C₁e^(r₁x) + C₂e^(r₂x); "
            "r₁ = r₂ = r: y = (C₁ + C₂x)e^(rx); "
            "α ± βi: y = e^(αx)(C₁cos βx + C₂sin βx)",
            "Дискриминант D = a² − 4b определяет случай: D > 0, D = 0 или D < 0.",
            "y″ − 3y′ + 2y = 0: λ² − 3λ + 2 = 0, λ₁ = 1, λ₂ = 2, y = C₁eˣ + C₂e²ˣ",
            "При кратном корне второй функцией служит xe^(rx), а не e^(rx).",
        ),
        "en": _article(
            "Linear homogeneous equation with constant coefficients",
            "Write the characteristic equation and choose the fundamental system from "
            "the type of its roots.",
            "λ² + aλ + b = 0; roots r₁ ≠ r₂: y = C₁e^(r₁x) + C₂e^(r₂x); "
            "r₁ = r₂ = r: y = (C₁ + C₂x)e^(rx); "
            "α ± βi: y = e^(αx)(C₁cos βx + C₂sin βx)",
            "The discriminant D = a² − 4b tells the case: D > 0, D = 0 or D < 0.",
            "y″ − 3y′ + 2y = 0: λ² − 3λ + 2 = 0, λ₁ = 1, λ₂ = 2, y = C₁eˣ + C₂e²ˣ",
            "For a double root the second function is xe^(rx), not e^(rx).",
        ),
    },
    "calculus_ode_special": {
        "ru": _article(
            "Неоднородное уравнение со специальной правой частью",
            "Частное решение подбирают по виду правой части; если её показатель совпал "
            "с корнем характеристического уравнения, форму умножают на x.",
            "f = Pₙ(x) → ỹ = Qₙ(x); f = Ce^(kx) → ỹ = Ae^(kx); "
            "f = Ccos ωx + Dsin ωx → ỹ = A cos ωx + B sin ωx; "
            "при совпадении с корнем — множитель x (кратность 2 — x²)",
            "Коэффициенты A, B находят, подставив ỹ, ỹ′, ỹ″ в уравнение и приравняв "
            "коэффициенты при одинаковых функциях.",
            "y″ + y = x: ỹ = Ax + B, A = 1, B = 0, ỹ = x; "
            "y″ + y = sin x: ỹ = x(A cos x + B sin x), ỹ = −(x/2)cos x",
            "Без резонанса подбор с x даёт лишнюю степень и неверные коэффициенты.",
        ),
        "en": _article(
            "Nonhomogeneous equation with a special right side",
            "Choose the particular solution from the form of the right side; when its "
            "exponent is a characteristic root, multiply the form by x.",
            "f = Pₙ(x) → ỹ = Qₙ(x); f = Ce^(kx) → ỹ = Ae^(kx); "
            "f = Ccos ωx + Dsin ωx → ỹ = A cos ωx + B sin ωx; "
            "on resonance multiply by x (multiplicity 2 gives x²)",
            "Find A, B by substituting ỹ, ỹ′, ỹ″ and equating coefficients of like terms.",
            "y″ + y = x: ỹ = Ax + B, A = 1, B = 0, ỹ = x; "
            "y″ + y = sin x: ỹ = x(A cos x + B sin x), ỹ = −(x/2)cos x",
            "Without resonance, multiplying by x gives wrong coefficients.",
        ),
    },
    "calculus_ode_variation": {
        "ru": _article(
            "Метод вариации постоянных",
            "Если правая часть не специальная, постоянные общего решения однородного "
            "уравнения считают функциями и находят их из системы.",
            "y = C₁(x)y₁ + C₂(x)y₂; C₁′y₁ + C₂′y₂ = 0, C₁′y₁′ + C₂′y₂′ = f",
            "y₁, y₂ — фундаментальная система; определитель Вронского W ≠ 0.",
            "y″ + y = sec x: C₁′cos x + C₂′sin x = 0, C₁ = ln|cos x|, C₂ = x",
            "Система нужна именно с нулём в первом уравнении; иначе производные не найти.",
        ),
        "en": _article(
            "Variation of constants",
            "When the right side is not special, treat the constants of the homogeneous "
            "solution as functions and find them from a system.",
            "y = C₁(x)y₁ + C₂(x)y₂; C₁′y₁ + C₂′y₂ = 0, C₁′y₁′ + C₂′y₂′ = f",
            "y₁, y₂ form a fundamental system; the Wronskian W ≠ 0.",
            "y″ + y = sec x: C₁′cos x + C₂′sin x = 0, C₁ = ln|cos x|, C₂ = x",
            "The first equation must equal zero; otherwise the derivatives are wrong.",
        ),
    },
    "calculus_ode_cauchy": {
        "ru": _article(
            "Задача Коши",
            "Начальные условия находят постоянные общего решения: подставляют x₀ в y и "
            "в производные и решают полученную систему.",
            "y(x₀) = y₀, y′(x₀) = y₁, … ⇒ C₁ = …, C₂ = …",
            "Число условий равно порядку уравнения; условия независимы.",
            "y″ + y = 0, y(0) = 0, y′(0) = 1: C₁ = 0, C₂ = 1, y = sin x",
            "Для уравнения второго порядка одного условия недостаточно для единственного "
            "решения: одна постоянная остаётся свободной.",
        ),
        "en": _article(
            "The Cauchy problem",
            "The initial conditions determine the constants of the general solution: "
            "substitute x₀ into y and its derivatives and solve the system.",
            "y(x₀) = y₀, y′(x₀) = y₁, … ⇒ C₁ = …, C₂ = …",
            "The number of conditions equals the order; the conditions are independent.",
            "y″ + y = 0, y(0) = 0, y′(0) = 1: C₁ = 0, C₂ = 1, y = sin x",
            "One condition is not enough for a unique second-order solution: one "
            "constant stays free.",
        ),
    },
}

RULE_TOPICS = {
    "derive_sum": "calculus_derivative_sum",
    "derive_prod": "calculus_derivative_product",
    "derive_quot": "calculus_derivative_quotient",
    "derive_chain": "calculus_derivative_chain",
    "derive_const": "calculus_derivative",
    "derive_var": "calculus_derivative",
    "find_derivative": "calculus_derivative",
    "find_derivative_with_respect": "calculus_derivative",
    "integrate": "calculus_integral_table",
    "integrate_calc": "calculus_integral_table",
    "integrate_def_rewrite": "calculus_definite_integral",
    "integrate_def_bounds": "calculus_definite_integral",
    "limit_solve": "calculus_limit",
    "limit_solve_insert_value": "calculus_limit",
    "series_sigma_find_sub": "calculus_sigma",
}
# Each stage opens the theory of its own method: a by-parts stage never shows the
# polynomial antiderivative, a definite-card stage never shows a limit or derivative.
_INTEGRAL_TABLE = {
    "integral",
    "power_integral",
    "integral_sum",
    "constant",
    "check_primitive",
    "header_int_table",
    "header_int_half_angle",
    "header_int_identity",
    "header_int_nonelementary",
    "int_table_rule",
    "int_expand",
    "int_inner_table",
    "int_term_table",
    "int_identity",
    "int_half_angle",
    "int_sine_half_angle",
    "int_answer",
    "int_nonelementary",
    "int_simplify",
}
_INTEGRAL_SUBSTITUTION = {
    "header_int_substitution",
    "int_substitute",
    "int_differential",
    "int_rewrite",
    "int_back_sub",
    "int_dx_expr",
    "int_from_substitution",
}
_INTEGRAL_PARTS = {
    "header_int_parts",
    "header_int_parts_first",
    "header_int_parts_second",
    "header_int_parts_next",
    "int_parts_formula",
    "int_parts_choose",
    "int_parts_differential",
    "int_parts_apply",
    "int_parts_remainder",
    "int_parts_answer",
    "int_parts_cyclic_define",
    "int_parts_cyclic_equation",
    "int_parts_cyclic_move",
    "int_parts_cyclic_value",
}
_INTEGRAL_FRACTIONS = {
    "header_int_frac",
    "header_int_square",
    "int_frac_divide",
    "int_frac_factor",
    "int_frac_form",
    "int_frac_equations",
    "int_frac_coeffs",
    "int_frac_numbers",
    "int_frac_square",
    "int_frac_split",
    "int_frac_ln",
}
_IMPROPER_INTEGRAL = {
    "header_int_improper",
    "header_int_diverges",
    "int_imp_formula",
    "int_imp_rewrite",
    "int_imp_primitive",
    "int_imp_value",
    "int_imp_diverges",
}
_INTEGRAL_PARITY = {
    "header_int_parity",
    "int_parity_odd",
    "int_parity_even",
    "int_parity_even_calc",
    "int_parity_zero",
}
_DEFINITE_INTEGRAL = {
    "newton",
    "upper",
    "lower",
    "subtract",
    "header_int_newton",
    "header_int_euler_poisson",
    "header_int_subst_limits",
    "int_newton_formula",
    "int_newton_primitive",
    "int_newton_bounds",
    "int_newton_subst",
    "int_newton_upper",
    "int_newton_lower",
    "int_newton_calc",
    "int_newton_sub_limits",
    "int_newton_sub_diff",
    "int_newton_sub_rewrite",
    "int_euler_poisson",
}
_ODE_SEPARABLE = {
    "ode_header_separable",
    "ode_sep_derivative",
    "ode_sep_separate",
    "ode_sep_integrate",
    "ode_sep_primitive",
    "ode_sep_implicit",
    "ode_sep_express",
    "ode_sep_express_log",
    "ode_sep_express_rename",
    "ode_sep_express_p",
    "ode_sep_express_log_p",
    "ode_sep_express_rename_p",
}
_ODE_HOMOGENEOUS = {
    "ode_header_homogeneous",
    "ode_hom_form",
    "ode_hom_substitute",
    "ode_hom_equation",
    "ode_hom_reduce",
    "ode_hom_separate",
    "ode_hom_integrate",
    "ode_hom_primitive",
    "ode_hom_back",
}
_ODE_LINEAR = {
    "ode_header_linear",
    "ode_lin_substitute",
    "ode_lin_substitute_z",
    "ode_lin_insert",
    "ode_lin_insert_z",
    "ode_lin_choose_v",
    "ode_lin_v",
    "ode_lin_v_value",
    "ode_lin_u_equation",
    "ode_lin_u",
    "ode_lin_u_value",
    "ode_lin_back",
    "ode_lin_back_z",
    "ode_lin_simplify",
}
_ODE_BERNOULLI = {
    "ode_header_bernoulli",
    "ode_bern_divide",
    "ode_bern_substitute",
    "ode_bern_linear",
    "ode_bern_back",
}
_ODE_EXACT = {
    "ode_header_exact",
    "ode_ex_differential",
    "ode_ex_pq",
    "ode_ex_check",
    "ode_ex_potential",
    "ode_ex_answer",
}
_ODE_REDUCTION = {
    "ode_header_reduction",
    "ode_reduce_first",
    "ode_reduce_second",
    "ode_reduce_substitute",
    "ode_reduce_equation",
    "ode_reduce_solution",
    "ode_reduce_integrate",
}
_ODE_CONSTANT = {
    "ode_header_constant",
    "ode_header_characteristic",
    "ode_char_equation",
    "ode_char_roots",
    "ode_char_discriminant",
    "ode_char_complex_roots",
    "ode_char_case_distinct",
    "ode_char_case_double",
    "ode_char_case_complex",
    "ode_char_general",
}
_ODE_SPECIAL = {
    "ode_header_special",
    "ode_step_homogeneous",
    "ode_step_particular",
    "ode_step_general",
    "ode_special_form",
    "ode_special_form_exp_resonance",
    "ode_special_form_trig_resonance",
    "ode_special_form_poly_resonance",
    "ode_special_derivatives",
    "ode_special_substitute",
    "ode_special_equate",
    "ode_special_solve",
    "ode_special_particular",
    "ode_special_general",
}
_ODE_CAUCHY = {
    "ode_step_conditions",
    "ode_conditions_system",
    "ode_conditions_values",
    "ode_conditions_answer",
    "ode_condition",
    "ode_condition_substitute",
    "ode_condition_value",
    "ode_condition_answer",
}
for _key in _TEXT:
    _topic = "calculus_derivative"
    if _key in _ODE_SEPARABLE:
        _topic = "calculus_ode_separable"
    elif _key in _ODE_HOMOGENEOUS:
        _topic = "calculus_ode_homogeneous"
    elif _key in _ODE_LINEAR:
        _topic = "calculus_ode_linear"
    elif _key in _ODE_BERNOULLI:
        _topic = "calculus_ode_bernoulli"
    elif _key in _ODE_EXACT:
        _topic = "calculus_ode_exact"
    elif _key in _ODE_REDUCTION:
        _topic = "calculus_ode_reduction"
    elif _key in _ODE_CONSTANT:
        _topic = "calculus_ode_constant"
    elif _key in _ODE_SPECIAL:
        _topic = "calculus_ode_special"
    elif _key in _ODE_CAUCHY:
        _topic = "calculus_ode_cauchy"
    elif _key == "ode_header_integrals" or _key in _INTEGRAL_TABLE:
        _topic = "calculus_integral_table"
    elif _key in {"header_int_sum", "int_sum_rule"}:
        _topic = "calculus_integral_linearity"
    elif _key in _INTEGRAL_SUBSTITUTION:
        _topic = "calculus_integral_substitution"
    elif _key in _INTEGRAL_PARTS:
        _topic = "calculus_integral_parts"
    elif _key in _INTEGRAL_FRACTIONS:
        _topic = "calculus_integral_fractions"
    elif _key in _IMPROPER_INTEGRAL:
        _topic = "calculus_improper_integral"
    elif _key in _INTEGRAL_PARITY:
        _topic = "calculus_integral_parity"
    elif _key in _DEFINITE_INTEGRAL:
        _topic = "calculus_definite_integral"
    elif _key in {"linear_integral", "int_linear_rule", "header_int_linear"}:
        _topic = "calculus_linear_integral"
    elif _key in {
        "limit",
        "factor",
        "cancel",
        "substitute",
        "domain",
        "header_factor",
        "header_inf",
        "header_sequence_root",
        "header_remarkable",
        "header_conjugate",
        "header_second_remarkable",
        "header_one_sided",
        "header_dne",
        "uncertainty_00",
        "uncertainty_inf",
        "uncertainty_inf_minus_inf",
        "uncertainty_inf_0",
        "uncertainty_1_inf",
        "cancel_factor",
        "divide_highest",
        "inf_deg_lt",
        "inf_deg_eq",
        "inf_deg_gt",
        "inf_terms_zero",
        "first_remarkable",
        "equivalents",
        "second_remarkable",
        "conjugate_multiply",
        "conjugate_simplify",
        "abs_right",
        "abs_left",
        "one_sided_sign_right",
        "one_sided_sign_left",
        "limit_result",
        "limit_result_exp",
        "limit_oscillation",
        "sequence_root",
        "log_over_n",
    }:
        _topic = "calculus_limit"
    elif _key in {"sigma", "term", "expand"}:
        _topic = "calculus_sigma"
    elif _key in {"sum_rule", "product_rule", "quotient_rule", "chain_rule"}:
        _topic = f"calculus_derivative_{_key.removesuffix('_rule')}"
    RULE_TOPICS[f"lesson_calc_{_key}"] = _topic


class _UnsupportedError(Exception):
    """No transparent lesson is available for this expression."""


def _node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _num(value: int) -> CoreNode:
    return CoreNode.constant(str(value))


def _fold(kind: T, nodes: list[CoreNode]) -> CoreNode:
    if not nodes:
        return _num(0 if kind is T.ADD else 1)
    value = nodes[0]
    for node in nodes[1:]:
        value = _node(kind, value, node)
    return value


def _substitute(node: CoreNode, variable: str, value: CoreNode) -> CoreNode:
    if node.type is T.VARIABLE and node.value == variable:
        return value
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_substitute(child, variable, value) for child in node.children],
    )


def _emit(result: SolveResult, left: CoreNode | None, right: CoreNode, key: str) -> None:
    from .solver.base import Step

    result.add(Step(left, right, f"lesson_calc_{key}"))


def _symbol(expression: CoreNode) -> sympy.Symbol:
    from .solver.sympy_bridge import to_sympy

    symbols = to_sympy(expression).free_symbols
    if len(symbols) > 1:
        raise _UnsupportedError
    return next(iter(symbols), sympy.Symbol("x"))


def _derivation(expression: CoreNode, variable: sympy.Symbol) -> CoreNode:
    return _node(T.DERIVATION1_DIFF, CoreNode.variable(str(variable)), expression)


def _derive(
    expression: CoreNode, variable: sympy.Symbol, detail: SolveResult, depth: int = 0
) -> CoreNode:
    """Apply only explicit elementary rules; recursively expose their operands."""
    from .solver.sympy_bridge import from_sympy, to_sympy

    if depth > 12 or len(detail) > 100:
        raise _UnsupportedError
    value = to_sympy(expression)
    left = _derivation(expression, variable)
    if not value.has(variable) or expression.type is T.VARIABLE:
        answer = _num(1 if value == variable else 0)
        _emit(detail, left, answer, "basic_derivative")
        return answer
    kind, children = expression.type, expression.children
    if kind in (T.BRACKET, T.POSITIVE) and len(children) == 1:
        return _derive(children[0], variable, detail, depth + 1)
    placeholders = [_derivation(child, variable) for child in children]
    if kind in (T.ADD, T.SUBTRACT, T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(children) >= 2:
        is_sum = kind in (T.ADD, T.SUBTRACT)

        def compose(parts: list[CoreNode]) -> CoreNode:
            if is_sum:
                return _fold(kind, parts)
            return _fold(
                T.ADD,
                [
                    _fold(
                        T.MULTIPLY,
                        [parts[i] if i == j else child for j, child in enumerate(children)],
                    )
                    for i in range(len(children))
                ],
            )

        rule_key = "sum_rule" if is_sum else "product_rule"
        raw_rule = compose(placeholders)
        _emit(detail, left, raw_rule, rule_key)
        parts = [_derive(child, variable, detail, depth + 1) for child in children]
        raw = compose(parts)
    elif kind in (T.FRACTION, T.DIVIDE) and len(children) == 2:
        u, v = children
        _emit(detail, None, _node(T.NOT_EQUALS, v, _num(0)), "domain")

        def quotient(parts: list[CoreNode]) -> CoreNode:
            return _node(
                T.FRACTION,
                _node(T.SUBTRACT, _node(T.MULTIPLY, parts[0], v), _node(T.MULTIPLY, u, parts[1])),
                _node(T.POWER, v, _num(2)),
            )

        raw_rule = quotient(placeholders)
        _emit(detail, left, raw_rule, "quotient_rule")
        raw = quotient([_derive(child, variable, detail, depth + 1) for child in children])
    elif kind is T.NEGATIVE and len(children) == 1:
        raw_rule = _node(T.NEGATIVE, placeholders[0])
        _emit(detail, left, raw_rule, "sum_rule")
        raw = _node(T.NEGATIVE, _derive(children[0], variable, detail, depth + 1))
    else:
        if not children:
            raise _UnsupportedError
        inner = children[0]
        u = to_sympy(inner)
        if kind is T.POWER and len(children) == 2:
            exponent = to_sympy(children[1])
            if exponent.has(variable) or exponent.is_number is not True:
                raise _UnsupportedError
            outer = _node(
                T.MULTIPLY,
                children[1],
                _node(T.POWER, inner, _node(T.SUBTRACT, children[1], _num(1))),
            )
            rule_key = "power_rule"
        elif kind in (T.SIN, T.COS, T.TAN, T.EXP, T.LN, T.ROOT2) and len(children) == 1:
            formulas = {
                T.SIN: sympy.cos(u),
                T.COS: -sympy.sin(u),
                T.TAN: 1 / sympy.cos(u) ** 2,
                T.EXP: sympy.exp(u),
                T.LN: 1 / u,
                T.ROOT2: 1 / (2 * sympy.sqrt(u)),
            }
            outer = from_sympy(formulas[kind])
            rule_key = "chain_rule"
        else:
            raise _UnsupportedError
        raw_rule = _node(T.MULTIPLY, outer, placeholders[0])
        _emit(detail, left, raw_rule, rule_key)
        raw = _node(T.MULTIPLY, outer, _derive(inner, variable, detail, depth + 1))
    _emit(detail, raw_rule, raw, "compose")
    answer = from_sympy(sympy.simplify(to_sympy(raw)))
    _emit(detail, raw, answer, "simplify")
    return answer


def _polynomial_primitive(
    expression: CoreNode, variable: sympy.Symbol, detail: SolveResult
) -> CoreNode:
    from .solver.sympy_bridge import from_sympy, to_sympy

    value = to_sympy(expression)
    if value.is_polynomial(variable) is not True:
        raise _UnsupportedError
    terms = sympy.Poly(value, variable).terms()
    if len(terms) > 12:
        raise _UnsupportedError
    primitives = []
    for (degree,), coefficient in terms:
        term = from_sympy(coefficient * variable**degree)
        raw = _node(
            T.MULTIPLY,
            _node(T.FRACTION, from_sympy(coefficient), _node(T.ADD, _num(degree), _num(1))),
            _node(T.POWER, CoreNode.variable(str(variable)), _node(T.ADD, _num(degree), _num(1))),
        )
        _emit(detail, _node(T.INTEGRAL, term), raw, "power_integral")
        primitive = from_sympy(coefficient * variable ** (degree + 1) / (degree + 1))
        _emit(detail, raw, primitive, "int_simplify")
        primitives.append(primitive)
    total = _fold(T.ADD, primitives)
    answer = from_sympy(sympy.simplify(to_sympy(total)))
    if not total.structural_eq(answer):
        # A single term already is the answer; a stage «x³/3 → x³/3» shows nothing.
        _emit(detail, total, answer, "integral_sum")
    return answer


def _integral(step: Step, detail: SolveResult) -> None:
    from .solver.sympy_bridge import from_sympy, to_sympy

    node = step.left
    if node is None:
        raise _UnsupportedError
    if node.type is T.INTEGRAL and node.children:
        expression = node.children[-1]
        variable = _symbol(expression)
        primitive = _polynomial_primitive(expression, variable, detail)
        if (
            step.right is not None
            and sympy.simplify(to_sympy(primitive) - to_sympy(step.right)) != 0
        ):
            raise _UnsupportedError
        _emit(detail, _derivation(primitive, variable), expression, "check_primitive")
        names = {str(symbol) for symbol in to_sympy(expression).free_symbols}
        name = "C"
        while name in names:
            name += "_"
        family = _node(T.ADD, primitive, CoreNode.variable(name))
        _emit(detail, _node(T.INTEGRAL, expression), family, "constant")
        detail.set_solution(family)
        return
    if node.type is T.INTEGRAL_RIGHT_DASH and len(node.children) == 3:
        primitive, lower, upper = node.children
        variable = _symbol(primitive)
    elif node.type is T.INTEGRAL_DEFINITE and len(node.children) == 3:
        lower, upper, expression = node.children
        variable = _symbol(expression)
        # These explicit rules all produce continuous integrands on the real line.
        if to_sympy(expression).is_polynomial(variable):
            primitive = _polynomial_primitive(expression, variable, detail)
        else:
            primitive = _linear_primitive(expression, variable, detail)
    else:
        raise _UnsupportedError
    lo, hi = to_sympy(lower), to_sympy(upper)
    if lo.is_finite is not True or hi.is_finite is not True:
        raise _UnsupportedError
    if lo.is_real is not True or hi.is_real is not True:
        raise _UnsupportedError
    value = to_sympy(primitive)
    upper_sub = _substitute(primitive, str(variable), upper)
    lower_sub = _substitute(primitive, str(variable), lower)
    difference = _node(T.SUBTRACT, upper_sub, lower_sub)
    bounds = _node(T.INTEGRAL_RIGHT_DASH, primitive, lower, upper)
    _emit(detail, node, bounds, "newton")
    _emit(detail, bounds, difference, "int_newton_bounds")
    upper_value = from_sympy(value.subs(variable, hi))
    lower_value = from_sympy(value.subs(variable, lo))
    _emit(detail, upper_sub, upper_value, "upper")
    _emit(detail, lower_sub, lower_value, "lower")
    answer = from_sympy(sympy.simplify(value.subs(variable, hi) - value.subs(variable, lo)))
    if step.right is not None and sympy.simplify(to_sympy(answer) - to_sympy(step.right)) != 0:
        raise _UnsupportedError
    _emit(detail, _node(T.SUBTRACT, upper_value, lower_value), answer, "subtract")
    detail.set_solution(answer)


def _linear_primitive(
    expression: CoreNode, variable: sympy.Symbol, detail: SolveResult
) -> CoreNode:
    """Table primitives with a linear argument: sin, cos, exp, and ``1/(kx+b)``."""
    from .solver.sympy_bridge import from_sympy, to_sympy

    value = to_sympy(expression)
    coefficient, function = value.as_coeff_Mul()
    if function.is_Pow and function.exp == -1 and function.base.has(variable):
        argument = function.base
        slope = sympy.diff(argument, variable)
        if slope.has(variable) or slope.is_real is not True or slope.is_zero is not False:
            raise _UnsupportedError
        offset = sympy.simplify(argument - slope * variable)
        if offset.has(variable) or offset.is_real is not True:
            raise _UnsupportedError
        _derive(from_sympy(argument), variable, detail)
        raw = _node(
            T.FRACTION,
            _node(
                T.MULTIPLY,
                from_sympy(coefficient),
                _node(T.LN, _node(T.ABS, from_sympy(argument))),
            ),
            from_sympy(slope),
        )
        _emit(detail, _node(T.INTEGRAL, expression), raw, "linear_integral")
        primitive = from_sympy(sympy.simplify(to_sympy(raw)))
        _emit(detail, raw, primitive, "int_simplify")
        if sympy.simplify(sympy.diff(to_sympy(primitive), variable) - value) != 0:
            raise _UnsupportedError
        _emit(detail, _derivation(primitive, variable), expression, "check_primitive")
        return primitive
    if function.func not in (sympy.sin, sympy.cos, sympy.exp) or len(function.args) != 1:
        raise _UnsupportedError
    argument = function.args[0]
    slope = sympy.diff(argument, variable)
    if slope.has(variable) or slope.is_real is not True or slope.is_zero is not False:
        raise _UnsupportedError
    offset = sympy.simplify(argument - slope * variable)
    if offset.has(variable) or offset.is_real is not True:
        raise _UnsupportedError
    _derive(from_sympy(argument), variable, detail)
    table = {
        sympy.sin: -sympy.cos(argument),
        sympy.cos: sympy.sin(argument),
        sympy.exp: sympy.exp(argument),
    }
    raw = _node(
        T.FRACTION,
        _node(T.MULTIPLY, from_sympy(coefficient), from_sympy(table[function.func])),
        from_sympy(slope),
    )
    _emit(detail, _node(T.INTEGRAL, expression), raw, "linear_integral")
    primitive = from_sympy(sympy.simplify(to_sympy(raw)))
    _emit(detail, raw, primitive, "simplify")
    if sympy.simplify(sympy.diff(to_sympy(primitive), variable) - value) != 0:
        raise _UnsupportedError
    _emit(detail, _derivation(primitive, variable), expression, "check_primitive")
    return primitive


def _limit(step: Step, detail: SolveResult) -> None:
    from .solver.sympy_bridge import from_sympy, to_sympy

    node = step.left
    if node is None or len(node.children) != 2:
        raise _UnsupportedError
    point_node, expression = node.children
    variable = _symbol(expression)
    point = to_sympy(point_node)
    if point.is_finite is not True or point.is_real is not True:
        raise _UnsupportedError
    value = to_sympy(expression)
    numerator, denominator = sympy.fraction(sympy.together(value))
    # Preserve a syntactic denominator: SymPy eagerly turns x/x into 1.
    if expression.type in (T.FRACTION, T.DIVIDE) and len(expression.children) == 2:
        numerator, denominator = (to_sympy(child) for child in expression.children)
    reduced = value
    if denominator.subs(variable, point) == 0:
        if not numerator.is_polynomial(variable) or not denominator.is_polynomial(variable):
            raise _UnsupportedError
        common = sympy.gcd(numerator, denominator)
        if common == 1 or numerator.subs(variable, point) != 0:
            raise _UnsupportedError
        reduced = sympy.cancel(value)
        _, reduced_denominator = sympy.fraction(reduced)
        if reduced_denominator.subs(variable, point) == 0:
            raise _UnsupportedError
        _emit(detail, None, _node(T.NOT_EQUALS, from_sympy(denominator), _num(0)), "domain")
        factored = _node(
            T.FRACTION, from_sympy(sympy.factor(numerator)), from_sympy(sympy.factor(denominator))
        )
        _emit(detail, expression, factored, "factor")
        expression = from_sympy(reduced)
        _emit(detail, factored, expression, "cancel")
    elif denominator != 1:
        _emit(detail, None, _node(T.NOT_EQUALS, from_sympy(denominator), _num(0)), "domain")
    # A finite value alone does not prove continuity (e.g. sign/branch functions).
    domain = sympy.calculus.util.continuous_domain(reduced, variable, sympy.S.Reals)
    if domain.interior.contains(point) is not sympy.true:
        raise _UnsupportedError
    substituted = _substitute(expression, str(variable), point_node)
    answer_value = sympy.simplify(reduced.subs(variable, point))
    if answer_value.is_finite is not True or answer_value.is_real is not True:
        raise _UnsupportedError
    if step.right is not None and sympy.simplify(answer_value - to_sympy(step.right)) != 0:
        raise _UnsupportedError
    answer = from_sympy(answer_value)
    _emit(detail, _node(node.type, point_node, expression), substituted, "substitute")
    _emit(detail, substituted, answer, "simplify")
    detail.set_solution(answer)


def _sigma(step: Step, detail: SolveResult) -> None:
    from .solver.sympy_bridge import from_sympy, to_sympy

    node = step.left
    if node is None:
        raise _UnsupportedError
    if len(node.children) == 4:
        index, lower, upper, expression = node.children
        if index.type is not T.VARIABLE or not index.value:
            raise _UnsupportedError
    elif len(node.children) == 3:
        lower, upper, expression = node.children
        index = CoreNode.variable("n")
    else:
        raise _UnsupportedError
    lo, hi = to_sympy(lower), to_sympy(upper)
    if not isinstance(lo, sympy.Integer) or not isinstance(hi, sympy.Integer):
        raise _UnsupportedError
    if not 1 <= int(hi - lo + 1) <= 12:
        raise _UnsupportedError
    substituted_terms, terms = [], []
    for integer in range(int(lo), int(hi) + 1):
        substituted = _substitute(expression, index.value or "n", _num(integer))
        value = sympy.simplify(to_sympy(substituted))
        if value.is_finite is not True:
            raise _UnsupportedError
        term = from_sympy(value)
        substituted_terms.append(substituted)
        terms.append(term)
        _emit(detail, substituted, term, "term")
    expansion = _fold(T.ADD, substituted_terms)
    _emit(detail, node, expansion, "expand")
    total = _fold(T.ADD, terms)
    _emit(detail, expansion, total, "substitute")
    answer = from_sympy(sympy.simplify(to_sympy(total)))
    if step.right is not None and sympy.simplify(to_sympy(answer) - to_sympy(step.right)) != 0:
        raise _UnsupportedError
    _emit(detail, total, answer, "simplify")
    detail.set_solution(answer)


# ── derivative cards: one named rule per stage, nested parts ──────────


def _chain_kind(kind: T, nodes: list[CoreNode]) -> CoreNode:
    """Fold ``nodes`` with a binary operator of the same kind."""
    value = nodes[0]
    for node in nodes[1:]:
        value = _node(kind, value, node)
    return value


def _prime(node: CoreNode) -> CoreNode:
    return _node(T.DERIVATION1_PRIME, node)


def _card_rule(key: str) -> str:
    return f"lesson_calc_{key}"


def _emit_rule(
    card: SolveResult,
    key: str,
    left: CoreNode | None,
    right: CoreNode | None,
    *args: CoreNode,
    subresult: SolveResult | None = None,
) -> None:
    """One stage of the card: the rule, applied, with its formula in ``args``."""
    from .solver.base import Step

    full = _card_rule(key)
    card.add_group(full, Step(left, right, full, list(args), subresult=subresult))


def _formula_sum() -> CoreNode:
    u, v = CoreNode.variable("u"), CoreNode.variable("v")
    return _node(T.EQUALS, _prime(_node(T.ADD, u, v)), _node(T.ADD, _prime(u), _prime(v)))


def _formula_difference() -> CoreNode:
    u, v = CoreNode.variable("u"), CoreNode.variable("v")
    return _node(T.EQUALS, _prime(_node(T.SUBTRACT, u, v)), _node(T.SUBTRACT, _prime(u), _prime(v)))


def _formula_constant_factor() -> CoreNode:
    c, u = CoreNode.variable("C"), CoreNode.variable("u")
    return _node(T.EQUALS, _prime(_node(T.MULTIPLY, c, u)), _node(T.MULTIPLY, c, _prime(u)))


def _formula_power() -> CoreNode:
    x, n = CoreNode.variable("x"), CoreNode.variable("n")
    return _node(
        T.EQUALS,
        _prime(_node(T.POWER, x, n)),
        _node(T.MULTIPLY, n, _node(T.POWER, x, _node(T.SUBTRACT, n, _num(1)))),
    )


def _formula_power_u() -> CoreNode:
    u, n = CoreNode.variable("u"), CoreNode.variable("n")
    return _node(
        T.EQUALS,
        _prime(_node(T.POWER, u, n)),
        _node(T.MULTIPLY, n, _node(T.POWER, u, _node(T.SUBTRACT, n, _num(1)))),
    )


def _formula_sqrt() -> CoreNode:
    u = CoreNode.variable("u")
    return _node(
        T.EQUALS,
        _prime(_node(T.ROOT2, u)),
        _node(
            T.FRACTION,
            _prime(u),
            _node(T.MULTIPLY, _num(2), _node(T.ROOT2, u)),
        ),
    )


def _formula_reciprocal() -> CoreNode:
    u = CoreNode.variable("u")
    return _node(
        T.EQUALS,
        _prime(_node(T.FRACTION, _num(1), u)),
        _node(
            T.NEGATIVE,
            _node(T.FRACTION, _prime(u), _node(T.POWER, u, _num(2))),
        ),
    )


def _formula_product() -> CoreNode:
    u, v = CoreNode.variable("u"), CoreNode.variable("v")
    return _node(
        T.EQUALS,
        _prime(_node(T.MULTIPLY, u, v)),
        _node(
            T.ADD,
            _node(T.MULTIPLY, _prime(u), v),
            _node(T.MULTIPLY, u, _prime(v)),
        ),
    )


def _formula_quotient() -> CoreNode:
    u, v = CoreNode.variable("u"), CoreNode.variable("v")
    return _node(
        T.EQUALS,
        _prime(_node(T.FRACTION, u, v)),
        _node(
            T.FRACTION,
            _node(
                T.SUBTRACT,
                _node(T.MULTIPLY, _prime(u), v),
                _node(T.MULTIPLY, u, _prime(v)),
            ),
            _node(T.POWER, v, _num(2)),
        ),
    )


def _formula_chain() -> CoreNode:
    """``(f(g(x)))′ = f′(g(x))·g′(x)`` as a display formula."""
    return _node(
        T.EQUALS,
        CoreNode.variable("(f(g(x)))′"),
        _node(
            T.MULTIPLY,
            CoreNode.variable("f′(g(x))"),
            CoreNode.variable("g′(x)"),
        ),
    )


def _table_formula(kind: T) -> CoreNode:
    u = CoreNode.variable("u")
    table = {
        T.SIN: _node(T.EQUALS, _prime(_node(T.SIN, u)), _node(T.COS, u)),
        T.COS: _node(T.EQUALS, _prime(_node(T.COS, u)), _node(T.NEGATIVE, _node(T.SIN, u))),
        T.TAN: _node(
            T.EQUALS,
            _prime(_node(T.TAN, u)),
            _node(T.FRACTION, _num(1), _node(T.POWER, _node(T.COS, u), _num(2))),
        ),
        T.COT: _node(
            T.EQUALS,
            _prime(_node(T.COT, u)),
            _node(
                T.NEGATIVE,
                _node(T.FRACTION, _num(1), _node(T.POWER, _node(T.SIN, u), _num(2))),
            ),
        ),
        T.LN: _node(T.EQUALS, _prime(_node(T.LN, u)), _node(T.FRACTION, _num(1), u)),
        T.EXP: _node(T.EQUALS, _prime(_node(T.EXP, u)), _node(T.EXP, u)),
        T.LOG10: _node(
            T.EQUALS,
            _prime(_node(T.LOG10, u)),
            _node(
                T.FRACTION,
                _num(1),
                _node(T.MULTIPLY, u, _node(T.LN, _num(10))),
            ),
        ),
        T.ASIN: _node(
            T.EQUALS,
            _prime(_node(T.ASIN, u)),
            _node(
                T.FRACTION,
                _num(1),
                _node(T.ROOT2, _node(T.SUBTRACT, _num(1), _node(T.POWER, u, _num(2)))),
            ),
        ),
        T.ATAN: _node(
            T.EQUALS,
            _prime(_node(T.ATAN, u)),
            _node(
                T.FRACTION,
                _num(1),
                _node(T.ADD, _num(1), _node(T.POWER, u, _num(2))),
            ),
        ),
        T.SINH: _node(T.EQUALS, _prime(_node(T.SINH, u)), _node(T.COSH, u)),
        T.COSH: _node(T.EQUALS, _prime(_node(T.COSH, u)), _node(T.SINH, u)),
        T.TANH: _node(
            T.EQUALS,
            _prime(_node(T.TANH, u)),
            _node(T.FRACTION, _num(1), _node(T.POWER, _node(T.COSH, u), _num(2))),
        ),
    }
    return table[kind]


def _outer_function(kind: T, argument: CoreNode) -> CoreNode:
    """The derivative of the outer table function, at ``argument``."""
    table = {
        T.SIN: lambda a: _node(T.COS, a),
        T.COS: lambda a: _node(T.NEGATIVE, _node(T.SIN, a)),
        T.TAN: lambda a: _node(T.FRACTION, _num(1), _node(T.POWER, _node(T.COS, a), _num(2))),
        T.COT: lambda a: _node(
            T.NEGATIVE, _node(T.FRACTION, _num(1), _node(T.POWER, _node(T.SIN, a), _num(2)))
        ),
        T.LN: lambda a: _node(T.FRACTION, _num(1), a),
        T.EXP: lambda a: _node(T.EXP, a),
        T.LOG10: lambda a: _node(T.FRACTION, _num(1), _node(T.MULTIPLY, a, _node(T.LN, _num(10)))),
        T.ASIN: lambda a: _node(
            T.FRACTION,
            _num(1),
            _node(T.ROOT2, _node(T.SUBTRACT, _num(1), _node(T.POWER, a, _num(2)))),
        ),
        T.ATAN: lambda a: _node(
            T.FRACTION, _num(1), _node(T.ADD, _num(1), _node(T.POWER, a, _num(2)))
        ),
        T.SINH: lambda a: _node(T.COSH, a),
        T.COSH: lambda a: _node(T.SINH, a),
        T.TANH: lambda a: _node(T.FRACTION, _num(1), _node(T.POWER, _node(T.COSH, a), _num(2))),
    }
    return table[kind](argument)


_DERIVATIVE_TABLE = frozenset(
    {
        T.SIN,
        T.COS,
        T.TAN,
        T.COT,
        T.LN,
        T.EXP,
        T.LOG10,
        T.ASIN,
        T.ATAN,
        T.SINH,
        T.COSH,
        T.TANH,
    }
)


def _simplify_expr(value: sympy.Expr) -> sympy.Expr:
    """Simplify a derivative; a rational answer is factored, as a textbook writes it."""
    simplified = sympy.simplify(value)
    try:
        if value.is_polynomial() and value == sympy.expand(value):
            # simplify() factors 3x² − 8x into x(3x − 8); keep the expanded form.
            simplified = sympy.expand(simplified)
        numerator, denominator = sympy.fraction(sympy.together(simplified))
        if denominator != 1 and numerator.is_polynomial() and denominator.is_polynomial():
            simplified = sympy.factor(simplified)
    except (TypeError, ValueError, sympy.PolynomialError):
        pass
    return simplified


def _answer_node(value: sympy.Expr) -> CoreNode:
    """The answer node: a polynomial in page order, a factorised rational function."""
    from .solver.sympy_bridge import from_sympy, ordered_terms, tidy

    simplified = _simplify_expr(value)

    def ordered(expression: sympy.Expr) -> CoreNode:
        """Keep the page order (``x² − 2x − 1``, not ``(x² − 1) − 2x``)."""
        token = ordered_terms.set(True)
        try:
            return _plain_negative(from_sympy(expression))
        finally:
            ordered_terms.reset(token)

    try:
        numerator, denominator = sympy.fraction(sympy.together(simplified))
        if denominator != 1 and numerator.is_polynomial() and denominator.is_polynomial():
            return ordered(simplified)
    except (TypeError, ValueError, sympy.PolynomialError):
        pass
    if simplified.is_polynomial() and simplified != sympy.expand(simplified):
        # An already factored answer such as 15(3x+1)^4 stays factored.
        return ordered(simplified)
    return _plain_negative(tidy(simplified))


def _plain_negative(node: CoreNode) -> CoreNode:
    """``−(1)`` as the constant ``−1``, as the arithmetic modules write it."""
    if node.type is T.NEGATIVE and len(node.children) == 1:
        child = node.children[0]
        if child.type is T.CONSTANT and child.value:
            value = child.value
            return CoreNode.constant(value[1:] if value.startswith("-") else "-" + value)
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_plain_negative(child) for child in node.children],
    )


def _simplified(node: CoreNode) -> CoreNode:
    from .solver.sympy_bridge import to_sympy

    return _answer_node(to_sympy(node))


def _same(left: CoreNode, right: CoreNode) -> bool:
    from .solver.sympy_bridge import to_sympy

    try:
        return bool(sympy.simplify(to_sympy(left) - to_sympy(right)) == 0)
    except (TypeError, ValueError):
        return False


def _leaf_card(
    expression: CoreNode, variable: sympy.Symbol, answer: CoreNode
) -> tuple[SolveResult, CoreNode]:
    from .solver.base import Step

    card = SolveResult(header="lesson_calc_header_deriv_table")
    left = _derivation(expression, variable)
    if expression.type is T.CONSTANT:
        card.add_group("derive_const", Step(left, answer, "derive_const", [answer]))
    elif expression.type is T.VARIABLE:
        card.add_group("derive_var", Step(left, answer, "derive_var", [answer]))
    else:
        _emit_rule(card, "basic_derivative", left, answer)
    card.set_solution(answer)
    return card, answer


def _derive_staged(
    expression: CoreNode, variable: sympy.Symbol, depth: int = 0
) -> tuple[SolveResult, CoreNode]:
    """Build the textbook card of ``expression``: one named rule per stage.

    Every rule stage shows the rule with its formula and the actual operands; the
    derivative of each operand is a nested «Подробнее» screen built the same way.
    """
    from .solver.sympy_bridge import to_sympy

    if depth > 9:
        raise _UnsupportedError
    value = to_sympy(expression)
    kind, children = expression.type, expression.children

    if kind is T.VARIABLE:
        return _leaf_card(expression, variable, _num(1 if value == variable else 0))
    if not value.has(variable):
        return _leaf_card(expression, variable, _num(0))
    if kind in (T.BRACKET, T.POSITIVE) and len(children) == 1:
        return _derive_staged(children[0], variable, depth + 1)

    left = _derivation(expression, variable)
    if kind in (T.ADD, T.SUBTRACT) and len(children) >= 2:
        return _staged_sum(expression, variable, depth, left)
    if kind is T.NEGATIVE and len(children) == 1:
        return _staged_constant_factor(expression, variable, depth, left)
    if kind in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        rest = [child for child in children if to_sympy(child).has(variable)]
        if len(children) >= 2 and len(rest) == 1:
            return _staged_constant_factor(expression, variable, depth, left)
        if len(children) >= 2:
            return _staged_product(expression, variable, depth, left)
        raise _UnsupportedError
    if kind in (T.FRACTION, T.DIVIDE) and len(children) == 2:
        numerator, _denominator = children
        if numerator.type is T.CONSTANT and (numerator.value or "").strip() == "1":
            return _staged_reciprocal(expression, variable, depth, left)
        return _staged_quotient(expression, variable, depth, left)
    if kind is T.POWER and len(children) == 2:
        return _staged_power(expression, variable, depth, left)
    if kind is T.ROOT2 and children:
        return _staged_root(expression, variable, depth, left)
    if kind in _DERIVATIVE_TABLE and len(children) == 1:
        return _staged_table(expression, variable, depth, left)
    raise _UnsupportedError


def _part_card(
    card: SolveResult,
    key: str,
    placeholder: CoreNode,
    part: CoreNode,
    variable: sympy.Symbol,
    depth: int,
) -> CoreNode:
    """Derive one operand into a nested screen and return its answer."""
    nested, answer = _derive_staged(part, variable, depth + 1)
    _emit_rule(card, key, placeholder, answer, subresult=nested)
    return answer


def _finish(
    card: SolveResult, composed: CoreNode, answer: CoreNode | None = None
) -> tuple[SolveResult, CoreNode]:
    if answer is None:
        answer = _simplified(composed)
    if not answer.structural_eq(composed):
        _emit_rule(card, "simplify_result", composed, answer)
    card.set_solution(answer)
    return card, answer


def _staged_sum(
    expression: CoreNode, variable: sympy.Symbol, depth: int, left: CoreNode
) -> tuple[SolveResult, CoreNode]:
    kind, children = expression.type, expression.children
    add = kind is T.ADD
    card = SolveResult(
        header="lesson_calc_header_deriv_sum" if add else "lesson_calc_header_deriv_difference"
    )
    placeholders = [_derivation(child, variable) for child in children]
    raw = _chain_kind(kind, placeholders)
    _emit_rule(
        card,
        "rule_sum" if add else "rule_difference",
        left,
        raw,
        _formula_sum() if add else _formula_difference(),
    )
    answers = []
    for index, child in enumerate(children):
        key = "part_first" if index == 0 else "part_second" if index == 1 else "part_rest"
        answers.append(_part_card(card, key, placeholders[index], child, variable, depth))
    composed = _chain_kind(kind, answers)
    _emit_rule(card, "compose_derivatives", raw, composed)
    return _finish(card, composed)


def _staged_constant_factor(
    expression: CoreNode, variable: sympy.Symbol, depth: int, left: CoreNode
) -> tuple[SolveResult, CoreNode]:
    from .solver.sympy_bridge import to_sympy

    card = SolveResult(header="lesson_calc_header_deriv_constant_factor")
    if expression.type is T.NEGATIVE:
        inner = expression.children[0]
        placeholder = _derivation(inner, variable)
        applied = _node(T.NEGATIVE, placeholder)
        _emit_rule(card, "rule_constant_factor", left, applied, _formula_constant_factor())
        answer = _part_card(card, "part_argument", placeholder, inner, variable, depth)
        composed = _node(T.NEGATIVE, answer)
    else:
        parts = list(expression.children)
        inner = next(child for child in parts if to_sympy(child).has(variable))
        constant = _chain_kind(T.MULTIPLY, [child for child in parts if child is not inner])
        placeholder = _derivation(inner, variable)
        applied = _node(T.MULTIPLY, placeholder, constant)
        _emit_rule(card, "rule_constant_factor", left, applied, _formula_constant_factor())
        answer = _part_card(card, "part_argument", placeholder, inner, variable, depth)
        composed = _node(T.MULTIPLY, answer, constant)
    _emit_rule(card, "compose_derivatives", applied, composed)
    return _finish(card, composed)


def _staged_product(
    expression: CoreNode, variable: sympy.Symbol, depth: int, left: CoreNode
) -> tuple[SolveResult, CoreNode]:
    children = list(expression.children)
    card = SolveResult(header="lesson_calc_header_deriv_product")
    placeholders = [_derivation(child, variable) for child in children]

    def compose(parts: list[CoreNode]) -> CoreNode:
        return _chain_kind(
            T.ADD,
            [
                _chain_kind(
                    T.MULTIPLY,
                    [parts[i] if i == j else child for j, child in enumerate(children)],
                )
                for i in range(len(children))
            ],
        )

    raw = compose(placeholders)
    _emit_rule(card, "rule_product", left, raw, _formula_product())
    answers = []
    for index, child in enumerate(children):
        key = "part_first" if index == 0 else "part_second" if index == 1 else "part_rest"
        answers.append(_part_card(card, key, placeholders[index], child, variable, depth))
    composed = compose(answers)
    _emit_rule(card, "compose_derivatives", raw, composed)
    return _finish(card, composed)


def _staged_quotient(
    expression: CoreNode, variable: sympy.Symbol, depth: int, left: CoreNode
) -> tuple[SolveResult, CoreNode]:
    numerator, denominator = expression.children
    card = SolveResult(header="lesson_calc_header_deriv_quotient")
    top, bottom = _derivation(numerator, variable), _derivation(denominator, variable)
    below = _node(T.POWER, denominator, _num(2))

    def compose(top_part: CoreNode, bottom_part: CoreNode) -> CoreNode:
        return _node(
            T.FRACTION,
            _node(
                T.SUBTRACT,
                _node(T.MULTIPLY, top_part, denominator),
                _node(T.MULTIPLY, numerator, bottom_part),
            ),
            below,
        )

    raw = compose(top, bottom)
    _emit_rule(card, "rule_quotient", left, raw, _formula_quotient())
    top_answer = _part_card(card, "part_numerator", top, numerator, variable, depth)
    bottom_answer = _part_card(card, "part_denominator", bottom, denominator, variable, depth)
    composed = compose(top_answer, bottom_answer)
    _emit_rule(card, "compose_derivatives", raw, composed)
    return _finish(card, composed)


def _staged_reciprocal(
    expression: CoreNode, variable: sympy.Symbol, depth: int, left: CoreNode
) -> tuple[SolveResult, CoreNode]:
    inner = expression.children[1]
    card = SolveResult(header="lesson_calc_header_deriv_power")
    placeholder = _derivation(inner, variable)
    applied = _node(
        T.NEGATIVE,
        _node(T.FRACTION, placeholder, _node(T.POWER, inner, _num(2))),
    )
    _emit_rule(card, "rule_reciprocal", left, applied, _formula_reciprocal())
    answer = _part_card(card, "part_argument", placeholder, inner, variable, depth)
    composed = _node(T.NEGATIVE, _node(T.FRACTION, answer, _node(T.POWER, inner, _num(2))))
    _emit_rule(card, "compose_derivatives", applied, composed)
    return _finish(card, composed)


def _staged_root(
    expression: CoreNode, variable: sympy.Symbol, depth: int, left: CoreNode
) -> tuple[SolveResult, CoreNode]:
    from .solver.sympy_bridge import to_sympy

    inner = expression.children[-1]
    single = to_sympy(inner) == variable
    placeholder = _derivation(inner, variable)
    outer = _node(T.FRACTION, _num(1), _node(T.MULTIPLY, _num(2), _node(T.ROOT2, inner)))
    applied = _node(T.MULTIPLY, outer, placeholder)
    if single:
        card = SolveResult(header="lesson_calc_header_deriv_power")
        _emit_rule(card, "rule_sqrt", left, outer, _formula_sqrt())
        return _finish(card, outer)
    card = SolveResult(header="lesson_calc_header_deriv_chain")
    _emit_rule(
        card,
        "rule_chain",
        left,
        applied,
        _formula_chain(),
        _node(T.EQUALS, CoreNode.variable("u"), inner),
        _formula_sqrt(),
    )
    answer = _part_card(card, "part_argument", placeholder, inner, variable, depth)
    composed = _node(T.MULTIPLY, outer, answer)
    _emit_rule(card, "compose_derivatives", applied, composed)
    return _finish(card, composed)


def _staged_power(
    expression: CoreNode, variable: sympy.Symbol, depth: int, left: CoreNode
) -> tuple[SolveResult, CoreNode]:
    from .solver.sympy_bridge import to_sympy

    base, exponent = expression.children
    exponent_value = to_sympy(exponent)
    if exponent_value.is_number and exponent_value.is_rational:
        n = exponent
        outer = _node(
            T.MULTIPLY,
            n,
            _node(T.POWER, base, _node(T.SUBTRACT, n, _num(1))),
        )
        placeholder = _derivation(base, variable)
        applied = _node(T.MULTIPLY, outer, placeholder)
        single = to_sympy(base) == variable
        if single:
            card = SolveResult(header="lesson_calc_header_deriv_power")
            _emit_rule(card, "rule_power", left, outer, _formula_power())
            return _finish(card, outer)
        card = SolveResult(header="lesson_calc_header_deriv_chain")
        _emit_rule(
            card,
            "rule_chain",
            left,
            applied,
            _formula_chain(),
            _node(T.EQUALS, CoreNode.variable("u"), base),
            _formula_power_u(),
        )
        answer = _part_card(card, "part_argument", placeholder, base, variable, depth)
        composed = _node(T.MULTIPLY, outer, answer)
        _emit_rule(card, "compose_derivatives", applied, composed)
        return _finish(card, composed)

    # a^u: the base is a constant, the exponent carries the variable.
    if not to_sympy(base).has(variable):
        return _staged_table(
            expression,
            variable,
            depth,
            left,
            base=base,
            exponent=exponent,
        )
    raise _UnsupportedError


def _staged_table(
    expression: CoreNode,
    variable: sympy.Symbol,
    depth: int,
    left: CoreNode,
    *,
    base: CoreNode | None = None,
    exponent: CoreNode | None = None,
) -> tuple[SolveResult, CoreNode]:
    from .solver.sympy_bridge import to_sympy

    if base is not None and exponent is not None:
        # (a^u)' = a^u · ln a · u'; for the natural base ln e = 1.
        argument = exponent
        if to_sympy(base) == sympy.E:
            outer = expression
            formula = _table_formula(T.EXP)
            rule_key, header = "rule_table", "lesson_calc_header_deriv_chain"
        else:
            outer = _node(
                T.MULTIPLY,
                expression,
                _node(T.LN, base),
            )
            a, u = CoreNode.variable("a"), CoreNode.variable("u")
            formula = _node(
                T.EQUALS,
                _prime(_node(T.POWER, a, u)),
                _node(
                    T.MULTIPLY,
                    _node(T.POWER, a, u),
                    _node(T.LN, a),
                    _prime(u),
                ),
            )
            rule_key, header = "rule_exponential", "lesson_calc_header_deriv_exponential"
    else:
        argument = expression.children[0]
        outer = _outer_function(expression.type, argument)
        formula = _table_formula(expression.type)
        rule_key, header = "rule_table", "lesson_calc_header_deriv_table"

    single = to_sympy(argument) == variable
    if rule_key == "rule_table":
        header = "lesson_calc_header_deriv_table" if single else "lesson_calc_header_deriv_chain"
    card = SolveResult(header=header)
    placeholder = _derivation(argument, variable)
    applied = _node(T.MULTIPLY, outer, placeholder)
    if single:
        _emit_rule(card, rule_key, left, outer, formula)
        return _finish(card, outer)
    _emit_rule(
        card,
        "rule_chain",
        left,
        applied,
        _formula_chain(),
        _node(T.EQUALS, CoreNode.variable("u"), argument),
        formula,
    )
    answer = _part_card(card, "part_argument", placeholder, argument, variable, depth)
    composed = _node(T.MULTIPLY, outer, answer)
    _emit_rule(card, "compose_derivatives", applied, composed)
    return _finish(card, composed)


def _logarithmic_card(expression: CoreNode, variable: sympy.Symbol) -> tuple[SolveResult, CoreNode]:
    """``x^x``: y = x^x, ln y = x·ln x, y′/y = (x·ln x)′, y′ = x^x(ln x + 1)."""
    from .solver.base import Step
    from .solver.sympy_bridge import to_sympy

    card = SolveResult(header="lesson_calc_header_deriv_log")
    x = CoreNode.variable(str(variable))
    y = CoreNode.variable("y")
    logged = _node(T.EQUALS, _node(T.LN, y), _node(T.MULTIPLY, x, _node(T.LN, x)))
    start = _node(T.EQUALS, y, expression)
    _emit_rule(card, "log_take", start, logged, logged)

    y_prime = _node(T.DERIVATION1_DIFF, x, y)
    product_card, product_answer = _derive_staged(_node(T.MULTIPLY, x, _node(T.LN, x)), variable)
    right = _node(
        T.EQUALS,
        _node(T.FRACTION, y_prime, y),
        product_answer,
    )
    differentiated = _node(
        T.EQUALS,
        _node(T.DERIVATION1_DIFF, x, _node(T.LN, y)),
        _node(T.DERIVATION1_DIFF, x, _node(T.MULTIPLY, x, _node(T.LN, x))),
    )
    card.add_group(
        _card_rule("log_differentiate"),
        Step(
            differentiated,
            right,
            _card_rule("log_differentiate"),
            [
                _node(
                    T.EQUALS,
                    _node(T.DERIVATION1_DIFF, x, _node(T.LN, y)),
                    _node(T.FRACTION, y_prime, y),
                )
            ],
            subresult=product_card,
        ),
    )
    answer = _answer_node(sympy.diff(to_sympy(expression), variable))
    solved = _node(
        T.EQUALS,
        y_prime,
        _node(T.MULTIPLY, expression, _node(T.ADD, _node(T.LN, x), _num(1))),
    )
    _emit_rule(card, "log_solve", right, solved, expression)
    card.set_solution(answer)
    _ = Step
    return card, answer


def derivative_card(expression: CoreNode, variable: str) -> tuple[SolveResult, CoreNode] | None:
    """The textbook derivative card of ``expression``, or ``None`` if unsupported."""
    from .solver.sympy_bridge import to_sympy

    symbol = sympy.Symbol(variable)
    try:
        if expression.type is T.POWER:
            base, exponent = expression.children
            if to_sympy(base).has(symbol) and to_sympy(exponent).has(symbol):
                card, answer = _logarithmic_card(expression, symbol)
            else:
                card, answer = _derive_staged(expression, symbol)
        else:
            card, answer = _derive_staged(expression, symbol)
        want = _answer_node(sympy.diff(to_sympy(expression), symbol))
    except (_UnsupportedError, SolveError, ValueError, TypeError, NotImplementedError):
        return None
    if not _same(answer, want):
        return None
    card.set_solution(want)
    return card, want


def second_derivative_card(
    expression: CoreNode, variable: str
) -> tuple[SolveResult, CoreNode] | None:
    """``f″ = (f′)′``: the first derivative with its rules, then its derivative."""
    from .solver.sympy_bridge import to_sympy

    symbol = sympy.Symbol(variable)
    try:
        first_card, first_answer = _derive_staged(expression, symbol)
        second_card, second_answer = _derive_staged(first_answer, symbol)
        want = _answer_node(sympy.diff(to_sympy(expression), symbol, 2))
    except (_UnsupportedError, SolveError, ValueError, TypeError, NotImplementedError):
        return None
    if not _same(second_answer, want):
        return None
    card = SolveResult(header="lesson_calc_header_deriv_second")
    formula = _node(
        T.EQUALS,
        CoreNode.variable("f″"),
        CoreNode.variable("(f′)′"),
    )
    _emit_rule(
        card,
        "second_first",
        _derivation(expression, symbol),
        first_answer,
        subresult=first_card,
    )
    _emit_rule(
        card,
        "second_again",
        _derivation(first_answer, symbol),
        second_answer,
        formula,
        subresult=second_card,
    )
    card.set_solution(want)
    return card, want


__all__ = [
    "ARTICLES",
    "RULE_TOPICS",
    "TEMPLATES",
    "derivative_card",
    "enrich",
    "second_derivative_card",
]


def enrich(step: Step) -> str | None:
    """Attach genuine intermediate calculations without changing the public step."""
    from .solver.base import SolveError, SolveResult
    from .solver.sympy_bridge import to_sympy

    if step.key.startswith("lesson_calc_") or step.left is None:
        return None
    # A limit card that already carries its own substitution screen keeps it:
    # its rows (using_trans, limit_solve_insert_value, …) are more specific than
    # the generic continuity screen that would replace them.
    if step.key == "limit_solve" and step.subresult is not None:
        return None
    detail = SolveResult()
    try:
        if step.key in {"find_derivative", "find_derivative_with_respect"}:
            node = step.left
            if node.type is T.DERIVATION1_DIFF and len(node.children) == 2:
                index, expression = node.children
                if index.type is not T.VARIABLE or not index.value:
                    return None
                variable = sympy.Symbol(index.value)
            elif (
                node.type in (T.DERIVATION, T.DERIVATION1, T.PRIME, T.DERIVATION1_PRIME)
                and len(node.children) == 1
            ):
                expression = node.children[0]
                variable = _symbol(expression)
            else:
                return None
            answer = _derive(expression, variable, detail)
            if step.right is None or sympy.simplify(to_sympy(answer) - to_sympy(step.right)) != 0:
                return None
            detail.set_solution(answer)
            title = "derivative"
        elif step.key in {"integrate_calc", "integrate_def_bounds"}:
            if step.key == "integrate_def_bounds" and step.left.type is T.INTEGRAL_DEFINITE:
                # The same breakdown is already attached to ``integrate_calc``.
                return None
            _integral(step, detail)
            title = "integral"
        elif step.key == "limit_solve":
            _limit(step, detail)
            title = "limit"
        elif step.key == "series_sigma_find_sub":
            _sigma(step, detail)
            title = "sigma"
        else:
            return None
    except (
        _UnsupportedError,
        SolveError,
        ValueError,
        TypeError,
        NotImplementedError,
        sympy.PolynomialError,
    ):
        return None
    # The detail card's groups were unlabelled, so the app showed the fallback
    # heading «Преобразование» on every nested «Подробнее».
    detail.name_groups(f"lesson_calc_{title}")
    step.subresult = detail
    return f"lesson_calc_{title}"


__all__ = ["ARTICLES", "RULE_TOPICS", "TEMPLATES", "enrich"]
