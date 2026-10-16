import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/functions/function_store.dart';
import 'package:mymath_app/src/model/core_node.dart';

CoreNode _var(String name) => CoreNode(type: CoreNodeType.variable, value: name);

CoreNode _num(String value) => CoreNode(type: CoreNodeType.constant, value: value);

CoreNode _definition() => CoreNode(
  type: CoreNodeType.equals,
  children: [
    CoreNode(
      type: CoreNodeType.function,
      value: 'f',
      children: [_var('x')],
    ),
    CoreNode(
      type: CoreNodeType.add,
      children: [_num('2'), _var('x')],
    ),
  ],
);

void main() {
  group('FunctionStore', () {
    test('распознаёт определение f(x) = …', () {
      final definition = FunctionStore.parse(_definition());
      expect(definition, isNotNull);
      expect(definition!.name, 'f');
      expect(definition.params, ['x']);
    });

    test('обычное выражение и уравнение — не определение', () {
      expect(FunctionStore.parse(_num('2')), isNull);
      expect(
        FunctionStore.parse(
          CoreNode(
            type: CoreNodeType.equals,
            children: [_var('x'), _num('2')],
          ),
        ),
        isNull,
      );
    });

    test('define/remove/clear и contract', () {
      final store = FunctionStore();
      store.define(FunctionStore.parse(_definition())!);
      expect(store.definitions, hasLength(1));
      expect(store.contract().single.type, CoreNodeType.equals);
      store.remove('f');
      expect(store.isEmpty, isTrue);
    });

    test('повторное определение заменяет прежнее', () {
      final store = FunctionStore();
      store.define(FunctionStore.parse(_definition())!);
      store.define(FunctionStore.parse(_definition())!);
      expect(store.definitions, hasLength(1));
    });
  });
}
