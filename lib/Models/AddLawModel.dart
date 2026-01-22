class AddLawModel
{
  final String sohieu;
  final String tenVanBan;
  final String ngayKy;
  final String ngayHieuLuc;
  final int matrangthai;
  final int macoquan;
  final int maloai;

  AddLawModel
  ({
    required this.sohieu,
    required this.tenVanBan,
    required this.ngayKy,
    required this.ngayHieuLuc,
    required this.matrangthai,
    required this.macoquan,
    required this.maloai,
  });

  Map<String, dynamic> toMap()
  {
    return {
      'sohieuvanban': sohieu,
      'tenvanban': tenVanBan,
      'ngayky': ngayKy,
      'ngaycohieuluc': ngayHieuLuc,
      'matrangthai': matrangthai,
      'macoquan': macoquan,
      'maloai': maloai,
    };
  }
}
