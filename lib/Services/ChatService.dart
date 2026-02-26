import 'dart:convert';
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

class ChatService {
  static String _chatUrl = ""; // port 8000
  static String _yoloUrl = ""; // port 8001

  static Future<void> initializeApiUrl() async {
    try {
      final supabase = Supabase.instance.client;

      final response = await supabase
          .from('app_config')
          .select('key, value')
          .inFilter('key', ['rag_url', 'yolo_url']);

      if (response is List && response.isNotEmpty) {
        for (final item in response) {
          if (item['key'] == 'rag_url') _chatUrl = (item['value'] ?? '').toString();
          if (item['key'] == 'yolo_url') _yoloUrl = (item['value'] ?? '').toString();
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
    if (kIsWeb) {
      if (_chatUrl.isEmpty) _chatUrl = "http://127.0.0.1:8000";
      if (_yoloUrl.isEmpty) _yoloUrl = "http://127.0.0.1:8001";
    } else if (defaultTargetPlatform == TargetPlatform.android) {
      if (_chatUrl.isEmpty) _chatUrl = "http://10.0.2.2:8000";
      if (_yoloUrl.isEmpty) _yoloUrl = "http://10.0.2.2:8001";
    } else {
      if (_chatUrl.isEmpty) _chatUrl = "http://127.0.0.1:8000";
      if (_yoloUrl.isEmpty) _yoloUrl = "http://127.0.0.1:8001";
    }
  }

  // ====== RAG STREAM (SSE) ======
  static Stream<String> streamChat(String question) async* {
    if (_chatUrl.isEmpty) {
      yield "Lỗi: Chưa có địa chỉ Server Chat.";
      return;
    }

    final client = http.Client();
    final request = http.Request('POST', Uri.parse('$_chatUrl/chat/stream'))
      ..headers['Content-Type'] = 'application/json'
      ..body = jsonEncode({'question': question});

    try {
      final response = await client.send(request);

      if (response.statusCode != 200) {
        yield "Lỗi máy chủ RAG: ${response.statusCode}";
        return;
      }

      await for (final line in response.stream
          .transform(utf8.decoder)
          .transform(const LineSplitter())) {
        if (!line.startsWith('data: ')) continue;

        final content = line.substring(6);

        if (content == '[DONE]') break;

        if (content.startsWith('[Lỗi')) {
          yield "\n($content)";
        } else {
          try {
            yield jsonDecode(content).toString();
          } catch (_) {
            yield content;
          }
        }
      }
    } catch (e) {
      yield "Không thể kết nối Server Chat: $e";
    } finally {
      client.close();
    }
  }

  // ====== YOLO UPLOAD ======
  static Future<Map<String, dynamic>> uploadToYOLO(Uint8List imageBytes, String filename) async {
    if (_yoloUrl.isEmpty) {
      return {"summary": "Chưa có địa chỉ Server YOLO"};
    }

    try {
      final fullUrl = '$_yoloUrl/detect';
      final request = http.MultipartRequest('POST', Uri.parse(fullUrl));
      request.files.add(http.MultipartFile.fromBytes('image', imageBytes, filename: filename));

      final res = await http.Response.fromStream(await request.send());

      if (res.statusCode == 200) {
        return jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
      }
      return {"summary": "Lỗi Server YOLO (${res.statusCode})"};
    } catch (e) {
      return {"summary": "Không thể kết nối Server YOLO: $e"};
    }
  }

  static Future<Map<String, dynamic>> uploadToYOLOLite(Uint8List imageBytes, String filename) async {
    if (_yoloUrl.isEmpty) return {"summary": "Chưa có địa chỉ Server YOLO", "boxes": [], "w": 0, "h": 0};

    try {
      final fullUrl = '$_yoloUrl/detect-lite';
      final req = http.MultipartRequest('POST', Uri.parse(fullUrl));
      req.files.add(http.MultipartFile.fromBytes('image', imageBytes, filename: filename));
      final res = await http.Response.fromStream(await req.send());

      if (res.statusCode == 200) {
        return jsonDecode(utf8.decode(res.bodyBytes));
      }
      return {"summary": "Lỗi Server YOLO (${res.statusCode})", "boxes": [], "w": 0, "h": 0};
    } catch (e) {
      return {"summary": "Không thể kết nối Server YOLO: $e", "boxes": [], "w": 0, "h": 0};
    }
  }

}

