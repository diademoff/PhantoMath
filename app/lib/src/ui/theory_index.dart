/// Reference screen: every offline theory article, searchable.
library;

import 'package:flutter/material.dart';

import '../api/solver_api.dart';
import '../i18n.dart';
import 'vertical_result.dart';

class TheoryIndexPage extends StatefulWidget {
  const TheoryIndexPage({super.key, required this.api, this.locale = 'ru'});

  final SolverApi api;
  final String locale;

  @override
  State<TheoryIndexPage> createState() => _TheoryIndexPageState();
}

class _TheoryIndexPageState extends State<TheoryIndexPage> {
  late final Future<List<TheoryArticle>> _articles = widget.api.theory(
    locale: widget.locale,
  );
  String _query = '';

  bool _matches(TheoryArticle article) {
    final needle = _query.trim().toLowerCase();
    if (needle.isEmpty) return true;
    return [
      article.title,
      article.summary,
      article.example,
    ].any((text) => text.toLowerCase().contains(needle));
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text(tr('Теория', 'Theory'))),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
            child: TextField(
              key: const ValueKey('theory-search'),
              onChanged: (value) => setState(() => _query = value),
              decoration: InputDecoration(
                prefixIcon: const Icon(Icons.search),
                hintText: tr(
                  'Найти тему: дискриминант, дроби, производная…',
                  'Find a topic: discriminant, fractions, derivative…',
                ),
              ),
            ),
          ),
          Expanded(
            child: FutureBuilder<List<TheoryArticle>>(
              future: _articles,
              builder: (context, snapshot) {
                if (snapshot.hasError) {
                  return Center(
                    child: Text(
                      tr(
                        'Не удалось загрузить теорию',
                        'Could not load theory',
                      ),
                      style: TextStyle(color: colors.error),
                    ),
                  );
                }
                final articles = snapshot.data;
                if (articles == null) {
                  return const Center(child: CircularProgressIndicator());
                }
                final shown = articles.where(_matches).toList();
                if (shown.isEmpty) {
                  return Center(
                    child: Text(tr('Ничего не найдено', 'Nothing found')),
                  );
                }
                return ListView.separated(
                  itemCount: shown.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final article = shown[index];
                    return ListTile(
                      title: Text(article.title),
                      subtitle: Text(
                        article.summary,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => TheoryPage(article: article),
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
