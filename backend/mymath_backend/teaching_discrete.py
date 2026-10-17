"""Authored, evidence-preserving worked lessons for discrete and linear algebra.

Only retained operands are used. In particular, a legacy ``calculate_short``
vector step does not identify its operation and is deliberately left alone.
"""

from __future__ import annotations

from typing import Any

import sympy

from .ast import CoreNode
from .node_types import CoreNodeType as T
from .solver.base import SolveError, SolveResult, Step, boolean_node
from .solver.sympy_bridge import from_sympy, to_sympy


def _copy(ru: str, en: str, arity: int = 0) -> dict[str, Any]:
    return {"arity": arity, "templates": {"ru": ru, "default": en}}


TEMPLATES = {
    "lesson_disc_matrix": _copy(
        "Разберём матричное вычисление", "Work through the matrix calculation"
    ),
    "lesson_disc_det_expand": _copy(
        "Разложим по первой строке: знаки чередуются +, −, +.",
        "Expand along the first row with alternating signs +, −, +.",
    ),
    "lesson_disc_minor": _copy(
        "Удалим строку ARG1 и столбец ARG2; вычислим полученный минор.",
        "Delete row ARG1 and column ARG2 and evaluate the resulting minor.",
        2,
    ),
    "lesson_disc_arithmetic": _copy(
        "Вычислим записанное выражение.", "Evaluate the displayed expression."
    ),
    "lesson_disc_augment": _copy(
        "Припишем справа единичную матрицу: [A | I].",
        "Append the identity matrix on the right: [A | I].",
    ),
    "lesson_disc_swap": _copy("Поменяем строки ARG1 и ARG2.", "Swap rows ARG1 and ARG2.", 2),
    "lesson_disc_scale": _copy(
        "Умножим строку ARG1 на ARG2.",
        "Multiply row ARG1 by ARG2.",
        2,
    ),
    "lesson_disc_eliminate": _copy(
        "К строке ARG1 прибавим строку ARG2, умноженную на ARG3.",
        "Add ARG3 times row ARG2 to row ARG1.",
        3,
    ),
    "lesson_disc_inverse_read": _copy(
        "Слева получена I; правая половина равна A⁻¹.",
        "The left block is I; the right block is A⁻¹.",
    ),
    "lesson_disc_cell": _copy(
        "Ячейка (ARG1, ARG2): перемножим соответствующие элементы строки и столбца.",
        "Cell (ARG1, ARG2): multiply matching row and column entries.",
        2,
    ),
    "lesson_disc_coordinate": _copy(
        "Подставим координаты в формулу компоненты ARG1.",
        "Substitute coordinates in the formula for component ARG1.",
        1,
    ),
    "lesson_disc_vector": _copy("Вычислим по координатам", "Calculate from coordinates"),
    "lesson_disc_counting": _copy("Раскроем комбинаторную формулу", "Expand the counting formula"),
    "lesson_disc_factorial": _copy(
        "Факториал — произведение целых от 1 до n; пустое произведение равно 1.",
        "A factorial is the product of integers from 1 to n; an empty product is 1.",
    ),
    "lesson_disc_choose": _copy(
        "Подставим n и k в n! / (k!(n−k)!). Порядок выбора не учитываем.",
        "Insert n and k in n! / (k!(n−k)!). Selection order does not matter.",
    ),
    "lesson_disc_arrange": _copy(
        "Для упорядоченного выбора без повторений используем n! / (n−k)!.",
        "For ordered selection without replacement use n! / (n−k)!.",
    ),
    "lesson_disc_sets": _copy("Проверим элементы множеств", "Check the set elements"),
    "lesson_disc_membership": _copy(
        "Проверим наличие данного элемента в указанном множестве.",
        "Check whether this element occurs in the specified set.",
    ),
    "lesson_disc_set_keep": _copy(
        "Проверим условие включения элемента в результат операции.",
        "Check the condition for including this element in the operation result.",
    ),
    "lesson_disc_statistics": _copy(
        "Подставим данные в формулу", "Substitute the data in the formula"
    ),
    "lesson_disc_mean": _copy(
        "Сложим все ARG1 значений и разделим на их количество.",
        "Add all ARG1 observations and divide by their count.",
        1,
    ),
    "lesson_disc_system": _copy(
        "Исключим неизвестные по строкам", "Eliminate unknowns by row operations"
    ),
    "lesson_disc_system_matrix": _copy(
        "Запишем коэффициенты и правые части; порядок неизвестных: ARG1.",
        "Write the coefficients and right sides; variable order: ARG1.",
        1,
    ),
    "lesson_disc_substitution": _copy(
        "Подставим заданное значение вместо переменной, сохраняя структуру выражения.",
        "Replace the variable by the given value while preserving the expression structure.",
    ),
}


def _article(ru: tuple[str, ...], en: tuple[str, ...]) -> dict[str, dict[str, str]]:
    fields = ("title", "summary", "formula", "conditions", "example", "mistake")
    return {"ru": dict(zip(fields, ru, strict=True)), "en": dict(zip(fields, en, strict=True))}


ARTICLES = {
    "discrete_determinant": _article(
        (
            "Определитель",
            "Разложение превращает определитель в сумму меньших определителей.",
            "det A = Σⱼ (−1)^(1+j) a₁ⱼ det M₁ⱼ",
            "Матрица квадратная.",
            "det [[2,3],[1,4]] = 2·4−3·1 = 5.",
            "Не забывайте знак минус у второго слагаемого.",
        ),
        (
            "Determinants",
            "Expansion reduces a determinant to smaller determinants.",
            "det A = Σⱼ (−1)^(1+j) a₁ⱼ det M₁ⱼ",
            "The matrix must be square.",
            "det [[2,3],[1,4]] = 2·4−3·1 = 5.",
            "Do not lose the minus sign on the second term.",
        ),
    ),
    "discrete_matrix": _article(
        (
            "Операции с матрицами",
            "Элемент произведения получается из строки и столбца.",
            "(AB)ᵢⱼ = Σₖ aᵢₖbₖⱼ; [A|I] → [I|A⁻¹]",
            "Для AB внутренние размеры совпадают; для A⁻¹ det A ≠ 0.",
            "[[1,2]]·[[3],[4]] = [[11]].",
            "Матричное произведение не является поэлементным.",
        ),
        (
            "Matrix operations",
            "Each product entry uses one row and one column.",
            "(AB)ᵢⱼ = Σₖ aᵢₖbₖⱼ; [A|I] → [I|A⁻¹]",
            "Product inner dimensions must agree; an inverse needs det A ≠ 0.",
            "[[1,2]]·[[3],[4]] = [[11]].",
            "Matrix multiplication is not entrywise multiplication.",
        ),
    ),
    "discrete_vectors": _article(
        (
            "Координаты векторов",
            "Скалярное произведение — сумма попарных произведений.",
            "u·v = Σ uᵢvᵢ; ‖u‖ = √Σ uᵢ²; (u×v)₁ = u₂v₃−u₃v₂",
            "Размерности совпадают; × здесь только в трёх измерениях.",
            "(1,2)·(3,4) = 3+8 = 11.",
            "Скалярное произведение даёт число, векторное — вектор.",
        ),
        (
            "Vector coordinates",
            "A dot product sums pairwise coordinate products.",
            "u·v = Σ uᵢvᵢ; ‖u‖ = √Σ uᵢ²; (u×v)₁ = u₂v₃−u₃v₂",
            "Dimensions agree; the cross product here is three-dimensional.",
            "(1,2)·(3,4) = 3+8 = 11.",
            "A dot product is a scalar, not a vector.",
        ),
    ),
    "discrete_counting": _article(
        (
            "Сочетания и размещения",
            "Сначала решите, важен ли порядок выбранных объектов.",
            "n! = 1·…·n; C(n,k) = n!/(k!(n−k)!); P(n,k) = n!/(n−k)!",
            "n,k целые; 0 ≤ k ≤ n; повторений нет; 0! = 1.",
            "C(5,2) = 120/(2·6) = 10; P(5,2) = 20.",
            "Не считайте разные порядки отдельными сочетаниями.",
        ),
        (
            "Combinations and arrangements",
            "First decide whether selection order matters.",
            "n! = 1·…·n; C(n,k) = n!/(k!(n−k)!); P(n,k) = n!/(n−k)!",
            "Integers 0 ≤ k ≤ n, no replacement, and 0! = 1.",
            "C(5,2) = 120/(2·6) = 10; P(5,2) = 20.",
            "Do not count different orders as different combinations.",
        ),
    ),
    "discrete_sets": _article(
        (
            "Конечные множества",
            "Условие принадлежности определяет каждый элемент результата.",
            "x∈A∪B ⇔ x∈A или x∈B; x∈A∩B ⇔ x∈A и x∈B",
            "Заданы конечные множества с определимой принадлежностью.",
            "{1,2}∩{2,3} = {2}; объединение равно {1,2,3}.",
            "Повторение элемента не увеличивает множество.",
        ),
        (
            "Finite sets",
            "Membership determines every element of the result.",
            "x∈A∪B ⇔ x∈A or x∈B; x∈A∩B ⇔ x∈A and x∈B",
            "Finite sets with decidable membership are given.",
            "{1,2}∩{2,3} = {2}; their union is {1,2,3}.",
            "Repeated entries do not enlarge a set.",
        ),
    ),
    "discrete_statistics": _article(
        (
            "Среднее и подстановка",
            "Среднее учитывает каждое наблюдение, включая повторы.",
            "x̄ = (x₁+…+xₙ)/n; p(a) = p(x)|ₓ₌ₐ",
            "n > 0; значение подстановки входит в область определения.",
            "Среднее 2,2,8: (2+2+8)/3 = 4; p(x)=x²+1: p(3)=10.",
            "Делите на число наблюдений, не на число разных значений.",
        ),
        (
            "Means and substitution",
            "The mean counts every observation, including repetitions.",
            "x̄ = (x₁+…+xₙ)/n; p(a) = p(x)|ₓ₌ₐ",
            "n > 0; a substituted value must lie in the domain.",
            "The mean of 2,2,8 is (2+2+8)/3 = 4; for p(x)=x²+1, p(3)=10.",
            "Divide by the observation count, not the distinct-value count.",
        ),
    ),
    "discrete_systems": _article(
        (
            "Метод Гаусса",
            "Обратимые операции со строками сохраняют множество решений.",
            "Rᵢ ↔ Rⱼ; Rᵢ ← cRᵢ (c ≠ 0); Rᵢ ← Rᵢ+cRⱼ",
            "Система линейная; коэффициенты и правые части известны.",
            "x+y=3, x−y=1: R₂←R₂−R₁ даёт −2y=−2, затем y=1, x=2.",
            "Применяйте действие ко всей строке, включая правую часть.",
        ),
        (
            "Gaussian elimination",
            "Invertible row operations preserve the solution set.",
            "Rᵢ ↔ Rⱼ; Rᵢ ← cRᵢ (c ≠ 0); Rᵢ ← Rᵢ+cRⱼ",
            "The system is linear with known coefficients and right sides.",
            "x+y=3, x−y=1: R₂←R₂−R₁ gives −2y=−2, then y=1 and x=2.",
            "Transform the entire row, including its right side.",
        ),
    ),
}

RULE_TOPICS = {
    **dict.fromkeys(
        (
            "det2_calc",
            "det2_determinant_rule",
            "det3_sarrus_eval",
            "det3_sarrus_rule",
            "det_laplace_rule_row_simple",
            "matrix_det_rewrite",
        ),
        "discrete_determinant",
    ),
    **dict.fromkeys(
        (
            "matrix_mul",
            "matrix_add",
            "matrix_sub",
            "matrix_mul_scalar",
            "matrix_inv_find_smpl",
            "matrix_inv_right_is_inv",
        ),
        "discrete_matrix",
    ),
    **dict.fromkeys(
        (
            "factorial_calculate",
            "choose_calculate",
            "permutation_calculate",
            "variation_not_allowed_calculate",
        ),
        "discrete_counting",
    ),
    **dict.fromkeys(
        ("union", "intersection", "set_difference", "set_membership", "set_inclusion"),
        "discrete_sets",
    ),
    **dict.fromkeys(
        (
            "vector_length",
            "vector_dot",
            "vector_cross",
            "vector_add",
            "vector_subtract",
            "vector_scale",
        ),
        "discrete_vectors",
    ),
    **dict.fromkeys(("function_evaluate_expr", "function_evaluate_value"), "discrete_statistics"),
    **dict.fromkeys(
        (
            "system_2x2_cramer_rule",
            "system_2x2_solve_elimination",
            "system_2x2_add_eqs",
            "system_3x3_eliminate_var",
            "system_3x3_rem_vars",
            "system_2x2_solve_substitution",
        ),
        "discrete_systems",
    ),
}


RULE_TOPICS.update(
    {
        **dict.fromkeys(("lesson_disc_det_expand", "lesson_disc_minor"), "discrete_determinant"),
        **dict.fromkeys(
            (
                "lesson_disc_matrix",
                "lesson_disc_augment",
                "lesson_disc_inverse_read",
                "lesson_disc_cell",
            ),
            "discrete_matrix",
        ),
        **dict.fromkeys(("lesson_disc_vector", "lesson_disc_coordinate"), "discrete_vectors"),
        **dict.fromkeys(
            (
                "lesson_disc_counting",
                "lesson_disc_factorial",
                "lesson_disc_choose",
                "lesson_disc_arrange",
            ),
            "discrete_counting",
        ),
        **dict.fromkeys(
            ("lesson_disc_sets", "lesson_disc_membership", "lesson_disc_set_keep"), "discrete_sets"
        ),
        **dict.fromkeys(
            ("lesson_disc_statistics", "lesson_disc_mean", "lesson_disc_substitution"),
            "discrete_statistics",
        ),
        **dict.fromkeys(
            (
                "lesson_disc_system",
                "lesson_disc_system_matrix",
                "lesson_disc_swap",
                "lesson_disc_scale",
                "lesson_disc_eliminate",
            ),
            "discrete_systems",
        ),
    }
)


def _num(value: int) -> CoreNode:
    return CoreNode.constant(str(value))


def _op(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _sum(nodes: list[CoreNode]) -> CoreNode:
    return _op(T.ADD, *nodes) if len(nodes) > 1 else nodes[0] if nodes else _num(0)


def _product(nodes: list[CoreNode]) -> CoreNode:
    return _op(T.MULTIPLY, *nodes) if len(nodes) > 1 else nodes[0] if nodes else _num(1)


def _add(result: SolveResult, left: CoreNode, right: CoreNode, key: str, *args: CoreNode) -> None:
    if not left.structural_eq(right):
        result.add(Step(left=left, right=right, key=key, args=list(args)))


def _calculate(result: SolveResult, expression: CoreNode) -> CoreNode:
    value = from_sympy(sympy.simplify(to_sympy(expression)))
    _add(result, expression, value, "lesson_disc_arithmetic")
    return value


def _matrix(node: CoreNode) -> sympy.Matrix:
    if node.type is T.MATRIX:
        matrix = to_sympy(node)
    else:
        elements = [
            item
            for row in node.children
            for item in (row.children if row.type is T.MATRIX_ROW else [row])
        ]
        size = sympy.integer_nthroot(len(elements), 2)[0]
        if not size or size * size != len(elements):
            raise ValueError("not a square matrix")
        matrix = sympy.Matrix(size, size, [to_sympy(item) for item in elements])
    if matrix.rows > 6 or matrix.cols > 12 or any(x.free_symbols for x in matrix):
        raise ValueError("unbounded or symbolic matrix")
    return matrix


def _det_node(matrix: sympy.Matrix) -> CoreNode:
    return _op(T.DETERMINANT, *[from_sympy(x) for x in matrix])


def _det(result: SolveResult, matrix: sympy.Matrix) -> CoreNode:
    size = matrix.rows
    if size != matrix.cols or size < 1:
        raise ValueError("determinant needs square matrix")
    if size == 1:
        return from_sympy(matrix[0, 0])
    terms = []
    for column in range(size):
        minor = matrix.minor_submatrix(0, column)
        if size == 3:
            _det(result, minor)
        if size > 2:
            _add(
                result,
                _det_node(minor),
                from_sympy(minor.det()),
                "lesson_disc_minor",
                _num(1),
                _num(column + 1),
            )
        # The 2x2 expansion keeps both products visible instead of pre-evaluating them.
        minor_value = from_sympy(minor[0, 0] if size == 2 else minor.det())
        term = _product([from_sympy(matrix[0, column]), minor_value])
        terms.append(_op(T.NEGATIVE, term) if column % 2 else term)
    expression = _sum(terms)
    _add(result, _det_node(matrix), expression, "lesson_disc_det_expand")
    return _calculate(result, expression)


def _reduce(result: SolveResult, matrix: sympy.Matrix, columns: int) -> sympy.Matrix:
    current = matrix.copy()
    pivot_row = 0
    for column in range(columns):
        pivot = next((r for r in range(pivot_row, current.rows) if current[r, column] != 0), None)
        if pivot is None:
            continue
        if pivot != pivot_row:
            before = from_sympy(current)
            current.row_swap(pivot, pivot_row)
            _add(
                result,
                before,
                from_sympy(current),
                "lesson_disc_swap",
                _num(pivot + 1),
                _num(pivot_row + 1),
            )
        factor = sympy.cancel(1 / current[pivot_row, column])
        if factor != 1:
            before = from_sympy(current)
            current[pivot_row, :] *= factor
            _add(
                result,
                before,
                from_sympy(current),
                "lesson_disc_scale",
                _num(pivot_row + 1),
                from_sympy(factor),
            )
        for row in range(current.rows):
            factor = -current[row, column]
            if row == pivot_row or factor == 0:
                continue
            before = from_sympy(current)
            current[row, :] += factor * current[pivot_row, :]
            _add(
                result,
                before,
                from_sympy(current),
                "lesson_disc_eliminate",
                _num(row + 1),
                _num(pivot_row + 1),
                from_sympy(factor),
            )
        pivot_row += 1
        if pivot_row == current.rows:
            break
    return current


def _matrix_detail(step: Step, result: SolveResult) -> None:
    assert step.left is not None
    matrix = _matrix(step.left)
    if step.key in RULE_TOPICS and RULE_TOPICS[step.key] == "discrete_determinant":
        result.set_solution(_det(result, matrix))
    elif step.key in ("matrix_inv_find_smpl", "matrix_inv_right_is_inv"):
        if matrix.rows != matrix.cols or matrix.det() == 0:
            return
        augmented = matrix.row_join(sympy.eye(matrix.rows))
        _add(result, step.left, from_sympy(augmented), "lesson_disc_augment")
        reduced = _reduce(result, augmented, matrix.cols)
        inverse = from_sympy(reduced[:, matrix.cols :])
        _add(result, from_sympy(reduced), inverse, "lesson_disc_inverse_read")
        result.set_solution(inverse)
    elif step.key in ("matrix_mul", "matrix_add", "matrix_sub", "matrix_mul_scalar"):
        if not step.args:
            return
        other = to_sympy(step.args[0])
        if step.key == "matrix_mul":
            if matrix.cols != other.rows:
                return
            answer = matrix * other
        elif step.key == "matrix_mul_scalar":
            answer = matrix * other
        else:
            if matrix.shape != other.shape:
                return
            answer = matrix + other if step.key == "matrix_add" else matrix - other
        for row in range(answer.rows):
            for col in range(answer.cols):
                if step.key == "matrix_mul":
                    expression = _sum(
                        [
                            _product([from_sympy(matrix[row, k]), from_sympy(other[k, col])])
                            for k in range(matrix.cols)
                        ]
                    )
                else:
                    operand = other if step.key == "matrix_mul_scalar" else other[row, col]
                    kind = {
                        "matrix_add": T.ADD,
                        "matrix_sub": T.SUBTRACT,
                        "matrix_mul_scalar": T.MULTIPLY,
                    }[step.key]
                    expression = _op(kind, from_sympy(matrix[row, col]), from_sympy(operand))
                _add(
                    result,
                    expression,
                    from_sympy(answer[row, col]),
                    "lesson_disc_cell",
                    _num(row + 1),
                    _num(col + 1),
                )
        result.set_solution(from_sympy(answer))


def _counting(step: Step, result: SolveResult) -> None:
    assert step.left is not None
    values = [to_sympy(c) for c in step.left.children]
    if not values or any(v.is_Integer is not True or v < 0 or v > 1000 for v in values):
        return
    n = int(values[0])
    if step.key == "factorial_calculate":
        if n > 60:
            return
        expression = _product([_num(i) for i in range(1, n + 1)])
        _add(result, step.left, expression, "lesson_disc_factorial")
    else:
        if len(values) != 2 or values[1] > n or n > 60:
            return
        k = int(values[1])
        numerator = _op(T.FACTORIAL, _num(n))
        denominator = _op(T.FACTORIAL, _num(n - k))
        choose = step.key == "choose_calculate"
        if choose:
            denominator = _product([_op(T.FACTORIAL, _num(k)), denominator])
        formula = _op(T.DIVIDE, numerator, denominator)
        _add(result, step.left, formula, "lesson_disc_choose" if choose else "lesson_disc_arrange")
        top = _product([_num(i) for i in range(n - k + 1, n + 1)])
        expression = (
            _op(T.DIVIDE, top, _product([_num(i) for i in range(1, k + 1)])) if choose else top
        )
        _add(result, formula, expression, "lesson_disc_factorial")
    result.set_solution(_calculate(result, expression))


def _vectors(step: Step, result: SolveResult) -> None:
    assert step.left is not None
    if step.left.type not in (T.LIST, T.VERTICAL_LIST):
        return
    first = list(step.left.children)
    if not first or len(first) > 12:
        return
    second = list(step.args[0].children) if step.args else []
    if step.key == "vector_length":
        expression = _op(T.ROOT2, _sum([_op(T.POWER, x, _num(2)) for x in first]))
        result.set_solution(_calculate(result, expression))
        return
    if step.key != "vector_scale" and len(second) != len(first):
        return
    if step.key == "vector_dot":
        result.set_solution(
            _calculate(result, _sum([_product([a, b]) for a, b in zip(first, second, strict=True)]))
        )
        return
    expressions = []
    if step.key == "vector_cross" and len(first) == 3:
        for i, j in ((1, 2), (2, 0), (0, 1)):
            expressions.append(
                _op(T.SUBTRACT, _product([first[i], second[j]]), _product([first[j], second[i]]))
            )
    elif step.key == "vector_scale" and step.args:
        expressions = [_product([x, step.args[0]]) for x in first]
    elif step.key in ("vector_add", "vector_subtract"):
        kind = T.ADD if step.key == "vector_add" else T.SUBTRACT
        expressions = [_op(kind, a, b) for a, b in zip(first, second, strict=True)]
    answers = []
    for index, expression in enumerate(expressions):
        answer = from_sympy(sympy.simplify(to_sympy(expression)))
        _add(result, expression, answer, "lesson_disc_coordinate", _num(index + 1))
        answers.append(answer)
    if answers:
        result.set_solution(_op(T.LIST, *answers))


def _sets(step: Step, result: SolveResult) -> None:
    assert step.left is not None
    node = step.left
    if node.type in (T.ELEMENT_OF, T.ELEMENT_NOT_OF) and len(node.children) == 2:
        element, target = node.children
        finite = to_sympy(target)
        if not isinstance(finite, sympy.FiniteSet) or len(finite) > 60:
            return
        if to_sympy(element).free_symbols or any(value.free_symbols for value in finite):
            return
        comparisons = [_op(T.EQUALS, element, from_sympy(value)) for value in finite]
        for comparison in comparisons:
            a, b = comparison.children
            _add(
                result,
                comparison,
                boolean_node(to_sympy(a) == to_sympy(b)),
                "lesson_disc_membership",
            )
        contains = to_sympy(element) in finite
        result.set_solution(
            boolean_node(not contains if node.type is T.ELEMENT_NOT_OF else contains)
        )
        return
    subset_types = (T.SUBSET_OR_EQUALS, T.PROPER_SUBSET, T.NOT_PROPER_SUBSET)
    superset_types = (T.SUPERSET_OR_EQUALS, T.PROPER_SUPERSET, T.NOT_PROPER_SUPERSET)
    if node.type in (*subset_types, *superset_types) and len(node.children) == 2:
        first, second = node.children
        if node.type in superset_types:
            first, second = second, first
        small, large = to_sympy(first), to_sympy(second)
        if not isinstance(small, sympy.FiniteSet) or not isinstance(large, sympy.FiniteSet):
            return
        if any(value.free_symbols for value in small | large):
            return
        if len(small) + len(large) > 60:
            return
        for element in small:
            _add(
                result,
                _op(T.ELEMENT_OF, from_sympy(element), second),
                boolean_node(element in large),
                "lesson_disc_membership",
            )
        if node.type not in (T.SUBSET_OR_EQUALS, T.SUPERSET_OR_EQUALS):
            _add(
                result,
                _op(T.EQUALS, first, second),
                boolean_node(small == large),
                "lesson_disc_set_keep",
            )
        included = small.is_subset(large)
        if node.type not in (T.SUBSET_OR_EQUALS, T.SUPERSET_OR_EQUALS):
            included = included and small != large
        if node.type in (T.NOT_PROPER_SUBSET, T.NOT_PROPER_SUPERSET):
            included = not included
        result.set_solution(boolean_node(bool(included)))
        return
    if node.type not in (T.UNION, T.INTERSECTION, T.DIFFERENCE):
        return
    operands = [to_sympy(child) for child in node.children]
    if not operands or not all(isinstance(value, sympy.FiniteSet) for value in operands):
        return
    if any(element.free_symbols for operand in operands for element in operand):
        return
    candidates = sympy.Union(*operands)
    answer = to_sympy(node)
    if len(candidates) > 60:
        return
    for element in candidates:
        checks = [_op(T.ELEMENT_OF, from_sympy(element), child) for child in node.children]
        _add(result, _op(T.LIST, *checks), boolean_node(element in answer), "lesson_disc_set_keep")
    result.set_solution(from_sympy(answer))


def _statistics(step: Step, result: SolveResult) -> None:
    assert step.left is not None
    node = step.left
    if node.type is T.MEAN and node.children:
        expression = _op(T.DIVIDE, _sum(list(node.children)), _num(len(node.children)))
        _add(result, node, expression, "lesson_disc_mean", _num(len(node.children)))
        total = _calculate(result, _sum(list(node.children)))
        result.set_solution(_calculate(result, _op(T.DIVIDE, total, _num(len(node.children)))))
    elif step.key in ("function_evaluate_expr", "function_evaluate_value"):
        if node.type is T.EVALUATE_EXPRESSION and len(node.children) == 2:
            expression, value = node.children
        elif step.args:
            expression, value = node, step.args[0]
        else:
            return
        symbols = to_sympy(expression).free_symbols
        if len(symbols) != 1:
            return
        name = next(iter(symbols)).name

        def replace(part: CoreNode) -> CoreNode:
            if part.type is T.VARIABLE and part.value == name:
                return value
            return CoreNode(
                type=part.type, value=part.value, children=[replace(c) for c in part.children]
            )

        substituted = replace(expression)
        _add(result, node, substituted, "lesson_disc_substitution")
        result.set_solution(_calculate(result, substituted))


def _system(step: Step, result: SolveResult) -> None:
    assert step.left is not None
    node = step.left
    if node.type is not T.SYSTEM or not 1 <= len(node.children) <= 6:
        return
    expressions = []
    for equation in node.children:
        if equation.type is not T.EQUALS or len(equation.children) != 2:
            return
        expressions.append(to_sympy(equation.children[0]) - to_sympy(equation.children[1]))
    symbols = sorted(set().union(*(e.free_symbols for e in expressions)), key=str)
    if not 1 <= len(symbols) <= 6:
        return
    matrix, rhs = sympy.linear_eq_to_matrix(expressions, symbols)
    if any(value.free_symbols for value in matrix.row_join(rhs)):
        return
    augmented = matrix.row_join(rhs)
    _add(
        result,
        node,
        from_sympy(augmented),
        "lesson_disc_system_matrix",
        _op(T.LIST, *[from_sympy(s) for s in symbols]),
    )
    reduced = _reduce(result, augmented, matrix.cols)
    result.set_solution(from_sympy(reduced))


def enrich(step: Step) -> str | None:
    """Attach genuine intermediate calculations without replacing the outer step.

    Existing subresults and authored detail keys are terminal. Unsupported,
    ambiguous, symbolic or oversized input receives no invented calculation.
    """
    if step.key.startswith("lesson_disc_") or step.left is None or step.subresult is not None:
        return None
    # Optional command marker preserves the legacy outer description key while
    # retaining operation identity. Other args remain the actual operands.
    working = step
    if step.key == "calculate_short":
        markers = [
            arg
            for arg in step.args
            if arg.type is T.TEXT_KEY and (arg.value or "").startswith("vector_")
        ]
        if len(markers) == 1:
            working = Step(
                step.left,
                step.right,
                markers[0].value or "",
                [arg for arg in step.args if arg is not markers[0]],
            )
    topic = RULE_TOPICS.get(working.key)
    if step.left.type is T.MEAN:
        topic = "discrete_statistics"
    if topic is None:
        return None
    detail = SolveResult()
    title = {
        "discrete_determinant": "lesson_disc_matrix",
        "discrete_matrix": "lesson_disc_matrix",
        "discrete_vectors": "lesson_disc_vector",
        "discrete_counting": "lesson_disc_counting",
        "discrete_sets": "lesson_disc_sets",
        "discrete_statistics": "lesson_disc_statistics",
        "discrete_systems": "lesson_disc_system",
    }[topic]
    try:
        if topic in ("discrete_determinant", "discrete_matrix"):
            _matrix_detail(step, detail)
        elif topic == "discrete_counting":
            _counting(step, detail)
        elif topic == "discrete_vectors":
            _vectors(working, detail)
        elif topic == "discrete_sets":
            _sets(step, detail)
        elif topic == "discrete_statistics":
            _statistics(step, detail)
        elif topic == "discrete_systems":
            _system(step, detail)
    except (
        ValueError,
        TypeError,
        AttributeError,
        IndexError,
        NotImplementedError,
        SolveError,
        sympy.PolynomialError,
    ):
        return None
    if not detail:
        return None
    detail.header = title
    # A nested answer must preserve the outer answer's semantics and representation.
    if step.right is not None:
        detail.set_solution(step.right)
    step.subresult = detail
    return title
