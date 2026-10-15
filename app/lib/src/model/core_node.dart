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
  sin('SIN'),
  cos('COS'),
  tan('TAN'),
  log('LOG'),
  ln('LN'),
  exp('EXP'),
  abs('ABS'),
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
  const CoreNode({required this.type, this.value, this.children = const []});

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
    );
  }

  final CoreNodeType type;

  /// Текст терминала; `null` у не-терминалов.
  final String? value;

  final List<CoreNode> children;

  /// Разбор разошёлся ли с контрактом: попался неизвестный тип.
  static bool hadUnknownTypeIn(Map<String, dynamic> json) =>
      CoreNodeType.fromWire(json['type'] as String?) == null;

  /// Текстовое представление для отладки и тестов.
  ///
  /// Это не рендер: дроби и корни здесь показываются плоско. Для показа
  /// используется [toLatex].
  @override
  String toString() => value ?? '${type.wire}(${children.join(', ')})';

  @override
  bool operator ==(Object other) =>
      other is CoreNode &&
      other.type == type &&
      other.value == value &&
      _sameChildren(children, other.children);

  @override
  int get hashCode => Object.hash(type, value, Object.hashAll(children));

  static bool _sameChildren(List<CoreNode> a, List<CoreNode> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }
}
