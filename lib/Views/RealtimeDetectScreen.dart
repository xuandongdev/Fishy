import 'dart:typed_data';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:image/image.dart' as img;

import '../Models/YoloBoxModel.dart';
import '../Services/ChatService.dart';
import '../Services/LocalNotiService.dart'; // IMPORT SERVICE THÔNG BÁO
import '../ViewModels/ChatVM.dart';
import '../Widgets/BBoxPainter.dart';

class RealtimeDetectScreen extends StatefulWidget {
  const RealtimeDetectScreen({super.key});

  @override
  State<RealtimeDetectScreen> createState() => _RealtimeDetectScreenState();
}

class _RealtimeDetectScreenState extends State<RealtimeDetectScreen> {
  CameraController? _controller;
  bool _processing = false;

  String _summary = "ĐANG CHỜ NHẬN DIỆN...";
  List<YoloBox> _boxes = [];
  double _imgW = 0, _imgH = 0;

  DateTime _lastSent = DateTime.fromMillisecondsSinceEpoch(0);
  static const int throttleMs = 600; // Khoảng cách giữa các lần gửi frame lên server

  // --- Biến chống Spam Thông Báo ---
  String _lastDetectedSummary = "";
  DateTime _lastDetectTime = DateTime.fromMillisecondsSinceEpoch(0);

  @override
  void initState() {
    super.initState();
    _enterImmersive();
    _initCam();
  }

  Future<void> _enterImmersive() async {
    await SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  }

  Future<void> _exitImmersive() async {
    await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  }

  Future<void> _initCam() async {
    final cams = await availableCameras();
    final back = cams.firstWhere(
          (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => cams.first,
    );

    final c = CameraController(
      back,
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.yuv420,
    );

    await c.initialize();
    await c.startImageStream(_onFrame);

    if (!mounted) return;
    setState(() => _controller = c);
  }

  Future<void> _onFrame(CameraImage frame) async {
    if (_processing) return;

    final now = DateTime.now();
    if (now.difference(_lastSent).inMilliseconds < throttleMs) return;
    _lastSent = now;

    _processing = true;
    try {
      final Uint8List? jpegBytes = await cameraImageToJpeg(frame);
      if (jpegBytes == null) return;

      final res = await ChatService.uploadToYOLOLite(jpegBytes, "frame.jpg");
      final sum = (res['summary'] ?? '').toString();
      final w = (res['w'] as num?)?.toDouble() ?? 0;
      final h = (res['h'] as num?)?.toDouble() ?? 0;

      final rawBoxes = (res['boxes'] as List?) ?? [];
      final boxes = rawBoxes
          .map((e) => YoloBox.fromJson(Map<String, dynamic>.from(e)))
          .toList();

      if (!mounted) return;

      setState(() {
        _summary = sum.toUpperCase();
        _imgW = w;
        _imgH = h;
        _boxes = boxes;
      });

      // ==========================================
      // LOGIC TỰ ĐỘNG THÔNG BÁO & LƯU CHAT CHỐNG SPAM
      // ==========================================
      if (boxes.isNotEmpty && !sum.contains("Không phát hiện")) {
        // Chỉ thông báo nếu: Là biển báo KHÁC với biển trước đó HOẶC đã trôi qua 5 GIÂY kể từ lần nhắc cuối
        if (sum != _lastDetectedSummary || now.difference(_lastDetectTime).inSeconds > 5) {
          _lastDetectedSummary = sum;
          _lastDetectTime = now;

          // 1. Lưu text vào Chat (Không có ảnh)
          context.read<ChatViewModel>().pushYoloResultToChat(sum);

          // 2. Hiện Toast Overlay trên màn hình
          _showTopToast("PHÁT HIỆN: ${sum.toUpperCase()}");

          // 3. Bắn thông báo đẩy (System Notification)
          LocalNotiService.showWarningNotification(sum);
        }
      }

    } finally {
      _processing = false;
    }
  }

  // Hàm hiện Toast Overlay (tương tự như trong ChatScreen)
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
              color: Colors.redAccent.withOpacity(0.9), // Đổi màu cảnh báo cho nổi bật
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              msg,
              style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.bold),
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

  Future<void> _stopStreamSafe() async {
    try {
      if (_controller?.value.isStreamingImages == true) {
        await _controller?.stopImageStream();
      }
    } catch (_) {}
  }

  // ========================
  // CameraImage -> JPEG bytes
  // ========================
  Future<Uint8List?> cameraImageToJpeg(CameraImage image) async {
    try {
      final img.Image rgb;
      if (image.format.group == ImageFormatGroup.bgra8888) {
        rgb = _bgra8888ToImage(image);
      } else if (image.format.group == ImageFormatGroup.yuv420) {
        rgb = _yuv420ToImage(image);
      } else {
        return null;
      }
      final jpg = img.encodeJpg(rgb, quality: 80);
      return Uint8List.fromList(jpg);
    } catch (e) {
      debugPrint("cameraImageToJpeg error: $e");
      return null;
    }
  }

  img.Image _bgra8888ToImage(CameraImage image) {
    final w = image.width;
    final h = image.height;
    final plane = image.planes[0];
    final bytes = plane.bytes;
    final rowStride = plane.bytesPerRow;

    final out = img.Image(width: w, height: h);

    for (int y = 0; y < h; y++) {
      final rowStart = y * rowStride;
      for (int x = 0; x < w; x++) {
        final i = rowStart + x * 4;
        final b = bytes[i];
        final g = bytes[i + 1];
        final r = bytes[i + 2];
        final a = bytes[i + 3];
        out.setPixelRgba(x, y, r, g, b, a);
      }
    }
    return out;
  }

  img.Image _yuv420ToImage(CameraImage image) {
    final w = image.width;
    final h = image.height;

    final planeY = image.planes[0];
    final planeU = image.planes[1];
    final planeV = image.planes[2];

    final yBytes = planeY.bytes;
    final uBytes = planeU.bytes;
    final vBytes = planeV.bytes;

    final yRowStride = planeY.bytesPerRow;
    final uvRowStride = planeU.bytesPerRow;
    final uvPixelStride = planeU.bytesPerPixel ?? 1;

    final out = img.Image(width: w, height: h);

    for (int y = 0; y < h; y++) {
      final yRow = yRowStride * y;
      final uvRow = uvRowStride * (y >> 1);

      for (int x = 0; x < w; x++) {
        final yIndex = yRow + x;
        final uvIndex = uvRow + (x >> 1) * uvPixelStride;

        final Y = yBytes[yIndex];
        final U = uBytes[uvIndex];
        final V = vBytes[uvIndex];

        int r = (Y + 1.402 * (V - 128)).round();
        int g = (Y - 0.344136 * (U - 128) - 0.714136 * (V - 128)).round();
        int b = (Y + 1.772 * (U - 128)).round();

        if (r < 0) r = 0;
        if (r > 255) r = 255;
        if (g < 0) g = 0;
        if (g > 255) g = 255;
        if (b < 0) b = 0;
        if (b > 255) b = 255;

        out.setPixelRgba(x, y, r, g, b, 255);
      }
    }
    return out;
  }

  // ========================
  // FULLSCREEN cover (không cần RepaintBoundary nữa)
  // ========================
  Widget _buildCoverCameraWithBoxes(CameraController c) {
    final previewSize = c.value.previewSize;
    if (previewSize == null) return CameraPreview(c);

    final bool isLandscape = previewSize.width > previewSize.height;
    final double childW = isLandscape ? previewSize.height : previewSize.width;
    final double childH = isLandscape ? previewSize.width : previewSize.height;

    return ClipRect(
      child: FittedBox(
        fit: BoxFit.cover,
        child: SizedBox(
          width: childW,
          height: childH,
          child: Stack(
            fit: StackFit.expand,
            children: [
              CameraPreview(c),
              CustomPaint(
                painter: BBoxPainter(boxes: _boxes, imgW: _imgW, imgH: _imgH),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _close() async {
    await _stopStreamSafe();
    await _exitImmersive();
    if (!mounted) return;
    Navigator.pop(context);
  }

  @override
  void dispose() {
    _stopStreamSafe();
    _controller?.dispose();
    _exitImmersive();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = _controller;
    final topPad = MediaQuery.of(context).padding.top;

    return Scaffold(
      backgroundColor: Colors.black,
      body: c == null
          ? const Center(child: CircularProgressIndicator())
          : Stack(
        children: [
          Positioned.fill(child: _buildCoverCameraWithBoxes(c)),

          // text bar
          Positioned(
            left: 12,
            right: 12,
            top: topPad + 12,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: Colors.black.withOpacity(0.55),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                "ĐÃ PHÁT HIỆN: $_summary",
                style: const TextStyle(color: Colors.white, fontSize: 14),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),

          // Chỉ giữ lại nút Đóng (Vì hệ thống tự động lưu vào Chat rồi)
          Positioned(
            left: 0,
            right: 0,
            bottom: 26,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _roundBtn(
                  icon: Icons.close,
                  onTap: _close,
                  enabled: true,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _roundBtn({
    required IconData icon,
    required VoidCallback onTap,
    required bool enabled,
  }) {
    return GestureDetector(
      onTap: enabled ? onTap : null,
      child: Container(
        width: 64,
        height: 64,
        decoration: BoxDecoration(
          color: enabled ? Colors.black.withOpacity(0.55) : Colors.black.withOpacity(0.25),
          shape: BoxShape.circle,
          border: Border.all(
            color: Colors.white.withOpacity(enabled ? 0.6 : 0.25),
            width: 2,
          ),
        ),
        child: Icon(
          icon,
          color: enabled ? Colors.white : Colors.white38,
          size: 30,
        ),
      ),
    );
  }
}