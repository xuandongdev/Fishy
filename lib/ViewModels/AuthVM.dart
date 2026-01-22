import 'package:flutter/foundation.dart';
import 'package:fishy/Services/AuthService.dart';
import 'package:fishy/ViewModels/ChatVM.dart';

class AuthViewModel extends ChangeNotifier {
  final AuthService _authService = AuthService();
  final ChatViewModel _chatViewModel = ChatViewModel();
  bool _isLoggedIn = false;
  Map<String, dynamic>? _userData;
  AuthViewModel() {
    checkSession();
  }
  bool get isLoggedIn => _isLoggedIn;
  Map<String, dynamic>? get userData => _userData;

  Future<bool> login(String username, String password) async {
    bool success = await _authService.signIn(username, password);
    if (success) {
      _userData = await _authService.getCurrentUser();
      _isLoggedIn = _userData != null;
      _chatViewModel.clearMessages();
      notifyListeners();
    }
    return success;
  }

  Future<void> logout() async {
    await _authService.signOut();
    _isLoggedIn = false;
    _userData = null;
    _chatViewModel.clearMessages();
    notifyListeners();
  }

  Future<void> checkSession() async {
    _userData = await _authService.getCurrentUser();
    _isLoggedIn = _userData != null;
    notifyListeners();
  }
}

