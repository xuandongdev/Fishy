import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../Models/AddLawModel.dart';
import '../ViewModels/AddLawVM.dart';

class WebAddLaw extends StatefulWidget {
  const WebAddLaw({super.key});

  @override
  State<WebAddLaw> createState() => _WebAddLawState();
}

class _WebAddLawState extends State<WebAddLaw> {
  final _formKey = GlobalKey<FormState>();
  final _soHieuController = TextEditingController();
  final _tenVanBanController = TextEditingController();
  final _ngayKyController = TextEditingController();
  final _ngayHieuLucController = TextEditingController();

  @override
  void dispose() {
    _soHieuController.dispose();
    _tenVanBanController.dispose();
    _ngayKyController.dispose();
    _ngayHieuLucController.dispose();
    super.dispose();
  }

  Future<void> _selectDate(BuildContext context, TextEditingController controller) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.now(),
      firstDate: DateTime(1900),
      lastDate: DateTime(2100),
    );
    if (picked != null) {
      setState(() {
        controller.text = DateFormat('yyyy-MM-dd').format(picked);
      });
    }
  }

  void _clearForm(AddLawVM vm) {
    _soHieuController.clear();
    _tenVanBanController.clear();
    _ngayKyController.clear();
    _ngayHieuLucController.clear();

    // reset dropdown
    vm.setSelectedCoQuan(null);
    vm.setSelectedLoaiVanBan(null);
    vm.setSelectedTrangThai(vm.trangThaiOptions.first);
  }

  @override
  Widget build(BuildContext context) {
    final vm = Provider.of<AddLawVM>(context);

    // đảm bảo có default trạng thái (tránh null khi build lần đầu)
    if (vm.selectedTrangThai == null && vm.trangThaiOptions.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        vm.setSelectedTrangThai(vm.trangThaiOptions.first);
      });
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text("Thêm Văn Bản Pháp Luật Mới"),
        elevation: 0,
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        automaticallyImplyLeading: false,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(30),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Hàng 1: Số hiệu + Tên
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    flex: 1,
                    child: TextFormField(
                      controller: _soHieuController,
                      decoration: const InputDecoration(
                        labelText: 'Số hiệu văn bản',
                        border: OutlineInputBorder(),
                      ),
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Nhập số hiệu' : null,
                    ),
                  ),
                  const SizedBox(width: 20),
                  Expanded(
                    flex: 2,
                    child: TextFormField(
                      controller: _tenVanBanController,
                      decoration: const InputDecoration(
                        labelText: 'Tên/Trích yếu văn bản',
                        border: OutlineInputBorder(),
                      ),
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Nhập tên văn bản' : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),

              // Hàng 2: Ngày ký + Ngày hiệu lực + Trạng thái (2 option)
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _ngayKyController,
                      decoration: const InputDecoration(
                        labelText: 'Ngày ký',
                        icon: Icon(Icons.calendar_today),
                        border: OutlineInputBorder(),
                      ),
                      readOnly: true,
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Chọn ngày ký' : null,
                      onTap: () => _selectDate(context, _ngayKyController),
                    ),
                  ),
                  const SizedBox(width: 20),
                  Expanded(
                    child: TextFormField(
                      controller: _ngayHieuLucController,
                      decoration: const InputDecoration(
                        labelText: 'Ngày hiệu lực',
                        icon: Icon(Icons.event_available),
                        border: OutlineInputBorder(),
                      ),
                      readOnly: true,
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Chọn ngày hiệu lực' : null,
                      onTap: () => _selectDate(context, _ngayHieuLucController),
                    ),
                  ),
                  const SizedBox(width: 20),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: vm.selectedTrangThai,
                      decoration: const InputDecoration(
                        labelText: 'Trạng thái',
                        border: OutlineInputBorder(),
                      ),
                      items: vm.trangThaiOptions
                          .map((s) => DropdownMenuItem<String>(
                        value: s,
                        child: Text(s),
                      ))
                          .toList(),
                      onChanged: vm.setSelectedTrangThai,
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Chọn trạng thái' : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),

              // Hàng 3: Cơ quan + Loại văn bản
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<int>(
                      value: vm.selectedCoQuan,
                      decoration: const InputDecoration(
                        labelText: 'Cơ quan ban hành',
                        border: OutlineInputBorder(),
                      ),
                      items: vm.coQuanList
                          .map((e) => DropdownMenuItem<int>(
                        value: e['macoquan'] as int?,
                        child: Text((e['tencoquan'] ?? '').toString()),
                      ))
                          .toList(),
                      onChanged: vm.setSelectedCoQuan,
                      validator: (v) => v == null ? 'Chọn cơ quan' : null,
                    ),
                  ),
                  const SizedBox(width: 20),
                  Expanded(
                    child: DropdownButtonFormField<int>(
                      value: vm.selectedLoaiVanBan,
                      decoration: const InputDecoration(
                        labelText: 'Loại văn bản',
                        border: OutlineInputBorder(),
                      ),
                      items: vm.loaiVanBanList
                          .map((e) => DropdownMenuItem<int>(
                        value: e['maloai'] as int?,
                        child: Text((e['tenloai'] ?? '').toString()),
                      ))
                          .toList(),
                      onChanged: vm.setSelectedLoaiVanBan,
                      validator: (v) => v == null ? 'Chọn loại văn bản' : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 40),

              // Nút submit
              Center(
                child: SizedBox(
                  width: 200,
                  height: 50,
                  child: ElevatedButton.icon(
                    icon: const Icon(Icons.save),
                    label: const Text("LƯU DỮ LIỆU"),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.blueAccent,
                      foregroundColor: Colors.white,
                    ),
                    onPressed: () async {
                      if (!_formKey.currentState!.validate()) return;

                      // chặn null chắc chắn
                      final trangThai = vm.selectedTrangThai ?? vm.trangThaiOptions.first;
                      if (vm.selectedCoQuan == null || vm.selectedLoaiVanBan == null) return;

                      final newLaw = AddLawModel(
                        sohieu: _soHieuController.text.trim(),
                        tenVanBan: _tenVanBanController.text.trim(),
                        ngayKy: _ngayKyController.text.trim(),
                        ngayHieuLuc: _ngayHieuLucController.text.trim(),
                        trangThai: (vm.selectedTrangThai ?? 'CÒN HIỆU LỰC').trim(),
                        macoquan: vm.selectedCoQuan!,
                        maloai: vm.selectedLoaiVanBan!,
                      );

                      final success = await vm.addLaw(newLaw);

                      if (!mounted) return;

                      if (success) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Thêm thành công!')),
                        );
                        _clearForm(vm);
                      } else {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Lỗi khi thêm!')),
                        );
                      }
                    },
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
