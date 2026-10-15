import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/settings/settings.dart';

void main() {
  group('AppSettings', () {
    test('значения по умолчанию', () {
      final settings = AppSettings();
      expect(settings.decimalSeparator, DecimalSeparator.point);
      expect(settings.binomialNotation, BinomialNotation.notationOne);
      expect(settings.multiplicationMethod, MultiplicationMethod.us);
      expect(settings.divisionMethod, DivisionMethod.us);
    });

    test('сериализация повторяет идентификаторы APK', () {
      final settings = AppSettings();
      settings.decimalSeparator = DecimalSeparator.comma;
      settings.binomialNotation = BinomialNotation.notationTwo;
      settings.multiplicationMethod = MultiplicationMethod.rtl;
      settings.divisionMethod = DivisionMethod.ru;
      expect(settings.toJson(), {
        'decimalSeparator': 'comma',
        'binomialNotation': 'NotationTwo',
        'multiplicationMethod': 'MUL_RTL',
        'divisionMethod': 'DIV_RU',
      });
    });

    test('разбор идентификаторов', () {
      expect(DecimalSeparator.fromId('comma'), DecimalSeparator.comma);
      expect(DecimalSeparator.fromId('bogus'), DecimalSeparator.point);
      expect(BinomialNotation.fromId('NotationTwo'), BinomialNotation.notationTwo);
      expect(MultiplicationMethod.fromId('MUL_LTR'), MultiplicationMethod.ltr);
      expect(DivisionMethod.fromId('DIV_STANDARD'), DivisionMethod.standard);
      expect(DivisionMethod.fromId(null), DivisionMethod.us);
    });

    test('смена значения уведомляет слушателей', () {
      final settings = AppSettings();
      var notified = 0;
      settings.addListener(() => notified++);
      settings.decimalSeparator = DecimalSeparator.comma;
      settings.decimalSeparator = DecimalSeparator.comma; // без изменений
      expect(notified, 1);
    });
  });
}
