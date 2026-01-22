import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fishy/ViewModels/AuthVM.dart';
import 'package:fishy/Themes/ThemeData.dart';

class CustomAppBar extends StatelessWidget implements PreferredSizeWidget {
  final String title;
  final Widget body;

  const CustomAppBar({super.key, required this.title, required this.body});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final textColor = theme.appBarTheme.foregroundColor ?? Colors.white;
    final bgColor = theme.appBarTheme.backgroundColor ?? AppTheme.navyBlue;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: bgColor,
        leading: Builder(
          builder: (context) => IconButton(
            icon: Icon(Icons.menu, color: textColor),
            onPressed: () => Scaffold.of(context).openDrawer(),
          ),
        ),
        title: Row(
          mainAxisAlignment: MainAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Image.asset('assets/logo.png', height: 30),
            const SizedBox(width: 10),
            Text(
              title,
              style: theme.appBarTheme.titleTextStyle,
            ),
          ],
        ),
        centerTitle: false,
      ),

      drawer: Drawer(
        child: Consumer<AuthViewModel>(
          builder: (context, authVM, _) {
            return ListView(
              padding: EdgeInsets.zero,
              children: [
                DrawerHeader(
                  decoration: BoxDecoration(color: bgColor),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Row(
                        children: [
                          Image.asset('assets/logo.png', height: 35),
                          const SizedBox(width: 10),
                          Text(
                            'Menu',
                            style: TextStyle(
                              color: textColor,
                              fontSize: 24,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      authVM.isLoggedIn && authVM.userData != null
                          ? Text(
                        'Xin chào, ${authVM.userData?['hoten']}!',
                        style: TextStyle(color: textColor, fontSize: 17),
                      )
                          : Text(
                        'Bạn chưa đăng nhập vào Fishy!',
                        style: TextStyle(color: textColor, fontSize: 17),
                      ),
                    ],
                  ),
                ),

                if (authVM.isLoggedIn && authVM.userData?['mavaitro'] == 1)
                  ListTile(
                    leading: const Icon(Icons.add_circle),
                    title: const Text('Thêm văn bản mới'),
                    onTap: () {
                      Navigator.pop(context);
                      Future.delayed(const Duration(milliseconds: 200), () {
                        Navigator.pushNamed(context, '/addLaw');
                      });
                    },
                  ),
                if (authVM.isLoggedIn && authVM.userData?['mavaitro'] == 1)
                  ListTile(
                    leading: const Icon(Icons.add_circle),
                    title: const Text('Thêm dữ liệu cho văn bản'),
                    onTap: () {
                      Navigator.pop(context);
                      Future.delayed(const Duration(milliseconds: 200), () {
                        Navigator.pushNamed(context, '/addData');
                      });
                    },
                  ),
                /*
                if (authVM.isLoggedIn && authVM.userData?['mavaitro'] == 1)
                  ListTile(
                    leading: const Icon(Icons.add),
                    title: const Text('Thêm từ đồng nghĩa'),
                    onTap: () {
                      Navigator.pop(context);
                      Future.delayed(const Duration(milliseconds: 200), () {
                        Navigator.pushNamed(context, '/dongNghia');
                      });
                    },
                  ),
                */
                if (authVM.isLoggedIn)
                  ListTile(
                    leading: const Icon(Icons.history),
                    title: const Text('Lịch sử trò chuyện'),
                    onTap: () {
                      Navigator.pop(context);
                      Future.delayed(const Duration(milliseconds: 200), () {
                        Navigator.pushNamed(context, '/chatHistory');
                      });
                    },
                  ),

                if (authVM.isLoggedIn && authVM.userData?['mavaitro'] == 1)
                  ListTile(
                    leading: const Icon(Icons.border_color_outlined),
                    title: const Text('Quản lý văn bản'),
                    onTap: () {
                      Navigator.pop(context);
                      Future.delayed(const Duration(milliseconds: 200), () {
                        Navigator.pushNamed(context, '/lawMana');
                      });
                    },
                  ),

                ListTile(
                  leading: const Icon(Icons.settings_applications),
                  title: const Text('Cài đặt'),
                  onTap: () {
                    Navigator.pop(context);
                    Future.delayed(const Duration(milliseconds: 200), () {
                      Navigator.pushNamed(context, '/setting');
                    });
                  },
                ),
                ListTile(
                  leading: Icon(authVM.isLoggedIn ? Icons.logout : Icons.login),
                  title: Text(authVM.isLoggedIn ? 'Đăng xuất' : 'Đăng nhập'),
                  onTap: () async {
                    Navigator.pop(context);
                    if (authVM.isLoggedIn) {
                      await authVM.logout();
                    }
                    Future.delayed(const Duration(milliseconds: 200), () {
                      Navigator.pushNamed(
                        context,
                        authVM.isLoggedIn ? '/logout' : '/login',
                      );
                    });
                  },
                ),
              ],
            );
          },
        ),
      ),

      body: body,
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);
}
