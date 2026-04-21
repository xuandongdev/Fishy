import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

class ServerConfig {
  static const int _ragPort = 8000;
  static const int _yoloPort = 8001;
  static const int _supabasePort = 54321;

  static String get _baseIp {
    if (kIsWeb) {
      return "127.0.0.1";
    }
    if (Platform.isAndroid) {
      return "10.0.2.2";
    }
    return "127.0.0.1";
  }

  static String? _envUrl(String key) {
    final value = dotenv.env[key]?.trim() ?? '';
    if (value.isEmpty) {
      return null;
    }
    return value.replaceAll(RegExp(r'/$'), '');
  }

  static String get ragBaseUrl => _envUrl('RAG_BASE_URL') ?? "http://$_baseIp:$_ragPort";

  static String get yoloBaseUrl => _envUrl('YOLO_BASE_URL') ?? "http://$_baseIp:$_yoloPort";

  static String get supabaseLocalUrl =>
      _envUrl('SUPABASE_LOCAL_URL') ?? "http://$_baseIp:$_supabasePort";
}
