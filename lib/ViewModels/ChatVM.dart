import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:fishy/Models/ChatMessages.dart';
import 'package:fishy/Services/ChatService.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:image_picker/image_picker.dart';

class ChatViewModel extends ChangeNotifier {
  final List<ChatMessage> messages = [];

  bool _isTyping = false;
  final SupabaseClient _supabase = Supabase.instance.client;

  bool get isTyping => _isTyping;

  void setTyping(bool value) {
    _isTyping = value;
    notifyListeners();
  }

  void clearMessages() {
    messages.clear();
    notifyListeners();
  }

  // =========================================================
  // 1) GỬI TIN NHẮN TEXT (STREAMING RAG)
  // =========================================================
  Future<void> sendMessage(String? userMessage) async {
    if (userMessage == null || userMessage.trim().isEmpty) return;

    final userText = userMessage.trim();

    // 1) Tin nhắn user
    messages.add(ChatMessage(text: userText, isUser: true));

    // 2) Tin nhắn bot rỗng để stream fill
    final botMessage = ChatMessage(text: "", isUser: false);
    messages.add(botMessage);

    setTyping(true);

    String fullResponse = "";

    try {
      await for (final chunk in ChatService.streamChat(userText)) {
        botMessage.text += chunk;
        fullResponse += chunk;
        notifyListeners();
      }

      await _saveChatHistory(userText, fullResponse);
    } catch (e) {
      botMessage.text = "LỖI KẾT NỐI: $e";
      notifyListeners();
    } finally {
      setTyping(false);
    }
  }

  // =========================================================
  // GỬI ẢNH (Gallery) -> /detect-lite (CÁCH 1)
  // =========================================================
  Future<void> sendImageFile(XFile pickedFile) async {
    setTyping(true);

    try {
      final Uint8List bytes = await pickedFile.readAsBytes();

      // 1. Chỉ tạo MỘT tin nhắn ảnh duy nhất (Tin nhắn của bot)
      // Không đẩy tin nhắn User lên UI để tránh ảnh gốc hiển thị 2 lần.
      
      // Call YOLO detect-lite
      final responseMap = await ChatService.uploadToYOLOLite(bytes, pickedFile.name);
      final liteResponse = YoloLiteResponse.fromJson(responseMap);

      // 2. Text bot (Summary)
      messages.add(ChatMessage(text: liteResponse.summaryText.toUpperCase(), isUser: false));

      // 3. Ảnh Bot trả về (Chính là ảnh gốc của User nhưng đính kèm Toạ độ)
      if (liteResponse.boxes.isNotEmpty && liteResponse.width > 0) {
        messages.add(ChatMessage(
          text: '',
          isUser: false,
          type: MessageType.image,
          imageBytes: bytes, // TÁI SỬ DỤNG byte ảnh gốc
          yoloBoxes: liteResponse.boxes, // Gắn toạ độ vẽ khung
          imageW: liteResponse.width,
          imageH: liteResponse.height,
        ));
      } else {
        // Nếu không phát hiện gì, vẫn in ra ảnh gốc
        messages.add(ChatMessage(
          text: '',
          isUser: false,
          type: MessageType.image,
          imageBytes: bytes, 
        ));
      }

      await _saveChatHistory("(GỬI ẢNH)", liteResponse.summaryText);
    } catch (e) {
      messages.add(ChatMessage(text: "LỖI XỬ LÝ ẢNH: $e", isUser: false));
    } finally {
      setTyping(false);
      notifyListeners();
    }
  }

  // =========================================================
  // CAMERA MODE (chụp 1 ảnh) -> /detect-lite (CÁCH 1)
  // =========================================================
  Future<String> detectFromCamera(XFile pickedFile) async {
    setTyping(true);

    try {
      final Uint8List bytes = await pickedFile.readAsBytes();

      // Call YOLO detect-lite
      final responseMap = await ChatService.uploadToYOLOLite(bytes, pickedFile.name);
      final liteResponse = YoloLiteResponse.fromJson(responseMap);

      // Text bot
      messages.add(ChatMessage(text: liteResponse.summaryText.toUpperCase(), isUser: false));

      // Ảnh bbox
      if (liteResponse.boxes.isNotEmpty && liteResponse.width > 0) {
        messages.add(ChatMessage(
          text: '',
          isUser: false,
          type: MessageType.image,
          imageBytes: bytes,
          yoloBoxes: liteResponse.boxes,
          imageW: liteResponse.width,
          imageH: liteResponse.height,
        ));
      } else {
         messages.add(ChatMessage(
          text: '',
          isUser: false,
          type: MessageType.image,
          imageBytes: bytes,
        ));
      }

      await _saveChatHistory("(CAMERA YOLO)", liteResponse.summaryText);
      notifyListeners();

      return liteResponse.summaryText;
    } catch (e) {
      final err = "LỖI NHẬN DIỆN: $e";
      messages.add(ChatMessage(text: err, isUser: false));
      notifyListeners();
      return err;
    } finally {
      setTyping(false);
    }
  }

  // =========================================================
  // 4) PUSH KẾT QUẢ (text-only) - dùng chung
  // =========================================================
  void pushYoloResultToChat(String summary) {
    final s = summary.trim();
    if (s.isEmpty) return;

    messages.add(ChatMessage(text: s.toUpperCase(), isUser: false));
    notifyListeners();
  }

  // =========================================================
  // 5) REALTIME MODE: CHỈ GỬI ẢNH KẾT QUẢ + TEXT (KHÔNG GỬI ẢNH USER)
  // =========================================================
  void pushRealtimeResultToChatResultOnly({
    required String summary,
    required Uint8List annotatedPng,
  }) {
    final s = summary.trim();
    if (s.isEmpty) return;

    // 1) Text bot
    messages.add(ChatMessage(text: s.toUpperCase(), isUser: false));

    // 2) Ảnh bbox overlay (PNG đã capture)
    messages.add(ChatMessage(
      text: '',
      isUser: false,
      type: MessageType.image,
      imageBytes: annotatedPng,
    ));

    notifyListeners();

    // Nếu muốn lưu lịch sử realtime thì mở dòng này:
    // _saveChatHistory("(REALTIME YOLO)", s);
  }

  // =========================================================
  // 6) LƯU LỊCH SỬ
  // =========================================================
  Future<void> _saveChatHistory(String question, String answer) async {
    final user = _supabase.auth.currentUser;
    if (user == null) return;

    try {
      await _supabase.from('lich_su_tro_chuyen').insert({
        'userid': user.id,
        'cauhoi': question,
        'traloi': answer,
      });
    } catch (e) {
      // ignore: avoid_print
      print('Lỗi lưu lịch sử: $e');
    }
  }
}
