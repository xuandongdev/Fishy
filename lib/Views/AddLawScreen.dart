import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fishy/Models/AddLawModel.dart';
import 'package:fishy/ViewModels/AddLawVM.dart';

class AddLawScreen extends StatefulWidget {
  @override
  _AddLawScreenState createState() => _AddLawScreenState();
}

class _AddLawScreenState extends State<AddLawScreen> {
  final TextEditingController sohieuController = TextEditingController();
  final TextEditingController tenVanBanController = TextEditingController();
  final TextEditingController ngayKyController = TextEditingController();
  final TextEditingController ngayHieuLucController = TextEditingController();
  DateTime? _ngayKy;
  DateTime? _ngayHieuLuc;

  bool isLoading = false;

  Future<void> _pickDate(BuildContext context, bool isNgayKy) async {
    final DateTime? picked = await showDatePicker(
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
    final lawVM = Provider.of<AddLawVM>(context);

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
              const Text('Trạng thái', style: TextStyle(fontWeight: FontWeight.bold)),
              DropdownButton<int>(
                value: lawVM.selectedTrangThai,
                items: lawVM.trangThaiList.isNotEmpty
                    ? lawVM.trangThaiList.map((trangthai) {
                  return DropdownMenuItem<int>(
                    value: trangthai['matrangthai'],
                    child: Text(trangthai['tentrangthai']),
                  );
                }).toList()
                    : [],
                onChanged: lawVM.setSelectedTrangThai,
                isExpanded: true,
                hint: const Text('Chọn trạng thái'),
              ),

              const SizedBox(height: 10),
              const Text('Cơ quan ban hành', style: TextStyle(fontWeight: FontWeight.bold)),
              DropdownButton<int>(
                value: lawVM.selectedCoQuan,
                items: lawVM.coQuanList.isNotEmpty
                    ? lawVM.coQuanList.map((coQuan) {
                  return DropdownMenuItem<int>(
                    value: coQuan['macoquan'],
                    child: Text(coQuan['tencoquan']),
                  );
                }).toList()
                    : [],
                onChanged: lawVM.setSelectedCoQuan,
                isExpanded: true,
                hint: const Text('Chọn cơ quan'),
              ),

              const SizedBox(height: 10),
              const Text('Loại văn bản', style: TextStyle(fontWeight: FontWeight.bold)),
              DropdownButton<int>(
                value: lawVM.selectedLoaiVanBan,
                items: lawVM.loaiVanBanList.isNotEmpty
                    ? lawVM.loaiVanBanList.map((loai) {
                  return DropdownMenuItem<int>(
                    value: loai['maloai'],
                    child: Text(loai['tenloai']),
                  );
                }).toList()
                    : [],
                onChanged: lawVM.setSelectedLoaiVanBan,
                isExpanded: true,
                hint: const Text('Chọn loại văn bản'),
              ),

              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: isLoading ? null : () async {
                  if (!validateInputs(lawVM)) return;

                  setState(() => isLoading = true);

                  final law = AddLawModel(
                    sohieu: sohieuController.text,
                    tenVanBan: tenVanBanController.text,
                    ngayKy: ngayKyController.text,
                    ngayHieuLuc: ngayHieuLucController.text,
                    matrangthai: lawVM.selectedTrangThai!,
                    macoquan: lawVM.selectedCoQuan!,
                    maloai: lawVM.selectedLoaiVanBan!,
                  );

                  bool success = await lawVM.addLaw(law);

                  setState(() => isLoading = false);

                  if (success) {
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Thêm văn bản thành công!'),
                      backgroundColor: Colors.green,
                    ));
                    clearInputs();

                    Future.delayed(const Duration(milliseconds: 400), () {
                      Navigator.pushNamed(context, "/addContent", arguments: law.sohieu);
                    });
                  }

                  else {
                    setState(() => isLoading = false);
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Lỗi khi thêm văn bản!'),
                      backgroundColor: Colors.red,
                    ));
                  }
                },
                child: isLoading ? const CircularProgressIndicator() : const Text('Thêm Văn bản'),
              ),

            ],
          ),
        ),
      ),
    );
  }


  Widget _buildTextField(TextEditingController controller, String label, {bool isDate = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: TextField(
        controller: controller,
        decoration: InputDecoration(
          labelText: label,
          border: OutlineInputBorder(),
        ),
        keyboardType: isDate ? TextInputType.datetime : TextInputType.text,
      ),
    );
  }

  bool validateInputs(AddLawVM lawVM) {
    if (sohieuController.text.isEmpty ||
        tenVanBanController.text.isEmpty ||
        ngayKyController.text.isEmpty ||
        ngayHieuLucController.text.isEmpty ||
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

  void clearInputs() {
    sohieuController.clear();
    tenVanBanController.clear();
    ngayKyController.clear();
    ngayHieuLucController.clear();
  }
}
