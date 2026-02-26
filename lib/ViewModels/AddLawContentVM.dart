import 'dart:collection';
import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../Models/AddLawContentModel.dart';
import '../Services/EmbeddingService.dart';

class AddContentVM extends ChangeNotifier {
  final SupabaseClient supabase = Supabase.instance.client;

  // =========================
  // DATA LISTS (for dropdown/tree)
  // =========================
  List<Map<String, dynamic>> vanBanList = [];
  List<Map<String, dynamic>> chuongList = [];
  List<Map<String, dynamic>> mucList = [];
  List<Map<String, dynamic>> dieuList = [];
  List<Map<String, dynamic>> khoanList = [];
  List<Map<String, dynamic>> diemList = [];

  // =========================
  // SELECTED
  // =========================
  String? selectedSohieu;
  int? selectedChuong;
  int? selectedMuc;
  int? selectedDieu;
  int? selectedKhoan;
  int? selectedDiem;

  // =========================
  // INPUT CONTROLLERS
  // =========================
  final TextEditingController noidungController = TextEditingController();
  final TextEditingController loaiMucController = TextEditingController(); // CHUONG/MUC/DIEU/KHOAN/DIEM
  final TextEditingController kyHieuController = TextEditingController();  // CHƯƠNG I / ĐIỀU 1 / ...
  final TextEditingController thuTuController = TextEditingController();   // 1,2,3...
  final TextEditingController relaController = TextEditingController();    // "a; b; c"

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
    super.dispose();
  }

  // =========================
  // SETTERS (UI helpers)
  // =========================
  void setLoaiMuc(String? value) {
    loaiMucController.text = (value ?? '').trim().toUpperCase();
    notifyListeners();
  }

  void setSelectedSohieu(String? value) {
    selectedSohieu = value;

    // reset tree selections
    selectedChuong = null;
    selectedMuc = null;
    selectedDieu = null;
    selectedKhoan = null;
    selectedDiem = null;

    chuongList = [];
    mucList = [];
    dieuList = [];
    khoanList = [];
    diemList = [];

    if (value != null) {
      fetchChuong(value);
    }
    notifyListeners();
  }

  void setSelectedChuong(int? value) {
    selectedChuong = value;

    selectedMuc = null;
    selectedDieu = null;
    selectedKhoan = null;
    selectedDiem = null;

    mucList = [];
    dieuList = [];
    khoanList = [];
    diemList = [];

    if (value != null) {
      fetchMuc(value);
      // Điều có thể nằm trực tiếp dưới Chương (khi không có Mục)
      fetchDieu(null, value);
    }
    notifyListeners();
  }

  void setSelectedMuc(int? value) {
    selectedMuc = value;

    selectedDieu = null;
    selectedKhoan = null;
    selectedDiem = null;

    dieuList = [];
    khoanList = [];
    diemList = [];

    if (selectedChuong != null) {
      fetchDieu(value, selectedChuong!);
    }
    notifyListeners();
  }

  void setSelectedDieu(int? value) {
    selectedDieu = value;

    selectedKhoan = null;
    selectedDiem = null;

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

  // =========================
  // FETCH
  // =========================
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
          .order('thu_tu', ascending: true)
          .order('sothutund', ascending: true);

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
          .order('thu_tu', ascending: true)
          .order('sothutund', ascending: true);

      mucList = List<Map<String, dynamic>>.from(res);
      notifyListeners();
    } catch (e) {
      debugPrint('fetchMuc error: $e');
    }
  }

  Future<void> fetchDieu(int? mucId, int chuongId) async {
    try {
      final parentId = mucId ?? chuongId;
      final res = await supabase
          .from('noidung')
          .select()
          .eq('sothutund_cha', parentId)
          .order('thu_tu', ascending: true)
          .order('sothutund', ascending: true);

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
          .order('thu_tu', ascending: true)
          .order('sothutund', ascending: true);

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
          .order('thu_tu', ascending: true)
          .order('sothutund', ascending: true);

      diemList = List<Map<String, dynamic>>.from(res);
      notifyListeners();
    } catch (e) {
      debugPrint('fetchDiem error: $e');
    }
  }

  // =========================
  // HELPERS
  // =========================
  String _normalizeLoaiMuc(String raw) {
    return raw.trim().toUpperCase();
  }

  /// Parse rela "a; b; c" -> ["a","b","c"] (trim, bỏ rỗng, bỏ trùng giữ thứ tự)
  List<String>? _parseRela(String raw) {
    final s = raw.trim();
    if (s.isEmpty) return null;

    final parts = s
        .split(';')
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();

    if (parts.isEmpty) return null;

    final set = LinkedHashSet<String>();
    for (final p in parts) {
      set.add(p);
    }
    return set.toList();
  }

  /// Tính parent đúng theo loai_muc user chọn
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
        return selectedDiem ??
            selectedKhoan ??
            selectedDieu ??
            selectedMuc ??
            selectedChuong;
    }
  }

  Future<void> _updateRelaEmbedIfAny(int sothutund, List<String>? relaList) async {
    if (relaList == null || relaList.isEmpty) return;

    final joined = relaList.join('; ');
    final vec = await EmbeddingService.generateEmbedding(joined);

    await supabase.from('noidung').update({
      'rela_embed': vec,
    }).eq('sothutund', sothutund);
  }

  Future<void> _refreshAfterInsert({
    required String sohieu,
    required String loaiMuc,
    required int newId,
  }) async {
    final type = _normalizeLoaiMuc(loaiMuc);

    if (type == 'DIEM') {
      if (selectedKhoan != null) {
        await fetchDiem(selectedKhoan!);
        selectedDiem = newId;
      } else {
        await fetchChuong(sohieu);
      }
      return;
    }

    if (type == 'KHOAN') {
      if (selectedDieu != null) {
        await fetchKhoan(selectedDieu!);
        selectedKhoan = newId;
      } else {
        await fetchChuong(sohieu);
      }
      return;
    }

    if (type == 'DIEU') {
      if (selectedChuong != null) {
        await fetchDieu(selectedMuc, selectedChuong!);
        selectedDieu = newId;
      } else {
        await fetchChuong(sohieu);
      }
      return;
    }

    if (type == 'MUC') {
      if (selectedChuong != null) {
        await fetchMuc(selectedChuong!);
        selectedMuc = newId;
      } else {
        await fetchChuong(sohieu);
      }
      return;
    }

    // CHUONG (hoặc default)
    await fetchChuong(sohieu);
    selectedChuong = newId;
  }

  // =========================
  // ADD CONTENT
  // =========================
  Future<bool> addContent() async {
    final sohieu = selectedSohieu;
    final noiDung = noidungController.text.trim();
    final loaiMuc = _normalizeLoaiMuc(loaiMucController.text);
    final kyHieu = kyHieuController.text.trim();
    final thuTu = int.tryParse(thuTuController.text.trim());
    final relaList = _parseRela(relaController.text);

    if (sohieu == null || sohieu.isEmpty) {
      debugPrint('Chưa chọn số hiệu văn bản.');
      return false;
    }
    if (noiDung.isEmpty) {
      debugPrint('Nội dung rỗng.');
      return false;
    }
    if (loaiMuc.isEmpty) {
      debugPrint('Chưa chọn loai_muc.');
      return false;
    }
    if (thuTu == null) {
      debugPrint('thu_tu không hợp lệ.');
      return false;
    }

    // Parent bắt theo type
    final parentId = _parentIdForType(loaiMuc);

    // Validate parent theo type (đỡ insert sai cây)
    if (loaiMuc == 'MUC' && selectedChuong == null) {
      debugPrint('Muốn thêm MỤC cần chọn CHƯƠNG.');
      return false;
    }
    if (loaiMuc == 'DIEU' && (selectedChuong == null && selectedMuc == null)) {
      debugPrint('Muốn thêm ĐIỀU cần chọn CHƯƠNG (và có thể chọn MỤC).');
      return false;
    }
    if (loaiMuc == 'KHOAN' && selectedDieu == null) {
      debugPrint('Muốn thêm KHOẢN cần chọn ĐIỀU.');
      return false;
    }
    if (loaiMuc == 'DIEM' && selectedKhoan == null) {
      debugPrint('Muốn thêm ĐIỂM cần chọn KHOẢN.');
      return false;
    }

    isLoading = true;
    notifyListeners();

    try {
      final content = AddLawContentModel(
        sohieu: sohieu,
        noidung: noiDung,
        sothutundCha: parentId,
        loaiMuc: loaiMuc,
        kyHieu: kyHieu.isEmpty ? null : kyHieu,
        thuTu: thuTu,
        rela: relaList,
      );

      final res = await supabase.from('noidung').insert(content.toMap()).select();
      final newRow = List<Map<String, dynamic>>.from(res).first;

      final int newId = newRow['sothutund'] as int;
      final String insertedText = (newRow['noidung'] ?? '').toString();

      // Clear inputs (giữ loai_muc để nhập nhanh nếu muốn)
      noidungController.clear();
      kyHieuController.clear();
      thuTuController.clear();
      relaController.clear();

      // 1) Embed nội dung -> update embedding
      await EmbeddingService.generateAndUpdateOneEmbedding(newId, insertedText);

      // 2) Embed rela (nếu có) -> update rela_embed
      await _updateRelaEmbedIfAny(newId, relaList);

      // Refresh lists theo type
      await _refreshAfterInsert(sohieu: sohieu, loaiMuc: loaiMuc, newId: newId);

      notifyListeners();
      return true;
    } catch (e) {
      debugPrint('addContent error: $e');
      return false;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }
}
