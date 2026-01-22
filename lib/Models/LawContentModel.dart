class LawContentModel
{
  final int sothutund;
  final String noidung;
  final String? sohieu;
  final int? modified_by;
  final String? modified_by_name;
  final DateTime? modified_at;

  LawContentModel
  ({
    required this.sothutund,
    required this.noidung,
    this.sohieu,
    this.modified_by,
    this.modified_by_name,
    this.modified_at,
  });

  factory LawContentModel.fromMap(Map<String, dynamic> map)
  {
    return LawContentModel
    (
      sothutund: map['sothutund'] as int,
      noidung: map['noidung'] as String,
      modified_by: map['modified_by'] as int?,
      modified_by_name: map['nguoidung']?['hoten'],
      modified_at: map['modified_at'] != null ? DateTime.parse(map['modified_at'] as String) : null,
    );
  }

  Map<String, dynamic> toMap()
  {
    return
    {
      'sothutund': sothutund,
      'noidung': noidung,
      'sohieu': sohieu,
      'modified_by': modified_by,
      'modified_at': modified_at?.toIso8601String(),
    };
  }
}