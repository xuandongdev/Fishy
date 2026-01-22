import 'dart:convert';
import 'dart:io'; // Giữ lại để dùng File cho Mobile, nhưng sẽ bọc kỹ
import 'package:flutter/foundation.dart'; // Để dùng kIsWeb
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:image_picker/image_picker.dart';

// Import các file nội bộ
import '../Models/ChatMessages.dart';
import 'package:fishy/Themes/ThemeData.dart';
import 'package:fishy/ViewModels/ChatVM.dart';
import 'package:fishy/Widgets/CustomAppBar.dart';
import '../Widgets/TypingIndicator.dart';

class ChatScreen extends StatelessWidget {
  const ChatScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return CustomAppBar(
      title: 'Fishy Traffic Laws',
      body: const ChatMessagesWidget(),
    );
  }
}

class ChatMessagesWidget extends StatefulWidget {
  const ChatMessagesWidget({super.key});

  @override
  _ChatMessagesWidgetState createState() => _ChatMessagesWidgetState();
}

class _ChatMessagesWidgetState extends State<ChatMessagesWidget> {
  final TextEditingController textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  // SỬA: Dùng XFile thay vì File để tương thích Web
  XFile? _pendingImage;

  @override
  Widget build(BuildContext context) {
    return Consumer<ChatViewModel>(
      builder: (context, chatVM, _) {
        // Tự động cuộn xuống
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_scrollController.hasClients) {
            _scrollController.animateTo(
              _scrollController.position.maxScrollExtent,
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOut,
            );
          }
        });

        return Column(
          children: [
            Expanded(
              child: ListView.builder(
                controller: _scrollController,
                itemCount: chatVM.messages.length,
                itemBuilder: (context, index) {
                  final message = chatVM.messages[index];
                  // Tách logic hiển thị để code gọn hơn
                  return _buildSingleMessage(message);
                },
              ),
            ),
            if (chatVM.isTyping) const TypingIndicator(),
            _buildInputArea(chatVM),
          ],
        );
      },
    );
  }

  // Widget hiển thị 1 dòng tin nhắn (Text hoặc Ảnh)
  Widget _buildSingleMessage(ChatMessage message) {
    Widget content;

    if (message.type == MessageType.image) {
      content = _buildImageContent(message);
    } else {
      content = Text(
        message.text,
        style: TextStyle(color: message.isUser ? Colors.white : Colors.black87),
      );
    }

    return Align(
      alignment: message.isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 5, horizontal: 10),
        child: Column(
          crossAxisAlignment: message.isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.7),
              decoration: BoxDecoration(
                color: message.isUser ? AppTheme.navyBlue : Colors.blueGrey[100],
                borderRadius: BorderRadius.circular(12),
              ),
              child: content,
            ),
            // Thời gian
            Padding(
              padding: const EdgeInsets.only(top: 2, right: 4, left: 4),
              child: Text(
                _formatTime(message.timestamp),
                style: const TextStyle(color: Colors.grey, fontSize: 10),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // Xử lý hiển thị ảnh trong tin nhắn (An toàn cho Web)
  Widget _buildImageContent(ChatMessage message) {
    // 1. Ưu tiên hiển thị từ Bytes (vừa upload hoặc từ memory) -> Chạy được mọi nền tảng
    if (message.imageBytes != null) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Image.memory(
          message.imageBytes!,
          fit: BoxFit.contain,
          errorBuilder: (context, error, stackTrace) => const Icon(Icons.broken_image, color: Colors.white),
        ),
      );
    }
    // 2. Hiển thị từ Base64 (Server trả về)
    else if (message.imageBase64 != null) {
      try {
        final bytes = base64Decode(message.imageBase64!);
        return ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: Image.memory(bytes, fit: BoxFit.contain),
        );
      } catch (e) {
        return const Text("Lỗi ảnh", style: TextStyle(color: Colors.red));
      }
    }
    return const SizedBox.shrink();
  }

  // Khu vực nhập liệu
  Widget _buildInputArea(ChatViewModel chatVM) {
    return Container(
      color: Colors.white,
      padding: const EdgeInsets.only(top: 8, bottom: 8), // Thêm padding bottom
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_pendingImage != null) _buildPendingImagePreview(),

          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              IconButton(
                icon: const Icon(Icons.camera_alt_outlined, color: AppTheme.navyBlue),
                onPressed: _showImageSourceActionSheet,
              ),
              Expanded(
                child: TextField(
                  controller: textController,
                  minLines: 1,
                  maxLines: 4,
                  decoration: InputDecoration(
                    hintText: 'Nhập câu hỏi...',
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(24),
                      borderSide: BorderSide.none,
                    ),
                    filled: true,
                    fillColor: Colors.grey[200],
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  ),
                  onSubmitted: (value) => _sendMessage(chatVM),
                ),
              ),
              IconButton(
                icon: Icon(
                  Icons.send,
                  color: (textController.text.isNotEmpty || _pendingImage != null)
                      ? AppTheme.navyBlue
                      : Colors.grey,
                ),
                onPressed: () => _sendMessage(chatVM),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // Widget xem trước ảnh chuẩn bị gửi (Fix lỗi Web ở đây)
  Widget _buildPendingImagePreview() {
    return Padding(
      padding: const EdgeInsets.only(left: 16, bottom: 8),
      child: Stack(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: SizedBox(
              height: 100,
              width: 100,
              // LOGIC HIỂN THỊ ẢNH PREVIEW QUAN TRỌNG
              child: kIsWeb
                  ? Image.network(_pendingImage!.path, fit: BoxFit.cover) // Web dùng network (blob)
                  : Image.file(File(_pendingImage!.path), fit: BoxFit.cover), // Mobile dùng File
            ),
          ),
          Positioned(
            top: 2,
            right: 2,
            child: GestureDetector(
              onTap: () => setState(() => _pendingImage = null),
              child: Container(
                padding: const EdgeInsets.all(2),
                decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                child: const Icon(Icons.close, size: 16, color: Colors.red),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // --- LOGIC ---

  void _sendMessage(ChatViewModel chatVM) {
    final text = textController.text.trim();
    if (text.isEmpty && _pendingImage == null) return;

    if (_pendingImage != null) {
      // Gửi XFile thẳng sang ViewModel
      chatVM.sendImageFile(_pendingImage!);
      setState(() => _pendingImage = null);
    }

    if (text.isNotEmpty) {
      chatVM.sendMessage(text);
      textController.clear();
    }
  }

  void _showImageSourceActionSheet() {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
      builder: (context) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              leading: const Icon(Icons.photo_library),
              title: const Text('Thư viện ảnh'),
              onTap: () {
                Navigator.pop(context);
                _pickImage(ImageSource.gallery);
              },
            ),
            ListTile(
              leading: const Icon(Icons.camera_alt),
              title: const Text('Chụp ảnh'),
              onTap: () {
                Navigator.pop(context);
                _pickImage(ImageSource.camera);
              },
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _pickImage(ImageSource source) async {
    final picker = ImagePicker();
    try {
      final XFile? picked = await picker.pickImage(source: source);
      if (picked != null) {
        setState(() {
          _pendingImage = picked; // Lưu XFile trực tiếp
        });
      }
    } catch (e) {
      print("Lỗi chọn ảnh: $e");
    }
  }

  String _formatTime(DateTime timestamp) {
    return "${timestamp.hour}:${timestamp.minute.toString().padLeft(2, '0')}";
  }

  @override
  void dispose() {
    textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }
}