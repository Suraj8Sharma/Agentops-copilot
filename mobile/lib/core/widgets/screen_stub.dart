// AgentOps Copilot — shared placeholder for unbuilt screens.
// Used by every feature screen until its owner replaces the body
// on their assigned build day (see Manual §14, Day-by-Day Plan).

import 'package:flutter/material.dart';

class ScreenStub extends StatelessWidget {
  const ScreenStub({
    super.key,
    required this.title,
    this.owner,
  });

  final String title;
  final String? owner;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.construction_outlined, size: 40),
              const SizedBox(height: 12),
              Text(
                '$title — stub',
                style: Theme.of(context).textTheme.titleMedium,
                textAlign: TextAlign.center,
              ),
              if (owner != null) ...[
                const SizedBox(height: 4),
                Text(
                  'Owner: $owner',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}