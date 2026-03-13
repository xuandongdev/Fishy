import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/material.dart';
import 'dart:typed_data';

import '../Models/YoloBoxModel.dart';

class BBoxPainter extends CustomPainter {
  final List<YoloBox> boxes;
  final double imgW, imgH; // size ảnh mà YOLO detect (w,h trả từ server)

  BBoxPainter({required this.boxes, required this.imgW, required this.imgH});

  @override
  void paint(Canvas canvas, Size size) {
    if (imgW <= 0 || imgH <= 0) return;

    final sx = size.width / imgW;
    final sy = size.height / imgH;

    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;

    final textPainter = TextPainter(textDirection: TextDirection.ltr);

    for (final b in boxes) {
      final rect = Rect.fromLTRB(b.x1 * sx, b.y1 * sy, b.x2 * sx, b.y2 * sy);
      canvas.drawRect(rect, paint);

      final label = "${b.name.toUpperCase()} ${(b.conf * 100).toStringAsFixed(0)}%";
      textPainter.text = TextSpan(
        text: label,
        style: const TextStyle(color: Colors.white, fontSize: 12, backgroundColor: Colors.black54),
      );
      textPainter.layout();
      textPainter.paint(canvas, Offset(rect.left, (rect.top - 16).clamp(0, size.height)));
    }
  }

  @override
  bool shouldRepaint(covariant BBoxPainter oldDelegate) {
    return oldDelegate.boxes != boxes || oldDelegate.imgW != imgW || oldDelegate.imgH != imgH;
  }
}

class YoloImageViewer extends StatelessWidget {
  final Uint8List imageBytes;
  final List<YoloBox> boxes;
  final double originalWidth;
  final double originalHeight;

  const YoloImageViewer({
    super.key,
    required this.imageBytes,
    required this.boxes,
    required this.originalWidth,
    required this.originalHeight,
  });

  @override
  Widget build(BuildContext context) {
    // Nếu API trả về kích thước lỗi (<= 0), ta fallback hiển thị ảnh gốc bình thường
    if (originalWidth <= 0 || originalHeight <= 0) {
      return Image.memory(imageBytes);
    }

    // AspectRatio giúp khung vẽ luôn đồng dạng với tỷ lệ của ảnh gốc
    return AspectRatio(
      aspectRatio: originalWidth / originalHeight,
      child: CustomPaint(
        // Gọi nguyên si BBoxPainter của bạn vào đây, không cần sửa gì cả!
        foregroundPainter: BBoxPainter(
          boxes: boxes,
          imgW: originalWidth,
          imgH: originalHeight,
        ),
        child: Image.memory(
          imageBytes,
          fit: BoxFit.fill, // Bắt buộc dùng fill để ảnh gốc căng tràn khít với AspectRatio
        ),
      ),
    );
  }
}