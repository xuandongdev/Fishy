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
  final TextEditingController linhVucController = TextEditingController();
  final LegalIngestService _legalIngestService = LegalIngestService();

  DateTime? _ngayKy;
  DateTime? _ngayHieuLuc;
  bool isLoading = false;
  bool isUploadingLegalFile = false;
  PickedLegalDocument? _selectedFile;

  @override
  void dispose() {
    sohieuController.dispose();
    tenVanBanController.dispose();
    ngayKyController.dispose();
    ngayHieuLucController.dispose();
    linhVucController.dispose();
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
        tooltip: 'Tai file vao kho tri thuc dung chung',
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
              _buildTextField(linhVucController, 'Linh vuc (khong bat buoc)'),
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
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(
                  _selectedFile == null
                      ? 'Chua chon file PDF/DOCX'
                      : 'Da chon file: ${_selectedFile!.fileName}',
                ),
                subtitle: const Text('Co the chi nhap tay, chi chon file, hoac ket hop ca hai'),
                trailing: TextButton.icon(
                  onPressed: isUploadingLegalFile ? null : _handleLegalFileUpload,
                  icon: isUploadingLegalFile
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.attach_file),
                  label: Text(_selectedFile == null ? 'Chon file' : 'Doi file'),
                ),
              ),
              if (_selectedFile != null)
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton(
                    onPressed: () => setState(() => _selectedFile = null),
                    child: const Text('Bo file da chon'),
                  ),
                ),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: isLoading
                    ? null
                    : () async {
                        if (!validateInputs(addLawVM, requireCompleteManual: false)) {
                          return;
                        }

                        setState(() => isLoading = true);

                        final hasMeaningfulManualMetadata = _hasMeaningfulManualMetadata(addLawVM);
                        final canPersistManualToDb = validateInputs(addLawVM, requireCompleteManual: true, showSnackBar: false);
                        final law = AddLawModel(
                          sohieu: sohieuController.text.trim(),
                          tenVanBan: tenVanBanController.text.trim(),
                          ngayKy: ngayKyController.text.trim(),
                          ngayHieuLuc: ngayHieuLucController.text.trim(),
                          trangThai: (addLawVM.selectedTrangThai ?? 'CON HIEU LUC').trim(),
                          macoquan: addLawVM.selectedCoQuan,
                          maloai: addLawVM.selectedLoaiVanBan,
                        );

                        bool success = true;
                        if (hasMeaningfulManualMetadata && canPersistManualToDb) {
                          success = await addLawVM.addLaw(law);
                        }

                        final ingestResult = await _legalIngestService.uploadGlobalDoc(
                          metadata: _buildUploadMetadata(addLawVM),
                          pickedFile: _selectedFile,
                        );
                        if (!mounted) {
                          return;
                        }
                        setState(() => isLoading = false);

                        if (success && ingestResult.success) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(
                                'Da luu van ban. Chunks: ${ingestResult.chunksIndexed}. Sections: ${ingestResult.sectionsCount}',
                              ),
                              backgroundColor: Colors.green,
                            ),
                          );
                          clearInputs(addLawVM);
                        } else {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(
                                !success
                                    ? 'Loi khi luu metadata van ban!'
                                    : ingestResult.message,
                              ),
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

  bool validateInputs(
    AddLawVM lawVM, {
    bool requireCompleteManual = false,
    bool showSnackBar = true,
  }) {
    final hasFile = _selectedFile != null;
    final hasManualMetadata = _hasMeaningfulManualMetadata(lawVM);
    if (!hasFile && !hasManualMetadata) {
      if (showSnackBar) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Hay nhap metadata hoac chon file PDF/DOCX.'),
            backgroundColor: Colors.red,
          ),
        );
      }
      return false;
    }
    if (!requireCompleteManual) {
      return true;
    }
    if (sohieuController.text.trim().isEmpty ||
        tenVanBanController.text.trim().isEmpty ||
        ngayKyController.text.trim().isEmpty ||
        ngayHieuLucController.text.trim().isEmpty ||
        lawVM.selectedTrangThai == null ||
        lawVM.selectedCoQuan == null ||
        lawVM.selectedLoaiVanBan == null) {
      if (showSnackBar) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Vui long dien day du thong tin!'),
            backgroundColor: Colors.red,
          ),
        );
      }
      return false;
    }
    return true;
  }

  bool _hasMeaningfulManualMetadata(AddLawVM lawVM) {
    return sohieuController.text.trim().isNotEmpty ||
        tenVanBanController.text.trim().isNotEmpty ||
        ngayKyController.text.trim().isNotEmpty ||
        ngayHieuLucController.text.trim().isNotEmpty ||
        linhVucController.text.trim().isNotEmpty ||
        lawVM.selectedCoQuan != null ||
        lawVM.selectedLoaiVanBan != null;
  }

  Map<String, String?> _buildUploadMetadata(AddLawVM vm) {
    final hasManual = _hasMeaningfulManualMetadata(vm);
    final selectedCoQuan = vm.coQuanList.cast<Map<String, dynamic>?>().firstWhere(
          (item) => item?['macoquan'] == vm.selectedCoQuan,
          orElse: () => null,
        );
    final selectedLoai = vm.loaiVanBanList.cast<Map<String, dynamic>?>().firstWhere(
          (item) => item?['maloai'] == vm.selectedLoaiVanBan,
          orElse: () => null,
        );
    return {
      'so_hieu': sohieuController.text.trim(),
      'ten_van_ban': tenVanBanController.text.trim(),
      'loai_van_ban': (selectedLoai?['tenloai'] ?? '').toString(),
      'trang_thai': hasManual ? _normalizeTrangThai(vm.selectedTrangThai) : '',
      'ngay_ban_hanh': ngayKyController.text.trim(),
      'ngay_hieu_luc': ngayHieuLucController.text.trim(),
      'linh_vuc': linhVucController.text.trim(),
      'co_quan_ban_hanh': (selectedCoQuan?['tencoquan'] ?? '').toString(),
      'uploaded_by': 'admin',
    };
  }

  String _normalizeTrangThai(String? value) {
    final normalized = (value ?? '').toUpperCase();
    if (normalized.contains('HET')) {
      return 'hetHieuLuc';
    }
    if (normalized.contains('CON')) {
      return 'conHieuLuc';
    }
    return value?.trim() ?? '';
  }

  void clearInputs(AddLawVM vm) {
    sohieuController.clear();
    tenVanBanController.clear();
    ngayKyController.clear();
    ngayHieuLucController.clear();
    linhVucController.clear();
    setState(() {
      _ngayKy = null;
      _ngayHieuLuc = null;
      _selectedFile = null;
    });
    vm.setSelectedTrangThai(vm.trangThaiOptions.first);
    vm.setSelectedCoQuan(null);
    vm.setSelectedLoaiVanBan(null);
  }

  Future<void> _handleLegalFileUpload() async {
    setState(() => isUploadingLegalFile = true);
    try {
      final picked = await _legalIngestService.pickDocument();
      if (!mounted) {
        return;
      }
      setState(() => _selectedFile = picked);
      if (picked != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Da chon file ${picked.fileName}. Bam "Them van ban" de lap chi muc.'),
            backgroundColor: Colors.green,
          ),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$e'),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      if (mounted) {
        setState(() => isUploadingLegalFile = false);
      }
    }
  }
}
