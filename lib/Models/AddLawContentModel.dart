class AddLawContentModel
{
  final String sohieu;
  final String noidung;
  final int? sothutundCha;
  final double? tocdoMin;
  final double? tocdoMax;

  AddLawContentModel(
  {
    required this.sohieu,
    required this.noidung,
    this.sothutundCha,
    this.tocdoMin,
    this.tocdoMax,
  });

  Map<String, dynamic> toMap()
  {
    return {
      'sohieu': sohieu,
      'noidung': noidung,
      'sothutund_cha': sothutundCha,
      'tocdomin': tocdoMin,
      'tocdomax': tocdoMax,
    };
  }
}
