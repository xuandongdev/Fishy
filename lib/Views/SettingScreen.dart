import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../ViewModels/ThemeVM.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Cài đặt'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Chế độ ánh sáng:',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            SwitchListTile(
              title: const Text('Chế độ tối'),
              value: Theme.of(context).brightness == Brightness.dark,
              onChanged: (bool value) {
                final themeProvider = Provider.of<ThemeNotifier>(context, listen: false);
                Future.delayed(const Duration(seconds: 1), () {
                  themeProvider.toggleTheme(value);
                });
              },
            ),
          ],
        ),
      ),
    );
  }
}
