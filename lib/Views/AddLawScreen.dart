import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../Models/AddLawModel.dart';
import '../ViewModels/AddLawVM.dart';
import 'AddLawContentScreen.dart';

class AddLawScreen extends StatefulWidget {
  const AddLawScreen({super.key});

  @override
  State<AddLawScreen> createState() => _AddLawScreenState();
}

class _AddLawScreenState extends State<AddLawScreen> {
  final AddLawVM _vm = AddLawVM();

  final TextEditingController sohieuController = TextEditingController();
  final TextEditingController tenVanBanController = TextEditingController();
  final TextEditingController ngayKyController = TextEditingController();
  final TextEditingController ngayHieuLucController = TextEditingController();

  DateTime? _ngayKy;
  DateTime? _ngayHieuLuc;
  bool isLoading = false;

  @override
  void dispose() {
    sohieuController.dispose();
    tenVanBanController.dispose();
    ngayKyController.dispose();
    ngayHieuLucController.dispose();
    _vm.dispose();
    super.dispose();
  }

  Future<void> _pickDate(BuildContext context, bool isNgayKy) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.now(),
      firstDate: DateTime(1900),
      lastDate: DateTime(2100),
    );

    if (picked != null) {
      setState(() {
        if (isNgayKy) {
          _ngayKy = picked;
          ngayKyController.text = picked.toIso8601String().split('T').first;
        } else {
          _ngayHieuLuc = picked;
          ngayHieuLucController.text = picked.toIso8601String().split('T').first;
        }
      });
    }
  }

  bool _validateInputs(AddLawVM vm) {
    if (sohieuController.text.trim().isEmpty ||
        tenVanBanController.text.trim().isEmpty ||
        _ngayKy == null ||
        _ngayHieuLuc == null ||
        vm.selectedCoQuan == null ||
        vm.selectedLoaiVanBan == null ||
        vm.selectedTrangThai == null ||
        vm.selectedTrangThai!.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Vui lòng nhập đầy đủ thông tin văn bản pháp luật'),
          backgroundColor: Colors.red,
        ),
      );
      return false;
    }
    return true;
  }

  Future<void> _handleSave(AddLawVM vm) async {
    if (!_validateInputs(vm)) return;

    setState(() => isLoading = true);

    final law = AddLawModel(
      sohieu: sohieuController.text.trim(),
      tenVanBan: tenVanBanController.text.trim(),
      ngayKy: ngayKyController.text.trim(),
      ngayHieuLuc: ngayHieuLucController.text.trim(),
      trangThai: (vm.selectedTrangThai ?? 'CÒN HIỆU LỰC').trim(),
      macoquan: vm.selectedCoQuan,
      maloai: vm.selectedLoaiVanBan,
    );

    final success = await vm.addLaw(law);
    if (!mounted) return;
    setState(() => isLoading = false);

    if (!success) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Lưu văn bản thất bại'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Đã lưu văn bản. Chuyển sang thêm nội dung.'),
        backgroundColor: Colors.green,
      ),
    );

    Navigator.pushReplacement(
      context,
      MaterialPageRoute(
        builder: (_) => AddLawContentScreen(sohieuvanban: law.sohieu),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider<AddLawVM>.value(
      value: _vm,
      child: Consumer<AddLawVM>(
        builder: (context, addLawVM, _) {
          return Scaffold(
            appBar: AppBar(
              title: const Text('Thêm văn bản pháp luật'),
            ),
            body: Padding(
              padding: const EdgeInsets.all(16),
              child: SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 20),
                    _buildTextField(sohieuController, 'Số hiệu văn bản'),
                    _buildTextField(tenVanBanController, 'Tên văn bản'),
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        _ngayKy == null
                            ? 'Chọn ngày ký'
                            : 'Ngày ký: ${_ngayKy!.toLocal().toString().split(' ').first}',
                      ),
                      trailing: const Icon(Icons.calendar_today),
                      onTap: () => _pickDate(context, true),
                    ),
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        _ngayHieuLuc == null
                            ? 'Chọn ngày có hiệu lực'
                            : 'Ngày hiệu lực: ${_ngayHieuLuc!.toLocal().toString().split(' ').first}',
                      ),
                      trailing: const Icon(Icons.calendar_today),
                      onTap: () => _pickDate(context, false),
                    ),
                    const SizedBox(height: 10),
                    const Text('Chọn trạng thái', style: TextStyle(fontWeight: FontWeight.bold)),
                    DropdownButton<String>(
                      value: addLawVM.selectedTrangThai,
                      items: addLawVM.trangThaiOptions
                          .map(
                            (s) => DropdownMenuItem<String>(
                              value: s,
                              child: Text(s),
                            ),
                          )
                          .toList(),
                      onChanged: addLawVM.setSelectedTrangThai,
                      isExpanded: true,
                    ),
                    const SizedBox(height: 10),
                    const Text('Cơ quan ban hành', style: TextStyle(fontWeight: FontWeight.bold)),
                    DropdownButton<int>(
                      value: addLawVM.selectedCoQuan,
                      items: addLawVM.coQuanList
                          .map(
                            (coQuan) => DropdownMenuItem<int>(
                              value: coQuan['macoquan'],
                              child: Text((coQuan['tencoquan'] ?? '').toString()),
                            ),
                          )
                          .toList(),
                      onChanged: addLawVM.setSelectedCoQuan,
                      isExpanded: true,
                      hint: const Text('Chọn cơ quan'),
                    ),
                    const SizedBox(height: 10),
                    const Text('Loại văn bản', style: TextStyle(fontWeight: FontWeight.bold)),
                    DropdownButton<int>(
                      value: addLawVM.selectedLoaiVanBan,
                      items: addLawVM.loaiVanBanList
                          .map(
                            (loai) => DropdownMenuItem<int>(
                              value: loai['maloai'],
                              child: Text((loai['tenloai'] ?? '').toString()),
                            ),
                          )
                          .toList(),
                      onChanged: addLawVM.setSelectedLoaiVanBan,
                      isExpanded: true,
                      hint: const Text('Chọn loại văn bản'),
                    ),
                    const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        onPressed: isLoading ? null : () => _handleSave(addLawVM),
                        icon: isLoading
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.save),
                        label: Text(isLoading ? 'Đang lưu...' : 'Lưu và chuyển sang thêm nội dung'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildTextField(TextEditingController ctrl, String label) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextField(
        controller: ctrl,
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
        ),
      ),
    );
  }
}
