import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/main.dart';

void main() {
  testWidgets('App boots and shows placeholder text', (WidgetTester tester) async {
    await tester.pumpWidget(const AgentOpsApp());
    expect(find.text('AgentOps Copilot — build in progress'), findsOneWidget);
  });
}
