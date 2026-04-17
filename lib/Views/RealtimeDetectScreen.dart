import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../Models/YoloBoxModel.dart';
import '../Services/LocalNotiService.dart';
import '../Services/LocalYoloService.dart';
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
  String _summary = 'ĐANG CHỜ NHẬN DIỆN...';
  List<YoloBox> _boxes = const [];
  double _imgW = 0;
  double _imgH = 0;
  DateTime _lastInferAt = DateTime.fromMillisecondsSinceEpoch(0);

  static const int throttleMs = 250;
  static const int frameSkip = 5;
  int _frameCounter = 0;

  String _lastDetectedSummary = '';
  DateTime _lastDetectTime = DateTime.fromMillisecondsSinceEpoch(0);

  @override
  void initState() {
    super.initState();
    _enterImmersive();
    _boot();
  }

  Future<void> _boot() async {
    await LocalYoloService.instance.init();
    await _initCam();
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

    final controller = CameraController(
      back,
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.yuv420,
    );

    await controller.initialize();
    await controller.startImageStream(_onFrame);

    if (!mounted) return;
    setState(() => _controller = controller);
  }

  Future<void> _onFrame(CameraImage frame) async {
    _frameCounter++;
    if (_frameCounter % frameSkip != 0) return;
    if (_processing) return;

    final now = DateTime.now();
    if (now.difference(_lastInferAt).inMilliseconds < throttleMs) return;

    _processing = true;
    _lastInferAt = now;

    try {
      final res = await LocalYoloService.instance.detectCameraFrame(
        frame,
        rotationDegrees: 90,
        confThreshold: 0.38,
        iouThreshold: 0.45,
      );

      if (!mounted) return;

      setState(() {
        _summary = res.summaryText.toUpperCase();
        _imgW = res.width;
        _imgH = res.height;
        _boxes = List<YoloBox>.from(res.boxes);
      });

      if (res.boxes.isNotEmpty && !res.summaryText.contains('Không phát hiện')) {
        if (res.summaryText != _lastDetectedSummary ||
            now.difference(_lastDetectTime).inSeconds > 5) {
          _lastDetectedSummary = res.summaryText;
          _lastDetectTime = now;

          context.read<ChatViewModel>().pushYoloResultToChat(res.summaryText);
          _showTopToast('PHÁT HIỆN: ${res.summaryText.toUpperCase()}');
          LocalNotiService.showWarningNotification(res.summaryText);
        }
      }
    } catch (e) {
      debugPrint('Realtime detect error: $e');
    } finally {
      _processing = false;
    }
  }

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
              color: Colors.redAccent.withOpacity(0.9),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              msg,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.bold,
              ),
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

  Widget _buildCoverCameraWithBoxes(CameraController c) {
    final previewSize = c.value.previewSize;
    if (previewSize == null) return CameraPreview(c);

    final isLandscape = previewSize.width > previewSize.height;
    final childW = isLandscape ? previewSize.height : previewSize.width;
    final childH = isLandscape ? previewSize.width : previewSize.height;

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
                painter: BBoxPainter(
                  boxes: _boxes,
                  imgW: _imgW,
                  imgH: _imgH,
                ),
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
    final controller = _controller;
    final topPad = MediaQuery.of(context).padding.top;

    return Scaffold(
      backgroundColor: Colors.black,
      body: controller == null
          ? const Center(child: CircularProgressIndicator())
          : Stack(
              children: [
                Positioned.fill(child: _buildCoverCameraWithBoxes(controller)),
                Positioned(
                  left: 12,
                  right: 12,
                  top: topPad + 12,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 10,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.black.withOpacity(0.55),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      'ĐÃ PHÁT HIỆN: $_summary',
                      style: const TextStyle(color: Colors.white, fontSize: 14),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
                Positioned(
                  left: 12,
                  bottom: 26,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: Colors.black.withOpacity(0.5),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Text(
                      'FISHY-Detect Realtime',
                      style: TextStyle(color: Colors.white70, fontSize: 12),
                    ),
                  ),
                ),
                Positioned(
                  right: 16,
                  bottom: 24,
                  child: GestureDetector(
                    onTap: _close,
                    child: Container(
                      width: 60,
                      height: 60,
                      decoration: BoxDecoration(
                        color: Colors.black.withOpacity(0.55),
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: Colors.white.withOpacity(0.6),
                          width: 2,
                        ),
                      ),
                      child: const Icon(
                        Icons.close,
                        color: Colors.white,
                        size: 28,
                      ),
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}