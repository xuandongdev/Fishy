import 'package:intl/intl.dart';
class LawModel
{
  final String sohieu;
  final String ten;
  final int matrangthai;
  final DateTime ngayKy;
  final DateTime ngayCoHieuLuc;

  LawModel
  ({
    required this.sohieu,
    required this.ten,
    required this.matrangthai,
    required this.ngayKy,
    required this.ngayCoHieuLuc,
  });

  factory LawModel.fromMap(Map<String, dynamic> map)
  {
    return LawModel
    (
      sohieu: map['sohieuvanban'] ?? '',
      ten: map['tenvanban'] ?? '',
      matrangthai: map['matrangthai'] ?? 1,
      ngayKy: map['ngayky'] != null ? DateTime.parse(map['ngayky']) : DateTime.now(),
      ngayCoHieuLuc: map['ngaycohieuluc'] != null ? DateTime.parse(map['ngaycohieuluc']) : DateTime.now(),
    );
  }

  Map<String, dynamic> toMap()
  {
    final dateFormat = DateFormat('yyyy-MM-dd');
    return {
      'sohieuvanban': sohieu,
      'tenvanban': ten,
      'matrangthai': matrangthai,
      'ngayky': dateFormat.format(ngayKy),
      'ngaycohieuluc': dateFormat.format(ngayCoHieuLuc),
    };
  }
}
