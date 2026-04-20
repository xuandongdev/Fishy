import 'dart:collection';

import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:flutter/material.dart';

import '../Models/AddLawContentModel.dart';
import '../Services/EmbeddingService.dart';
import '../Services/LegalIngestService.dart';

class AddContentVM extends ChangeNotifier {
  final SupabaseClient supabase = Supabase.instance.client;
  final LegalIngestService _legalIngestService = LegalIngestService();

  List<Map<String, dynamic>> vanBanList = [];
  List<Map<String, dynamic>> chuongList = [];
  List<Map<String, dynamic>> mucList = [];
  List<Map<String, dynamic>> dieuList = [];
  List<Map<String, dynamic>> khoanList = [];
  List<Map<String, dynamic>> diemList = [];

  String? selectedSohieu;
  int? selectedChuong;
  int? selectedMuc;
  int? selectedDieu;
  int? selectedKhoan;
  int? selectedDiem;

  PickedLegalDocument? selectedFile;
  String? selectedFileName;
  String? lastIngestMessage;

  final TextEditingController noidungController = TextEditingController();
  final TextEditingController loaiMucController = TextEditingController();
  final TextEditingController kyHieuController = TextEditingController();
  final TextEditingController thuTuController = TextEditingController();
  final TextEditingController relaController = TextEditingController();
  final TextEditingController minKmController = TextEditingController();
  final TextEditingController maxKmController = TextEditingController();

  bool isLoading = false;

  AddContentVM() {
    fetchVanBan();
  }

  @override
  void dispose() {
    noidungController.dispose();
    loaiMucController.dispose();
    kyHieuController.dispose();
    thuTuController.dispose();
    relaController.dispose();
    minKmController.dispose();
    maxKmController.dispose();
    super.dispose();
  }

  void setLoaiMuc(String? value) {
    loaiMucController.text = (value ?? '').trim().toUpperCase();
    notifyListeners();
  }

  void setSelectedSohieu(String? value) {
    selectedSohieu = value;
    selectedChuong = selectedMuc = selectedDieu = selectedKhoan = selectedDiem = null;
    chuongList = [];
    mucList = [];
    dieuList = [];
    khoanList = [];
    diemList = [];
    if (value != null) fetchChuong(value);
    notifyListeners();
  }

  void setSelectedChuong(int? value) {
    selectedChuong = value;
    selectedMuc = selectedDieu = selectedKhoan = selectedDiem = null;
    mucList = [];
    dieuList = [];
    khoanList = [];
    diemList = [];
    if (value != null) {
      fetchMuc(value);
      fetchDieu(null, value);
    }
    notifyListeners();
  }

  void setSelectedMuc(int? value) {
    selectedMuc = value;
    selectedDieu = selectedKhoan = selectedDiem = null;
    dieuList = [];
    khoanList = [];
    diemList = [];
    if (selectedChuong != null) fetchDieu(value, selectedChuong!);
    notifyListeners();
  }

  void setSelectedDieu(int? value) {
    selectedDieu = value;
    selectedKhoan = selectedDiem = null;
    khoanList = [];
    diemList = [];
    if (value != null) fetchKhoan(value);
    notifyListeners();
  }

  void setSelectedKhoan(int? value) {
    selectedKhoan = value;
    selectedDiem = null;
    diemList = [];
    if (value != null) fetchDiem(value);
    notifyListeners();
  }

  void setSelectedDiem(int? value) {
    selectedDiem = value;
    notifyListeners();
  }

  Future<void> fetchVanBan() async {
    try {
      final res = await supabase
          .from('vanbanphapluat')
          .select('sohieuvanban, tenvanban')
          .order('sohieuvanban', ascending: true);
      vanBanList = List<Map<String, dynamic>>.from(res);
      notifyListeners();
    } catch (e) {
      debugPrint('fetchVanBan error: $e');
    }
  }

  Future<void> fetchChuong(String sohieu) async {
    try {
      final res = await supabase
          .from('noidung')
          .select()
          .eq('sohieu', sohieu)
          .filter('sothutund_cha', 'is', null)
          .order('thu_tu', ascending: true);
      chuongList = List<Map<String, dynamic>>.from(res);
      notifyListeners();
    } catch (e) {
      debugPrint('fetchChuong error: $e');
    }
  }

  Future<void> fetchMuc(int chuongId) async {
    try {
      final res = await supabase
          .from('noidung')
          .select()
          .eq('sothutund_cha', chuongId)
          .order('thu_tu', ascending: true);
      mucList = List<Map<String, dynamic>>.from(res);
      notifyListeners();
    } catch (e) {
      debugPrint('fetchMuc error: $e');
    }
  }

  Future<void> fetchDieu(int? mucId, int chuongId) async {
    try {
      final res = await supabase
          .from('noidung')
          .select()
          .eq('sothutund_cha', mucId ?? chuongId)
          .order('thu_tu', ascending: true);
      dieuList = List<Map<String, dynamic>>.from(res);
      notifyListeners();
    } catch (e) {
      debugPrint('fetchDieu error: $e');
    }
  }

  Future<void> fetchKhoan(int dieuId) async {
    try {
      final res = await supabase
          .from('noidung')
          .select()
          .eq('sothutund_cha', dieuId)
          .order('thu_tu', ascending: true);
      khoanList = List<Map<String, dynamic>>.from(res);
      notifyListeners();
    } catch (e) {
      debugPrint('fetchKhoan error: $e');
    }
  }

  Future<void> fetchDiem(int khoanId) async {
    try {
      final res = await supabase
          .from('noidung')
          .select()
          .eq('sothutund_cha', khoanId)
          .order('thu_tu', ascending: true);
      diemList = List<Map<String, dynamic>>.from(res);
      notifyListeners();
    } catch (e) {
      debugPrint('fetchDiem error: $e');
    }
  }

  Future<void> pickLegalFile() async {
    try {
      final picked = await _legalIngestService.pickDocument();
      if (picked != null) {
        selectedFile = picked;
        selectedFileName = picked.fileName;
        lastIngestMessage = null;
        notifyListeners();
      }
    } catch (e) {
      debugPrint('pickLegalFile error: $e');
    }
  }

  Future<bool> ingestSelectedFile() async {
    if (selectedSohieu == null || selectedSohieu!.trim().isEmpty || selectedFile == null) {
      lastIngestMessage = 'Vui lòng chọn số hiệu văn bản và file trước khi ingest';
      notifyListeners();
      return false;
    }

    isLoading = true;
    lastIngestMessage = null;
    notifyListeners();

    try {
      final result = await _legalIngestService.uploadGlobalDoc(
        metadata: {
          'so_hieu': selectedSohieu!.trim(),
          'uploaded_by': 'admin',
        },
        pickedFile: selectedFile,
      );

      if (result.success) {
        lastIngestMessage = 'Ingest thành công. Chunks: ${result.chunksIndexed}. Sections: ${result.sectionsCount}';
        selectedFile = null;
        selectedFileName = null;
        return true;
      }

      lastIngestMessage = result.message ?? 'Ingest file thất bại';
      return false;
    } catch (e) {
      debugPrint('ingestSelectedFile error: $e');
      lastIngestMessage = 'Ingest file thất bại: $e';
      return false;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  String _normalizeLoaiMuc(String raw) => raw.trim().toUpperCase();

  List<String>? _parseRela(String raw) {
    final s = raw.trim();
    if (s.isEmpty) return null;
    final parts = s
        .split(';')
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
    return parts.isEmpty ? null : LinkedHashSet<String>.from(parts).toList();
  }

  int? _parentIdForType(String type) {
    switch (type) {
      case 'CHUONG':
        return null;
      case 'MUC':
        return selectedChuong;
      case 'DIEU':
        return selectedMuc ?? selectedChuong;
      case 'KHOAN':
        return selectedDieu;
      case 'DIEM':
        return selectedKhoan;
      default:
        return selectedDiem ?? selectedKhoan ?? selectedDieu ?? selectedMuc ?? selectedChuong;
    }
  }

  Future<bool> addContent() async {
    final sohieu = selectedSohieu;
    final noiDung = noidungController.text.trim();
    final loaiMuc = _normalizeLoaiMuc(loaiMucController.text);
    final kyHieu = kyHieuController.text.trim();
    final thuTu = int.tryParse(thuTuController.text.trim());
    final relaList = _parseRela(relaController.text);
    final minKmValue = double.tryParse(minKmController.text.trim());
    final maxKmValue = double.tryParse(maxKmController.text.trim());

    if (sohieu == null || noiDung.isEmpty || loaiMuc.isEmpty || thuTu == null) {
      return false;
    }

    isLoading = true;
    notifyListeners();

    try {
      final content = AddLawContentModel(
        sohieu: sohieu,
        noidung: noiDung,
        sothutundCha: _parentIdForType(loaiMuc),
        loaiMuc: loaiMuc,
        kyHieu: kyHieu.isEmpty ? null : kyHieu,
        thuTu: thuTu,
        rela: relaList,
        minKm: minKmValue,
        maxKm: maxKmValue,
      );

      final res = await supabase.from('noidung').insert(content.toMap()).select();
      final newId = (List<Map<String, dynamic>>.from(res).first)['sothutund'] as int;

      noidungController.clear();
      kyHieuController.clear();
      thuTuController.clear();
      relaController.clear();
      minKmController.clear();
      maxKmController.clear();

      await EmbeddingService.generateAndUpdateOneEmbedding(newId, noiDung);
      if (relaList != null) {
        final vec = await EmbeddingService.generateEmbedding(relaList.join('; '));
        await supabase.from('noidung').update({'rela_embed': vec}).eq('sothutund', newId);
      }

      await _refreshAfterInsert(sohieu: sohieu, loaiMuc: loaiMuc, newId: newId);
      return true;
    } catch (e) {
      debugPrint('addContent error: $e');
      return false;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<void> _refreshAfterInsert({
    required String sohieu,
    required String loaiMuc,
    required int newId,
  }) async {
    final type = _normalizeLoaiMuc(loaiMuc);
    if (type == 'DIEM' && selectedKhoan != null) {
      await fetchDiem(selectedKhoan!);
      selectedDiem = newId;
    } else if (type == 'KHOAN' && selectedDieu != null) {
      await fetchKhoan(selectedDieu!);
      selectedKhoan = newId;
    } else if (type == 'DIEU' && selectedChuong != null) {
      await fetchDieu(selectedMuc, selectedChuong!);
      selectedDieu = newId;
    } else if (type == 'MUC' && selectedChuong != null) {
      await fetchMuc(selectedChuong!);
      selectedMuc = newId;
    } else {
      await fetchChuong(sohieu);
      selectedChuong = newId;
    }
  }
}
