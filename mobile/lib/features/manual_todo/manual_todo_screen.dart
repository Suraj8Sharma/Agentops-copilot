import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/theme.dart';

class ManualTodoItem {
  const ManualTodoItem({
    required this.id,
    required this.title,
    required this.done,
    required this.createdAt,
  });

  final String id;
  final String title;
  final bool done;
  final DateTime createdAt;

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'done': done,
        'createdAt': createdAt.toIso8601String(),
      };

  factory ManualTodoItem.fromJson(Map<String, dynamic> json) {
    return ManualTodoItem(
      id: (json['id'] ?? '').toString(),
      title: (json['title'] ?? '').toString(),
      done: json['done'] == true,
      createdAt: DateTime.tryParse((json['createdAt'] ?? '').toString()) ??
          DateTime.now(),
    );
  }
}

class ManualTodoScreen extends StatefulWidget {
  const ManualTodoScreen({super.key});

  @override
  State<ManualTodoScreen> createState() => _ManualTodoScreenState();
}

class _ManualTodoScreenState extends State<ManualTodoScreen> {
  static const String _storageKey = 'manual_todo_items_v1';

  final TextEditingController _controller = TextEditingController();
  final List<ManualTodoItem> _items = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadItems();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _loadItems() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_storageKey);
      final items = <ManualTodoItem>[];

      if (raw != null && raw.isNotEmpty) {
        final decoded = jsonDecode(raw);
        if (decoded is List) {
          for (final item in decoded) {
            if (item is Map<String, dynamic>) {
              items.add(ManualTodoItem.fromJson(item));
            }
          }
        }
      }

      if (!mounted) return;
      setState(() {
        _items
          ..clear()
          ..addAll(items);
        _loading = false;
        _error = null;
      });
    } catch (exception) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = exception.toString();
      });
    }
  }

  Future<void> _saveItems() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _storageKey,
      jsonEncode(_items.map((item) => item.toJson()).toList()),
    );
  }

  Future<void> _addItem() async {
    final text = _controller.text.trim();
    if (text.isEmpty) {
      setState(() {
        _error = 'Please enter a to-do item.';
      });
      return;
    }

    final item = ManualTodoItem(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      title: text,
      done: false,
      createdAt: DateTime.now(),
    );

    setState(() {
      _items.insert(0, item);
      _error = null;
    });
    _controller.clear();
    await _saveItems();
  }

  Future<void> _toggleItem(ManualTodoItem item) async {
    setState(() {
      final index = _items.indexWhere((entry) => entry.id == item.id);
      if (index >= 0) {
        _items[index] = ManualTodoItem(
          id: item.id,
          title: item.title,
          done: !item.done,
          createdAt: item.createdAt,
        );
      }
    });
    await _saveItems();
  }

  Future<void> _deleteItem(String id) async {
    setState(() {
      _items.removeWhere((item) => item.id == id);
    });
    await _saveItems();
  }

  @override
  Widget build(BuildContext context) {
    final completedCount = _items.where((item) => item.done).length;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Manual To-Do Fallback'),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.screenPadding),
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Fallback checklist',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      'When the agent cannot handle the task, keep a simple manual checklist here.',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    if (_error != null)
                      Container(
                        padding: const EdgeInsets.all(AppSpacing.md),
                        decoration: BoxDecoration(
                          color: AppColors.riskHighBg,
                          borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
                        ),
                        child: Text(
                          _error!,
                          style: const TextStyle(color: AppColors.error),
                        ),
                      ),
                    const SizedBox(height: AppSpacing.md),
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _controller,
                            decoration: const InputDecoration(
                              hintText: 'Add a manual checklist item',
                              border: OutlineInputBorder(),
                            ),
                            onSubmitted: (_) => _addItem(),
                          ),
                        ),
                        const SizedBox(width: AppSpacing.sm),
                        ElevatedButton(
                          onPressed: _addItem,
                          child: const Text('Add'),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Text(
                      '$completedCount/${_items.length} complete',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Expanded(
                      child: _items.isEmpty
                          ? Center(
                              child: Text(
                                'No manual tasks yet. Add one to get started.',
                                style: Theme.of(context).textTheme.bodyMedium,
                              ),
                            )
                          : ListView.separated(
                              itemCount: _items.length,
                              separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
                              itemBuilder: (context, index) {
                                final item = _items[index];
                                return Card(
                                  child: ListTile(
                                    leading: Checkbox(
                                      value: item.done,
                                      onChanged: (_) => _toggleItem(item),
                                    ),
                                    title: Text(
                                      item.title,
                                      style: TextStyle(
                                        decoration: item.done ? TextDecoration.lineThrough : null,
                                        color: item.done ? AppColors.neutral500 : AppColors.neutral900,
                                      ),
                                    ),
                                    trailing: IconButton(
                                      icon: const Icon(Icons.delete_outline),
                                      onPressed: () => _deleteItem(item.id),
                                    ),
                                  ),
                                );
                              },
                            ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}