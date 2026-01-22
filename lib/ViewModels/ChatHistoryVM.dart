import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

class ChatHistoryViewModel extends ChangeNotifier {
  final SupabaseClient _client = Supabase.instance.client;
  List<Map<String, dynamic>> _chatHistory = [];
  bool _isLoading = false;

  List<Map<String, dynamic>> get chatHistory => _chatHistory;
  bool get isLoading => _isLoading;

  Future<void> fetchChatHistory(int userid) async {
    _isLoading = true;
    notifyListeners();

    try {
      final response = await _client
          .from('lich_su_tro_chuyen')
          .select('*')
          .eq('userid', userid)
          .order('thoidiem', ascending: false);

      _chatHistory = List<Map<String, dynamic>>.from(response);
    } catch (e) {
      debugPrint("Lỗi khi tải lịch sử trò chuyện: $e");
      _chatHistory = [];
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
