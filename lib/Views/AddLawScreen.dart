import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../Models/AddLawModel.dart';
import '../ViewModels/AddLawVM.dart';

class AddLawScreen extends StatefulWidget {
  const AddLawScreen({super.key});

  @override
  State<AddLawScreen> createState() => _AddLawScreenState();
}

class _AddLawScreenState extends State<AddLawScreen> {
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

  @override
  Widget build(BuildContext context) {
    final addLawVM = Provider.of<AddLawVM>(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Thêm Văn bản mới')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildTextField(sohieuController, 'Số hiệu văn bản'),
              _buildTextField(tenVanBanController, 'Tên văn bản'),

              ListTile(
                title: Text(
                  _ngayKy == null
                      ? "Chọn ngày ký"
                      : "Ngày ký: ${_ngayKy!.toLocal().toString().split(' ').first}",
                ),
                trailing: const Icon(Icons.calendar_today),
                onTap: () => _pickDate(context, true),
              ),

              ListTile(
                title: Text(
                  _ngayHieuLuc == null
                      ? "Chọn ngày có hiệu lực"
                      : "Ngày hiệu lực: ${_ngayHieuLuc!.toLocal().toString().split(' ').first}",
                ),
                trailing: const Icon(Icons.calendar_today),
                onTap: () => _pickDate(context, false),
              ),

              const SizedBox(height: 10),
              const SizedBox(height: 10),
              const Text('Chọn trạng thái', style: TextStyle(fontWeight: FontWeight.bold)),
              DropdownButton<String>(
                value: addLawVM.selectedTrangThai,
                items: addLawVM.trangThaiOptions.map((s) {
                  return DropdownMenuItem<String>(
                    value: s,
                    child: Text(s),
                  );
                }).toList(),
                onChanged: addLawVM.setSelectedTrangThai,
                isExpanded: true,
              ),

              const SizedBox(height: 10),
              const Text('Cơ quan ban hành', style: TextStyle(fontWeight: FontWeight.bold)),
              DropdownButton<int>(
                value: addLawVM.selectedCoQuan,
                items: addLawVM.coQuanList.isNotEmpty
                    ? addLawVM.coQuanList.map((coQuan) {
                  return DropdownMenuItem<int>(
                    value: coQuan['macoquan'],
                    child: Text((coQuan['tencoquan'] ?? '').toString()),
                  );
                }).toList()
                    : [],
                onChanged: addLawVM.setSelectedCoQuan,
                isExpanded: true,
                hint: const Text('Chọn cơ quan'),
              ),

              const SizedBox(height: 10),
              const Text('Loại văn bản', style: TextStyle(fontWeight: FontWeight.bold)),
              DropdownButton<int>(
                value: addLawVM.selectedLoaiVanBan,
                items: addLawVM.loaiVanBanList.isNotEmpty
                    ? addLawVM.loaiVanBanList.map((loai) {
                  return DropdownMenuItem<int>(
                    value: loai['maloai'],
                    child: Text((loai['tenloai'] ?? '').toString()),
                  );
                }).toList()
                    : [],
                onChanged: addLawVM.setSelectedLoaiVanBan,
                isExpanded: true,
                hint: const Text('Chọn loại văn bản'),
              ),

              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: isLoading
                    ? null
                    : () async {
                  if (!validateInputs(addLawVM)) return;

                  setState(() => isLoading = true);

                  final law = AddLawModel(
                    sohieu: sohieuController.text.trim(),
                    tenVanBan: tenVanBanController.text.trim(),
                    ngayKy: ngayKyController.text.trim(),
                    ngayHieuLuc: ngayHieuLucController.text.trim(),
                    trangThai: (addLawVM.selectedTrangThai ?? 'CÒN HIỆU LỰC').trim(),
                    macoquan: addLawVM.selectedCoQuan!,
                    maloai: addLawVM.selectedLoaiVanBan!,
                  );

                  final success = await addLawVM.addLaw(law);
                  setState(() => isLoading = false);

                  if (success) {
                    if (!mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Thêm văn bản thành công!'),
                      backgroundColor: Colors.green,
                    ));
                    clearInputs(addLawVM);

                    Future.delayed(const Duration(milliseconds: 400), () {
                      if (!mounted) return;
                      Navigator.pushNamed(context, "/addContent", arguments: law.sohieu);
                    });
                  } else {
                    if (!mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Lỗi khi thêm văn bản!'),
                      backgroundColor: Colors.red,
                    ));
                  }
                },
                child: isLoading
                    ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
                    : const Text('Thêm Văn bản'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTextField(TextEditingController controller, String label) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: TextField(
        controller: controller,
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
        ),
      ),
    );
  }

  bool validateInputs(AddLawVM lawVM) {
    if (sohieuController.text.trim().isEmpty ||
        tenVanBanController.text.trim().isEmpty ||
        ngayKyController.text.trim().isEmpty ||
        ngayHieuLucController.text.trim().isEmpty ||
        lawVM.selectedTrangThai == null ||
        lawVM.selectedCoQuan == null ||
        lawVM.selectedLoaiVanBan == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Vui lòng điền đầy đủ thông tin!'),
        backgroundColor: Colors.red,
      ));
      return false;
    }
    return true;
  }

  void clearInputs(AddLawVM vm) {
    sohieuController.clear();
    tenVanBanController.clear();
    ngayKyController.clear();
    ngayHieuLucController.clear();
    setState(() {
      _ngayKy = null;
      _ngayHieuLuc = null;
    });

    // reset dropdown nếu muốn
    vm.setSelectedTrangThai(vm.trangThaiOptions.first);
    vm.setSelectedCoQuan(null);
    vm.setSelectedLoaiVanBan(null);
  }
}
