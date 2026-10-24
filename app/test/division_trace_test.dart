import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/division_trace.dart';

DivisionTrace? trace(String a, String b) => DivisionTrace.fromNode(
  CoreNode(
    type: CoreNodeType.divide,
    children: [
      CoreNode(type: CoreNodeType.constant, value: a),
      CoreNode(type: CoreNodeType.constant, value: b),
    ],
  ),
);

void main() {
  test('long division is exact, including internal zeros', () {
    final t = trace('1005', '5')!;
    expect(t.digits.last.quotient, '201');
    expect(t.digits.map((d) => d.digit), [2, 0, 1]);
    for (final d in t.digits) {
      expect(d.partial, d.product + d.remainder);
      expect(d.product, t.divisor * BigInt.from(d.digit));
      expect(d.remainder < t.divisor, isTrue);
    }
  });
  test('terminating decimal, zero and repeating decimal are distinguished', () {
    expect(trace('1', '8')!.digits.last.quotient, '0.125');
    expect(trace('0', '3')!.digits.last.quotient, '0');
    expect(trace('1', '3')!.repeatAt, 0);
    expect(trace('1', '7')!.digits.last.quotient, '0.142857');
    expect(trace('1', '7')!.repeatAt, 0);
    expect(trace('1', '97')!.truncated, isTrue);
  });
  test('unsupported inputs and division by zero never invent a trace', () {
    expect(trace('3', '0'), isNull);
    expect(trace('-3', '2'), isNull);
    expect(trace('1.5', '2'), isNull);
  });
}
