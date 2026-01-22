import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'ServerConfig.dart';

class SupabaseConfig {
  static bool _isInitialized = false;

  // Khi test local, dùng supabaseLocalUrl từ ServerConfig (10.0.2.2:54321)
  static String get supaUrl => ServerConfig.supabaseLocalUrl;

  // Lấy Anon Key Local từ file .env
  static String get supaKey => dotenv.get('SUPABASE_ANON_KEY', fallback: '');

  static Future<void> initialize() async {
    if (!_isInitialized) {
      try {
        await Supabase.initialize(
          url: supaUrl,
          anonKey: supaKey,
        );
        _isInitialized = true;
        print("Đã kết nối Supabase Local: $supaUrl");
      } catch (e) {
        print("Lỗi khởi tạo Supabase: $e");
      }
    }
  }
}