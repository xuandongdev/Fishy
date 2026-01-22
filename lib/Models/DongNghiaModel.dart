class DongNghia
{
  final String tuKhoa;
  final List<String> dongNghia;

  DongNghia({required this.tuKhoa, required this.dongNghia});

  Map<String, dynamic> toMap()
  {
    return{
      'tuKhoa': tuKhoa,
      'dong_nghia': dongNghia
    };
  }
}