class LawContentModel {
  final int sothutund;
  final String noidung;
  final String? sohieu;

  final int? sothutundCha;

  final String? loaiMuc;
  final String? kyHieu;
  final int? thuTu;

  final List<String>? rela;
  final double? minKm;
  final double? maxKm;

  final int? modifiedBy;
  final String? modifiedByName;
  final DateTime? modifiedAt;

  LawContentModel({
    required this.sothutund,
    required this.noidung,
    this.sohieu,
    this.sothutundCha,
    this.loaiMuc,
    this.kyHieu,
    this.thuTu,
    this.rela,
    this.minKm,
    this.maxKm,
    this.modifiedBy,
    this.modifiedByName,
    this.modifiedAt,
  });

  // ====== ALIAS GETTERS (snake_case) để UI đang dùng không bị lỗi ======
  int? get sothutund_cha => sothutundCha;
  String? get loai_muc => loaiMuc;
  String? get ky_hieu => kyHieu;
  int? get thu_tu => thuTu;

  int? get modified_by => modifiedBy;
  String? get modified_by_name => modifiedByName;
  DateTime? get modified_at => modifiedAt;

  factory LawContentModel.fromMap(Map<String, dynamic> map) {
    // rela có thể là List<dynamic> hoặc null
    List<String>? relaList;
    final relaRaw = map['rela'];
    if (relaRaw is List) {
      relaList = relaRaw.map((e) => e.toString()).toList();
    }

    // modified_by_name lấy từ join: nguoidung(hoten)
    String? editorName;
    final nguoidung = map['nguoidung'];
    if (nguoidung is Map && nguoidung['hoten'] != null) {
      editorName = nguoidung['hoten'].toString();
    }

    // modified_at có thể là String ISO hoặc null
    DateTime? modifiedAt;
    final modifiedAtRaw = map['modified_at'];
    if (modifiedAtRaw != null) {
      modifiedAt = DateTime.tryParse(modifiedAtRaw.toString());
    }

    return LawContentModel(
      sothutund: (map['sothutund'] as num).toInt(),
      noidung: (map['noidung'] ?? '').toString(),
      sohieu: map['sohieu']?.toString(),

      sothutundCha: map['sothutund_cha'] == null ? null : (map['sothutund_cha'] as num).toInt(),

      loaiMuc: map['loai_muc']?.toString(),
      kyHieu: map['ky_hieu']?.toString(),
      thuTu: map['thu_tu'] == null ? null : (map['thu_tu'] as num).toInt(),

      rela: relaList,
      minKm: map['min_km'] == null ? null : (map['min_km'] as num).toDouble(),
      maxKm: map['max_km'] == null ? null : (map['max_km'] as num).toDouble(),

      modifiedBy: map['modified_by'] == null ? null : (map['modified_by'] as num).toInt(),
      modifiedByName: editorName,
      modifiedAt: modifiedAt,
    );
  }

  Map<String, dynamic> toMap() {
    final m = <String, dynamic>{
      'sothutund': sothutund,
      'noidung': noidung,
      'sohieu': sohieu,
      'sothutund_cha': sothutundCha,
      'loai_muc': loaiMuc,
      'ky_hieu': kyHieu,
      'thu_tu': thuTu,
      'rela': rela,
      'modified_by': modifiedBy,
      'modified_at': modifiedAt?.toUtc().toIso8601String(),
    };

    m.removeWhere((k, v) => v == null);
    return m;
  }
}
