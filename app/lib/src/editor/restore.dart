/// Restore a saved problem as editable tokens, never as rendered text.
library;

import '../model/core_node.dart';
import 'kind.dart';
import 'model.dart';

/// Convert a history problem into an editor document.
///
/// Grouping parentheses may be added to preserve the operator tree. Unsupported
/// nodes (including malformed arities) throw [UnsupportedError], so callers can
/// keep the current document and explain why this problem cannot be edited.
ENode coreToEditor(CoreNode node) {
  if (node.type == CoreNodeType.system && node.children.length > 2) {
    _plain(node);
    final tokens = <ENode>[];
    for (final child in node.children) {
      if (child.type == CoreNodeType.system ||
          child.type == CoreNodeType.empty) {
        throw UnsupportedError('Cannot restore nested or empty system lines');
      }
      if (tokens.isNotEmpty) tokens.add(const ENode(ENodeKind.newline));
      tokens.addAll(_tokens(child));
    }
    return ENode.row(tokens);
  }
  return ENode.row(_tokens(node));
}

void _plain(CoreNode node) {
  if (node.value != null) {
    throw UnsupportedError('Unexpected value on ${node.type.wire}');
  }
}

void _arity(CoreNode node, int count) {
  if (node.children.length != count) {
    throw UnsupportedError(
      '${node.type.wire} requires $count children, got ${node.children.length}',
    );
  }
}

int _precedence(CoreNodeType type) => switch (type) {
  CoreNodeType.equals ||
  CoreNodeType.notEquals ||
  CoreNodeType.lessThan ||
  CoreNodeType.lessThanEqual ||
  CoreNodeType.greaterThan ||
  CoreNodeType.greaterThanEqual => 1,
  CoreNodeType.add || CoreNodeType.subtract => 2,
  CoreNodeType.multiply || CoreNodeType.divide => 3,
  CoreNodeType.multiplyImplicit => 4,
  CoreNodeType.negative || CoreNodeType.positive => 5,
  _ => 6,
};

List<ENode> _operand(CoreNode node, int precedence, {bool right = false}) {
  final tokens = _tokens(node);
  if (tokens.isEmpty) {
    throw UnsupportedError('Cannot restore an empty operator operand');
  }
  final own = _precedence(node.type);
  if (own < precedence || (right && own == precedence)) {
    return [
      ENode(ENodeKind.bracket, children: [ENode.row(tokens)]),
    ];
  }
  return tokens;
}

List<ENode> _tokens(CoreNode node) {
  if (node.type == CoreNodeType.constant ||
      node.type == CoreNodeType.variable) {
    _arity(node, 0);
    if (node.value == null || node.value!.isEmpty) {
      throw UnsupportedError('Missing value on ${node.type.wire}');
    }
    return [
      ENode.terminal(
        node.type == CoreNodeType.constant
            ? ENodeKind.constant
            : ENodeKind.variable,
        node.value!,
      ),
    ];
  }
  if (node.type == CoreNodeType.function ||
      node.type == CoreNodeType.functionInverse) {
    _arity(node, 1);
    final inverse = node.type == CoreNodeType.functionInverse;
    final kind = switch (node.value) {
      'f' => inverse ? ENodeKind.functionInverseF : ENodeKind.functionF,
      'g' => inverse ? ENodeKind.functionInverseG : ENodeKind.functionG,
      _ => throw UnsupportedError('Cannot edit function ${node.value}'),
    };
    return [
      ENode(kind, children: [_slot(node.children.single)]),
    ];
  }
  _plain(node);
  if (node.type == CoreNodeType.empty) {
    _arity(node, 0);
    return [];
  }
  if (node.type == CoreNodeType.matrix) return [_matrix(node)];
  if (node.type == CoreNodeType.sigmaDefinite && node.children.length == 3) {
    return [
      ENode(ENodeKind.sigma, children: node.children.map(_slot).toList()),
    ];
  }

  if (node.type == CoreNodeType.positive ||
      node.type == CoreNodeType.negative) {
    _arity(node, 1);
    return [
      ENode(
        node.type == CoreNodeType.negative ? ENodeKind.subtract : ENodeKind.add,
      ),
      ..._operand(node.children.single, 5),
    ];
  }

  for (final kind in ENodeKind.values.where((kind) => kind.isInfix)) {
    if (kind.coreType != node.type) continue;
    _arity(node, 2);
    final precedence = _precedence(node.type);
    return [
      ..._operand(node.children[0], precedence),
      ENode(kind),
      ..._operand(node.children[1], precedence, right: true),
    ];
  }
  if (node.type == CoreNodeType.multiplyImplicit) {
    _arity(node, 2);
    final right = node.children[1];
    return [
      ..._operand(node.children[0], 4),
      if (right.type == CoreNodeType.negative ||
          right.type == CoreNodeType.positive)
        ENode(ENodeKind.bracket, children: [_slot(right)])
      else
        ..._operand(right, 4, right: true),
    ];
  }
  for (final kind in ENodeKind.values.where((kind) => kind.isPostfix)) {
    if (kind.coreType != node.type) continue;
    _arity(node, 1);
    // Prefix signs bind differently from postfix signs in the row parser.
    return [..._operand(node.children.single, 6), ENode(kind)];
  }

  // Only general templates: shortcut kinds bake in constants and would make
  // the exponent, root index, or logarithm base impossible to edit.
  const shortcuts = {
    ENodeKind.powerTwo,
    ENodeKind.powerThree,
    ENodeKind.rootThree,
    ENodeKind.log2,
    ENodeKind.functionF,
    ENodeKind.functionG,
    ENodeKind.functionInverseF,
    ENodeKind.functionInverseG,
    ENodeKind.matrix2,
    ENodeKind.matrix3,
  };
  for (final kind in ENodeKind.values) {
    if (!kind.isTemplate || shortcuts.contains(kind)) continue;
    if (kind.coreType != node.type) continue;
    _arity(node, kind.arity);
    return [
      ENode(kind, children: [for (final child in node.children) _slot(child)]),
    ];
  }
  throw UnsupportedError('Cannot edit ${node.type.wire}');
}

ENode _slot(CoreNode node) => ENode.row(_tokens(node));

ENode _matrix(CoreNode node) {
  if (node.children.isEmpty) {
    throw UnsupportedError('Cannot edit a matrix without rows');
  }
  final cols = node.children.first.children.length;
  if (cols == 0) throw UnsupportedError('Cannot edit a matrix without columns');
  final cells = <ENode>[];
  for (final row in node.children) {
    if (row.type != CoreNodeType.matrixRow || row.children.length != cols) {
      throw UnsupportedError('Cannot edit a non-rectangular matrix');
    }
    _plain(row);
    cells.addAll(row.children.map(_slot));
  }
  return ENode(
    ENodeKind.matrix2,
    value: '${node.children.length},$cols',
    children: cells,
  );
}
