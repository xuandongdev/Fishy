import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';

import '../Models/LawContentModel.dart';
import '../Models/LawModel.dart';
import '../ViewModels/LawVM.dart';
import 'EditContentScreen.dart';

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
  String? _trangThai; // TEXT

  @override
  void initState() {
    super.initState();
    _sohieuController = TextEditingController(text: widget.law.sohieu);
    _tenController = TextEditingController(text: widget.law.ten);
    _ngayKy = widget.law.ngayKy;
    _ngayCoHieuLuc = widget.law.ngayCoHieuLuc;
    _trangThai = widget.law.trangthai; // phải là TT_CON hoặc TT_HET
    if (_trangThai != TT_CON && _trangThai != TT_HET) {
      _trangThai = TT_CON; // fallback an toàn
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
        _trangThai == null) return;

    final newLaw = LawModel(
      sohieu: _sohieuController.text.trim(),
      ten: _tenController.text.trim(),
      ngayKy: _ngayKy!,
      ngayCoHieuLuc: _ngayCoHieuLuc!,
      trangthai: _trangThai!, // TEXT bắt buộc
      macoquan: widget.law.macoquan,
      maloai: widget.law.maloai,
    );

    final lawVM = Provider.of<LawViewModel>(context, listen: false);

    try {
      await lawVM.updateVanBan(newLaw);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Cập nhật thành công!"), backgroundColor: Colors.green),
      );
      Navigator.pop(context, true);
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Cập nhật thất bại!"), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    const statusOptions = [TT_CON, TT_HET];

    return Scaffold(
      appBar: AppBar(title: const Text("Chi tiết văn bản")),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: ListView(
          children: [
            Text(
              "Số hiệu văn bản: ${_sohieuController.text}",
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            const SizedBox(height: 20),
            Form(
              key: _formKey,
              child: Column(
                children: [
                  TextFormField(
                    controller: _tenController,
                    decoration: const InputDecoration(labelText: "Tên văn bản"),
                    validator: (v) =>
                        (v == null || v.trim().isEmpty) ? "Không được để trống" : null,
                  ),
                  const SizedBox(height: 16),

                  // ✅ bắt buộc chọn 1 trong 2 option
                  DropdownButtonFormField<String>(
                    value: _trangThai,
                    decoration: const InputDecoration(
                      labelText: "Trạng thái",
                      border: OutlineInputBorder(),
                    ),
                    items: statusOptions
                        .map((s) => DropdownMenuItem(value: s, child: Text(s)))
                        .toList(),
                    onChanged: (v) => setState(() => _trangThai = v),
                    validator: (v) {
                      if (v == null) return "Bắt buộc chọn trạng thái";
                      if (v != TT_CON && v != TT_HET) return "Trạng thái không hợp lệ";
                      return null;
                    },
                  ),

                  const SizedBox(height: 16),
                  ListTile(
                    title: Text(_ngayKy == null ? "Chọn ngày ký" : "Ngày ký: ${_fmt(_ngayKy!)}"),
                    trailing: const Icon(Icons.calendar_today),
                    onTap: () => _pickDate(context, true),
                  ),
                  ListTile(
                    title: Text(_ngayCoHieuLuc == null
                        ? "Chọn ngày hiệu lực"
                        : "Ngày hiệu lực: ${_fmt(_ngayCoHieuLuc!)}"),
                    trailing: const Icon(Icons.calendar_today),
                    onTap: () => _pickDate(context, false),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            const Text("Nội dung văn bản",
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),

            FutureBuilder<List<LawContentModel>>(
              future: Provider.of<LawViewModel>(context, listen: false)
                  .fetchNoiDungSoHieu(widget.law.sohieu),
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snapshot.hasError) {
                  return const Center(child: Text("Lỗi khi tải nội dung"));
                }
                final noidungList = snapshot.data ?? [];
                if (noidungList.isEmpty) {
                  return const Center(child: Text("Không có nội dung"));
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
                        onTap: () async {
                          final result = await Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => EditContentScreen(content: noidung)),
                          );
                          if (result == true) setState(() {});
                        },
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
          ],
        ),
      ),
      bottomNavigationBar: Padding(
        padding: const EdgeInsets.all(16),
        child: ElevatedButton.icon(
          icon: const Icon(Icons.save),
          label: const Text("Lưu"),
          onPressed: _save,
          style: ElevatedButton.styleFrom(minimumSize: const Size.fromHeight(50)),
        ),
      ),
    );
  }
}
