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
  void setTyping(bool v) { _isTyping = v; notifyListeners(); }
  void clearMessages() { messages.clear(); notifyListeners(); }

  // 1) SEND TEXT (RAG - Đã sửa lỗi 404 & History)
  Future<void> sendMessage(String? userMessage) async {
    if (userMessage == null || userMessage.trim().isEmpty) return;
    final userText = userMessage.trim();

    messages.add(ChatMessage(text: userText, isUser: true));
    notifyListeners();
    setTyping(true);

    try {
      // Lấy 5 tin nhắn text mới nhất làm ngữ cảnh
      var historyNodes = messages.where((m) => m.text.isNotEmpty && m.imageBytes == null).toList();
      if (historyNodes.length > 5) historyNodes = historyNodes.sublist(historyNodes.length - 5);

      List<Map<String, String>> history = historyNodes.map((m) => {
        "role": m.isUser ? "user" : "assistant",
        "content": m.text
      }).toList();

      final response = await ChatService.getChat(userText, history: history);
      messages.add(ChatMessage(text: response, isUser: false));
      await _saveChatHistory(userText, response);
    } catch (e) {
      messages.add(ChatMessage(text: "Lỗi kết nối: $e", isUser: false));
    } finally {
      setTyping(false);
      notifyListeners();
    }
  }

  // 2) SEND IMAGE (Giữ nguyên logic YOLO của Thanh)
  Future<void> sendImageFile(XFile pickedFile) async {
    setTyping(true);
    try {
      final Uint8List bytes = await pickedFile.readAsBytes();
      final res = await ChatService.uploadToYOLOLite(bytes, pickedFile.name);
      final summary = res['summary'] ?? "Không xác định";

      messages.add(ChatMessage(text: summary.toString().toUpperCase(), isUser: false));

      if (res['boxes'] != null && (res['boxes'] as List).isNotEmpty) {
        messages.add(ChatMessage(
          text: '', isUser: false, type: MessageType.image,
          imageBytes: bytes, yoloBoxes: res['boxes'],
          imageW: (res['w'] ?? 0).toDouble(), imageH: (res['h'] ?? 0).toDouble(),
        ));
      } else {
        messages.add(ChatMessage(text: '', isUser: false, type: MessageType.image, imageBytes: bytes));
      }
      await _saveChatHistory("(GỬI ẢNH)", summary.toString());
    } catch (e) {
      messages.add(ChatMessage(text: "Lỗi: $e", isUser: false));
    } finally { setTyping(false); notifyListeners(); }
  }

  // 3) CAMERA YOLO (Giữ nguyên logic của Thanh)
  Future<String> detectFromCamera(XFile pickedFile) async {
    setTyping(true);
    try {
      final Uint8List bytes = await pickedFile.readAsBytes();
      final res = await ChatService.uploadToYOLOLite(bytes, pickedFile.name);
      final summary = res['summary'] ?? "Không xác định";

      messages.add(ChatMessage(text: summary.toString().toUpperCase(), isUser: false));

      if (res['boxes'] != null && (res['boxes'] as List).isNotEmpty) {
        messages.add(ChatMessage(
          text: '', isUser: false, type: MessageType.image,
          imageBytes: bytes, yoloBoxes: res['boxes'],
          imageW: (res['w'] ?? 0).toDouble(), imageH: (res['h'] ?? 0).toDouble(),
        ));
      } else {
        messages.add(ChatMessage(text: '', isUser: false, type: MessageType.image, imageBytes: bytes));
      }
      await _saveChatHistory("(CAMERA YOLO)", summary.toString());
      notifyListeners();
      return summary.toString();
    } catch (e) {
      messages.add(ChatMessage(text: "Lỗi: $e", isUser: false));
      notifyListeners();
      return "Lỗi";
    } finally { setTyping(false); }
  }

  // CÁC HÀM REALTIME & LỊCH SỬ GIỮ NGUYÊN ĐỂ KHÔNG ẢNH HƯỞNG YOLO
  void pushYoloResultToChat(String summary) {
    if (summary.trim().isEmpty) return;
    messages.add(ChatMessage(text: summary.toUpperCase(), isUser: false));
    notifyListeners();
  }

  void pushRealtimeResultToChatResultOnly({required String summary, required Uint8List annotatedPng}) {
    messages.add(ChatMessage(text: summary.toUpperCase(), isUser: false));
    messages.add(ChatMessage(text: '', isUser: false, type: MessageType.image, imageBytes: annotatedPng));
    notifyListeners();
  }

  Future<void> _saveChatHistory(String q, String a) async {
    final user = _supabase.auth.currentUser;
    if (user == null) return;
    try {
      await _supabase.from('lich_su_tro_chuyen').insert({'userid': user.id, 'cauhoi': q, 'traloi': a});
    } catch (e) { debugPrint('Lỗi lịch sử: $e'); }
  }
}