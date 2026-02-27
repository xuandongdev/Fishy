import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:image_picker/image_picker.dart';

import '../Models/ChatMessages.dart';
import 'package:fishy/Themes/ThemeData.dart';
import 'package:fishy/ViewModels/ChatVM.dart';
import 'package:fishy/Widgets/CustomAppBar.dart';
import '../Widgets/TypingIndicator.dart';
import '../Widgets/BBoxPainter.dart';
import 'RealtimeDetectScreen.dart';

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
  State<ChatMessagesWidget> createState() => _ChatMessagesWidgetState();
}

class _ChatMessagesWidgetState extends State<ChatMessagesWidget> {
  final TextEditingController textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  XFile? _pendingImage;              // chỉ dùng cho Gallery
  Uint8List? _pendingImageBytes;     // preview (chạy cả web/mobile)

  @override
  Widget build(BuildContext context) {
    return Consumer<ChatViewModel>(
      builder: (context, chatVM, _) {
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

  Widget _buildSingleMessage(ChatMessage message) {
    final Widget content = (message.type == MessageType.image)
        ? _buildImageContent(message)
        : Text(
      message.text,
      style: TextStyle(color: message.isUser ? Colors.white : Colors.black87),
    );

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

  // =======================================================================
  // ĐÃ SỬA: CẬP NHẬT HÀM NÀY ĐỂ VẼ Bounding Box bằng YoloImageViewer
  // =======================================================================
  Widget _buildImageContent(ChatMessage message) {
    // 1. NẾU TIN NHẮN CÓ TOẠ ĐỘ -> VẼ KHUNG (Chỉ dành cho tin nhắn của Bot)
    if (message.yoloBoxes != null && message.yoloBoxes!.isNotEmpty) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: YoloImageViewer(
          imageBytes: message.imageBytes!,
          boxes: message.yoloBoxes!,
          originalWidth: message.imageW ?? 0.0,
          originalHeight: message.imageH ?? 0.0,
        ),
      );
    } 
    // 2. NẾU LÀ ẢNH BÌNH THƯỜNG DO USER GỬI -> HIỂN THỊ BÌNH THƯỜNG
    else if (message.imageBytes != null) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Image.memory(
          message.imageBytes!,
          fit: BoxFit.contain,
          errorBuilder: (_, __, ___) => const Icon(Icons.broken_image, color: Colors.white),
        ),
      );
    }

    // 3. FALLBACK: Vẫn giữ lại phần đọc Base64 nếu như sau này bạn dùng lại API cũ
    if (message.imageBase64 != null && message.imageBase64!.isNotEmpty) {
      try {
        final bytes = base64Decode(message.imageBase64!);
        return ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: Image.memory(bytes, fit: BoxFit.contain),
        );
      } catch (_) {
        return const Text("Lỗi ảnh", style: TextStyle(color: Colors.red));
      }
    }

    return const SizedBox.shrink();
  }
  // =======================================================================

  Widget _buildInputArea(ChatViewModel chatVM) {
    return Container(
      color: Colors.white,
      padding: const EdgeInsets.only(top: 8, bottom: 8),
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
                  onSubmitted: (_) => _sendMessage(chatVM),
                ),
              ),
              IconButton(
                icon: Icon(
                  Icons.send,
                  color: (textController.text.trim().isNotEmpty || _pendingImage != null)
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
              child: _pendingImageBytes != null
                  ? Image.memory(_pendingImageBytes!, fit: BoxFit.cover)
                  : const SizedBox.shrink(),
            ),
          ),
          Positioned(
            top: 2,
            right: 2,
            child: GestureDetector(
              onTap: () => setState(() {
                _pendingImage = null;
                _pendingImageBytes = null;
              }),
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

  void _sendMessage(ChatViewModel chatVM) {
    final text = textController.text.trim();
    if (text.isEmpty && _pendingImage == null) return;

    // Gallery flow: bấm Send mới gửi YOLO
    if (_pendingImage != null) {
      chatVM.sendImageFile(_pendingImage!);
      setState(() {
        _pendingImage = null;
        _pendingImageBytes = null;
      });
    }

    if (text.isNotEmpty) {
      chatVM.sendMessage(text);
      textController.clear();
    }
  }

  void _showImageSourceActionSheet() {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              leading: const Icon(Icons.photo_library),
              title: const Text('Tải ảnh lên (Gallery)'),
              onTap: () {
                Navigator.pop(ctx);
                _pickImage(ImageSource.gallery, autoDetect: false);
              },
            ),
            ListTile(
              leading: const Icon(Icons.camera_alt),
              title: const Text('Chụp để nhận diện'),
              onTap: () {
                Navigator.pop(ctx);
                _pickImage(ImageSource.camera, autoDetect: true); // chụp -> detect ngay
              },
            ),
            ListTile(
              leading: const Icon(Icons.videocam),
              title: const Text('Nhận diện Realtime'),
              onTap: () {
                Navigator.pop(ctx);
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => const RealtimeDetectScreen(),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _pickImage(ImageSource source, {required bool autoDetect}) async {
    final picker = ImagePicker();
    try {
      final XFile? picked = await picker.pickImage(source: source);
      if (picked == null) return;

      // đọc bytes để preview/toast nhanh, chạy cả web/mobile
      final bytes = await picked.readAsBytes();

      if (!autoDetect) {
        // Gallery: chỉ preview
        setState(() {
          _pendingImage = picked;
          _pendingImageBytes = bytes;
        });
        return;
      }

      // Camera: detect ngay + toast top
      final chatVM = context.read<ChatViewModel>();
      final resultText = await chatVM.detectFromCamera(picked);

      if (!mounted) return;
      _showTopToast("ĐĐ PHÁT HIỆN THẤY: ${resultText.toUpperCase()}");
    } catch (e) {
      if (!mounted) return;
      _showTopToast("LỖI CHỌN ẢNH: $e");
    }
  }

  // ✅ Toast top giống app hiện nay (Overlay)
  void _showTopToast(String msg) {
    final overlay = Overlay.of(context);
    if (overlay == null) return;

    final topPadding = MediaQuery.of(context).padding.top;

    final entry = OverlayEntry(
      builder: (_) => Positioned(
        top: topPadding + 12,
        left: 12,
        right: 12,
        child: Material(
          color: Colors.transparent,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: Colors.black.withOpacity(0.85),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              msg,
              style: const TextStyle(color: Colors.white, fontSize: 14),
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
      ),
    );

    overlay.insert(entry);
    Future.delayed(const Duration(seconds: 3), entry.remove);
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