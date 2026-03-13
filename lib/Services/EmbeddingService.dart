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

  // =================================================================
  // [TÍNH NĂNG MỚI] - HÀM LẤY TOÀN BỘ NGỮ CẢNH (CHA, ÔNG NỘI)
  // =================================================================
  static Future<String> _buildHierarchyText(int sothutund) async {
    int? currentId = sothutund;
    List<String> hierarchyParts = [];

    // Vòng lặp leo ngược lên cây thư mục cho đến khi không còn cha
    while (currentId != null) {
      final res = await supabase
          .from('noidung')
          .select('noidung, ky_hieu, sothutund_cha')
          .eq('sothutund', currentId)
          .maybeSingle();

      if (res == null) break;

      String kyHieu = (res['ky_hieu'] ?? '').toString();
      String noiDung = (res['noidung'] ?? '').toString();
      
      // Ghép "Ký hiệu: Nội dung" (VD: Điều 6: Xử phạt xe ô tô...)
      String partText = kyHieu.isNotEmpty ? '$kyHieu: $noiDung' : noiDung;

      // Chèn vào đầu danh sách để thứ tự luôn là: Ông -> Cha -> Con
      hierarchyParts.insert(0, partText);

      // Cập nhật currentId thành ID của cha để tiếp tục leo lên
      currentId = res['sothutund_cha'] as int?;
    }

    // Nối các phần lại với nhau bằng dấu chấm hoặc gạch ngang
    return hierarchyParts.join(' - ');
  }

  // =================================================================
  // CẬP NHẬT 1 DÒNG (DÙNG KHI BẤM NÚT "THÊM NỘI DUNG" Ở APP)
  // =================================================================
  static Future<void> generateAndUpdateOneEmbedding(int sothutund, [String? ignoreRawContent]) async {
    try {
      // 1. Tự động lấy nội dung đầy đủ (bao gồm cả bối cảnh của Cha)
      String fullContextText = await _buildHierarchyText(sothutund);
      
      // ignore: avoid_print
      print('Chuỗi đem đi nhúng: $fullContextText');

      // 2. Nhúng Vector
      final embedding = await generateEmbedding(fullContextText);
      
      // 3. Lưu vào Database
      await supabase
          .from('noidung')
          .update({'embedding': embedding}).eq('sothutund', sothutund);
          
      // ignore: avoid_print
      print('Đã cập nhật embedding có ngữ cảnh cho sothutund: $sothutund');
    } catch (e) {
      // ignore: avoid_print
      print('Lỗi khi sinh embedding cho $sothutund: $e');
    }
  }

  // =================================================================
  // CẬP NHẬT TOÀN BỘ CƠ SỞ DỮ LIỆU
  // =================================================================
  static Future<void> generateAndUpdateAllEmbeddings() async {
    final rows = await supabase
        .from('noidung')
        .select('sothutund')
        .filter('embedding', 'is', null);

    print('Tìm thấy ${rows.length} dòng cần nhúng Vector...');

    for (final row in rows) {
      final int id = row['sothutund'] as int;
      await generateAndUpdateOneEmbedding(id);
      
      await Future.delayed(const Duration(seconds: 1)); 
    }
    print('Đã nhúng xong toàn bộ!');
  }
}