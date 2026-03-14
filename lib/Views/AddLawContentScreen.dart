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
        if (sohieuvanban.trim().isNotEmpty) vm.setSelectedSohieu(sohieuvanban.trim());
        return vm;
      },
      child: Consumer<AddContentVM>(
        builder: (context, vm, child) {
          const loaiMucOptions = ['CHUONG', 'MUC', 'DIEU', 'KHOAN', 'DIEM'];

          int? safeInt(int? v, List<Map<String, dynamic>> items) =>
              (v != null && items.any((e) => e['sothutund'] == v)) ? v : null;

          final selectedSohieuSafe = (vm.selectedSohieu != null && vm.vanBanList.any((e) => e['sohieuvanban'] == vm.selectedSohieu)) ? vm.selectedSohieu : null;

          return Scaffold(
            appBar: AppBar(title: const Text('Thêm Nội Dung Văn Bản')),
            body: vm.vanBanList.isEmpty && !vm.isLoading
                ? const Center(child: Text('Chưa có văn bản nào.'))
                : Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: ListView(
                      children: [
                        const Text('Chọn số hiệu văn bản:'),
                        DropdownButton<String>(
                          isExpanded: true,
                          value: selectedSohieuSafe,
                          items: vm.vanBanList.map((vb) => DropdownMenuItem(value: vb['sohieuvanban'].toString(), child: Text(vb['sohieuvanban'].toString()))).toList(),
                          onChanged: vm.setSelectedSohieu,
                        ),
                        
                        // 1. Luôn hiện CHƯƠNG khi đã chọn Văn bản
                        if (selectedSohieuSafe != null) ...[
                          const SizedBox(height: 12),
                          _buildDropdown<int?>('Chương', safeInt(vm.selectedChuong, vm.chuongList), vm.chuongList, vm.setSelectedChuong),
                          
                          // 2. MỤC và ĐIỀU cùng hiện ra khi đã chọn CHƯƠNG
                          if (vm.selectedChuong != null) ...[
                            _buildDropdown<int?>('Mục', safeInt(vm.selectedMuc, vm.mucList), vm.mucList, vm.setSelectedMuc),
                            
                            // ĐIỀU nằm ngang hàng với MỤC (không bị nhốt trong if chọn Mục)
                            _buildDropdown<int?>('Điều', safeInt(vm.selectedDieu, vm.dieuList), vm.dieuList, vm.setSelectedDieu),
                            
                            // 3. KHOẢN chỉ hiện khi đã chọn ĐIỀU
                            if (vm.selectedDieu != null) ...[
                              _buildDropdown<int?>('Khoản', safeInt(vm.selectedKhoan, vm.khoanList), vm.khoanList, vm.setSelectedKhoan),

                              // 4. ĐIỂM chỉ hiện khi đã chọn KHOẢN
                              if (vm.selectedKhoan != null) ...[
                                _buildDropdown<int?>('Điểm', safeInt(vm.selectedDiem, vm.diemList), vm.diemList, vm.setSelectedDiem),
                              ],
                            ],
                          ],
                        ],
                        
                        const SizedBox(height: 12),
                        const Text('Loại mục:'),
                        DropdownButton<String>(
                          isExpanded: true,
                          value: loaiMucOptions.contains(vm.loaiMucController.text) ? vm.loaiMucController.text : null,
                          items: loaiMucOptions.map((e) => DropdownMenuItem(value: e, child: Text(e))).toList(),
                          onChanged: vm.setLoaiMuc,
                        ),
                        const SizedBox(height: 12),
                        _buildTextField(vm.kyHieuController, 'Ký hiệu (VD: ĐIỀU 1; ĐIỂM a)'),
                        const SizedBox(height: 12),
                        _buildTextField(vm.thuTuController, 'Thứ tự (số)', isNumber: true),
                        
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(child: _buildTextField(vm.minKmController, 'Vượt từ (km/h)', isNumber: true)),
                            const SizedBox(width: 12),
                            Expanded(child: _buildTextField(vm.maxKmController, 'Đến mức (km/h)', isNumber: true)),
                          ],
                        ),
                        
                        const SizedBox(height: 12),
                        _buildTextField(vm.relaController, 'Từ liên quan (cách bởi ;)'),
                        const SizedBox(height: 12),
                        _buildTextField(vm.noidungController, 'Nội dung', maxLines: 5),
                        const SizedBox(height: 20),
                        ElevatedButton(
                          onPressed: vm.isLoading ? null : () async {
                            final ok = await vm.addContent();
                            ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(ok ? 'Thêm dữ liệu thành công' : 'Thêm dữ liệu thất bại do chưa điền đủ thông tin'), backgroundColor: ok ? Colors.green : Colors.red));
                          },
                          child: vm.isLoading ? const CircularProgressIndicator() : const Text('Thêm nội dung'),
                        ),
                      ],
                    ),
                  ),
          );
        },
      ),
    );
  }

  Widget _buildTextField(TextEditingController ctrl, String label, {bool isNumber = false, int maxLines = 1}) {
    return TextField(
      controller: ctrl,
      keyboardType: isNumber ? TextInputType.number : TextInputType.text,
      maxLines: maxLines,
      decoration: InputDecoration(labelText: label, border: const OutlineInputBorder()),
    );
  }

  Widget _buildDropdown<T>(String label, T value, List<Map<String, dynamic>> items, Function(T) onChanged) {
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
              // --- TÍCH HỢP XỬ LÝ KÝ HIỆU + NỘI DUNG TẠI ĐÂY ---
              final String kyHieu = i['ky_hieu']?.toString() ?? '';
              final String noiDung = i['noidung']?.toString() ?? '';
              
              // Ghép chuỗi thông minh
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