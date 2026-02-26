// import 'dart:io';
// import 'dart:typed_data';

// enum MessageType{text, image}

// class ChatMessage
// {
//   final String text;
//   final bool isUser;
//   final DateTime timestamp;
//   final MessageType type;

//   final File? imageFile;  //mobile
//   final Uint8List? imageBytes;  //web
//   final String? imageBase64;

//   ChatMessage(
//   {
//     required this.text,
//     required this.isUser,
//     DateTime? timestamp,
//     this.type = MessageType.text,
//     this.imageFile,
//     this.imageBytes,
//     this.imageBase64
//   }
//   ) : this.timestamp = timestamp ?? DateTime.now();
// }
// class LawSearchResult
// {
//   final String sohieu;
//   final String tenvanban;
//   final String noidung;

//   LawSearchResult({required this.sohieu, required this.tenvanban, required this.noidung});

//   factory LawSearchResult.fromJson(Map<String, dynamic> json)
//   {
//     return LawSearchResult(
//       sohieu: json['sohieuvanban'],
//       tenvanban: json['tenvanban'],
//       noidung: json['noidung'],
//     );
//   }
// }

// class YoloResponse {
//   final String summaryText;
//   final String? imageBase64;

//   YoloResponse({required this.summaryText, this.imageBase64});

//   factory YoloResponse.fromJson(Map<String, dynamic> json) {
//     return YoloResponse(
//       summaryText: json['summary'] ?? json['text'] ?? json['message'] ?? 'Kết quả nhận diện',
//       imageBase64: json['image_base64'] ?? json['image'],
//     );
//   }
// }
import 'dart:io';
import 'dart:typed_data';

enum MessageType { text, image }

class ChatMessage {
  String text; // Bỏ final để có thể update text khi stream
  final bool isUser;
  final DateTime timestamp;
  final MessageType type;

  // Hỗ trợ hiển thị ảnh
  final File? imageFile;      // Mobile
  final Uint8List? imageBytes; // Web
  final String? imageBase64;  // Server Response

  ChatMessage({
    required this.text,
    required this.isUser,
    DateTime? timestamp,
    this.type = MessageType.text,
    this.imageFile,
    this.imageBytes,
    this.imageBase64,
  }) : timestamp = timestamp ?? DateTime.now();
}

// Model hứng kết quả YOLO (Giữ lại nếu bạn định tích hợp endpoint /detect vào Python server sau này)
class YoloResponse {
  final String summaryText;
  final String? imageBase64;

  YoloResponse({required this.summaryText, this.imageBase64});

  factory YoloResponse.fromJson(Map<String, dynamic> json) {
    return YoloResponse(
      summaryText: json['summary'] ?? json['text'] ?? 'Kết quả nhận diện',
      imageBase64: json['image_base64'] ?? json['image'],
    );
  }
}

