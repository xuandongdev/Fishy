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
  // 2) GỬI ẢNH (Gallery) -> /detect
  // =========================================================
  Future<void> sendImageFile(XFile pickedFile) async {
    setTyping(true);

    try {
      final Uint8List bytes = await pickedFile.readAsBytes();

      // Ảnh user (gallery)
      messages.add(ChatMessage(
        text: '',
        isUser: true,
        type: MessageType.image,
        imageBytes: bytes,
      ));
      notifyListeners();

      // Call YOLO detect
      final responseMap = await ChatService.uploadToYOLO(bytes, pickedFile.name);
      final yoloResponse = YoloResponse.fromJson(responseMap);

      // Text bot
      messages.add(ChatMessage(text: yoloResponse.summaryText.toUpperCase(), isUser: false));

      // Ảnh bbox (server trả base64)
      if (yoloResponse.imageBase64 != null && yoloResponse.imageBase64!.isNotEmpty) {
        messages.add(ChatMessage(
          text: '',
          isUser: false,
          type: MessageType.image,
          imageBase64: yoloResponse.imageBase64,
        ));
      }

      await _saveChatHistory("(GỬI ẢNH)", yoloResponse.summaryText);
    } catch (e) {
      messages.add(ChatMessage(text: "LỖI XỬ LÝ ẢNH: $e", isUser: false));
      notifyListeners();
    } finally {
      setTyping(false);
    }
  }

  // =========================================================
  // 3) CAMERA MODE (chụp 1 ảnh) -> /detect
  // =========================================================
  Future<String> detectFromCamera(XFile pickedFile) async {
    setTyping(true);

    try {
      final Uint8List bytes = await pickedFile.readAsBytes();

      // Ảnh user (camera)
      messages.add(ChatMessage(
        text: '',
        isUser: true,
        type: MessageType.image,
        imageBytes: bytes,
      ));
      notifyListeners();

      // Call YOLO detect
      final responseMap = await ChatService.uploadToYOLO(bytes, pickedFile.name);
      final yoloResponse = YoloResponse.fromJson(responseMap);

      // Text bot
      messages.add(ChatMessage(text: yoloResponse.summaryText.toUpperCase(), isUser: false));

      // Ảnh bbox (server trả base64)
      if (yoloResponse.imageBase64 != null && yoloResponse.imageBase64!.isNotEmpty) {
        messages.add(ChatMessage(
          text: '',
          isUser: false,
          type: MessageType.image,
          imageBase64: yoloResponse.imageBase64,
        ));
      }

      await _saveChatHistory("(CAMERA YOLO)", yoloResponse.summaryText);
      notifyListeners();

      return yoloResponse.summaryText;
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
