import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../Models/AddLawModel.dart';
import '../Services/LegalIngestService.dart';
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
  final LegalIngestService _legalIngestService = LegalIngestService();

  bool _isUploadingLegalFile = false;

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
    vm.setSelectedCoQuan(null);
    vm.setSelectedLoaiVanBan(null);
    vm.setSelectedTrangThai(vm.trangThaiOptions.first);
  }

  @override
  Widget build(BuildContext context) {
    final vm = Provider.of<AddLawVM>(context);

    if (vm.selectedTrangThai == null && vm.trangThaiOptions.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        vm.setSelectedTrangThai(vm.trangThaiOptions.first);
      });
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text("Them van ban phap luat moi"),
        elevation: 0,
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            tooltip: 'Tai file vao legal_ingest',
            onPressed: _isUploadingLegalFile ? null : _handleLegalFileUpload,
            icon: _isUploadingLegalFile
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.add),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(30),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    flex: 1,
                    child: TextFormField(
                      controller: _soHieuController,
                      decoration: const InputDecoration(
                        labelText: 'So hieu van ban',
                        border: OutlineInputBorder(),
                      ),
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Nhap so hieu' : null,
                    ),
                  ),
                  const SizedBox(width: 20),
                  Expanded(
                    flex: 2,
                    child: TextFormField(
                      controller: _tenVanBanController,
                      decoration: const InputDecoration(
                        labelText: 'Ten/Trich yeu van ban',
                        border: OutlineInputBorder(),
                      ),
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Nhap ten van ban' : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _ngayKyController,
                      decoration: const InputDecoration(
                        labelText: 'Ngay ky',
                        icon: Icon(Icons.calendar_today),
                        border: OutlineInputBorder(),
                      ),
                      readOnly: true,
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Chon ngay ky' : null,
                      onTap: () => _selectDate(context, _ngayKyController),
                    ),
                  ),
                  const SizedBox(width: 20),
                  Expanded(
                    child: TextFormField(
                      controller: _ngayHieuLucController,
                      decoration: const InputDecoration(
                        labelText: 'Ngay hieu luc',
                        icon: Icon(Icons.event_available),
                        border: OutlineInputBorder(),
                      ),
                      readOnly: true,
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Chon ngay hieu luc' : null,
                      onTap: () => _selectDate(context, _ngayHieuLucController),
                    ),
                  ),
                  const SizedBox(width: 20),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: vm.selectedTrangThai,
                      decoration: const InputDecoration(
                        labelText: 'Trang thai',
                        border: OutlineInputBorder(),
                      ),
                      items: vm.trangThaiOptions
                          .map(
                            (s) => DropdownMenuItem<String>(
                              value: s,
                              child: Text(s),
                            ),
                          )
                          .toList(),
                      onChanged: vm.setSelectedTrangThai,
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Chon trang thai' : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<int>(
                      value: vm.selectedCoQuan,
                      decoration: const InputDecoration(
                        labelText: 'Co quan ban hanh',
                        border: OutlineInputBorder(),
                      ),
                      items: vm.coQuanList
                          .map(
                            (e) => DropdownMenuItem<int>(
                              value: e['macoquan'] as int?,
                              child: Text((e['tencoquan'] ?? '').toString()),
                            ),
                          )
                          .toList(),
                      onChanged: vm.setSelectedCoQuan,
                      validator: (v) => v == null ? 'Chon co quan' : null,
                    ),
                  ),
                  const SizedBox(width: 20),
                  Expanded(
                    child: DropdownButtonFormField<int>(
                      value: vm.selectedLoaiVanBan,
                      decoration: const InputDecoration(
                        labelText: 'Loai van ban',
                        border: OutlineInputBorder(),
                      ),
                      items: vm.loaiVanBanList
                          .map(
                            (e) => DropdownMenuItem<int>(
                              value: e['maloai'] as int?,
                              child: Text((e['tenloai'] ?? '').toString()),
                            ),
                          )
                          .toList(),
                      onChanged: vm.setSelectedLoaiVanBan,
                      validator: (v) => v == null ? 'Chon loai van ban' : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 40),
              Center(
                child: SizedBox(
                  width: 200,
                  height: 50,
                  child: ElevatedButton.icon(
                    icon: const Icon(Icons.save),
                    label: const Text("LUU DU LIEU"),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.blueAccent,
                      foregroundColor: Colors.white,
                    ),
                    onPressed: () async {
                      if (!_formKey.currentState!.validate()) {
                        return;
                      }
                      if (vm.selectedCoQuan == null || vm.selectedLoaiVanBan == null) {
                        return;
                      }

                      final newLaw = AddLawModel(
                        sohieu: _soHieuController.text.trim(),
                        tenVanBan: _tenVanBanController.text.trim(),
                        ngayKy: _ngayKyController.text.trim(),
                        ngayHieuLuc: _ngayHieuLucController.text.trim(),
                        trangThai: (vm.selectedTrangThai ?? 'CON HIEU LUC').trim(),
                        macoquan: vm.selectedCoQuan!,
                        maloai: vm.selectedLoaiVanBan!,
                      );

                      final success = await vm.addLaw(newLaw);
                      if (!mounted) {
                        return;
                      }

                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(success ? 'Them thanh cong!' : 'Loi khi them!'),
                        ),
                      );

                      if (success) {
                        _clearForm(vm);
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

  Future<void> _handleLegalFileUpload() async {
    if (_soHieuController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Vui long nhap so hieu truoc khi tai file.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }

    setState(() => _isUploadingLegalFile = true);
    final result = await _legalIngestService.pickAndUploadDocument(
      soHieu: _soHieuController.text.trim(),
    );
    if (!mounted) {
      return;
    }
    setState(() => _isUploadingLegalFile = false);

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          result.success
              ? 'Da ingest file ${result.fileName ?? ''}. Inserted: ${result.insertedCount}'
              : result.message,
        ),
        backgroundColor: result.success ? Colors.green : Colors.red,
      ),
    );
  }
}
