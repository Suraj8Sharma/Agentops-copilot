import 'package:flutter/material.dart';

void main() {
  runApp(const AgentOpsApp());
}

class AgentOpsApp extends StatelessWidget {
  const AgentOpsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'AgentOps Copilot',
      home: Scaffold(
        body: Center(child: Text('AgentOps Copilot — build in progress')),
      ),
    );
  }
}