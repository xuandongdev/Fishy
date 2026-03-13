import 'dart:io';
import 'dart:typed_data';
import '../Models/YoloBoxModel.dart';

enum MessageType { text, image }

class ChatMessage {
  String text;
  final bool isUser;
  final DateTime timestamp;
  final MessageType type;

  final File? imageFile;
  final Uint8List? imageBytes;
  final String? imageBase64;

  // THÊM MỚI: Thuộc tính để hứng toạ độ và kích thước ảnh
  final List<YoloBox>? yoloBoxes;
  final double? imageW;
  final double? imageH;

  ChatMessage({
    required this.text,
    required this.isUser,
    DateTime? timestamp,
    this.type = MessageType.text,
    this.imageFile,
    this.imageBytes,
    this.imageBase64,
    this.yoloBoxes,
    this.imageW,
    this.imageH,
  }) : timestamp = timestamp ?? DateTime.now();
}

// CẬP NHẬT: Model này giờ sẽ đọc JSON từ API /detect-lite
class YoloLiteResponse {
  final String summaryText;
  final List<YoloBox> boxes;
  final double width;
  final double height;

  YoloLiteResponse({
    required this.summaryText,
    required this.boxes,
    required this.width,
    required this.height,
  });

  factory YoloLiteResponse.fromJson(Map<String, dynamic> json) {
    var boxList = json['boxes'] as List? ?? [];
    return YoloLiteResponse(
      summaryText: json['summary'] ?? json['text'] ?? 'Kết quả nhận diện',
      boxes: boxList.map((i) => YoloBox.fromJson(i)).toList(),
      width: (json['w'] as num?)?.toDouble() ?? 0.0,
      height: (json['h'] as num?)?.toDouble() ?? 0.0,
    );
  }
}