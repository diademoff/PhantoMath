import '../model/core_node.dart';

class DivisionDigit {
  const DivisionDigit({required this.column, required this.partial, required this.digit,
    required this.product, required this.remainder, required this.quotient});
  final int column;
  final BigInt partial;
  final int digit;
  final BigInt product;
  final BigInt remainder;
  final String quotient;
}

/// Exact, bounded presentation trace. Never replaces the solver's answer.
/// Unsupported operands have no animation rather than an invented explanation.
class DivisionTrace {
  const DivisionTrace(this.dividend, this.divisor, this.digits, this.decimalPlaces, this.repeatAt, this.truncated);
  final String dividend;
  final BigInt divisor;
  final List<DivisionDigit> digits;
  final int decimalPlaces;
  final int? repeatAt;
  final bool truncated;

  static DivisionTrace? fromNode(CoreNode node) {
    if (!{CoreNodeType.divide, CoreNodeType.fraction}.contains(node.type) || node.children.length != 2) return null;
    final a = node.children[0]; final b = node.children[1];
    if (a.type != CoreNodeType.constant || b.type != CoreNodeType.constant) return null;
    final pattern = RegExp(r'^\d{1,12}$');
    if (!pattern.hasMatch(a.value ?? '') || !pattern.hasMatch(b.value ?? '')) return null;
    final numerator = BigInt.parse(a.value!); final divisor = BigInt.parse(b.value!);
    if (divisor == BigInt.zero) return null;
    final source = numerator.toString();
    final digits = <DivisionDigit>[];
    var remainder = BigInt.zero;
    var quotient = '';
    for (var column = 0; column < source.length; column++) {
      final partial = remainder * BigInt.from(10) + BigInt.parse(source[column]);
      final digit = (partial ~/ divisor).toInt();
      remainder = partial % divisor;
      if (digits.isEmpty && digit == 0 && column < source.length - 1) continue;
      quotient += '$digit';
      digits.add(DivisionDigit(column: column, partial: partial, digit: digit,
        product: divisor * BigInt.from(digit), remainder: remainder, quotient: quotient));
    }
    final seen = <BigInt, int>{};
    var decimals = 0;
    int? repeatAt;
    while (remainder != BigInt.zero && decimals < 12) {
      if (seen.containsKey(remainder)) { repeatAt = seen[remainder]; break; }
      seen[remainder] = decimals;
      final partial = remainder * BigInt.from(10);
      final digit = (partial ~/ divisor).toInt();
      remainder = partial % divisor;
      quotient += decimals == 0 ? '.$digit' : '$digit';
      digits.add(DivisionDigit(column: source.length + 1 + decimals, partial: partial,
        digit: digit, product: divisor * BigInt.from(digit), remainder: remainder, quotient: quotient));
      decimals++;
    }
    return DivisionTrace(source, divisor, digits, decimals, repeatAt, remainder != BigInt.zero && repeatAt == null);
  }
}
