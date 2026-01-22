
import 'package:flutter/cupertino.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import '../Models/LawModel.dart';
import '../Models/LawContentModel.dart';

class LawViewModel extends ChangeNotifier {
  final List<LawModel> _vanBan = [];
  bool _isLoading = false;

  List<LawModel> get vanBan => _vanBan;
  bool get isLoading => _isLoading;

  Future<void> fetchVanBan() async {
    _isLoading = true;
    notifyListeners();
    try {
      final response = await Supabase.instance.client
          .from('vanbanphapluat')
          .select()
          .order('ngayky', ascending: false);

      print("DEBUG - Dữ liệu trả về: $response");

      _vanBan.clear();
      _vanBan.addAll(
        response.map((e) => LawModel.fromMap(e)),
      );
    } catch (e) {
      print("Lỗi fetchVanBans: $e");
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> updateTrangThai(String sohieu, int newTrangThai) async {
    try {
      await Supabase.instance.client
          .from('vanbanphapluat')
          .update({'matrangthai': newTrangThai})
          .eq('sohieuvanban', sohieu);
      await fetchVanBan();
    } catch (e) {
      print("Lỗi khi cập nhật trạng thái: $e");
    }
  }

  Future<void> updateVanBan(LawModel vb) async {
    try{
      await Supabase.instance.client
          .from('vanbanphapluat')
          .update(vb.toMap())
          .eq('sohieuvanban', vb.sohieu);

      await fetchVanBan();
    }catch(e){
      print("Lỗi khi cập nhật văn bản: $e");
    }finally{
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<List<LawContentModel>> fetchNoiDungSoHieu(String sohieu) async {
    try {
      final response = await Supabase.instance.client
          .from('noidung')
          .select()
          .eq('sohieu', sohieu)
          .order('sothutund', ascending: true);

      return (response as List).map((e) => LawContentModel.fromMap(e)).toList();
    } catch (e) {
      print("Lỗi fetchNoiDungBySohieu: $e");
      return [];
    }
  }

  Future<LawContentModel?> updateLawContent(
      int sothutund,
      String noidung, {
        int? modifiedBy,
      }) async {
    try {
      final updateData = {
        'noidung': noidung,
        'modified_by': modifiedBy,
        'modified_at': DateTime.now().toUtc().toIso8601String(),
      };

      await Supabase.instance.client
          .from('noidung')
          .update(updateData)
          .eq('sothutund', sothutund);

      _isLoading = true;
      notifyListeners();

      final response = await Supabase.instance.client
          .from('noidung')
          .select()
          .eq('sothutund', sothutund)
          .single();

      return LawContentModel.fromMap(response);
    } catch (e) {
      print("Lỗi updateLawContent: $e");
      return null;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<LawContentModel?> fetchContentWithEditor(int sothutund) async {
    try {
      final response = await Supabase.instance.client
          .from('noidung')
          .select('sothutund, noidung, modified_by, modified_at, nguoidung(hoten)')
          .eq('sothutund', sothutund)
          .single();

      print("DEBUG - Dữ liệu trả về: $response");
      return LawContentModel.fromMap(response);
    } catch (e) {
      print("Lỗi khi lấy nội dung với người chỉnh sửa: $e");
      return null;
    }
  }
}