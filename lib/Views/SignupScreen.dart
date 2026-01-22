import 'package:flutter/material.dart';
import 'package:flutter_chat_ui/flutter_chat_ui.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:fishy/Services/AuthService.dart';
import 'LoginScreen.dart';

class SignUpScreen extends StatefulWidget {
  @override
  _SignUpScreenState createState() => _SignUpScreenState();
}

class _SignUpScreenState extends State<SignUpScreen> {
  final _formKey = GlobalKey<FormState>();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _phoneController = TextEditingController();
  final AuthService _authService = AuthService();

  void _signUp() async {
    if (_formKey.currentState!.validate()) {
      bool success = await _authService.signUp(
        _emailController.text,
        _passwordController.text,
        _nameController.text,
        _phoneController.text,
      );

      Color snackBarColor = success ? Colors.green : Colors.red;
      String snackBarMessage = success ? 'Đăng ký thành công!' : 'Đăng ký thất bại!';

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(
        SnackBar(
          content: Text(
            snackBarMessage,
            style: const TextStyle(color: Colors.white),
          ),
          backgroundColor: snackBarColor,
        ),
      );

      if (success) {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (context) => LoginScreen()),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Đăng Ký')),
      body: Padding(
        padding: EdgeInsets.all(16.0),
        child: Form(
          key: _formKey,
          child: Column(
            children: [
              TextFormField(
                controller: _nameController,
                decoration: InputDecoration(labelText: 'Họ và Tên'),
                validator:
                    (value) => value!.isEmpty ? 'Vui lòng nhập họ tên' : null,
              ),
              const SizedBox(height: 10),
              TextFormField(
                controller: _emailController,
                decoration: InputDecoration(labelText: 'Email'),
                keyboardType: TextInputType.emailAddress,
                validator:
                    (value) =>
                        !value!.contains('@') ? 'Email không hợp lệ' : null,
              ),
              const SizedBox(height: 10),
              TextFormField(
                controller: _phoneController,
                decoration: InputDecoration(labelText: 'Số điện thoại'),
                keyboardType: TextInputType.phone,
              ),
              const SizedBox(height: 10),
              TextFormField(
                controller: _passwordController,
                decoration: InputDecoration(labelText: 'Mật khẩu'),
                obscureText: true,
                validator:
                    (value) =>
                        value!.length < 6 ? 'Mật khẩu ít nhất 6 ký tự' : null,
              ),
              const SizedBox(height: 10),
              SizedBox(height: 20),
              ElevatedButton(onPressed: _signUp, child: Text('Đăng Ký')),
            ]
          ),
        ),
      ),
    );
  }
}
