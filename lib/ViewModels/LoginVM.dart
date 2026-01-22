import 'package:flutter/material.dart';
import 'package:fishy/Services/AuthService.dart';

class LoginViewModel extends ChangeNotifier {
  final AuthService _authService = AuthService();
  bool isLoading = false;
  String? errorMessage;

  Future<bool> login(String username, String password) async {
    isLoading = true;
      errorMessage = null;
    notifyListeners();

    try {
      bool? success = await _authService.signIn(username, password);
      if (success == false) {
        if (_authService.errorMessage == "Tài khoản bị khóa, không thể đăng nhập!") {
          errorMessage = _authService.errorMessage;
        } else {
          errorMessage = "Tên đăng nhập hoặc mật khẩu không đúng!";
        }
        return false;
      }
      return success ?? false;
    } catch (e) {
      errorMessage = "Lỗi hệ thống! Vui lòng thử lại.";
      return false;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }
}