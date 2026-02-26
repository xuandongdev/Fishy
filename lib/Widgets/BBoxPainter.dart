import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

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
