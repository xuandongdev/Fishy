import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:fishy/Models/AddLawModel.dart';

class AddLawVM extends ChangeNotifier {
  final SupabaseClient supabase = Supabase.instance.client;

  List<Map<String, dynamic>> coQuanList = [];
  List<Map<String, dynamic>> loaiVanBanList = [];
  List<Map<String, dynamic>> trangThaiList = [];

  int? selectedCoQuan;
  int? selectedLoaiVanBan;
  int? selectedTrangThai;

  AddLawVM() {
    _fetchDropdownData();
  }

  Future<void> _fetchDropdownData() async {
    try {
      final coQuanResponse = await supabase.from('coquanbanhanh').select();
      final loaiVanBanResponse = await supabase.from('loaivanban').select();
      final trangThaiResponse = await supabase.from('trangthai').select();

      coQuanList = List<Map<String, dynamic>>.from(coQuanResponse);
      loaiVanBanList = List<Map<String, dynamic>>.from(loaiVanBanResponse);
      trangThaiList = List<Map<String, dynamic>>.from(trangThaiResponse);

      notifyListeners();
    } catch (e) {
      print('Lỗi tải dữ liệu dropdown: $e');
    }
  }

  Future<bool> addLaw(AddLawModel law) async {
    try {
      await supabase.from('vanbanphapluat').insert(law.toMap());
      return true;
    } catch (e) {
      print('Lỗi khi thêm luật: $e');
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

  void setSelectedTrangThai(int? value) {
    selectedTrangThai = value;
    notifyListeners();
  }
}

