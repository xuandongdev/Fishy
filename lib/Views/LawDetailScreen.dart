import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../Models/LawContentModel.dart';
import '../Models/LawModel.dart';
import '../ViewModels/LawVM.dart';

class LawDetailScreen extends StatefulWidget {
  final LawModel law;

  const LawDetailScreen({super.key, required this.law});

  @override
  State<LawDetailScreen> createState() => _LawDetailScreenState();
}

class _LawDetailScreenState extends State<LawDetailScreen> {
  static const String TT_CON = 'CÒN HIỆU LỰC';
  static const String TT_HET = 'HẾT HIỆU LỰC';

  final _formKey = GlobalKey<FormState>();

  late TextEditingController _sohieuController;
  late TextEditingController _tenController;

  DateTime? _ngayKy;
  DateTime? _ngayCoHieuLuc;
  String? _trangThai;

  @override
  void initState() {
    super.initState();
    _sohieuController = TextEditingController(text: widget.law.sohieu);
    _tenController = TextEditingController(text: widget.law.ten);
    _ngayKy = widget.law.ngayKy;
    _ngayCoHieuLuc = widget.law.ngayCoHieuLuc;
    _trangThai = widget.law.trangthai;
    if (_trangThai != TT_CON && _trangThai != TT_HET) {
      _trangThai = TT_CON;
    }
  }

  @override
  void dispose() {
    _sohieuController.dispose();
    _tenController.dispose();
    super.dispose();
  }

  String _fmt(DateTime d) => DateFormat('yyyy-MM-dd').format(d);

  Future<void> _pickDate(BuildContext context, bool isNgayKy) async {
    final now = DateTime.now();
    final initialDate = isNgayKy ? (_ngayKy ?? now) : (_ngayCoHieuLuc ?? now);

    final picked = await showDatePicker(
      context: context,
      initialDate: initialDate,
      firstDate: DateTime(1900),
      lastDate: DateTime(2100),
    );

    if (picked != null) {
      setState(() {
        if (isNgayKy) {
          _ngayKy = picked;
        } else {
          _ngayCoHieuLuc = picked;
        }
      });
    }
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate() ||
        _ngayKy == null ||
        _ngayCoHieuLuc == null ||
        _trangThai == null) {
      return;
    }

    final newLaw = LawModel(
      sohieu: _sohieuController.text.trim(),
      ten: _tenController.text.trim(),
      ngayKy: _ngayKy!,
      ngayCoHieuLuc: _ngayCoHieuLuc!,
      trangthai: _trangThai!,
      macoquan: widget.law.macoquan,
      maloai: widget.law.maloai,
    );

    final lawVM = Provider.of<LawViewModel>(context, listen: false);

    try {
      await lawVM.updateVanBan(newLaw);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Cập nhật thành công!'), backgroundColor: Colors.green),
      );
      Navigator.pop(context, true);
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Cập nhật thất bại!'), backgroundColor: Colors.red),
      );
    }
  }

  Future<void> _editManualContent(LawContentModel content) async {
    final controller = TextEditingController(text: content.noidung);
    final lawVM = Provider.of<LawViewModel>(context, listen: false);

    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Chỉnh sửa nội dung thủ công'),
        content: TextField(
          controller: controller,
          maxLines: 8,
          decoration: const InputDecoration(border: OutlineInputBorder()),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Hủy'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Lưu'),
          ),
        ],
      ),
    );

    if (ok == true) {
      final updated = await lawVM.updateLawContent(content.sothutund, controller.text.trim());
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(updated != null ? 'Cập nhật nội dung thành công' : 'Cập nhật nội dung thất bại'),
          backgroundColor: updated != null ? Colors.green : Colors.red,
        ),
      );
      setState(() {});
    }
  }

  Future<void> _editNoiDung2(Map<String, dynamic> row) async {
    final controller = TextEditingController(text: (row['noidung'] ?? '').toString());
    final lawVM = Provider.of<LawViewModel>(context, listen: false);

    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Chỉnh sửa nội dung ingest file'),
        content: TextField(
          controller: controller,
          maxLines: 8,
          decoration: const InputDecoration(border: OutlineInputBorder()),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Hủy'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Lưu'),
          ),
        ],
      ),
    );

    if (ok == true) {
      final updated = await lawVM.updateNoiDung2Content(row['sothutund'] as int, controller.text.trim());
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(updated ? 'Cập nhật nội dung ingest thành công' : 'Cập nhật nội dung ingest thất bại'),
          backgroundColor: updated ? Colors.green : Colors.red,
        ),
      );
      setState(() {});
    }
  }

  @override
  Widget build(BuildContext context) {
    const statusOptions = [TT_CON, TT_HET];

    return Scaffold(
      appBar: AppBar(title: const Text('Chi tiết văn bản')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: ListView(
          children: [
            Text(
              'Số hiệu văn bản: ${_sohieuController.text}',
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            const SizedBox(height: 20),
            Form(
              key: _formKey,
              child: Column(
                children: [
                  TextFormField(
                    controller: _tenController,
                    decoration: const InputDecoration(labelText: 'Tên văn bản'),
                    validator: (v) => (v == null || v.trim().isEmpty) ? 'Không được để trống' : null,
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    value: _trangThai,
                    decoration: const InputDecoration(
                      labelText: 'Trạng thái',
                      border: OutlineInputBorder(),
                    ),
                    items: statusOptions
                        .map((s) => DropdownMenuItem(value: s, child: Text(s)))
                        .toList(),
                    onChanged: (v) => setState(() => _trangThai = v),
                    validator: (v) {
                      if (v == null) return 'Bắt buộc chọn trạng thái';
                      if (v != TT_CON && v != TT_HET) return 'Trạng thái không hợp lệ';
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),
                  ListTile(
                    title: Text(_ngayKy == null ? 'Chọn ngày ký' : 'Ngày ký: ${_fmt(_ngayKy!)}'),
                    trailing: const Icon(Icons.calendar_today),
                    onTap: () => _pickDate(context, true),
                  ),
                  ListTile(
                    title: Text(_ngayCoHieuLuc == null
                        ? 'Chọn ngày hiệu lực'
                        : 'Ngày hiệu lực: ${_fmt(_ngayCoHieuLuc!)}'),
                    trailing: const Icon(Icons.calendar_today),
                    onTap: () => _pickDate(context, false),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            const SizedBox(height: 8),
            FutureBuilder<List<LawContentModel>>(
              future: Provider.of<LawViewModel>(context, listen: false)
                  .fetchNoiDungSoHieu(widget.law.sohieu),
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snapshot.hasError) {
                  return const Center(child: Text('Lỗi khi tải nội dung'));
                }
                final noidungList = snapshot.data ?? [];
                if (noidungList.isEmpty) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: Text('Không có nội dung'),
                  );
                }

                return ListView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: noidungList.length,
                  itemBuilder: (context, index) {
                    final noidung = noidungList[index];
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: InkWell(
                        onTap: () => _editManualContent(noidung),
                        child: Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: Colors.grey[200],
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(noidung.noidung, style: const TextStyle(fontSize: 16)),
                        ),
                      ),
                    );
                  },
                );
              },
            ),
            const SizedBox(height: 24),
            const Text(
              'Nội dung đã thêm file',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            FutureBuilder<List<Map<String, dynamic>>>(
              future: Provider.of<LawViewModel>(context, listen: false)
                  .fetchNoiDung2SoHieu(widget.law.sohieu),
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snapshot.hasError) {
                  return const Center(child: Text('Lỗi khi tải nội dung'));
                }
                final rows = snapshot.data ?? [];
                if (rows.isEmpty) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: Text('Không có nội dung'),
                  );
                }

                return ListView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: rows.length,
                  itemBuilder: (context, index) {
                    final row = rows[index];
                    final kyHieu = (row['ky_hieu'] ?? '').toString();
                    final sectionPath = (row['section_path'] ?? '').toString();
                    final sourceFile = (row['source_file_name'] ?? '').toString();
                    final content = (row['noidung'] ?? '').toString();

                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: InkWell(
                        onTap: () => _editNoiDung2(row),
                        child: Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: Colors.blueGrey[50],
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: Colors.blueGrey.shade100),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              if (kyHieu.isNotEmpty)
                                Text(
                                  kyHieu,
                                  style: const TextStyle(fontWeight: FontWeight.bold),
                                ),
                              if (sectionPath.isNotEmpty)
                                Padding(
                                  padding: const EdgeInsets.only(top: 4),
                                  child: Text(sectionPath),
                                ),
                              if (sourceFile.isNotEmpty)
                                Padding(
                                  padding: const EdgeInsets.only(top: 4),
                                  child: Text('File: $sourceFile'),
                                ),
                              const SizedBox(height: 6),
                              Text(content, style: const TextStyle(fontSize: 16)),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          ],
        ),
      ),
      bottomNavigationBar: Padding(
        padding: const EdgeInsets.all(16),
        child: ElevatedButton.icon(
          icon: const Icon(Icons.save),
          label: const Text('Lưu'),
          onPressed: _save,
          style: ElevatedButton.styleFrom(minimumSize: const Size.fromHeight(50)),
        ),
      ),
    );
  }
}
