import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import '../Models/AddLawContentModel.dart';
import '../Services/EmbeddingService.dart';

class AddContentVM extends ChangeNotifier {
  final SupabaseClient supabase = Supabase.instance.client;

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

  final TextEditingController noidungController = TextEditingController();
  final TextEditingController tocdoMinController = TextEditingController();
  final TextEditingController tocdoMaxController = TextEditingController();
  bool isLoading = false;

  AddContentVM() {
    fetchVanBan();
  }

  Future<void> fetchVanBan() async {
    final res = await supabase
        .from('vanbanphapluat')
        .select('sohieuvanban, tenvanban')
        .order('sohieuvanban', ascending: true);
    vanBanList = List<Map<String, dynamic>>.from(res);
    notifyListeners();
  }

  Future<void> fetchChuong(String sohieu) async {
    final res = await supabase
        .from('noidung')
        .select()
        .eq('sohieu', sohieu)
        .filter('sothutund_cha', 'is', null)
        .order('sothutund', ascending: true);

    chuongList = List<Map<String, dynamic>>.from(res);
    selectedChuong = null;
    selectedMuc = null;
    selectedDieu = null;
    selectedKhoan = null;
    selectedDiem = null;
    dieuList = [];
    notifyListeners();
  }

  Future<void> fetchMuc(int chuongId) async {
    final res = await supabase
        .from('noidung')
        .select()
        .eq('sothutund_cha', chuongId)
        .order('sothutund', ascending: true);

    mucList = List<Map<String, dynamic>>.from(res);
    selectedMuc = null;
    dieuList = [];
    khoanList = [];
    diemList = [];
    notifyListeners();
  }

  Future<void> fetchDieu(int? mucId, int chuongId) async {
    final res = await supabase
        .from('noidung')
        .select()
        .eq('sothutund_cha', mucId ?? chuongId)
        .order('sothutund', ascending: true);

    dieuList = List<Map<String, dynamic>>.from(res);
    selectedDieu = null;
    selectedKhoan = null;
    selectedDiem = null;
    khoanList = [];
    diemList = [];
    notifyListeners();
  }

  Future<void> fetchKhoan(int dieuId) async {
    final res = await supabase
        .from('noidung')
        .select()
        .eq('sothutund_cha', dieuId)
        .order('sothutund', ascending: true);

    khoanList = List<Map<String, dynamic>>.from(res);
    selectedKhoan = null;
    diemList = [];
    notifyListeners();
  }

  Future<void> fetchDiem(int khoanId) async {
    final res = await supabase
        .from('noidung')
        .select()
        .eq('sothutund_cha', khoanId)
        .order('sothutund', ascending: true);
    diemList = List<Map<String, dynamic>>.from(res);
    selectedDiem = null;
    notifyListeners();
  }

  void setSelectedSohieu(String? value) {
    selectedSohieu = value;
    if (value != null) fetchChuong(value);
    notifyListeners();
  }

  void setSelectedChuong(int? value) {
    selectedChuong = value;
    selectedMuc = null;
    selectedDieu = null;
    selectedKhoan = null;
    selectedDiem = null;
    if (value != null) fetchMuc(value);
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
    if (selectedChuong != null) fetchDieu(value, selectedChuong!);
    notifyListeners();
  }

  void setSelectedDieu(int? value) {
    selectedDieu = value;
    selectedKhoan = null;
    selectedDiem = null;
    if (value != null) fetchKhoan(value);
    notifyListeners();
  }

  void setSelectedKhoan(int? value) {
    selectedKhoan = value;
    selectedDiem = null;
    if (value != null) fetchDiem(value);
    notifyListeners();
  }

  void setSelectedDiem(int? value) {
    selectedDiem = value;
    notifyListeners();
  }

  int? getParentId() {
    if (selectedDiem != null) return selectedDiem;
    if (selectedKhoan != null) return selectedKhoan;
    if (selectedDieu != null) return selectedDieu;
    if (selectedMuc != null) return selectedMuc;
    if (selectedChuong != null) return selectedChuong;
    return null;
  }

  Future<bool> addContent() async {
    isLoading = true;
    notifyListeners();

    final content = AddLawContentModel(
      sohieu: selectedSohieu!,
      noidung: noidungController.text,
      sothutundCha: getParentId(),
      tocdoMin: tocdoMinController.text.isNotEmpty
          ? double.tryParse(tocdoMinController.text)
          : null,
      tocdoMax: tocdoMaxController.text.isNotEmpty
          ? double.tryParse(tocdoMaxController.text)
          : null,
    );

    try {
      final res =
          await supabase.from('noidung').insert(content.toMap()).select();
      noidungController.clear();
      tocdoMinController.clear();
      tocdoMaxController.clear();
      final newContent = List<Map<String, dynamic>>.from(res).first;
      final newContentId = newContent['sothutund'];

      final newNoiDung = newContent['noidung'];
      await EmbeddingService.generateAndUpdateOneEmbedding(
        newContentId,
        newNoiDung,
      );

      if (selectedDiem != null) {
        await fetchDiem(selectedKhoan!);
        if (diemList.any((element) => element['sothutund'] == newContentId)) {
          selectedDiem = newContentId;
        } else {
          selectedDiem = null;
        }
      } else if (selectedKhoan != null) {
        await fetchKhoan(selectedDieu!);
        if (khoanList.any((element) => element['sothutund'] == newContentId)) {
          selectedKhoan = newContentId;
        } else {
          selectedKhoan = null;
        }
      } else if (selectedDieu != null) {
        if (selectedChuong != null) {
          await fetchDieu(selectedMuc, selectedChuong!);
        }
        if (dieuList.any((element) => element['sothutund'] == newContentId)) {
          selectedDieu = newContentId;
        } else {
          selectedDieu = null;
        }
      } else if (selectedMuc != null) {
        await fetchMuc(selectedChuong!);
        if (mucList.any((element) => element['sothutund'] == newContentId)) {
          selectedMuc = newContentId;
        } else {
          selectedMuc = null;
        }
      } else if (selectedChuong != null) {
        await fetchChuong(selectedSohieu!);
        if (chuongList.any((element) => element['sothutund'] == newContentId)) {
          selectedChuong = newContentId;
        } else {
          selectedChuong = null;
        }
      }

      notifyListeners();
      return true;
    } catch (e) {
      print("Lỗi khi thêm nội dung: $e");
      return false;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }
}
