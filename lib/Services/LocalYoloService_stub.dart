import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:image_picker/image_picker.dart';

import '../Models/ChatMessages.dart';

class LocalYoloService {
  LocalYoloService._();

  static final LocalYoloService instance = LocalYoloService._();

  bool get isReady => false;

  bool get supportsOnDevice => false;

  Future<void> init() async {}

  Future<YoloLiteResponse> detectXFile(
    XFile pickedFile, {
    double confThreshold = 0.35,
    double iouThreshold = 0.45,
  }) async {
    return YoloLiteResponse(
      summaryText: 'YOLO on-device khong ho tro tren nen tang nay',
      boxes: const [],
      width: 0,
      height: 0,
    );
  }

  Future<YoloLiteResponse> detectImageBytes(
    Uint8List bytes, {
    int rotationDegrees = 0,
    double confThreshold = 0.35,
    double iouThreshold = 0.45,
  }) async {
    return YoloLiteResponse(
      summaryText: 'YOLO on-device khong ho tro tren nen tang nay',
      boxes: const [],
      width: 0,
      height: 0,
    );
  }

  Future<YoloLiteResponse> detectCameraFrame(
    CameraImage frame, {
    int rotationDegrees = 90,
    double confThreshold = 0.35,
    double iouThreshold = 0.45,
  }) async {
    return YoloLiteResponse(
      summaryText: 'YOLO on-device khong ho tro tren nen tang nay',
      boxes: const [],
      width: 0,
      height: 0,
    );
  }
}
