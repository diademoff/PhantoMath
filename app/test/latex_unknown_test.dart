import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';

CoreNode _n(String type, [List<CoreNode> kids = const [], String? value]) =>
    CoreNode.fromJson({
      'type': type,
      'value': ?value,
      'children': [
        for (final kid in kids) {'type': kid.type.wire, 'value': kid.value},
      ],
    });

CoreNode _c(String value) =>
    CoreNode(type: CoreNodeType.constant, value: value);

void main() {
  test('every node type the backend emits has a rendering', () {
    expect(
      nodeToLatex(_n('ADD_SUBTRACT', [_c('1'), _c('3')])),
      contains(r'\pm'),
    );
    expect(nodeToLatex(_n('ADD_SUBTRACT', [_c('2')])), contains(r'\pm'));
    expect(nodeToLatex(_c('22/5')), r'\frac{22}{5}');
    expect(nodeToLatex(_c('-1/2')), r'-\frac{1}{2}');
    expect(nodeToLatex(_n('CONJUGATE', [_c('z')])), contains('overline'));
    expect(
      nodeToLatex(
        _n('CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT', [_c('5'), _c('2')]),
      ),
      contains('C'),
    );
    expect(nodeToLatex(_n('MEAN', [_c('1'), _c('2')])), isNotEmpty);
    expect(
      nodeToLatex(_n('SEQUENCE', [_c('1'), _c('2'), _c('3')])),
      contains(','),
    );
  });
}
