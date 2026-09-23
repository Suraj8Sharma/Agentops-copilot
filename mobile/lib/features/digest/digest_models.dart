// Data models for the Digest feature.
//
// Mirrors the backend DigestOut / DigestListOut Pydantic schemas.

class DigestItem {
  const DigestItem({
    required this.id,
    required this.userId,
    required this.periodType,
    required this.summaryText,
    required this.generatedAt,
    this.tasksIncluded = const [],
  });

  final String id;
  final String userId;
  final String periodType; // "daily" | "weekly"
  final String summaryText;
  final DateTime generatedAt;
  final List<String> tasksIncluded;

  factory DigestItem.fromJson(Map<String, dynamic> json) {
    // tasks_included is a jsonb list of task_id strings (may be null)
    final raw = json['tasks_included'];
    final tasks = raw is List
        ? raw.map((e) => e.toString()).toList()
        : <String>[];

    return DigestItem(
      id: json['id'] as String,
      userId: json['user_id'] as String,
      periodType: json['period_type'] as String,
      summaryText: json['summary_text'] as String,
      generatedAt: DateTime.parse(json['generated_at'] as String),
      tasksIncluded: tasks,
    );
  }

  bool get isWeekly => periodType == 'weekly';
}

class DigestList {
  const DigestList({
    required this.digests,
    required this.total,
    required this.limit,
    required this.offset,
  });

  final List<DigestItem> digests;
  final int total;
  final int limit;
  final int offset;

  bool get hasMore => offset + limit < total;

  factory DigestList.fromJson(Map<String, dynamic> json) {
    final items = (json['digests'] as List<dynamic>)
        .map((e) => DigestItem.fromJson(e as Map<String, dynamic>))
        .toList();
    return DigestList(
      digests: items,
      total: json['total'] as int,
      limit: json['limit'] as int,
      offset: json['offset'] as int,
    );
  }
}
