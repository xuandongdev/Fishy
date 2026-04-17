import 'dart:math' as math;
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:image/image.dart' as img;
import 'package:image_picker/image_picker.dart';
import 'package:tflite_flutter/tflite_flutter.dart';

import '../Models/ChatMessages.dart';
import '../Models/YoloBoxModel.dart';

class LocalYoloService {
  LocalYoloService._();

  static final LocalYoloService instance = LocalYoloService._();

  static const String _modelAsset = 'assets/models/11s2_float16.tflite';
  static const String _labelsAsset = 'assets/models/classes_vie.txt';

  Interpreter? _interpreter;
  List<String> _labels = const [];
  bool _initAttempted = false;
  bool _ready = false;

  int _inputH = 320;
  int _inputW = 320;
  TensorType _inputType = TensorType.float32;

  bool get isReady => _ready;

  bool get supportsOnDevice {
    if (kIsWeb) return false;
    return defaultTargetPlatform == TargetPlatform.android ||
        defaultTargetPlatform == TargetPlatform.iOS;
  }

  Future<void> init() async {
    if (_initAttempted) return;
    _initAttempted = true;

    if (!supportsOnDevice) {
      debugPrint('LocalYoloService: platform hien tai khong bat YOLO on-device.');
      return;
    }

    try {
      _labels = await _loadLabels(_labelsAsset);

      final options = InterpreterOptions()..threads = 2;
      _interpreter = await Interpreter.fromAsset(_modelAsset, options: options);

      final inputTensor = _interpreter!.getInputTensor(0);
      final shape = inputTensor.shape;
      if (shape.length != 4) {
        throw Exception('Input tensor khong hop le: $shape');
      }

      _inputH = shape[1];
      _inputW = shape[2];
      _inputType = inputTensor.type;
      _ready = true;

      debugPrint(
        'LocalYoloService ready | input=$_inputW x $_inputH | type=$_inputType | labels=${_labels.length}',
      );
    } catch (e) {
      _ready = false;
      debugPrint('LocalYoloService init error: $e');
    }
  }

  Future<YoloLiteResponse> detectXFile(
    XFile pickedFile, {
    double confThreshold = 0.35,
    double iouThreshold = 0.45,
  }) async {
    final bytes = await pickedFile.readAsBytes();
    return detectImageBytes(
      bytes,
      confThreshold: confThreshold,
      iouThreshold: iouThreshold,
    );
  }

  Future<YoloLiteResponse> detectImageBytes(
    Uint8List bytes, {
    int rotationDegrees = 0,
    double confThreshold = 0.35,
    double iouThreshold = 0.45,
  }) async {
    await init();
    if (!_ready) {
      return YoloLiteResponse(
        summaryText: 'YOLO on-device chua san sang',
        boxes: const [],
        width: 0,
        height: 0,
      );
    }

    final decoded = img.decodeImage(bytes);
    if (decoded == null) {
      return YoloLiteResponse(
        summaryText: 'Khong doc duoc anh',
        boxes: const [],
        width: 0,
        height: 0,
      );
    }

    img.Image source = decoded;
    if (rotationDegrees != 0) {
      source = img.copyRotate(source, angle: rotationDegrees);
    }

    return _runOnImage(
      source,
      confThreshold: confThreshold,
      iouThreshold: iouThreshold,
    );
  }

  Future<YoloLiteResponse> detectCameraFrame(
    CameraImage frame, {
    int rotationDegrees = 90,
    double confThreshold = 0.35,
    double iouThreshold = 0.45,
  }) async {
    await init();
    if (!_ready) {
      return YoloLiteResponse(
        summaryText: 'YOLO on-device chua san sang',
        boxes: const [],
        width: 0,
        height: 0,
      );
    }

    final converted = _cameraImageToImage(frame);
    if (converted == null) {
      return YoloLiteResponse(
        summaryText: 'Khong doi duoc frame camera',
        boxes: const [],
        width: 0,
        height: 0,
      );
    }

    img.Image source = converted;
    if (rotationDegrees != 0) {
      source = img.copyRotate(source, angle: rotationDegrees);
    }

    return _runOnImage(
      source,
      confThreshold: confThreshold,
      iouThreshold: iouThreshold,
    );
  }

  Future<YoloLiteResponse> _runOnImage(
    img.Image source, {
    required double confThreshold,
    required double iouThreshold,
  }) async {
    final meta = _letterbox(source);
    final input = _buildInputTensor(meta.canvas);

    final outputTensor = _interpreter!.getOutputTensor(0);
    final outputShape = outputTensor.shape;
    final outputBuffer = _createTensorBuffer(outputShape, 0.0);

    _interpreter!.run(input, outputBuffer);

    final decoded = _decodeOutput(
      outputBuffer,
      outputShape,
      meta,
      confThreshold: confThreshold,
    );

    final filtered = _nms(decoded, iouThreshold);
    final summary = _buildSummary(filtered);

    return YoloLiteResponse(
      summaryText: summary,
      boxes: filtered,
      width: source.width.toDouble(),
      height: source.height.toDouble(),
    );
  }

  Future<List<String>> _loadLabels(String path) async {
    try {
      final raw = await rootBundle.loadString(path);
      return raw
          .split(RegExp(r'\r?\n'))
          .map((e) => e.trim())
          .where((e) => e.isNotEmpty)
          .toList();
    } catch (_) {
      return const [];
    }
  }

  _LetterboxMeta _letterbox(img.Image src) {
    final scale = math.min(_inputW / src.width, _inputH / src.height);
    final resizedW = math.max(1, (src.width * scale).round());
    final resizedH = math.max(1, (src.height * scale).round());

    final resized = img.copyResize(src, width: resizedW, height: resizedH);
    final canvas = img.Image(width: _inputW, height: _inputH);
    img.fill(canvas, color: img.ColorRgb8(114, 114, 114));

    final padX = ((_inputW - resizedW) / 2).floor();
    final padY = ((_inputH - resizedH) / 2).floor();
    img.compositeImage(canvas, resized, dstX: padX, dstY: padY);

    return _LetterboxMeta(
      canvas: canvas,
      originalW: src.width,
      originalH: src.height,
      scale: scale,
      padX: padX.toDouble(),
      padY: padY.toDouble(),
      inputW: _inputW,
      inputH: _inputH,
    );
  }

  Object _buildInputTensor(img.Image image) {
    if (_inputType == TensorType.uint8) {
      return [
        List.generate(_inputH, (y) {
          return List.generate(_inputW, (x) {
            final p = image.getPixel(x, y);
            return [p.r.toInt(), p.g.toInt(), p.b.toInt()];
          });
        }),
      ];
    }

    return [
      List.generate(_inputH, (y) {
        return List.generate(_inputW, (x) {
          final p = image.getPixel(x, y);
          return [p.r / 255.0, p.g / 255.0, p.b / 255.0];
        });
      }),
    ];
  }

  dynamic _createTensorBuffer(List<int> shape, double fillValue) {
    if (shape.isEmpty) return fillValue;
    if (shape.length == 1) {
      return List<double>.filled(shape.first, fillValue, growable: false);
    }
    return List.generate(
      shape.first,
      (_) => _createTensorBuffer(shape.sublist(1), fillValue),
      growable: false,
    );
  }

  List<YoloBox> _decodeOutput(
    dynamic output,
    List<int> shape,
    _LetterboxMeta meta, {
    required double confThreshold,
  }) {
    if (shape.length != 3 || shape[0] != 1) {
      debugPrint('Output shape chua duoc ho tro: $shape');
      return const [];
    }

    final flat = <double>[];
    _flattenOutput(output, flat);

    final d1 = shape[1];
    final d2 = shape[2];
    final candidates = <YoloBox>[];

    bool treated = false;

    if (d2 <= 128 && d1 > 1) {
      treated = true;
      for (int i = 0; i < d1; i++) {
        final start = i * d2;
        final feature = flat.sublist(start, start + d2);
        final box = _decodeFeatureVector(
          feature,
          meta,
          confThreshold: confThreshold,
        );
        if (box != null) candidates.add(box);
      }
    }

    if (!treated && d1 <= 128 && d2 > 1) {
      treated = true;
      for (int j = 0; j < d2; j++) {
        final feature = List<double>.generate(d1, (i) => flat[i * d2 + j]);
        final box = _decodeFeatureVector(
          feature,
          meta,
          confThreshold: confThreshold,
        );
        if (box != null) candidates.add(box);
      }
    }

    if (!treated) {
      debugPrint('Khong suy ra duoc orientation cua output: $shape');
    }

    return candidates;
  }

  YoloBox? _decodeFeatureVector(
    List<double> feature,
    _LetterboxMeta meta, {
    required double confThreshold,
  }) {
    if (feature.length < 6) return null;

    double x1;
    double y1;
    double x2;
    double y2;
    double score;
    int classId;

    final bool looksLikeNms = feature.length == 6 &&
        feature[4] >= 0 &&
        feature[4] <= 1.0 &&
        feature[5] >= 0;

    if (looksLikeNms) {
      x1 = feature[0];
      y1 = feature[1];
      x2 = feature[2];
      y2 = feature[3];
      score = feature[4];
      classId = feature[5].round();

      final maxCoord = [x1.abs(), y1.abs(), x2.abs(), y2.abs()].reduce(math.max);
      if (maxCoord <= 2.0) {
        x1 *= meta.inputW;
        x2 *= meta.inputW;
        y1 *= meta.inputH;
        y2 *= meta.inputH;
      }
    } else {
      final bool hasObjectness = _labels.isNotEmpty &&
          feature.length == _labels.length + 5;

      final double cx = feature[0];
      final double cy = feature[1];
      final double w = feature[2];
      final double h = feature[3];

      final List<double> classScores = hasObjectness
          ? feature.sublist(5)
          : feature.sublist(4);
      if (classScores.isEmpty) return null;

      int bestIdx = 0;
      double bestScore = classScores.first;
      for (int i = 1; i < classScores.length; i++) {
        if (classScores[i] > bestScore) {
          bestScore = classScores[i];
          bestIdx = i;
        }
      }

      final obj = hasObjectness ? feature[4] : 1.0;
      score = obj * bestScore;
      classId = bestIdx;
      if (score < confThreshold) return null;

      double bx = cx;
      double by = cy;
      double bw = w;
      double bh = h;

      final maxCoord = [bx.abs(), by.abs(), bw.abs(), bh.abs()].reduce(math.max);
      if (maxCoord <= 2.0) {
        bx *= meta.inputW;
        by *= meta.inputH;
        bw *= meta.inputW;
        bh *= meta.inputH;
      }

      x1 = bx - (bw / 2);
      y1 = by - (bh / 2);
      x2 = bx + (bw / 2);
      y2 = by + (bh / 2);
    }

    if (score < confThreshold) return null;

    x1 = (x1 - meta.padX) / meta.scale;
    y1 = (y1 - meta.padY) / meta.scale;
    x2 = (x2 - meta.padX) / meta.scale;
    y2 = (y2 - meta.padY) / meta.scale;

    x1 = x1.clamp(0.0, meta.originalW.toDouble()).toDouble();
    y1 = y1.clamp(0.0, meta.originalH.toDouble()).toDouble();
    x2 = x2.clamp(0.0, meta.originalW.toDouble()).toDouble();
    y2 = y2.clamp(0.0, meta.originalH.toDouble()).toDouble();

    if (x2 <= x1 || y2 <= y1) return null;
    if ((x2 - x1) < 2 || (y2 - y1) < 2) return null;

    return YoloBox(
      x1: x1,
      y1: y1,
      x2: x2,
      y2: y2,
      conf: score,
      name: _labelFor(classId),
    );
  }

  List<YoloBox> _nms(List<YoloBox> boxes, double iouThreshold) {
    if (boxes.isEmpty) return const [];

    final sorted = [...boxes]..sort((a, b) => b.conf.compareTo(a.conf));
    final selected = <YoloBox>[];

    while (sorted.isNotEmpty) {
      final current = sorted.removeAt(0);
      selected.add(current);
      sorted.removeWhere(
        (other) =>
            other.name == current.name && _iou(current, other) >= iouThreshold,
      );
    }

    return selected;
  }

  double _iou(YoloBox a, YoloBox b) {
    final interX1 = math.max(a.x1, b.x1);
    final interY1 = math.max(a.y1, b.y1);
    final interX2 = math.min(a.x2, b.x2);
    final interY2 = math.min(a.y2, b.y2);

    final interW = math.max(0.0, interX2 - interX1);
    final interH = math.max(0.0, interY2 - interY1);
    final interArea = interW * interH;
    if (interArea <= 0) return 0.0;

    final areaA = (a.x2 - a.x1) * (a.y2 - a.y1);
    final areaB = (b.x2 - b.x1) * (b.y2 - b.y1);
    final union = areaA + areaB - interArea;
    if (union <= 0) return 0.0;

    return interArea / union;
  }

  String _buildSummary(List<YoloBox> boxes) {
    if (boxes.isEmpty) return 'Khong phat hien bien bao';

    final orderedNames = <String>[];
    for (final box in boxes) {
      if (!orderedNames.contains(box.name)) {
        orderedNames.add(box.name);
      }
    }

    return orderedNames.take(3).join(', ');
  }

  String _labelFor(int classId) {
    if (classId >= 0 && classId < _labels.length) {
      return _labels[classId];
    }
    return 'class_$classId';
  }

  void _flattenOutput(dynamic value, List<double> out) {
    if (value is List) {
      for (final item in value) {
        _flattenOutput(item, out);
      }
      return;
    }
    out.add((value as num).toDouble());
  }

  img.Image? _cameraImageToImage(CameraImage image) {
    try {
      if (image.format.group == ImageFormatGroup.bgra8888) {
        return _bgra8888ToImage(image);
      }
      if (image.format.group == ImageFormatGroup.yuv420) {
        return _yuv420ToImage(image);
      }
      return null;
    } catch (e) {
      debugPrint('_cameraImageToImage error: $e');
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
        final yy = yBytes[yIndex];
        final uu = uBytes[uvIndex];
        final vv = vBytes[uvIndex];

        int r = (yy + 1.402 * (vv - 128)).round();
        int g = (yy - 0.344136 * (uu - 128) - 0.714136 * (vv - 128)).round();
        int b = (yy + 1.772 * (uu - 128)).round();

        r = r.clamp(0, 255).toInt();
        g = g.clamp(0, 255).toInt();
        b = b.clamp(0, 255).toInt();

        out.setPixelRgba(x, y, r, g, b, 255);
      }
    }

    return out;
  }
}

class _LetterboxMeta {
  const _LetterboxMeta({
    required this.canvas,
    required this.originalW,
    required this.originalH,
    required this.scale,
    required this.padX,
    required this.padY,
    required this.inputW,
    required this.inputH,
  });

  final img.Image canvas;
  final int originalW;
  final int originalH;
  final double scale;
  final double padX;
  final double padY;
  final int inputW;
  final int inputH;
}
