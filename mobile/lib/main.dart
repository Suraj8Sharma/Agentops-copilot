import 'package:flutter/material.dart';

/// D1 scope: skeleton only. Design tokens (mobile/lib/core/theme.dart) and
/// the navigation shell land the same day per the implementation manual;
/// real screens are wired in on their owner's day.
void main() {
  runApp(const AgentOpsApp());
}

class AgentOpsApp extends StatelessWidget {
  const AgentOpsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AgentOps Copilot',
      home: Scaffold(
        body: Center(child: Text('AgentOps Copilot — build in progress')),
      ),
    );
  }
}
