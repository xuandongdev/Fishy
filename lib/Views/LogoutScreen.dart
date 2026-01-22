import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fishy/ViewModels/AuthVM.dart';

class LogoutScreen extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Đăng xuất'),
        backgroundColor: Colors.redAccent,
      ),
      body: Center(
        child: ElevatedButton(
          onPressed: () {
            Provider.of<AuthViewModel>(context, listen: false).logout();
            Navigator.pushNamedAndRemoveUntil(context, '/login', (route) => false);
          },
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.red,
            padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 15),
          ),
          child: const Text('Xác nhận đăng xuất', style: TextStyle(color: Colors.white)),
        ),
      ),
    );
  }
}