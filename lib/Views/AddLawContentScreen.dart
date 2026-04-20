import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../ViewModels/AddLawContentVM.dart';

class AddLawContentScreen extends StatelessWidget {
  final String sohieuvanban;
  const AddLawContentScreen({super.key, required this.sohieuvanban});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) {
        final vm = AddContentVM();
        if (sohieuvanban.trim().isNotEmpty) {
          vm.setSelectedSohieu(sohieuvanban.trim());
        }
        return vm;
      },
      child: Consumer<AddContentVM>(
        builder: (context, vm, child) {
          const loaiMucOptions = ['CHUONG', 'MUC', 'DIEU', 'KHOAN', 'DIEM'];

          int? safeInt(int? v, List<Map<String, dynamic>> items) =>
              (v != null && items.any((e) => e['sothutund'] == v)) ? v : null;

          final selectedSohieuSafe = (vm.selectedSohieu != null &&
                  vm.vanBanList.any((e) => e['sohieuvanban'] == vm.selectedSohieu))
              ? vm.selectedSohieu
              : null;

          return Scaffold(
            appBar: AppBar(title: const Text('Thêm nội dung văn bản')),
            body: vm.vanBanList.isEmpty && !vm.isLoading
                ? const Center(child: Text('Chưa có văn bản nào.'))
                : Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: ListView(
                      children: [
                        const SizedBox(height: 16),
                        const Text('Chọn số hiệu văn bản:'),
                        DropdownButton<String>(
                          isExpanded: true,
                          value: selectedSohieuSafe,
                          items: vm.vanBanList
                              .map(
                                (vb) => DropdownMenuItem(
                                  value: vb['sohieuvanban'].toString(),
                                  child: Text(vb['sohieuvanban'].toString()),
                                ),
                              )
                              .toList(),
                          onChanged: vm.setSelectedSohieu,
                        ),
                        const SizedBox(height: 16),
                        const Divider(),
                        const SizedBox(height: 8),
                        const Text(
                          'Tải lên file văn bản (PDF/DOCX/TXT)',
                          style: TextStyle(fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 8),
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(vm.selectedFileName ?? 'Chưa chọn file PDF/DOCX/TXT'),
                          subtitle: const Text('Yêu cầu: bắt buộc phải là văn bản đã được thêm'),
                          trailing: TextButton.icon(
                            onPressed: vm.isLoading ? null : vm.pickLegalFile,
                            icon: const Icon(Icons.attach_file),
                            label: const Text('Chọn file'),
                          ),
                        ),
                        if (vm.selectedFileName != null)
                          Align(
                            alignment: Alignment.centerLeft,
                            child: TextButton(
                              onPressed: vm.isLoading
                                  ? null
                                  : () {
                                      vm.selectedFile = null;
                                      vm.selectedFileName = null;
                                      vm.notifyListeners();
                                    },
                              child: const Text('Bỏ file đã chọn'),
                            ),
                          ),
                        SizedBox(
                          width: double.infinity,
                          child: ElevatedButton.icon(
                            onPressed: vm.isLoading ? null : () async {
                              final ok = await vm.ingestSelectedFile();
                              if (!context.mounted) return;
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text(ok
                                      ? (vm.lastIngestMessage ?? 'Ingest file thành công')
                                      : (vm.lastIngestMessage ?? 'Ingest file thất bại')),
                                  backgroundColor: ok ? Colors.green : Colors.red,
                                ),
                              );
                            },
                            icon: vm.isLoading
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  )
                                : const Icon(Icons.upload_file),
                            label: Text(vm.isLoading ? 'Đang ingest...' : 'Ingest file'),
                          ),
                        ),
                        if (vm.lastIngestMessage != null) ...[
                          const SizedBox(height: 8),
                          Text(vm.lastIngestMessage!),
                        ],
                        const SizedBox(height: 20),
                        const Divider(),
                        const SizedBox(height: 8),
                        const Text(
                          'Nhập thông tin nội dung văn bản (bỏ qua nếu đã thêm từ file)',
                          style: TextStyle(fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 12),
                        if (selectedSohieuSafe != null) ...[
                          _buildDropdown<int?>(
                            'Chương',
                            safeInt(vm.selectedChuong, vm.chuongList),
                            vm.chuongList,
                            vm.setSelectedChuong,
                          ),
                          if (vm.selectedChuong != null) ...[
                            _buildDropdown<int?>(
                              'Mục',
                              safeInt(vm.selectedMuc, vm.mucList),
                              vm.mucList,
                              vm.setSelectedMuc,
                            ),
                            _buildDropdown<int?>(
                              'Điều',
                              safeInt(vm.selectedDieu, vm.dieuList),
                              vm.dieuList,
                              vm.setSelectedDieu,
                            ),
                            if (vm.selectedDieu != null) ...[
                              _buildDropdown<int?>(
                                'Khoản',
                                safeInt(vm.selectedKhoan, vm.khoanList),
                                vm.khoanList,
                                vm.setSelectedKhoan,
                              ),
                              if (vm.selectedKhoan != null) ...[
                                _buildDropdown<int?>(
                                  'Điểm',
                                  safeInt(vm.selectedDiem, vm.diemList),
                                  vm.diemList,
                                  vm.setSelectedDiem,
                                ),
                              ],
                            ],
                          ],
                        ],
                        const SizedBox(height: 12),
                        const Text('Loại mục:'),
                        DropdownButton<String>(
                          isExpanded: true,
                          value: loaiMucOptions.contains(vm.loaiMucController.text)
                              ? vm.loaiMucController.text
                              : null,
                          items: loaiMucOptions
                              .map((e) => DropdownMenuItem(value: e, child: Text(e)))
                              .toList(),
                          onChanged: vm.setLoaiMuc,
                        ),
                        const SizedBox(height: 12),
                        _buildTextField(vm.kyHieuController, 'Ký hiệu (VD: ĐIỀU 1; ĐIỂM a)'),
                        const SizedBox(height: 12),
                        _buildTextField(vm.thuTuController, 'Thứ tự (số)', isNumber: true),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: _buildTextField(vm.minKmController, 'Vượt từ (km/h)', isNumber: true),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: _buildTextField(vm.maxKmController, 'Đến mức (km/h)', isNumber: true),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        _buildTextField(vm.relaController, 'Từ liên quan (cách bởi ;)'),
                        const SizedBox(height: 12),
                        _buildTextField(vm.noidungController, 'Nội dung', maxLines: 5),
                        const SizedBox(height: 20),
                        ElevatedButton(
                          onPressed: vm.isLoading
                              ? null
                              : () async {
                                  final ok = await vm.addContent();
                                  if (!context.mounted) return;
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(ok
                                          ? 'Thêm dữ liệu thủ công thành công'
                                          : 'Thêm dữ liệu thủ công thất bại do chưa điền đủ thông tin'),
                                      backgroundColor: ok ? Colors.green : Colors.red,
                                    ),
                                  );
                                },
                          child: vm.isLoading
                              ? const CircularProgressIndicator()
                              : const Text('Thêm nội dung thủ công'),
                        ),
                      ],
                    ),
                  ),
          );
        },
      ),
    );
  }

  Widget _buildTextField(
    TextEditingController ctrl,
    String label, {
    bool isNumber = false,
    int maxLines = 1,
  }) {
    return TextField(
      controller: ctrl,
      keyboardType: isNumber ? TextInputType.number : TextInputType.text,
      maxLines: maxLines,
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
      ),
    );
  }

  Widget _buildDropdown<T>(
    String label,
    T value,
    List<Map<String, dynamic>> items,
    Function(T) onChanged,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Chọn $label:'),
        DropdownButton<T>(
          isExpanded: true,
          value: value,
          items: [
            const DropdownMenuItem(value: null, child: Text('- Thêm nội dung mới -')),
            ...items.map((i) {
              final String kyHieu = i['ky_hieu']?.toString() ?? '';
              final String noiDung = i['noidung']?.toString() ?? '';
              final String displayText = kyHieu.isNotEmpty ? '$kyHieu - $noiDung' : noiDung;

              return DropdownMenuItem(
                value: i['sothutund'] as T,
                child: Text(displayText, overflow: TextOverflow.ellipsis),
              );
            })
          ],
          onChanged: (val) => onChanged(val as T),
        ),
        const SizedBox(height: 8),
      ],
    );
  }
}
