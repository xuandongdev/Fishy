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
  final _linhVucController = TextEditingController();
  final LegalIngestService _legalIngestService = LegalIngestService();

  bool _isUploadingLegalFile = false;
  PickedLegalDocument? _selectedFile;

  @override
  void dispose() {
    _soHieuController.dispose();
    _tenVanBanController.dispose();
    _ngayKyController.dispose();
    _ngayHieuLucController.dispose();
    _linhVucController.dispose();
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
    _linhVucController.clear();
    _selectedFile = null;
    vm.setSelectedCoQuan(null);
    vm.setSelectedLoaiVanBan(null);
    vm.setSelectedTrangThai(vm.trangThaiOptions.first);
  }

  bool _hasMeaningfulManualMetadata(AddLawVM vm) {
    return _soHieuController.text.trim().isNotEmpty ||
        _tenVanBanController.text.trim().isNotEmpty ||
        _ngayKyController.text.trim().isNotEmpty ||
        _ngayHieuLucController.text.trim().isNotEmpty ||
        _linhVucController.text.trim().isNotEmpty ||
        vm.selectedCoQuan != null ||
        vm.selectedLoaiVanBan != null;
  }

  bool _isManualComplete(AddLawVM vm) {
    return _soHieuController.text.trim().isNotEmpty &&
        _tenVanBanController.text.trim().isNotEmpty &&
        _ngayKyController.text.trim().isNotEmpty &&
        _ngayHieuLucController.text.trim().isNotEmpty &&
        vm.selectedTrangThai != null &&
        vm.selectedCoQuan != null &&
        vm.selectedLoaiVanBan != null;
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
      'so_hieu': _soHieuController.text.trim(),
      'ten_van_ban': _tenVanBanController.text.trim(),
      'loai_van_ban': (selectedLoai?['tenloai'] ?? '').toString(),
      'trang_thai': hasManual ? _normalizeTrangThai(vm.selectedTrangThai) : '',
      'ngay_ban_hanh': _ngayKyController.text.trim(),
      'ngay_hieu_luc': _ngayHieuLucController.text.trim(),
      'linh_vuc': _linhVucController.text.trim(),
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
            tooltip: 'Chon file PDF/DOCX',
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
                      validator: (v) {
                        if (_selectedFile != null && (v == null || v.trim().isEmpty)) {
                          return null;
                        }
                        return (v == null || v.trim().isEmpty) ? 'Nhap so hieu' : null;
                      },
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
                      validator: (v) {
                        if (_selectedFile != null && (v == null || v.trim().isEmpty)) {
                          return null;
                        }
                        return (v == null || v.trim().isEmpty) ? 'Nhap ten van ban' : null;
                      },
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
                      validator: (v) {
                        if (_selectedFile != null && (v == null || v.trim().isEmpty)) {
                          return null;
                        }
                        return (v == null || v.trim().isEmpty) ? 'Chon ngay ky' : null;
                      },
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
                      validator: (v) {
                        if (_selectedFile != null && (v == null || v.trim().isEmpty)) {
                          return null;
                        }
                        return (v == null || v.trim().isEmpty) ? 'Chon ngay hieu luc' : null;
                      },
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
                      validator: (v) {
                        if (_selectedFile != null && (v == null || v.trim().isEmpty)) {
                          return null;
                        }
                        return (v == null || v.trim().isEmpty) ? 'Chon trang thai' : null;
                      },
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
                      validator: (v) {
                        if (_selectedFile != null && v == null) {
                          return null;
                        }
                        return v == null ? 'Chon co quan' : null;
                      },
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
                      validator: (v) {
                        if (_selectedFile != null && v == null) {
                          return null;
                        }
                        return v == null ? 'Chon loai van ban' : null;
                      },
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              TextFormField(
                controller: _linhVucController,
                decoration: const InputDecoration(
                  labelText: 'Linh vuc (khong bat buoc)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      _selectedFile == null ? 'Chua chon file PDF/DOCX' : 'Da chon file: ${_selectedFile!.fileName}',
                    ),
                  ),
                  TextButton.icon(
                    onPressed: _isUploadingLegalFile ? null : _handleLegalFileUpload,
                    icon: const Icon(Icons.attach_file),
                    label: Text(_selectedFile == null ? 'Chon file' : 'Doi file'),
                  ),
                  if (_selectedFile != null)
                    TextButton(
                      onPressed: () => setState(() => _selectedFile = null),
                      child: const Text('Bo file'),
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
                      final hasManualMetadata = _hasMeaningfulManualMetadata(vm);
                      if (!hasManualMetadata && _selectedFile == null) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Hay nhap metadata hoac chon file PDF/DOCX.')),
                        );
                        return;
                      }
                      final canPersistManual = _isManualComplete(vm);
                      if (hasManualMetadata && !canPersistManual && _selectedFile == null) {
                        _formKey.currentState!.validate();
                        return;
                      }

                      final newLaw = AddLawModel(
                        sohieu: _soHieuController.text.trim(),
                        tenVanBan: _tenVanBanController.text.trim(),
                        ngayKy: _ngayKyController.text.trim(),
                        ngayHieuLuc: _ngayHieuLucController.text.trim(),
                        trangThai: (vm.selectedTrangThai ?? 'CON HIEU LUC').trim(),
                        macoquan: vm.selectedCoQuan,
                        maloai: vm.selectedLoaiVanBan,
                      );

                      bool success = true;
                      if (hasManualMetadata && canPersistManual) {
                        success = await vm.addLaw(newLaw);
                      }
                      final ingestResult = await _legalIngestService.uploadGlobalDoc(
                        metadata: _buildUploadMetadata(vm),
                        pickedFile: _selectedFile,
                      );
                      if (!mounted) {
                        return;
                      }

                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(
                            success && ingestResult.success
                                ? 'Da luu van ban. Chunks: ${ingestResult.chunksIndexed}. Sections: ${ingestResult.sectionsCount}'
                                : (!success ? 'Loi khi luu metadata van ban!' : ingestResult.message),
                          ),
                        ),
                      );

                      if (success && ingestResult.success) {
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
    setState(() => _isUploadingLegalFile = true);
    try {
      final picked = await _legalIngestService.pickDocument();
      if (!mounted) {
        return;
      }
      setState(() => _selectedFile = picked);
      if (picked != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Da chon file ${picked.fileName}. Bam "LUU DU LIEU" de lap chi muc.')),
        );
      }
    } catch (e) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$e')),
      );
    } finally {
      if (mounted) {
        setState(() => _isUploadingLegalFile = false);
      }
    }
  }
}
