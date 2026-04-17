import 'dart:convert';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import '../Configs/ServerConfig.dart';

class LegalIngestResult {
  final bool success;
  final String message;
  final int insertedCount;
  final String? fileName;

  const LegalIngestResult({
    required this.success,
    required this.message,
    this.insertedCount = 0,
    this.fileName,
  });
}

class LegalIngestService {
  static const List<String> _allowedExtensions = ['pdf', 'docx', 'txt'];
  static String _legalIngestUrl = '';

  static Future<void> initializeApiUrl() async {
    try {
      final supabase = Supabase.instance.client;
      final response = await supabase
          .from('app_config')
          .select('key, value')
          .eq('key', 'legal_ingest_url')
          .maybeSingle();
      final value = (response?['value'] ?? '').toString().replaceAll(RegExp(r'/$'), '');
      _legalIngestUrl = value.isNotEmpty ? value : ServerConfig.legalIngestBaseUrl;
    } catch (_) {
      _legalIngestUrl = ServerConfig.legalIngestBaseUrl;
    }
  }

  String get _baseUrl {
    if (_legalIngestUrl.isEmpty) {
      _legalIngestUrl = ServerConfig.legalIngestBaseUrl;
    }
    return _legalIngestUrl;
  }

  Future<LegalIngestResult> pickAndUploadDocument({
    required String soHieu,
  }) async {
    final normalizedSoHieu = soHieu.trim();
    if (normalizedSoHieu.isEmpty) {
      return const LegalIngestResult(
        success: false,
        message: 'Vui long nhap so hieu truoc khi tai file.',
      );
    }

    final picked = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: _allowedExtensions,
      withData: true,
    );

    if (picked == null || picked.files.isEmpty) {
      return const LegalIngestResult(
        success: false,
        message: 'Chua chon file de tai len.',
      );
    }

    final file = picked.files.first;
    if (file.bytes == null || file.bytes!.isEmpty) {
      return LegalIngestResult(
        success: false,
        message: 'Khong doc duoc noi dung file ${file.name}.',
        fileName: file.name,
      );
    }

    return uploadDocument(
      soHieu: normalizedSoHieu,
      fileName: file.name,
      fileBytes: file.bytes!,
    );
  }

  Future<LegalIngestResult> uploadDocument({
    required String soHieu,
    required String fileName,
    required Uint8List fileBytes,
  }) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$_baseUrl/api/legal-documents/ingest'),
      );
      request.fields['so_hieu'] = soHieu.trim();
      request.files.add(
        http.MultipartFile.fromBytes(
          'file',
          fileBytes,
          filename: fileName,
        ),
      );

      final streamedResponse = await request.send();
      final response = await http.Response.fromStream(streamedResponse);
      final dynamic decoded = jsonDecode(utf8.decode(response.bodyBytes));
      final Map<String, dynamic> payload = decoded is Map<String, dynamic>
          ? decoded
          : <String, dynamic>{};

      if (response.statusCode == 200 && payload['success'] == true) {
        return LegalIngestResult(
          success: true,
          message: 'Tai file va insert du lieu thanh cong.',
          insertedCount: (payload['inserted_count'] ?? 0) as int,
          fileName: payload['file_name']?.toString() ?? fileName,
        );
      }

      return LegalIngestResult(
        success: false,
        message: payload['detail']?.toString() ??
            payload['error']?.toString() ??
            'Legal ingest loi (${response.statusCode}).',
        fileName: fileName,
      );
    } catch (e) {
      return LegalIngestResult(
        success: false,
        message: 'Khong the ket noi legal_ingest: $e',
        fileName: fileName,
      );
    }
  }
}
