/// Настройки пользователя.
///
/// Повторяют профиль Photomath (`User` в APK): десятичный разделитель,
/// нотация биномиального коэффициента и предпочитаемый метод умножения/
/// деления. Значения взяты из оригинала:
///
/// * `DecimalSeparator` — `POINT`/`COMMA` (символ `.`/`,`);
/// * `BinomialType` — `NOTATION_ONE`/`NOTATION_TWO`;
/// * метод умножения — `MUL_US`/`MUL_LTR`/`MUL_RTL`;
/// * метод деления — `DIV_US`/`DIV_RU`/`DIV_STANDARD`.
///
/// Хранится в файле `settings.json` в каталоге приложения. Если файловая
/// система недоступна (тесты, окружение без плагина) — работаем в памяти.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

/// Десятичный разделитель. Оригинал: `DecimalSeparator`.
enum DecimalSeparator {
  /// Точка — `DecimalSeparator.POINT`.
  point('.', 'point'),

  /// Запятая — `DecimalSeparator.COMMA`.
  comma(',', 'comma');

  const DecimalSeparator(this.symbol, this.id);

  /// Символ, которым показываем дробную часть.
  final String symbol;

  /// Идентификатор для хранения (`point`/`comma`).
  final String id;

  static DecimalSeparator fromId(String? value) {
    for (final separator in values) {
      if (separator.id == value) return separator;
    }
    return DecimalSeparator.point;
  }
}

/// Нотация биномиального коэффициента. Оригинал: `BinomialType`.
enum BinomialNotation {
  /// `NOTATION_ONE` — «этажная» запись (скобки, верхний/нижний индекс).
  notationOne('NotationOne'),

  /// `NOTATION_TWO` — строчная запись `C(n, k)`.
  notationTwo('NotationTwo');

  const BinomialNotation(this.id);

  final String id;

  static BinomialNotation fromId(String? value) {
    for (final notation in values) {
      if (notation.id == value) return notation;
    }
    return BinomialNotation.notationOne;
  }
}

/// Предпочитаемый метод умножения. Оригинал: `MUL_*`.
enum MultiplicationMethod {
  /// `MUL_US` — «столбиком» в американской записи.
  us('MUL_US', 'Столбиком (US)'),

  /// `MUL_LTR` — умножение слева направо.
  ltr('MUL_LTR', 'Слева направо'),

  /// `MUL_RTL` — умножение справа налево.
  rtl('MUL_RTL', 'Справа налево');

  const MultiplicationMethod(this.id, this.label);

  final String id;
  final String label;

  static MultiplicationMethod fromId(String? value) {
    for (final method in values) {
      if (method.id == value) return method;
    }
    return MultiplicationMethod.us;
  }
}

/// Предпочитаемый метод деления. Оригинал: `DIV_*`.
enum DivisionMethod {
  /// `DIV_US` — американская запись.
  us('DIV_US', 'Столбиком (US)'),

  /// `DIV_RU` — русская запись «уголком».
  ru('DIV_RU', 'Уголком (RU)'),

  /// `DIV_STANDARD` — стандартная запись.
  standard('DIV_STANDARD', 'Стандартная');

  const DivisionMethod(this.id, this.label);

  final String id;
  final String label;

  static DivisionMethod fromId(String? value) {
    for (final method in values) {
      if (method.id == value) return method;
    }
    return DivisionMethod.us;
  }
}

/// Настройки пользователя с сохранением на диск.
class AppSettings extends ChangeNotifier {
  DecimalSeparator _decimalSeparator = DecimalSeparator.point;
  BinomialNotation _binomialNotation = BinomialNotation.notationOne;
  MultiplicationMethod _multiplicationMethod = MultiplicationMethod.us;
  DivisionMethod _divisionMethod = DivisionMethod.us;

  DecimalSeparator get decimalSeparator => _decimalSeparator;

  BinomialNotation get binomialNotation => _binomialNotation;

  MultiplicationMethod get multiplicationMethod => _multiplicationMethod;

  DivisionMethod get divisionMethod => _divisionMethod;

  set decimalSeparator(DecimalSeparator value) {
    if (value == _decimalSeparator) return;
    _decimalSeparator = value;
    notifyListeners();
    unawaited(_save());
  }

  set binomialNotation(BinomialNotation value) {
    if (value == _binomialNotation) return;
    _binomialNotation = value;
    notifyListeners();
    unawaited(_save());
  }

  set multiplicationMethod(MultiplicationMethod value) {
    if (value == _multiplicationMethod) return;
    _multiplicationMethod = value;
    notifyListeners();
    unawaited(_save());
  }

  set divisionMethod(DivisionMethod value) {
    if (value == _divisionMethod) return;
    _divisionMethod = value;
    notifyListeners();
    unawaited(_save());
  }

  /// Прочитать настройки с диска (если он доступен).
  Future<void> load() async {
    try {
      final file = await _file();
      if (!await file.exists()) return;
      final raw = jsonDecode(await file.readAsString());
      if (raw is! Map<String, dynamic>) return;
      _decimalSeparator = DecimalSeparator.fromId(raw['decimalSeparator'] as String?);
      _binomialNotation = BinomialNotation.fromId(raw['binomialNotation'] as String?);
      _multiplicationMethod =
          MultiplicationMethod.fromId(raw['multiplicationMethod'] as String?);
      _divisionMethod = DivisionMethod.fromId(raw['divisionMethod'] as String?);
      notifyListeners();
    } on Object {
      // Диска нет — остаются значения по умолчанию.
    }
  }

  Map<String, dynamic> toJson() => {
    'decimalSeparator': _decimalSeparator.id,
    'binomialNotation': _binomialNotation.id,
    'multiplicationMethod': _multiplicationMethod.id,
    'divisionMethod': _divisionMethod.id,
  };

  Future<File> _file() async {
    final directory = await getApplicationSupportDirectory();
    return File('${directory.path}/settings.json');
  }

  Future<void> _save() async {
    try {
      final file = await _file();
      await file.writeAsString(jsonEncode(toJson()));
    } on Object {
      // Нет диска — значения остаются в памяти текущего запуска.
    }
  }
}
