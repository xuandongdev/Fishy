import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import '../Models/AddLawModel.dart';

class AddLawVM extends ChangeNotifier {
  final SupabaseClient supabase = Supabase.instance.client;

  List<Map<String, dynamic>> coQuanList = [];
  List<Map<String, dynamic>> loaiVanBanList = [];

  int? selectedCoQuan;
  int? selectedLoaiVanBan;

  // ✅ 2 option cố định IN HOA
  final List<String> trangThaiOptions = const [
    'CÒN HIỆU LỰC',
    'HẾT HIỆU LỰC',
  ];

  String? selectedTrangThai;

  AddLawVM() {
    fetchDropdownData();
    // default trạng thái
    selectedTrangThai = trangThaiOptions.first;
  }

  Future<void> fetchDropdownData() async {
    try {
      final coQuanResponse = await supabase.from('coquanbanhanh').select();
      final loaiVanBanResponse = await supabase.from('loaivanban').select();

      coQuanList = List<Map<String, dynamic>>.from(coQuanResponse);
      loaiVanBanList = List<Map<String, dynamic>>.from(loaiVanBanResponse);

      notifyListeners();
    } catch (e) {
      debugPrint('Lỗi tải dropdown: $e');
    }
  }

  Future<bool> addLaw(AddLawModel law) async {
    try {
      await supabase.from('vanbanphapluat').insert(law.toMap());
      return true;
    } catch (e) {
      debugPrint('Lỗi khi thêm văn bản: $e');
      return false;
    }
  }

  void setSelectedCoQuan(int? value) {
    selectedCoQuan = value;
    notifyListeners();
  }

  void setSelectedLoaiVanBan(int? value) {
    selectedLoaiVanBan = value;
    notifyListeners();
  }

  void setSelectedTrangThai(String? value) {
    selectedTrangThai = value;
    notifyListeners();
  }
}
