import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../Models/AddLawModel.dart';
import '../Services/LegalIngestService.dart';
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
  final LegalIngestService _legalIngestService = LegalIngestService();

  DateTime? _ngayKy;
  DateTime? _ngayHieuLuc;
  bool isLoading = false;
  bool isUploadingLegalFile = false;

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
      appBar: AppBar(
        title: const Text('Them van ban moi'),
      ),
      floatingActionButton: FloatingActionButton(
        tooltip: 'Tai file vao legal_ingest',
        onPressed: isUploadingLegalFile ? null : _handleLegalFileUpload,
        backgroundColor: const Color(0xFF27408B),
        child: isUploadingLegalFile
            ? const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(
                  strokeWidth: 2.2,
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                ),
              )
            : Padding(
                padding: const EdgeInsets.all(10),
                child: Image.asset(
                  'assets/add_docs.png',
                  fit: BoxFit.contain,
                ),
              ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildTextField(sohieuController, 'So hieu van ban'),
              _buildTextField(tenVanBanController, 'Ten van ban'),
              ListTile(
                title: Text(
                  _ngayKy == null
                      ? 'Chon ngay ky'
                      : 'Ngay ky: ${_ngayKy!.toLocal().toString().split(' ').first}',
                ),
                trailing: const Icon(Icons.calendar_today),
                onTap: () => _pickDate(context, true),
              ),
              ListTile(
                title: Text(
                  _ngayHieuLuc == null
                      ? 'Chon ngay co hieu luc'
                      : 'Ngay hieu luc: ${_ngayHieuLuc!.toLocal().toString().split(' ').first}',
                ),
                trailing: const Icon(Icons.calendar_today),
                onTap: () => _pickDate(context, false),
              ),
              const SizedBox(height: 10),
              const Text('Chon trang thai', style: TextStyle(fontWeight: FontWeight.bold)),
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
              const Text('Co quan ban hanh', style: TextStyle(fontWeight: FontWeight.bold)),
              DropdownButton<int>(
                value: addLawVM.selectedCoQuan,
                items: addLawVM.coQuanList.isNotEmpty
                    ? addLawVM.coQuanList
                        .map(
                          (coQuan) => DropdownMenuItem<int>(
                            value: coQuan['macoquan'],
                            child: Text((coQuan['tencoquan'] ?? '').toString()),
                          ),
                        )
                        .toList()
                    : [],
                onChanged: addLawVM.setSelectedCoQuan,
                isExpanded: true,
                hint: const Text('Chon co quan'),
              ),
              const SizedBox(height: 10),
              const Text('Loai van ban', style: TextStyle(fontWeight: FontWeight.bold)),
              DropdownButton<int>(
                value: addLawVM.selectedLoaiVanBan,
                items: addLawVM.loaiVanBanList.isNotEmpty
                    ? addLawVM.loaiVanBanList
                        .map(
                          (loai) => DropdownMenuItem<int>(
                            value: loai['maloai'],
                            child: Text((loai['tenloai'] ?? '').toString()),
                          ),
                        )
                        .toList()
                    : [],
                onChanged: addLawVM.setSelectedLoaiVanBan,
                isExpanded: true,
                hint: const Text('Chon loai van ban'),
              ),
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: isLoading
                    ? null
                    : () async {
                        if (!validateInputs(addLawVM)) {
                          return;
                        }

                        setState(() => isLoading = true);

                        final law = AddLawModel(
                          sohieu: sohieuController.text.trim(),
                          tenVanBan: tenVanBanController.text.trim(),
                          ngayKy: ngayKyController.text.trim(),
                          ngayHieuLuc: ngayHieuLucController.text.trim(),
                          trangThai: (addLawVM.selectedTrangThai ?? 'CON HIEU LUC').trim(),
                          macoquan: addLawVM.selectedCoQuan!,
                          maloai: addLawVM.selectedLoaiVanBan!,
                        );

                        final success = await addLawVM.addLaw(law);
                        if (!mounted) {
                          return;
                        }
                        setState(() => isLoading = false);

                        if (success) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Them van ban thanh cong!'),
                              backgroundColor: Colors.green,
                            ),
                          );
                          clearInputs(addLawVM);

                          Future.delayed(const Duration(milliseconds: 400), () {
                            if (!mounted) {
                              return;
                            }
                            Navigator.pushNamed(context, "/addContent", arguments: law.sohieu);
                          });
                        } else {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Loi khi them van ban!'),
                              backgroundColor: Colors.red,
                            ),
                          );
                        }
                      },
                child: isLoading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Them van ban'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTextField(TextEditingController controller, String label) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
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
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Vui long dien day du thong tin!'),
          backgroundColor: Colors.red,
        ),
      );
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
    vm.setSelectedTrangThai(vm.trangThaiOptions.first);
    vm.setSelectedCoQuan(null);
    vm.setSelectedLoaiVanBan(null);
  }

  Future<void> _handleLegalFileUpload() async {
    if (sohieuController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Vui long nhap so hieu truoc khi tai file.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }

    setState(() => isUploadingLegalFile = true);
    final result = await _legalIngestService.pickAndUploadDocument(
      soHieu: sohieuController.text.trim(),
    );
    if (!mounted) {
      return;
    }
    setState(() => isUploadingLegalFile = false);

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
