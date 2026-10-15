/// Модель узла выражения — зеркало `CoreNode` из Python-бэкенда.
///
/// Имена полей и значения `type` повторяют контракт Photomath
/// (`truth/03-solver-contract.md`), поэтому ответ бэкенда разбирается
/// без преобразований, а расхождение с оригиналом видно сразу.
library;

import 'package:flutter/foundation.dart';

/// Тип узла выражения.
///
/// Значения совпадают с `CoreNodeType` из APK — 143 штуки, из которых
/// сейчас используется часть. Полный перечень: `truth/data/enums.json`.
///
/// Новое значение добавляется сначала в Python (`node_types.py`,
/// генерируется из того же файла), потом сюда.
enum CoreNodeType {
  constant('CONSTANT'),
  variable('VARIABLE'),
  empty('EMPTY'),
  text('TEXT'),
  fraction('FRACTION'),
  fractionMixed('FRACTION_MIXED'),
  positive('POSITIVE'),
  negative('NEGATIVE'),
  add('ADD'),
  subtract('SUBTRACT'),
  divide('DIVIDE'),
  multiply('MULTIPLY'),
  multiplyImplicit('MULTIPLY_IMPLICIT'),
  bracket('BRACKET'),
  power('POWER'),
  factorial('FACTORIAL'),
  root('ROOT'),
  root2('ROOT2'),
  equals('EQUALS'),
  notEquals('NOT_EQUALS'),
  lessThan('LESS_THAN'),
  lessThanEqual('LESS_THAN_EQUAL'),
  greaterThan('GREATER_THAN'),
  greaterThanEqual('GREATER_THAN_EQUAL'),
  cot('COT'),
  sec('SEC'),
  csc('CSC'),
  asin('ASIN'),
  acos('ACOS'),
  atan('ATAN'),
  acot('ACOT'),
  asec('ASEC'),
  acsc('ACSC'),
  sinh('SINH'),
  cosh('COSH'),
  tanh('TANH'),
  coth('COTH'),
  sech('SECH'),
  csch('CSCH'),
  asinh('ASINH'),
  acosh('ACOSH'),
  atanh('ATANH'),
  acoth('ACOTH'),
  asech('ASECH'),
  acsch('ACSCH'),
  sin('SIN'),
  cos('COS'),
  tan('TAN'),
  log('LOG'),
  log10('LOG10'),
  ln('LN'),
  exp('EXP'),
  sign('SIGN'),
  floor('FLOOR'),
  abs('ABS'),
  degree('DEGREE'),
  radian('RADIAN'),
  percentage('PERCENTAGE'),
  derivation('DERIVATION'),
  derivation1('DERIVATION1'),
  integral('INTEGRAL'),
  integralDefinite('INTEGRAL_DEFINITE'),
  limit('LIMIT'),
  sigmaDefinite('SIGMA_DEFINITE'),
  choose('CHOOSE'),
  partialPermutation('PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT'),
  variation('VARIATION'),
  determinant2('DETERMINANT2'),
  determinant3('DETERMINANT3'),
  matrix('MATRIX'),
  matrixRow('MATRIX_ROW'),
  list('LIST'),
  system('SYSTEM');

  const CoreNodeType(this.wire);

  /// Имя типа в JSON — так его отдаёт бэкенд.
  final String wire;

  /// Разобрать имя типа; `null`, если такого типа нет.
  static CoreNodeType? fromWire(String? value) {
    for (final type in CoreNodeType.values) {
      if (type.wire == value) return type;
    }
    return null;
  }
}

/// Узел выражения.
@immutable
class CoreNode {
  const CoreNode({
    required this.type,
    this.value,
    this.children = const [],
    this.color,
    this.crossed,
  });

  /// Узел из JSON ответа бэкенда.
  ///
  /// Неизвестный тип не роняет разбор: подставляется [CoreNodeType.text],
  /// чтобы не потерять содержимое узла. Возвращаемое значение — вместе с
  /// признаком [CoreNodeParseResult.hadUnknownType].
  factory CoreNode.fromJson(Map<String, dynamic> json) {
    final type = CoreNodeType.fromWire(json['type'] as String?);
    final rawChildren = json['children'] as List<dynamic>? ?? const [];
    return CoreNode(
      type: type ?? CoreNodeType.text,
      value: json['value'] as String?,
      children: [
        for (final child in rawChildren)
          if (child is Map<String, dynamic>) CoreNode.fromJson(child),
      ],
      color: json['color'] as int?,
      crossed: json['crossed'] as bool?,
    );
  }

  final CoreNodeType type;

  /// Текст терминала; `null` у не-терминалов.
  final String? value;

  final List<CoreNode> children;

  /// Цвет подсветки части выражения (ARGB) — микро-анимация шага.
  final int? color;

  /// Зачёркнута ли часть выражения (сокращаемая часть) — микро-анимация.
  final bool? crossed;

  /// Разбор разошёлся ли с контрактом: попался неизвестный тип.
  static bool hadUnknownTypeIn(Map<String, dynamic> json) =>
      CoreNodeType.fromWire(json['type'] as String?) == null;

  /// Текстовое представление для отладки и тестов.
  ///
  /// Это не рендер: дроби и корни здесь показываются плоско. Для показа
  /// используется [toLatex].
  @override
  String toString() => value ?? '${type.wire}(${children.join(', ')})';

  /// Формат контракта: так узел уходит на бэкенд и сохраняется в блокнот.
  Map<String, dynamic> toJson() => {
    'type': type.wire,
    if (value != null) 'value': value,
    if (children.isNotEmpty)
      'children': [for (final child in children) child.toJson()],
    if (color != null) 'color': color,
    if (crossed != null) 'crossed': crossed,
  };

  @override
  bool operator ==(Object other) =>
      other is CoreNode &&
      other.type == type &&
      other.value == value &&
      other.color == color &&
      other.crossed == crossed &&
      _sameChildren(children, other.children);

  @override
  int get hashCode =>
      Object.hash(type, value, color, crossed, Object.hashAll(children));

  static bool _sameChildren(List<CoreNode> a, List<CoreNode> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }
}
