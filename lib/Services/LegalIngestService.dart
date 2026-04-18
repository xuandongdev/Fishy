import 'dart:convert';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import '../Configs/ServerConfig.dart';

class PickedLegalDocument {
  final String fileName;
  final Uint8List fileBytes;

  const PickedLegalDocument({
    required this.fileName,
    required this.fileBytes,
  });
}

class LegalIngestResult {
  final bool success;
  final String message;
  final int insertedCount;
  final int chunksIndexed;
  final int sectionsCount;
  final String? fileName;
  final String? title;
  final String? chunkingMode;

  const LegalIngestResult({
    required this.success,
    required this.message,
    this.insertedCount = 0,
    this.chunksIndexed = 0,
    this.sectionsCount = 0,
    this.fileName,
    this.title,
    this.chunkingMode,
  });
}

class LegalIngestService {
  static const List<String> _allowedExtensions = ['pdf', 'docx'];
  static String _ragUrl = '';

  static Future<void> initializeApiUrl() async {
    try {
      final supabase = Supabase.instance.client;
      final response = await supabase
          .from('app_config')
          .select('key, value')
          .eq('key', 'rag_url')
          .maybeSingle();
      final value = (response?['value'] ?? '').toString().replaceAll(RegExp(r'/$'), '');
      _ragUrl = value.isNotEmpty ? value : ServerConfig.ragBaseUrl;
    } catch (_) {
      _ragUrl = ServerConfig.ragBaseUrl;
    }
  }

  String get _baseUrl {
    if (_ragUrl.isEmpty) {
      _ragUrl = ServerConfig.ragBaseUrl;
    }
    return _ragUrl;
  }

  Future<PickedLegalDocument?> pickDocument() async {
    final picked = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: _allowedExtensions,
      withData: true,
    );

    if (picked == null || picked.files.isEmpty) {
      return null;
    }

    final file = picked.files.first;
    if (file.bytes == null || file.bytes!.isEmpty) {
      throw Exception('Khong doc duoc noi dung file ${file.name}.');
    }

    return PickedLegalDocument(
      fileName: file.name,
      fileBytes: file.bytes!,
    );
  }

  Future<LegalIngestResult> uploadGlobalDoc({
    Map<String, String?> metadata = const {},
    PickedLegalDocument? pickedFile,
  }) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$_baseUrl/upload-global-doc'),
      );

      for (final entry in metadata.entries) {
        final value = (entry.value ?? '').trim();
        if (value.isNotEmpty) {
          request.fields[entry.key] = value;
        }
      }
      request.fields.putIfAbsent('uploaded_by', () => 'admin');
      if (pickedFile != null) {
        request.files.add(
          http.MultipartFile.fromBytes(
            'file',
            pickedFile.fileBytes,
            filename: pickedFile.fileName,
          ),
        );
      }

      final streamedResponse = await request.send();
      final response = await http.Response.fromStream(streamedResponse);
      final dynamic decoded = jsonDecode(utf8.decode(response.bodyBytes));
      final Map<String, dynamic> payload = decoded is Map<String, dynamic>
          ? decoded
          : <String, dynamic>{};

      if ((response.statusCode == 200 || response.statusCode == 201) && payload['success'] == true) {
        return LegalIngestResult(
          success: true,
          message: payload['message']?.toString() ?? 'Tai lieu da duoc lap chi muc thanh cong.',
          chunksIndexed: (payload['chunks_indexed'] ?? 0) as int,
          sectionsCount: (payload['sections_count'] ?? 0) as int,
          fileName: payload['filename']?.toString() ?? pickedFile?.fileName,
          title: payload['title']?.toString() ?? payload['ten_van_ban']?.toString() ?? metadata['ten_van_ban']?.trim(),
          chunkingMode: payload['chunking_mode']?.toString(),
        );
      }

      return LegalIngestResult(
        success: false,
        message: payload['detail']?.toString() ??
            payload['error']?.toString() ??
            'Global doc upload loi (${response.statusCode}).',
        fileName: pickedFile?.fileName,
      );
    } catch (e) {
      return LegalIngestResult(
        success: false,
        message: 'Khong the ket noi RAG upload global doc: $e',
        fileName: pickedFile?.fileName,
      );
    }
  }
}
