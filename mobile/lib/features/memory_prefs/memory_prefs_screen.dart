import 'package:flutter/material.dart';

import '../../core/theme.dart';
import 'memory_prefs_service.dart';

class MemoryPrefsScreen extends StatefulWidget {
  const MemoryPrefsScreen({super.key});

  @override
  State<MemoryPrefsScreen> createState() => _MemoryPrefsScreenState();
}

class _MemoryPrefsScreenState extends State<MemoryPrefsScreen> {
  final TextEditingController _keyController = TextEditingController();
  final TextEditingController _valueController = TextEditingController();
  final Map<String, dynamic> _preferences = {};
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadPreferences();
  }

  @override
  void dispose() {
    _keyController.dispose();
    _valueController.dispose();
    super.dispose();
  }

  Future<void> _loadPreferences() async {
    try {
      final prefs = await MemoryPrefsService.fetchPreferences();
      if (!mounted) return;
      setState(() {
        _preferences.clear();
        _preferences.addAll(prefs);
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  Future<void> _savePreference() async {
    final key = _keyController.text.trim();
    final value = _valueController.text.trim();
    if (key.isEmpty || value.isEmpty) {
      setState(() => _error = 'Key and value are both required.');
      return;
    }

    try {
      await MemoryPrefsService.savePreference(
        key,
        value,
      );
      if (!mounted) return;
      setState(() {
        _preferences[key] = value;
        _error = null;
      });
      _keyController.clear();
      _valueController.clear();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Preference saved.')),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    }
  }

  Future<void> _deletePreference(String key) async {
    try {
      await MemoryPrefsService.deletePreference(key);
      if (!mounted) return;
      setState(() {
        _preferences.remove(key);
        _error = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Deleted $key')),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Memory / Preferences')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.screenPadding),
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  children: [
                    Text(
                      'Agent memory',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      'Store short user preferences that the planner can use when generating plans.',
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
                        child: Text(_error!, style: const TextStyle(color: AppColors.error)),
                      ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      controller: _keyController,
                      decoration: const InputDecoration(labelText: 'Preference key'),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      controller: _valueController,
                      decoration: const InputDecoration(labelText: 'Preference value'),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: _savePreference,
                        child: const Text('Save preference'),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.xl),
                    if (_preferences.isEmpty)
                      const Text('No stored preferences yet.')
                    else
                      ..._preferences.entries.map((entry) {
                        return Card(
                          child: ListTile(
                            title: Text(entry.key),
                            subtitle: Text(entry.value.toString()),
                            trailing: IconButton(
                              icon: const Icon(Icons.delete_outline),
                              onPressed: () => _deletePreference(entry.key),
                            ),
                          ),
                        );
                      }),
                  ],
                ),
        ),
      ),
    );
  }
}