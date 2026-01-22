// import 'dart:convert';
// import 'dart:io';
// import 'package:flutter/foundation.dart';
// import 'package:google_generative_ai/google_generative_ai.dart';
// import 'package:http/http.dart' as http;
// import 'dart:typed_data';
// import 'package:supabase_flutter/supabase_flutter.dart';
// import 'package:flutter_dotenv/flutter_dotenv.dart';

// class ChatService {
//   final GenerativeModel _generativeModel;
//   final _supabase = Supabase.instance.client;

//   // Cấu hình linh hoạt: Ưu tiên Gemini Flash để ổn định
//   static const bool useGeminiForClassification = true;
//   static const bool useGeminiForGeneralChat = true;
//   static const bool useGeminiForRAG = true;

//   static String get _localHost => kIsWeb ? "127.0.0.1" : (Platform.isAndroid ? "10.0.2.2" : "127.0.0.1");

//   ChatService({
//     String generativeModelName = 'gemini-2.5-flash',
//   }) : _generativeModel = GenerativeModel(
//     model: generativeModelName,
//     apiKey: dotenv.get('GEMINI_API_KEY', fallback: ""),
//   );

//   // --- 1. GỌI LEGAL RAG (Edge Function) ---
//   Future<Map<String, dynamic>> callLegalRag(String question) async {
//     try {
//       print("🚀 [Flow] Tra cứu Luật: Gọi Edge Function (useGemini: $useGeminiForRAG)");
//       final response = await _supabase.functions.invoke(
//         'legal-rag',
//         body: {'query': question, 'useGemini': useGeminiForRAG},
//       );
//       if (response.status == 200) return response.data as Map<String, dynamic>;
//       return {"answer": "Lỗi Server (${response.status})", "error": true};
//     } catch (e) {
//       print("❌ [Error] callLegalRag: $e");
//       return {"answer": "Không thể kết nối bộ não RAG.", "error": true};
//     }
//   }

//   // --- 2. PHÂN LOẠI Ý ĐỊNH ---
//   Future<bool> classifyTrafficIntent(String userMessage) async {
//     final prompt = "Phân tích tin nhắn: '$userMessage'. Nếu hỏi về luật giao thông/biển báo/xử phạt: trả lời 'CÓ'. Nếu là chào hỏi/tán gẫu: trả lời 'KHÔNG'. Trả lời duy nhất 1 từ.";

//     try {
//       final response = await _generativeModel.generateContent([Content.text(prompt)],
//           generationConfig: GenerationConfig(maxOutputTokens: 5, temperature: 0.1));

//       final result = response.text?.trim().toUpperCase() ?? "KHÔNG";
//       print("🔍 [Log] AI phân loại: $result");

//       // Chấp nhận cả "C", "CÓ", "YES" để tránh AI trả về token thiếu
//       return result.startsWith("C") || result.contains("CÓ");
//     } catch (e) {
//       print("❌ [Error] Phân loại: $e");
//       return false;
//     }
//   }

//   // --- 3. TRÒ CHUYỆN CHUNG ---
//   Future<String> getBotResponse(String prompt) async {
//     try {
//       print("📡 [Log] Đang gọi Gemini Flash cho General Chat...");
//       final response = await _generativeModel.generateContent([Content.text(prompt)]);
//       return response.text ?? "Tôi chưa có câu trả lời phù hợp.";
//     } catch (e) {
//       print("❌ [Error] Gemini Chat: $e");
//       return "Lỗi kết nối Gemini API. Hãy kiểm tra Internet.";
//     }
//   }

//   // --- 4. TẠO EMBEDDING (Hugging Face) ---
//   Future<List<double>?> generateEmbedding(String text) async {
//     try {
//       final hfToken = dotenv.get('HF_API_KEY', fallback: '');
//       final res = await http.post(
//         Uri.parse("https://router.huggingface.co/hf-inference/models/intfloat/multilingual-e5-large"),
//         headers: {'Authorization': 'Bearer $hfToken', 'Content-Type': 'application/json'},
//         body: jsonEncode({"inputs": "query: $text"}),
//       );
//       if (res.statusCode == 200) return (jsonDecode(res.body) as List).cast<double>();
//       return null;
//     } catch (e) { return null; }
//   }

//   // --- 5. YOLO ---
//   Future<Map<String, dynamic>> uploadToYOLO(Uint8List imageBytes, String filename) async {
//     try {
//       var request = http.MultipartRequest('POST', Uri.parse('http://$_localHost:8000/detect'));
//       request.files.add(http.MultipartFile.fromBytes('image', imageBytes, filename: filename));
//       var res = await http.Response.fromStream(await request.send());
//       return res.statusCode == 200 ? jsonDecode(utf8.decode(res.bodyBytes)) : {"summary": "Lỗi YOLO"};
//     } catch (e) { return {"summary": "Lỗi kết nối YOLO"}; }
//   }
// }
import 'dart:convert';
import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

class ChatService {
  // Tách biệt 2 URL
  static String _chatUrl = "";  // Dành cho port 8000
  static String _yoloUrl = "";  // Dành cho port 8001

  // Khởi tạo URL từ Supabase (Lấy cả 2 link)
  static Future<void> initializeApiUrl() async {
    try {
      print("[Config] Đang đồng bộ địa chỉ Server...");
      final supabase = Supabase.instance.client;
      
      // Lấy cả 2 key cùng lúc - SỬA: dùng .in_() thay vì .inFilter()
      final response = await supabase
          .from('app_config')
          .select('key, value')
          .inFilter('key', ['rag_url', 'yolo_url']);

      print("[Debug] Response từ Supabase: $response");

      if (response != null && (response as List).isNotEmpty) {
        for (var item in response) {
          if (item['key'] == 'rag_url') {
            _chatUrl = item['value'] ?? '';
            print("Chat URL (RAG): $_chatUrl");
          } else if (item['key'] == 'yolo_url') {
            _yoloUrl = item['value'] ?? '';
            print("Vision URL (YOLO): $_yoloUrl");
          }
        }
      } else {
        print("[Warning] Supabase trả về rỗng - dùng Fallback");
      }
      
      // Kiểm tra nếu thiếu thì dùng Fallback
      if (_chatUrl.isEmpty || _yoloUrl.isEmpty) {
        print("[Warning] Một hoặc cả 2 URL bị rỗng:");
        print("  - _chatUrl: '${_chatUrl.isEmpty ? "EMPTY" : _chatUrl}'");
        print("  - _yoloUrl: '${_yoloUrl.isEmpty ? "EMPTY" : _yoloUrl}'");
        _useFallbackUrl();
      }

    } catch (e) {
      print("[Config] Lỗi lấy cấu hình: $e");
      _useFallbackUrl();
    }
  }

  static void _useFallbackUrl() {
    if (kIsWeb) {
      if (_chatUrl.isEmpty) _chatUrl = "http://127.0.0.1:8000";
      if (_yoloUrl.isEmpty) _yoloUrl = "http://127.0.0.1:8001";
    } else if (Platform.isAndroid) {
      // Android Emulator
      if (_chatUrl.isEmpty) _chatUrl = "http://10.0.2.2:8000";
      if (_yoloUrl.isEmpty) _yoloUrl = "http://10.0.2.2:8001"; 
    } else {
      // iOS / Desktop
      if (_chatUrl.isEmpty) _chatUrl = "http://127.0.0.1:8000";
      if (_yoloUrl.isEmpty) _yoloUrl = "http://127.0.0.1:8001";
    }
    print("[Fallback] Chat: $_chatUrl | YOLO: $_yoloUrl");
  }

  // --- 1. GỬI TIN NHẮN TEXT (Dùng _chatUrl - Port 8000) ---
  Stream<String> streamChat(String question) async* {
    if (_chatUrl.isEmpty) {
      yield "Lỗi: Chưa có địa chỉ Server Chat.";
      return;
    }

    final client = http.Client();
    final request = http.Request('POST', Uri.parse('$_chatUrl/chat/stream'));

    request.headers['Content-Type'] = 'application/json';
    request.body = jsonEncode({'question': question});

    try {
      final response = await client.send(request);

      if (response.statusCode != 200) {
        yield "Lỗi máy chủ RAG: ${response.statusCode}";
        return;
      }

      await for (final line in response.stream
          .transform(utf8.decoder)
          .transform(const LineSplitter())) {

        if (line.startsWith('data: ')) {
          final content = line.substring(6);

          if (content == '[DONE]') {
            break;
          } else if (content.startsWith('[Lỗi')) {
            yield "\n($content)";
          } else {
            try {
              final decodedText = jsonDecode(content);
              yield decodedText.toString();
            } catch (e) {
              yield content;
            }
          }
        }
      }
    } catch (e) {
      yield "Không thể kết nối Server Chat: $e";
    } finally {
      client.close();
    }
  }

  // --- 2. GỬI ẢNH (Dùng _yoloUrl - Port 8001) ---
  Future<Map<String, dynamic>> uploadToYOLO(Uint8List imageBytes, String filename) async {
    print("[YOLO] Kiểm tra URL trước khi gửi:");
    print("  - _yoloUrl = '$_yoloUrl'");
    print("  - _chatUrl = '$_chatUrl'");

    if (_yoloUrl.isEmpty) {
      print("[YOLO] URL bị rỗng!");
      return {"summary": "Chưa có địa chỉ Server YOLO"};
    }

    try {
      final fullUrl = '$_yoloUrl/detect';
      print("[YOLO] Đang gửi ảnh tới: $fullUrl");
      
      var request = http.MultipartRequest('POST', Uri.parse(fullUrl));
      
      // Thêm file vào request
      request.files.add(http.MultipartFile.fromBytes('image', imageBytes, filename: filename));
      
      // Gửi request
      var res = await http.Response.fromStream(await request.send());

      print("[YOLO] Response status: ${res.statusCode}");

      if (res.statusCode == 200) {
        return jsonDecode(utf8.decode(res.bodyBytes));
      }
      return {"summary": "Lỗi Server YOLO (${res.statusCode})"};
    } catch (e) {
      print("[YOLO] Lỗi kết nối: $e");
      return {"summary": "Không thể kết nối Server YOLO: $e"};
    }
  }
}