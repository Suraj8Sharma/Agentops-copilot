import 'package:flutter/material.dart';
import '../../core/widgets/screen_stub.dart';

class ManualTodoScreen extends StatelessWidget {
  const ManualTodoScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const ScreenStub(
      title: 'Manual To-Do Fallback',
      owner: 'Shivangi',
    );
  }
}