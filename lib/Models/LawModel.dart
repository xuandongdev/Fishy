class LawModel {
  /// Schema: vanbanphapluat
  /// - sohieuvanban (PK)
  /// - tenvanban
  /// - trangthai (TEXT)  -> "Còn hiệu lực" | "Hết hiệu lực"
  /// - ngayky (DATE)
  /// - ngaycohieuluc (DATE)
  /// - macoquan (INT, nullable)
  /// - maloai (INT, nullable)

  final String sohieu;
  final String ten;
  final String trangthai;
  final DateTime ngayKy;
  final DateTime ngayCoHieuLuc;
  final int? macoquan;
  final int? maloai;

  LawModel({
    required this.sohieu,
    required this.ten,
    required this.trangthai,
    required this.ngayKy,
    required this.ngayCoHieuLuc,
    this.macoquan,
    this.maloai,
  });

  factory LawModel.fromMap(Map<String, dynamic> map) {
    final ngayKyRaw = map['ngayky'];
    final ngayHLRaw = map['ngaycohieuluc'];

    DateTime parseDate(dynamic v) {
      if (v == null) return DateTime.fromMillisecondsSinceEpoch(0);
      if (v is DateTime) return v;
      return DateTime.parse(v.toString());
    }

    return LawModel(
      sohieu: (map['sohieuvanban'] ?? '').toString(),
      ten: (map['tenvanban'] ?? '').toString(),
      trangthai: (map['trangthai'] ?? '').toString(),
      ngayKy: parseDate(ngayKyRaw),
      ngayCoHieuLuc: parseDate(ngayHLRaw),
      macoquan: map['macoquan'] is int ? map['macoquan'] as int : int.tryParse('${map['macoquan']}'),
      maloai: map['maloai'] is int ? map['maloai'] as int : int.tryParse('${map['maloai']}'),
    );
  }

  /// Dùng cho UPDATE/INSERT
  Map<String, dynamic> toMap() {
    String toDateOnly(DateTime d) => d.toIso8601String().split('T').first;

    final m = <String, dynamic>{
      // Không bắt buộc đưa PK vào UPDATE, vì bạn eq theo sohieu rồi.
      // 'sohieuvanban': sohieu,
      'tenvanban': ten,
      'trangthai': trangthai,
      'ngayky': toDateOnly(ngayKy),
      'ngaycohieuluc': toDateOnly(ngayCoHieuLuc),
      'macoquan': macoquan,
      'maloai': maloai,
    };

    // nếu bạn không muốn ghi đè null lên DB, bật dòng dưới:
    // m.removeWhere((k, v) => v == null);

    return m;
  }
}
