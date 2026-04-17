import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../Models/YoloBoxModel.dart';

class BBoxPainter extends CustomPainter {
  const BBoxPainter({
    required this.boxes,
    required this.imgW,
    required this.imgH,
    this.fit = BoxFit.fill,
  });

  final List<YoloBox> boxes;
  final double imgW;
  final double imgH;
  final BoxFit fit;

  @override
  void paint(Canvas canvas, Size size) {
    if (imgW <= 0 || imgH <= 0 || boxes.isEmpty) return;

    final _PaintTransform tf = _resolveTransform(size);

    final boxPaint = Paint()
      ..color = Colors.redAccent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5;

    final labelBg = Paint()..color = Colors.black54;
    final textPainter = TextPainter(textDirection: TextDirection.ltr);

    for (final b in boxes) {
      final rect = Rect.fromLTRB(
        tf.offsetX + b.x1 * tf.scaleX,
        tf.offsetY + b.y1 * tf.scaleY,
        tf.offsetX + b.x2 * tf.scaleX,
        tf.offsetY + b.y2 * tf.scaleY,
      );

      canvas.drawRect(rect, boxPaint);

      final label = '${b.name.toUpperCase()} ${(b.conf * 100).toStringAsFixed(0)}%';
      textPainter.text = TextSpan(
        text: label,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      );
      textPainter.layout(maxWidth: size.width - 12);

      final labelX = rect.left
          .clamp(0.0, math.max(0.0, size.width - textPainter.width - 8))
          .toDouble();
      final labelY = (rect.top - textPainter.height - 6)
          .clamp(0.0, math.max(0.0, size.height - textPainter.height - 4))
          .toDouble();

      final bgRect = RRect.fromRectAndRadius(
        Rect.fromLTWH(
          labelX - 4,
          labelY - 2,
          textPainter.width + 8,
          textPainter.height + 4,
        ),
        const Radius.circular(4),
      );

      canvas.drawRRect(bgRect, labelBg);
      textPainter.paint(canvas, Offset(labelX, labelY));
    }
  }

  _PaintTransform _resolveTransform(Size size) {
    if (fit == BoxFit.cover) {
      final scale = math.max(size.width / imgW, size.height / imgH);
      final drawW = imgW * scale;
      final drawH = imgH * scale;
      return _PaintTransform(
        scaleX: scale,
        scaleY: scale,
        offsetX: (size.width - drawW) / 2,
        offsetY: (size.height - drawH) / 2,
      );
    }

    if (fit == BoxFit.contain) {
      final scale = math.min(size.width / imgW, size.height / imgH);
      final drawW = imgW * scale;
      final drawH = imgH * scale;
      return _PaintTransform(
        scaleX: scale,
        scaleY: scale,
        offsetX: (size.width - drawW) / 2,
        offsetY: (size.height - drawH) / 2,
      );
    }

    return _PaintTransform(
      scaleX: size.width / imgW,
      scaleY: size.height / imgH,
      offsetX: 0,
      offsetY: 0,
    );
  }

  @override
  bool shouldRepaint(covariant BBoxPainter oldDelegate) {
    return oldDelegate.boxes != boxes ||
        oldDelegate.imgW != imgW ||
        oldDelegate.imgH != imgH ||
        oldDelegate.fit != fit;
  }
}

class YoloImageViewer extends StatelessWidget {
  const YoloImageViewer({
    super.key,
    required this.imageBytes,
    required this.boxes,
    required this.originalWidth,
    required this.originalHeight,
  });

  final Uint8List imageBytes;
  final List<YoloBox> boxes;
  final double originalWidth;
  final double originalHeight;

  @override
  Widget build(BuildContext context) {
    if (originalWidth <= 0 || originalHeight <= 0) {
      return Image.memory(imageBytes);
    }

    return AspectRatio(
      aspectRatio: originalWidth / originalHeight,
      child: CustomPaint(
        foregroundPainter: BBoxPainter(
          boxes: boxes,
          imgW: originalWidth,
          imgH: originalHeight,
          fit: BoxFit.fill,
        ),
        child: Image.memory(
          imageBytes,
          fit: BoxFit.fill,
        ),
      ),
    );
  }
}

class _PaintTransform {
  const _PaintTransform({
    required this.scaleX,
    required this.scaleY,
    required this.offsetX,
    required this.offsetY,
  });

  final double scaleX;
  final double scaleY;
  final double offsetX;
  final double offsetY;
}
