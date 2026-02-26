class AddLawContentModel {
  final String sohieu;
  final String noidung;
  final int? sothutundCha;

  final String? loaiMuc;
  final String? kyHieu;
  final int? thuTu;

  final List<String>? rela; // text[]

  AddLawContentModel({
    required this.sohieu,
    required this.noidung,
    this.sothutundCha,
    this.loaiMuc,
    this.kyHieu,
    this.thuTu,
    this.rela,
  });

  Map<String, dynamic> toMap() {
    final m = <String, dynamic>{
      'sohieu': sohieu,
      'noidung': noidung,
      'sothutund_cha': sothutundCha,
      'loai_muc': loaiMuc,
      'ky_hieu': kyHieu,
      'thu_tu': thuTu,
      'rela': rela,
    };

    m.removeWhere((k, v) => v == null);
    return m;
  }
}
