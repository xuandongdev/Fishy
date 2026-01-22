import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'AddLaw.dart';
import 'AddContent.dart';
import '../ViewModels/addlawVM.dart';
import '../ViewModels/AddLawContentVM.dart';

class AdminWebLayout extends StatefulWidget {
  @override
  _AdminWebLayoutState createState() => _AdminWebLayoutState();
}

class _AdminWebLayoutState extends State<AdminWebLayout> {
  int _selectedIndex = 0;

  final List<Widget> _pages = [
    WebAddLaw(),      // Index 0
    WebAddContent(),  // Index 1
  ];

  @override
  Widget build(BuildContext context) {
    // MultiProvider để cung cấp VM cho toàn bộ Dashboard
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AddLawVM()),
        ChangeNotifierProvider(create: (_) => AddContentVM()),
      ],
      child: Scaffold(
        backgroundColor: Colors.grey[100], // Màu nền nhẹ cho dashboard
        body: Row(
          children: [
            // --- SIDEBAR (Menu bên trái) ---
            NavigationRail(
              selectedIndex: _selectedIndex,
              onDestinationSelected: (int index) {
                setState(() {
                  _selectedIndex = index;
                });
              },
              extended: true, // Hiển thị cả text label
              backgroundColor: Colors.white,
              elevation: 5,
              leading: Padding(
                padding: const EdgeInsets.symmetric(vertical: 20),
                child: Column(
                  children: [
                    Icon(Icons.gavel, size: 40, color: Colors.blue),
                    SizedBox(height: 10),
                    Text("Luật Dashboard", style: TextStyle(fontWeight: FontWeight.bold)),
                  ],
                ),
              ),
              destinations: const [
                NavigationRailDestination(
                  icon: Icon(Icons.library_books_outlined),
                  selectedIcon: Icon(Icons.library_books),
                  label: Text('Thêm Văn Bản Gốc'),
                ),
                NavigationRailDestination(
                  icon: Icon(Icons.format_list_numbered_outlined),
                  selectedIcon: Icon(Icons.format_list_numbered),
                  label: Text('Soạn Thảo Nội Dung'),
                ),
              ],
            ),

            // --- MAIN CONTENT (Nội dung bên phải) ---
            Expanded(
              child: Container(
                margin: EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(10),
                  boxShadow: [
                    BoxShadow(color: Colors.black12, blurRadius: 10, offset: Offset(0, 5))
                  ],
                ),
                child: _pages[_selectedIndex],
              ),
            ),
          ],
        ),
      ),
    );
  }
}