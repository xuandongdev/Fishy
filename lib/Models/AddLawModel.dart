class AddLawModel {
  final String sohieu;
  final String tenVanBan;
  final String ngayKy;       // yyyy-MM-dd
  final String ngayHieuLuc;  // yyyy-MM-dd
  final String trangThai;    // TEXT (lưu tentrangthai)
  final int? macoquan;
  final int? maloai;

  AddLawModel({
    required this.sohieu,
    required this.tenVanBan,
    required this.ngayKy,
    required this.ngayHieuLuc,
    required this.trangThai,
    this.macoquan,
    this.maloai,
  });

  Map<String, dynamic> toMap() {
    return {
      'sohieuvanban': sohieu,
      'tenvanban': tenVanBan,
      'trangthai': trangThai,
      'ngayky': ngayKy,
      'ngaycohieuluc': ngayHieuLuc,
      'macoquan': macoquan,
      'maloai': maloai,
    };
  }
}
