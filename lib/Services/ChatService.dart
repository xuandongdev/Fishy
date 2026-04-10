import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import '../Configs/ServerConfig.dart';

class ChatService {
  static String _chatUrl = "";
  static String _yoloUrl = "";

  static Future<void> initializeApiUrl() async {
    try {
      final supabase = Supabase.instance.client;
      final response = await supabase
          .from('app_config')
          .select('key, value')
          .inFilter('key', ['rag_url', 'yolo_url']);

      if (response is List && response.isNotEmpty) {
        for (final item in response) {
          final value = (item['value'] ?? '').toString().replaceAll(RegExp(r'/$'), '');
          if (item['key'] == 'rag_url') {
            _chatUrl = value;
          }
          if (item['key'] == 'yolo_url') {
            _yoloUrl = value;
          }
        }
      }
      if (_chatUrl.isEmpty || _yoloUrl.isEmpty) {
        _useFallbackUrl();
      }
    } catch (_) {
      _useFallbackUrl();
    }
  }

  static void _useFallbackUrl() {
    if (_chatUrl.isEmpty) {
      _chatUrl = ServerConfig.ragBaseUrl;
    }
    if (_yoloUrl.isEmpty) {
      _yoloUrl = ServerConfig.yoloBaseUrl;
    }
  }

  static Future<String> getChat(
    String question, {
    List<Map<String, String>> history = const [],
  }) async {
    if (_chatUrl.isEmpty) {
      _useFallbackUrl();
    }

    try {
      final response = await _postChat(
        baseUrl: _chatUrl,
        question: question,
        history: history,
      );
      return _parseChatResponse(response);
    } catch (error) {
      final fallbackUrl = ServerConfig.ragBaseUrl;
      if (_chatUrl == fallbackUrl) {
        return 'Loi ket noi: $error';
      }

      try {
        _chatUrl = fallbackUrl;
        final response = await _postChat(
          baseUrl: _chatUrl,
          question: question,
          history: history,
        );
        return _parseChatResponse(response);
      } catch (fallbackError) {
        return 'Loi ket noi: $fallbackError';
      }
    }
  }

  static String _parseChatResponse(http.Response response) {
    if (response.statusCode == 200) {
      final payload = jsonDecode(utf8.decode(response.bodyBytes));
      return payload['answer'] ?? 'AI khong phan hoi.';
    }
    return 'Loi Server (${response.statusCode})';
  }

  static Future<http.Response> _postChat({
    required String baseUrl,
    required String question,
    required List<Map<String, String>> history,
  }) {
    return http
        .post(
          Uri.parse('$baseUrl/chat'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'question': question, 'history': history}),
        )
        .timeout(const Duration(seconds: 120));
  }

  static Future<Map<String, dynamic>> uploadToYOLO(Uint8List bytes, String filename) async {
    if (_yoloUrl.isEmpty) {
      _useFallbackUrl();
    }
    try {
      final request = http.MultipartRequest('POST', Uri.parse('$_yoloUrl/detect'));
      request.files.add(http.MultipartFile.fromBytes('image', bytes, filename: filename));
      final response = await http.Response.fromStream(await request.send());

      if (response.statusCode == 200) {
        return jsonDecode(utf8.decode(response.bodyBytes));
      }
      return {"summary": "Loi YOLO (${response.statusCode})"};
    } catch (error) {
      return {"summary": "Loi ket noi YOLO: $error"};
    }
  }

  static Future<Map<String, dynamic>> uploadToYOLOLite(Uint8List bytes, String filename) async {
    if (_yoloUrl.isEmpty) {
      _useFallbackUrl();
    }
    try {
      final request = http.MultipartRequest('POST', Uri.parse('$_yoloUrl/detect-lite'));
      request.files.add(http.MultipartFile.fromBytes('image', bytes, filename: filename));
      final response = await http.Response.fromStream(await request.send());

      if (response.statusCode == 200) {
        return jsonDecode(utf8.decode(response.bodyBytes));
      }
      return {"summary": "Loi YOLO (${response.statusCode})", "boxes": [], "w": 0, "h": 0};
    } catch (error) {
      return {"summary": "Loi ket noi YOLO: $error", "boxes": [], "w": 0, "h": 0};
    }
  }
}
