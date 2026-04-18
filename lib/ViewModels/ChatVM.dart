import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'package:fishy/Models/ChatMessages.dart';
import 'package:fishy/Services/ChatService.dart';
import 'package:fishy/Services/LocalYoloService.dart';

class ChatViewModel extends ChangeNotifier {
  final List<ChatMessage> messages = [];
  bool _isTyping = false;
  final SupabaseClient _supabase = Supabase.instance.client;

  bool get isTyping => _isTyping;

  void setTyping(bool v) {
    _isTyping = v;
    notifyListeners();
  }

  void clearMessages() {
    messages.clear();
    ChatService.resetChatSession();
    notifyListeners();
  }

  Future<void> sendMessage(String? userMessage) async {
    if (userMessage == null || userMessage.trim().isEmpty) return;

    final userText = userMessage.trim();
    messages.add(ChatMessage(text: userText, isUser: true));
    notifyListeners();
    setTyping(true);

    try {
      var historyNodes = messages
          .where((m) => m.text.isNotEmpty && m.imageBytes == null)
          .toList();
      if (historyNodes.length > 16) {
        historyNodes = historyNodes.sublist(historyNodes.length - 16);
      }

      final history = historyNodes
          .map(
            (m) => {
              'role': m.isUser ? 'user' : 'assistant',
              'content': m.text,
            },
          )
          .toList();

      final response = await ChatService.getChat(userText, history: history);
      messages.add(ChatMessage(text: response, isUser: false));
      await _saveChatHistory(userText, response);
    } catch (e) {
      messages.add(ChatMessage(text: 'Lỗi kết nối: $e', isUser: false));
    } finally {
      setTyping(false);
      notifyListeners();
    }
  }

  Future<void> sendImageFile(XFile pickedFile) async {
    setTyping(true);
    try {
      final bytes = await pickedFile.readAsBytes();
      final yoloRes = await _detectPreferLocal(bytes, pickedFile.name);

      messages.add(
        ChatMessage(text: yoloRes.summaryText.toUpperCase(), isUser: false),
      );

      if (yoloRes.boxes.isNotEmpty) {
        messages.add(
          ChatMessage(
            text: '',
            isUser: false,
            type: MessageType.image,
            imageBytes: bytes,
            yoloBoxes: yoloRes.boxes,
            imageW: yoloRes.width,
            imageH: yoloRes.height,
          ),
        );
      } else {
        messages.add(
          ChatMessage(
            text: '',
            isUser: false,
            type: MessageType.image,
            imageBytes: bytes,
          ),
        );
      }

      await _saveChatHistory('(GỬI ẢNH)', yoloRes.summaryText);
    } catch (e) {
      messages.add(ChatMessage(text: 'Lỗi: $e', isUser: false));
    } finally {
      setTyping(false);
      notifyListeners();
    }
  }

  Future<String> detectFromCamera(XFile pickedFile) async {
    setTyping(true);
    try {
      final bytes = await pickedFile.readAsBytes();
      final yoloRes = await _detectPreferLocal(bytes, pickedFile.name);

      messages.add(
        ChatMessage(text: yoloRes.summaryText.toUpperCase(), isUser: false),
      );

      if (yoloRes.boxes.isNotEmpty) {
        messages.add(
          ChatMessage(
            text: '',
            isUser: false,
            type: MessageType.image,
            imageBytes: bytes,
            yoloBoxes: yoloRes.boxes,
            imageW: yoloRes.width,
            imageH: yoloRes.height,
          ),
        );
      } else {
        messages.add(
          ChatMessage(
            text: '',
            isUser: false,
            type: MessageType.image,
            imageBytes: bytes,
          ),
        );
      }

      await _saveChatHistory('(CAMERA YOLO)', yoloRes.summaryText);
      notifyListeners();
      return yoloRes.summaryText;
    } catch (e) {
      messages.add(ChatMessage(text: 'Lỗi: $e', isUser: false));
      notifyListeners();
      return 'Lỗi';
    } finally {
      setTyping(false);
    }
  }

  Future<YoloLiteResponse> _detectPreferLocal(
    Uint8List bytes,
    String filename,
  ) async {
    await LocalYoloService.instance.init();

    if (LocalYoloService.instance.isReady) {
      return LocalYoloService.instance.detectImageBytes(bytes);
    }

    final res = await ChatService.uploadToYOLOLite(bytes, filename);
    return YoloLiteResponse.fromJson(Map<String, dynamic>.from(res));
  }

  void pushYoloResultToChat(String summary) {
    if (summary.trim().isEmpty) return;
    messages.add(ChatMessage(text: summary.toUpperCase(), isUser: false));
    notifyListeners();
  }

  void pushRealtimeResultToChatResultOnly({
    required String summary,
    required Uint8List annotatedPng,
  }) {
    messages.add(ChatMessage(text: summary.toUpperCase(), isUser: false));
    messages.add(
      ChatMessage(
        text: '',
        isUser: false,
        type: MessageType.image,
        imageBytes: annotatedPng,
      ),
    );
    notifyListeners();
  }

  Future<void> _saveChatHistory(String q, String a) async {
    final user = _supabase.auth.currentUser;
    if (user == null) return;

    try {
      await _supabase.from('lich_su_tro_chuyen').insert({
        'userid': user.id,
        'cauhoi': q,
        'traloi': a,
      });
    } catch (e) {
      debugPrint('Lỗi lịch sử: $e');
    }
  }
}
