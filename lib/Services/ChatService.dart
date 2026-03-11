import 'dart:convert';
import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

class ChatService {
  static String _chatUrl = "";
  static String _yoloUrl = "";

  static Future<void> initializeApiUrl() async {
    try {
      final supabase = Supabase.instance.client;
      final response = await supabase.from('app_config').select('key, value').inFilter('key', ['rag_url', 'yolo_url']);

      if (response is List && response.isNotEmpty) {
        for (final item in response) {
          String val = (item['value'] ?? '').toString().replaceAll(RegExp(r'/$'), '');
          if (item['key'] == 'rag_url') _chatUrl = val;
          if (item['key'] == 'yolo_url') _yoloUrl = val;
        }
      }
      if (_chatUrl.isEmpty || _yoloUrl.isEmpty) _useFallbackUrl();
    } catch (_) { _useFallbackUrl(); }
  }

  static void _useFallbackUrl() {
    String host = (defaultTargetPlatform == TargetPlatform.android) ? "10.0.2.2" : "127.0.0.1";
    if (_chatUrl.isEmpty) _chatUrl = "http://$host:8000";
    if (_yoloUrl.isEmpty) _yoloUrl = "http://$host:8001";
  }

  // RAG Chat - Nhận trọn gói (Khớp với Server mới)
  static Future<String> getChat(String question, {List<Map<String, String>> history = const []}) async {
    if (_chatUrl.isEmpty) return "Chưa có URL Server Chat.";
    try {
      final res = await http.post(
        Uri.parse('$_chatUrl/chat'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'question': question, 'history': history}),
      ).timeout(const Duration(seconds: 120)); // Đã nới lỏng timeout

      if (res.statusCode == 200) {
        return jsonDecode(utf8.decode(res.bodyBytes))['answer'] ?? "AI không phản hồi.";
      }
      return "Lỗi Server (${res.statusCode})";
    } catch (e) { return "Lỗi kết nối: $e"; }
  }

  // ====== GIỮ NGUYÊN YOLO CHO THANH ======
  static Future<Map<String, dynamic>> uploadToYOLO(Uint8List bytes, String filename) async {
    if (_yoloUrl.isEmpty) return {"summary": "Chưa có URL YOLO"};
    try {
      final req = http.MultipartRequest('POST', Uri.parse('$_yoloUrl/detect'));
      req.files.add(http.MultipartFile.fromBytes('image', bytes, filename: filename));
      final res = await http.Response.fromStream(await req.send());
      
      if (res.statusCode == 200) {
        return jsonDecode(utf8.decode(res.bodyBytes));
      } else {
        return {"summary": "Lỗi YOLO (${res.statusCode})"};
      }
    } catch (e) { return {"summary": "Lỗi kết nối YOLO: $e"}; }
  }

  static Future<Map<String, dynamic>> uploadToYOLOLite(Uint8List bytes, String filename) async {
    if (_yoloUrl.isEmpty) return {"summary": "Chưa có URL YOLO", "boxes": [], "w": 0, "h": 0};
    try {
      final req = http.MultipartRequest('POST', Uri.parse('$_yoloUrl/detect-lite'));
      req.files.add(http.MultipartFile.fromBytes('image', bytes, filename: filename));
      final res = await http.Response.fromStream(await req.send());
      
      if (res.statusCode == 200) {
        return jsonDecode(utf8.decode(res.bodyBytes));
      } else {
        return {"summary": "Lỗi YOLO (${res.statusCode})", "boxes": [], "w": 0, "h": 0};
      }
    } catch (e) { return {"summary": "Lỗi kết nối YOLO: $e", "boxes": [], "w": 0, "h": 0}; }
  }
}