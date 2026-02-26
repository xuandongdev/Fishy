import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

class EmbeddingService {
  static final SupabaseClient supabase = Supabase.instance.client;

    static const String hfModel = "intfloat/multilingual-e5-large";
  static const String hfUrl =
      "https://router.huggingface.co/hf-inference/models/$hfModel";

  static Future<List<double>> generateEmbedding(String content) async {
    final String inputText = "passage: $content";
    final hfToken = dotenv.get('HF_API_KEY', fallback: "");

    final response = await http.post(
      Uri.parse(hfUrl),
      headers: {
        'Authorization': 'Bearer $hfToken',
        'Content-Type': 'application/json',
      },
      body: jsonEncode({"inputs": inputText}),
    );

    if (response.statusCode == 200) {
      final dynamic decoded = jsonDecode(response.body);

      // HF đôi khi trả về:
      // - [float, float, ...]
      // - [[float, float, ...]]  (nested)
      List<dynamic> vec;
      if (decoded is List && decoded.isNotEmpty && decoded.first is List) {
        vec = List<dynamic>.from(decoded.first as List);
      } else if (decoded is List) {
        vec = List<dynamic>.from(decoded);
      } else {
        throw Exception("HF trả về format không hợp lệ: ${response.body}");
      }

      return vec.map((e) => (e as num).toDouble()).toList();
    }

    if (response.statusCode == 503) {
      throw Exception('Model HF đang khởi động. Thử lại sau vài giây.');
    }

    throw Exception('Lỗi Hugging Face API: ${response.body}');
  }

  static Future<void> generateAndUpdateAllEmbeddings() async {
    final rows = await supabase
        .from('noidung')
        .select('sothutund, noidung')
        // tuỳ version supabase_flutter:
        // .is_('embedding', null);
        .filter('embedding', 'is', null);

    for (final row in rows) {
      final int id = row['sothutund'] as int;
      final String content = (row['noidung'] ?? '') as String;
      await generateAndUpdateOneEmbedding(id, content);
    }
  }

  static Future<void> generateAndUpdateOneEmbedding(
      int sothutund, String noidung) async {
    try {
      final embedding = await generateEmbedding(noidung);
      await supabase
          .from('noidung')
          .update({'embedding': embedding}).eq('sothutund', sothutund);
      // ignore: avoid_print
      print('Đã cập nhật embedding cho sothutund: $sothutund');
    } catch (e) {
      // ignore: avoid_print
      print('Lỗi khi sinh embedding cho $sothutund: $e');
    }
  }
}
