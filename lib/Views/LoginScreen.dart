import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fishy/ViewModels/LoginVM.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import '../ViewModels/AuthVM.dart';

class LoginScreen extends StatelessWidget {
  final TextEditingController usernameController = TextEditingController();
  final TextEditingController passwordController = TextEditingController();

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => LoginViewModel(),
      child: Consumer<LoginViewModel>(
        builder: (context, viewModel, child) {
          return Scaffold(
            appBar: AppBar(
              title: const Text("Đăng nhập"),
              leading: IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: () {
                  Navigator.pushReplacementNamed(context, "/chat");
                },
              ),
            ),

            body: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  TextField(
                    controller: usernameController,
                    decoration: const InputDecoration(labelText: "Email"),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: passwordController,
                    decoration: const InputDecoration(labelText: "Mật khẩu"),
                    obscureText: true,
                  ),
                  const SizedBox(height: 20),
                  if (viewModel.errorMessage != null)
                    Text(
                      viewModel.errorMessage!,
                      style: const TextStyle(color: Colors.red),
                    ),
                  const SizedBox(height: 10),
                  ElevatedButton(
                    onPressed:
                        viewModel.isLoading
                            ? null
                            : () async {
                              bool success = await viewModel.login(
                                usernameController.text.trim(),
                                passwordController.text.trim(),
                              );
                              if (success) {
                                Provider.of<AuthViewModel>(
                                  context,
                                  listen: false,
                                ).checkSession();
                                Future.delayed(Duration(milliseconds: 200), () {
                                  Navigator.pushReplacementNamed(
                                    context,
                                    "/chat",
                                  );
                                });
                              }
                            },
                    child:
                        viewModel.isLoading
                            ? const CircularProgressIndicator()
                            : const Text("Đăng nhập"),
                  ),

                  const SizedBox(height: 10),
                  TextButton(
                    onPressed: viewModel.isLoading ? null : () async {
                      await Supabase.instance.client.auth.signOut();
                        Provider.of<AuthViewModel>(
                        context,
                        listen: false,
                      ).checkSession();
                      Navigator.pushReplacementNamed(context, "/chat");
                    },
                    child: const Text("Tiếp tục mà không cần đăng nhập"),
                  ),
                  const SizedBox(height: 10),
                  TextButton(
                    onPressed: () {
                      Navigator.pushNamed(
                        context,
                        "/register",
                      );
                    },
                    child: const Text("Đăng ký tài khoản"),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
