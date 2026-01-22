// import 'package:flutter/material.dart';
// import 'package:fishy/Models/ChatMessages.dart';
// import 'package:fishy/Services/ChatService.dart';
// import 'package:supabase_flutter/supabase_flutter.dart';
// import 'package:fishy/Services/AuthService.dart';
// import 'dart:convert';
// import 'package:image_picker/image_picker.dart';
// import 'dart:typed_data';

// class ChatViewModel extends ChangeNotifier {
//   final List<ChatMessage> messages = [];
//   final ChatService chatService = ChatService();
//   bool _isTyping = false;
//   final SupabaseClient _supabase = Supabase.instance.client;

//   bool get isTyping => _isTyping;

//   void setTyping(bool value) {
//     _isTyping = value;
//     notifyListeners();
//   }

//   void clearMessages() {
//     messages.clear();
//     notifyListeners();
//   }

//   // --- 1. LOGIC GỬI TIN NHẮN CHÍNH (TEXT) ---
//   Future<void> sendMessage(String? userMessage) async {
//     if (userMessage == null || userMessage.trim().isEmpty) return;

//     // Hiển thị tin nhắn người dùng ngay lập tức
//     messages.add(ChatMessage(text: userMessage, isUser: true));
//     setTyping(true);
//     notifyListeners();

//     try {
//       // BƯỚC 1: Phân loại ý định (Topic: Luật hay Trò chuyện?)
//       final isTrafficLaw = await chatService.classifyTrafficIntent(userMessage);
//       String botResponse = "";

//       if (isTrafficLaw) {
//         print("Topic: Luật giao thông -> Gọi Edge Function (RAG)");

//         // BƯỚC 2: Gọi RAG (Model Gemini/Gemma được cấu hình trong ChatService)
//         final ragResult = await chatService.callLegalRag(userMessage);

//         if (ragResult['error'] == true) {
//           botResponse = "Xin lỗi, hiện tại bộ não RAG đang gặp sự cố: ${ragResult['answer']}";
//         } else {
//           // BƯỚC 3: Xử lý câu trả lời AI và Nguồn trích dẫn (Hierarchy)
//           final String aiAnswer = ragResult['answer'] ?? "AI không tìm thấy tài liệu phù hợp.";
//           final List<dynamic> sources = ragResult['sources'] ?? [];

//           if (sources.isNotEmpty) {
//             // Server đã làm sẵn full_path cho chúng ta (Ví dụ: Chương I > Điều 5)
//             String citationText = "\n\n**Nguồn trích dẫn:**";

//             // Dùng Set để tránh hiển thị trùng lặp nếu nhiều đoạn luật thuộc cùng 1 Điều
//             final Set<String> uniqueSources = {};
//             for (var src in sources) {
//               final path = src['full_path'] ?? "Quy định";
//               final sohieu = src['sohieu'] ?? "N/A";
//               uniqueSources.add("🔹 $path (Văn bản $sohieu)");
//             }

//             botResponse = "$aiAnswer$citationText\n${uniqueSources.join('\n')}";
//           } else {
//             botResponse = aiAnswer;
//           }
//         }
//       } else {
//         // BƯỚC 4: Trò chuyện chung (Gemini)
//         print("Topic: Trò chuyện chung -> Gọi Gemini");
//         botResponse = await chatService.getBotResponse(userMessage);
//       }

//       // Thêm phản hồi của Bot vào danh sách tin nhắn
//       messages.add(ChatMessage(text: botResponse, isUser: false));

//       // Lưu lịch sử vào Supabase
//       await _saveChatHistory(userMessage, botResponse);

//     } catch (e) {
//       print("Lỗi sendMessage: $e");
//       messages.add(ChatMessage(text: "Đã xảy ra lỗi kết nối đến máy chủ AI.", isUser: false));
//     } finally {
//       setTyping(false);
//       notifyListeners();
//     }
//   }

//   // --- 2. LOGIC GỬI ẢNH (YOLO) ---
//   Future<void> sendImageFile(XFile pickedFile) async {
//     setTyping(true);
//     notifyListeners();

//     try {
//       final Uint8List bytes = await pickedFile.readAsBytes();

//       // Hiển thị ảnh người dùng đã chọn
//       messages.add(ChatMessage(
//         isUser: true,
//         type: MessageType.image,
//         imageBytes: bytes,
//         text: '',
//       ));
//       notifyListeners();

//       // Gửi sang server YOLO
//       final Map<String, dynamic> responseMap = await chatService.uploadToYOLO(bytes, pickedFile.name);
//       final YoloResponse yoloResponse = YoloResponse.fromJson(responseMap);

//       // Hiển thị tóm tắt kết quả
//       messages.add(ChatMessage(
//         text: yoloResponse.summaryText,
//         isUser: false,
//         type: MessageType.text,
//       ));

//       // Nếu có ảnh đã vẽ khung (Base64) thì hiển thị tiếp
//       if (yoloResponse.imageBase64 != null && yoloResponse.imageBase64!.isNotEmpty) {
//         String cleanBase64 = yoloResponse.imageBase64!.replaceAll(RegExp(r'\s+'), '');
//         messages.add(ChatMessage(
//           isUser: false,
//           type: MessageType.image,
//           imageBase64: cleanBase64,
//           text: '',
//         ));
//       }

//       await _saveChatHistory("(Người dùng gửi ảnh)", yoloResponse.summaryText);

//     } catch (e) {
//       print("Lỗi YOLO: $e");
//       messages.add(ChatMessage(text: "Lỗi xử lý ảnh: $e", isUser: false));
//     } finally {
//       setTyping(false);
//       notifyListeners();
//     }
//   }

//   // --- 3. LƯU LỊCH SỬ ---
//   Future<void> _saveChatHistory(String userMessage, String botResponse) async {
//     final user = _supabase.auth.currentUser;
//     if (user != null) {
//       try {
//         final currentUser = await AuthService().getCurrentUser();
//         final userId = currentUser?['userid'];
//         if (userId != null) {
//           await _supabase.from('lich_su_tro_chuyen').insert({
//             'userid': userId,
//             'cauhoi': userMessage,
//             'traloi': botResponse,
//           });
//         }
//       } catch (e) {
//         print('Lỗi lưu lịch sử: $e');
//       }
//     }
//   }
// }
import 'package:flutter/material.dart';
import 'package:fishy/Models/ChatMessages.dart';
import 'package:fishy/Services/ChatService.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:image_picker/image_picker.dart';
import 'dart:typed_data';

class ChatViewModel extends ChangeNotifier {
  // Danh sách tin nhắn
  final List<ChatMessage> messages = [];

  // Service giao tiếp với Server Python
  final ChatService chatService = ChatService();

  bool _isTyping = false;
  final SupabaseClient _supabase = Supabase.instance.client;

  bool get isTyping => _isTyping;

  void setTyping(bool value) {
    _isTyping = value;
    notifyListeners();
  }

  // --- [ĐÃ THÊM LẠI] HÀM XÓA TIN NHẮN ---
  // Hàm này được AuthViewModel gọi khi Login/Logout
  void clearMessages() {
    messages.clear();
    notifyListeners();
  }

  // --- 1. GỬI TIN NHẮN TEXT (STREAMING) ---
  Future<void> sendMessage(String? userMessage) async {
    if (userMessage == null || userMessage.trim().isEmpty) return;

    // 1. Hiển thị tin nhắn User
    messages.add(ChatMessage(text: userMessage, isUser: true));

    // 2. Tạo tin nhắn Bot rỗng để hứng dữ liệu
    final botMessage = ChatMessage(text: "", isUser: false);
    messages.add(botMessage);

    setTyping(true);
    notifyListeners();

    String fullResponse = "";

    try {
      // 3. Lắng nghe Stream từ Server Python
      await for (final chunk in chatService.streamChat(userMessage)) {
        botMessage.text += chunk;
        fullResponse += chunk;
        notifyListeners(); // Cập nhật UI liên tục tạo hiệu ứng gõ chữ
      }

      // 4. Lưu lịch sử
      _saveChatHistory(userMessage, fullResponse);

    } catch (e) {
      botMessage.text = "Lỗi kết nối: $e";
      notifyListeners();
    } finally {
      setTyping(false);
    }
  }

  // --- 2. GỬI ẢNH (YOLO) ---
  Future<void> sendImageFile(XFile pickedFile) async {
    setTyping(true);
    notifyListeners();

    try {
      final Uint8List bytes = await pickedFile.readAsBytes();

      // Hiển thị ảnh User
      messages.add(ChatMessage(
          text: '', isUser: true, type: MessageType.image, imageBytes: bytes
      ));
      notifyListeners();

      // Gửi sang Server
      final responseMap = await chatService.uploadToYOLO(bytes, pickedFile.name);
      final yoloResponse = YoloResponse.fromJson(responseMap);

      // Hiển thị kết quả Text
      messages.add(ChatMessage(text: yoloResponse.summaryText, isUser: false));

      // Hiển thị ảnh BBox (nếu có)
      if (yoloResponse.imageBase64 != null) {
        messages.add(ChatMessage(
            text: '', isUser: false, type: MessageType.image, imageBase64: yoloResponse.imageBase64
        ));
      }

      _saveChatHistory("(Gửi ảnh)", yoloResponse.summaryText);

    } catch (e) {
      messages.add(ChatMessage(text: "Lỗi xử lý ảnh: $e", isUser: false));
    } finally {
      setTyping(false);
    }
  }

  // --- 3. LƯU LỊCH SỬ ---
  Future<void> _saveChatHistory(String question, String answer) async {
    final user = _supabase.auth.currentUser;
    if (user != null) {
      try {
        await _supabase.from('lich_su_tro_chuyen').insert({
          'userid': user.id, // Lưu ý kiểm tra xem DB của bạn dùng ID là int hay uuid
          'cauhoi': question,
          'traloi': answer,
        });
      } catch (e) {
        print('Lỗi lưu lịch sử: $e');
      }
    }
  }
}