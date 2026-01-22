import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

class EmbeddingService
{
  // Supabase client dùng để cập nhật embedding vào database.
  static final SupabaseClient supabase = Supabase.instance.client;

  static const String hfModel = "intfloat/multilingual-e5-large";
  static const String hfUrl = "https://router.huggingface.co/hf-inference/models/$hfModel";

  static Future<List<double>> generateEmbedding(String content) async
  {
    final String inputText = "passage: $content";
    final hfToken = dotenv.get('HF_API_KEY', fallback: "");

    final response = await http.post(
      Uri.parse(hfUrl),
      headers: {
        'Authorization': 'Bearer $hfToken',
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        "inputs": inputText,
      }),
    );

    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.cast<double>();
    } else if (response.statusCode == 503) {
      print('Model đang khởi động, vui lòng đợi...');
      throw Exception('Model đang khởi động. Hãy thử lại sau vài giây.');
    } else {
      throw Exception('Lỗi Hugging Face API: ${response.body}');
    }
  }

  /// Đồng bộ các dòng chưa có embedding và cập nhật
  static Future<void> generateAndUpdateAllEmbeddings() async {
    final rows = await supabase
        .from('noidung')
        .select('sothutund, noidung')
        .isFilter('embedding', null);

    for (var row in rows) {
      final id = row['sothutund'];
      final content = row['noidung'];
      await generateAndUpdateOneEmbedding(id, content);
    }
  }

  /// Sinh embedding cho một bản ghi `sothutund` cụ thể và cập nhật trường
  /// `embedding` tương ứng trong database.
  static Future<void> generateAndUpdateOneEmbedding(int sothutund, String noidung) async {
    try {
      final embedding = await generateEmbedding(noidung);
      await supabase.from('noidung').update({
        'embedding': embedding,
      }).eq('sothutund', sothutund);
      print('Đã cập nhật embedding cho sothutund: $sothutund');
    } catch (e) {
      print('Lỗi khi sinh embedding cho $sothutund: $e');
    }
  }
}
