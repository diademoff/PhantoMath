import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/notebook/notebook.dart';

CoreNode num_(String value) =>
    CoreNode(type: CoreNodeType.constant, value: value);

void main() {
  group('Notebook', () {
    test('добавление и очистка', () async {
      final notebook = Notebook();
      await notebook.add(
        NotebookEntry(
          problem: num_('2'),
          solution: num_('2'),
          savedAt: DateTime(2020, 1, 2, 3, 4),
        ),
      );
      expect(notebook.entries, hasLength(1));
      expect(notebook.entries.single.solution?.value, '2');

      await notebook.clear();
      expect(notebook.isEmpty, isTrue);
    });

    test('удалённая свайпом запись возвращается на своё место', () async {
      final notebook = Notebook();
      for (final value in ['1', '2', '3']) {
        await notebook.add(
          NotebookEntry(problem: num_(value), savedAt: DateTime(2020)),
        );
      }
      final middle = notebook.entries[1];
      final index = await notebook.remove(middle);
      expect(index, 1);
      expect(notebook.entries, hasLength(2));
      await notebook.insertAt(index, middle);
      expect(notebook.entries[1].problem.value, '2');
    });

    test('свежие записи сверху и лимит', () async {
      final notebook = Notebook(maxEntries: 2);
      for (final value in ['1', '2', '3']) {
        await notebook.add(
          NotebookEntry(problem: num_(value), savedAt: DateTime(2020)),
        );
      }
      expect(notebook.entries, hasLength(2));
      expect(notebook.entries.first.problem.value, '3');
    });

    test('запись переживает круг сериализации', () {
      final entry = NotebookEntry(
        problem: CoreNode(
          type: CoreNodeType.add,
          children: [num_('2'), num_('3')],
        ),
        solution: num_('5'),
        savedAt: DateTime(2020, 1, 2, 3, 4),
      );
      final restored = NotebookEntry.fromJson(entry.toJson());
      expect(restored.problem, entry.problem);
      expect(restored.solution?.value, '5');
      expect(restored.savedAt, entry.savedAt);
    });

    test('очистка возвращает записи, восстановление их возвращает', () async {
      final notebook = Notebook();
      await notebook.add(
        NotebookEntry(problem: num_('2'), savedAt: DateTime(2020)),
      );
      final removed = await notebook.clear();
      expect(notebook.isEmpty, isTrue);
      expect(removed, hasLength(1));
      await notebook.restore(removed);
      expect(notebook.entries, hasLength(1));
    });

    test('метаданные задачи переживают сериализацию', () {
      final entry = NotebookEntry(
        problem: num_('2'),
        savedAt: DateTime(2020),
        uuid: 'abc',
        version: 2,
        source: 'core',
        command: 'expand',
        locale: 'en',
        methodIndex: 1,
      );
      final restored = NotebookEntry.fromJson(entry.toJson());
      expect(restored.uuid, 'abc');
      expect(restored.version, 2);
      expect(restored.command, 'expand');
      expect(restored.locale, 'en');
      expect(restored.methodIndex, 1);
    });
  });
}
