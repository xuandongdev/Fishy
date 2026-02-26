class YoloBox {
  final double x1, y1, x2, y2, conf;
  final String name;
  YoloBox({
    required this.x1, required this.y1, required this.x2, required this.y2,
    required this.conf, required this.name,
  });

  factory YoloBox.fromJson(Map<String, dynamic> j) => YoloBox(
    x1: (j['x1'] as num).toDouble(),
    y1: (j['y1'] as num).toDouble(),
    x2: (j['x2'] as num).toDouble(),
    y2: (j['y2'] as num).toDouble(),
    conf: (j['conf'] as num).toDouble(),
    name: (j['name'] ?? '').toString(),
  );
}
