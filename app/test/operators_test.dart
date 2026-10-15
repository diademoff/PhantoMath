import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/editor/operators.dart';

void main() {
  group('каталог операторов редактора', () {
    test('перечислены все 128 операторов APK без дублей', () {
      expect(apkEditorOperators, hasLength(128));
      expect(apkEditorOperators.toSet(), hasLength(128));
    });

    test('у каждого оператора есть действие или причина недоступности', () {
      for (final binding in operatorCatalog()) {
        expect(
          binding.available || (binding.reason?.isNotEmpty ?? false),
          isTrue,
          reason: '${binding.name}: нужен ключ или причина',
        );
        expect(
          binding.available ? binding.reason : binding.key,
          isNull,
          reason: '${binding.name}: не должно быть и ключа, и причины',
        );
        expect(binding.reason, isNot('не сопоставлен'), reason: binding.name);
      }
    });

    test('доступно подавляющее большинство операторов', () {
      final available = operatorCatalog().where((b) => b.available).length;
      expect(available, greaterThan(110));
    });

    test('недоступные помечены причиной', () {
      final unavailable =
          operatorCatalog().where((b) => !b.available).toList();
      expect(unavailable, isNotEmpty);
      for (final binding in unavailable) {
        expect(binding.reason, isNotNull);
      }
    });
  });
}
