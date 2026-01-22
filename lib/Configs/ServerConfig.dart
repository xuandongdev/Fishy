import 'dart:io';
import 'package:flutter/foundation.dart';

class ServerConfig {
  static const int _yoloPort = 8000;
  static const int _supabasePort = 54321; // Cổng mặc định của Supabase Local

  static String get _baseIp {
    if (kIsWeb) return "127.0.0.1";
    if (Platform.isAndroid) return "10.0.2.2"; // Android Emulator
    return "127.0.0.1";
  }

  static String get yoloBaseUrl => "http://$_baseIp:$_yoloPort";

  static String get supabaseLocalUrl => "http://$_baseIp:$_supabasePort";
}
