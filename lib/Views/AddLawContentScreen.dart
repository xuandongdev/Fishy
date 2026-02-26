import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../ViewModels/AddLawContentVM.dart';

class AddLawContentScreen extends StatelessWidget {
  final String sohieuvanban;

  const AddLawContentScreen({
    super.key,
    required this.sohieuvanban,
  });

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      // ✅ Chỉ auto chọn khi sohieuvanban có giá trị thật và khác rỗng
      create: (_) {
        final vm = AddContentVM();
        final s = sohieuvanban.trim();
        if (s.isNotEmpty) {
          vm.setSelectedSohieu(s);
        }
        return vm;
      },
      child: Consumer<AddContentVM>(
        builder: (context, vm, child) {
          const loaiMucOptions = <String>[
            'CHUONG',
            'MUC',
            'DIEU',
            'KHOAN',
            'DIEM',
          ];

          // ===== helper: ép value về null nếu không có trong items =====
          String? safeStringValue(String? v, List<Map<String, dynamic>> items, String key) {
            if (v == null) return null;
            return items.any((e) => (e[key]?.toString() ?? '') == v) ? v : null;
          }

          int? safeIntValue(int? v, List<Map<String, dynamic>> items, String key) {
            if (v == null) return null;
            return items.any((e) => e[key] == v) ? v : null;
          }

          // ✅ Safe value cho dropdown văn bản
          final selectedSohieuSafe = safeStringValue(
            vm.selectedSohieu,
            vm.vanBanList,
            'sohieuvanban',
          );

          // ✅ Safe value cho dropdown phân cấp
          final selectedChuongSafe = safeIntValue(vm.selectedChuong, vm.chuongList, 'sothutund');
          final selectedMucSafe = safeIntValue(vm.selectedMuc, vm.mucList, 'sothutund');
          final selectedDieuSafe = safeIntValue(vm.selectedDieu, vm.dieuList, 'sothutund');
          final selectedKhoanSafe = safeIntValue(vm.selectedKhoan, vm.khoanList, 'sothutund');
          final selectedDiemSafe = safeIntValue(vm.selectedDiem, vm.diemList, 'sothutund');

          // ===== Safe cho loai_muc dropdown (lấy từ controller) =====
          final currentLoai = vm.loaiMucController.text.trim().toUpperCase();
          final String? selectedLoaiMuc =
          loaiMucOptions.contains(currentLoai) ? currentLoai : null;

          // ✅ Nếu chưa có văn bản nào => show màn báo, KHÔNG render dropdown để tránh crash
          final noLawYet = !vm.isLoading && vm.vanBanList.isEmpty;

          return Scaffold(
            appBar: AppBar(title: const Text('Thêm Nội Dung Văn Bản')),
            body: noLawYet
                ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.description_outlined, size: 48, color: Colors.grey),
                    const SizedBox(height: 12),
                    const Text(
                      'Hiện tại chưa có văn bản nào được lưu',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Hãy thêm văn bản trước rồi mới nhập nội dung (chunk).',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey),
                    ),
                    const SizedBox(height: 16),
                    ElevatedButton.icon(
                      onPressed: () {
                        // bạn có route /addLaw thì dùng luôn
                        Navigator.pushNamed(context, '/addLaw');
                      },
                      icon: const Icon(Icons.add),
                      label: const Text('Thêm văn bản'),
                    ),
                  ],
                ),
              ),
            )
                : Padding(
              padding: const EdgeInsets.all(16.0),
              child: ListView(
                children: [
                  const Text('Chọn số hiệu văn bản:'),
                  const SizedBox(height: 6),
                  SizedBox(
                    height: 55,
                    child: DropdownButton<String>(
                      isExpanded: true,
                      value: selectedSohieuSafe,
                      hint: const Text('- Chọn số hiệu -'),
                      items: vm.vanBanList.map((vb) {
                        final so = (vb['sohieuvanban'] ?? '').toString();
                        final ten = (vb['tenvanban'] ?? '').toString();
                        return DropdownMenuItem<String>(
                          value: so,
                          child: Text(
                            '$so - $ten',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        );
                      }).toList(),
                      onChanged: vm.isLoading ? null : vm.setSelectedSohieu,
                    ),
                  ),

                  if (selectedSohieuSafe != null) ...[
                    const SizedBox(height: 16),
                    const Text('Chọn CHƯƠNG (hoặc để trống để thêm chương mới):'),
                    const SizedBox(height: 6),
                    DropdownButton<int?>(
                      isExpanded: true,
                      value: selectedChuongSafe,
                      hint: const Text('- Chọn chương -'),
                      items: [
                        const DropdownMenuItem<int?>(
                          value: null,
                          child: Text('- (Không chọn) -'),
                        ),
                        ...vm.chuongList.map((c) {
                          final id = c['sothutund'] as int?;
                          final text = (c['noidung'] ?? '').toString();
                          return DropdownMenuItem<int?>(
                            value: id,
                            child: Text(
                              text,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          );
                        }).toList(),
                      ],
                      onChanged: vm.isLoading ? null : vm.setSelectedChuong,
                    ),
                  ],

                  if (selectedChuongSafe != null) ...[
                    const SizedBox(height: 16),
                    const Text(
                        'Chọn MỤC (hoặc để trống để thêm mục mới / không chọn để thêm điều mới):'),
                    const SizedBox(height: 6),
                    DropdownButton<int?>(
                      isExpanded: true,
                      value: selectedMucSafe,
                      hint: const Text('- Chọn mục -'),
                      items: [
                        const DropdownMenuItem<int?>(
                          value: null,
                          child: Text('- (Không chọn) -'),
                        ),
                        ...vm.mucList.map((m) {
                          final id = m['sothutund'] as int?;
                          final text = (m['noidung'] ?? '').toString();
                          return DropdownMenuItem<int?>(
                            value: id,
                            child: Text(
                              text,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          );
                        }).toList(),
                      ],
                      onChanged: vm.isLoading ? null : vm.setSelectedMuc,
                    ),
                  ],

                  if (selectedChuongSafe != null) ...[
                    const SizedBox(height: 16),
                    const Text('Chọn ĐIỀU (hoặc để trống để thêm điều mới):'),
                    const SizedBox(height: 6),
                    DropdownButton<int?>(
                      isExpanded: true,
                      value: selectedDieuSafe,
                      hint: const Text('- Chọn điều -'),
                      items: [
                        const DropdownMenuItem<int?>(
                          value: null,
                          child: Text('- (Không chọn) -'),
                        ),
                        ...vm.dieuList.map((d) {
                          final id = d['sothutund'] as int?;
                          final text = (d['noidung'] ?? '').toString();
                          return DropdownMenuItem<int?>(
                            value: id,
                            child: Text(
                              text,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          );
                        }).toList(),
                      ],
                      onChanged: vm.isLoading ? null : vm.setSelectedDieu,
                    ),
                  ],

                  if (selectedDieuSafe != null) ...[
                    const SizedBox(height: 16),
                    const Text('Chọn KHOẢN (hoặc để trống để thêm khoản mới):'),
                    const SizedBox(height: 6),
                    DropdownButton<int?>(
                      isExpanded: true,
                      value: selectedKhoanSafe,
                      hint: const Text('- Chọn khoản -'),
                      items: [
                        const DropdownMenuItem<int?>(
                          value: null,
                          child: Text('- (Không chọn) -'),
                        ),
                        ...vm.khoanList.map((k) {
                          final id = k['sothutund'] as int?;
                          final text = (k['noidung'] ?? '').toString();
                          return DropdownMenuItem<int?>(
                            value: id,
                            child: Text(
                              text,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          );
                        }).toList(),
                      ],
                      onChanged: vm.isLoading ? null : vm.setSelectedKhoan,
                    ),
                  ],

                  if (selectedKhoanSafe != null) ...[
                    const SizedBox(height: 16),
                    const Text('Chọn ĐIỂM (hoặc để trống để thêm điểm mới):'),
                    const SizedBox(height: 6),
                    DropdownButton<int?>(
                      isExpanded: true,
                      value: selectedDiemSafe,
                      hint: const Text('- Chọn điểm -'),
                      items: [
                        const DropdownMenuItem<int?>(
                          value: null,
                          child: Text('- (Không chọn) -'),
                        ),
                        ...vm.diemList.map((d) {
                          final id = d['sothutund'] as int?;
                          final text = (d['noidung'] ?? '').toString();
                          return DropdownMenuItem<int?>(
                            value: id,
                            child: Text(
                              text,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          );
                        }).toList(),
                      ],
                      onChanged: vm.isLoading ? null : vm.setSelectedDiem,
                    ),
                  ],

                  const SizedBox(height: 16),

                  // ===== loai_muc dropdown =====
                  const Text('Loại mục (bắt buộc):'),
                  const SizedBox(height: 6),
                  DropdownButton<String>(
                    isExpanded: true,
                    value: selectedLoaiMuc,
                    hint: const Text('- Chọn loại mục -'),
                    items: loaiMucOptions
                        .map(
                          (x) => DropdownMenuItem<String>(
                        value: x,
                        child: Text(x),
                      ),
                    )
                        .toList(),
                    onChanged: vm.isLoading ? null : vm.setLoaiMuc,
                  ),

                  const SizedBox(height: 12),
                  TextField(
                    controller: vm.kyHieuController,
                    decoration: const InputDecoration(
                      labelText: 'Ký hiệu (VD: CHƯƠNG I / ĐIỀU 1 / KHOẢN 5 / ĐIỂM a)',
                      border: OutlineInputBorder(),
                      hintText: 'VD: KHOẢN 5',
                    ),
                  ),

                  const SizedBox(height: 12),
                  TextField(
                    controller: vm.thuTuController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Thứ tự (bắt buộc - số thứ tự 1,2,3...)',
                      border: OutlineInputBorder(),
                      hintText: 'VD: 5',
                    ),
                  ),

                  const SizedBox(height: 12),
                  TextField(
                    controller: vm.relaController,
                    decoration: const InputDecoration(
                      labelText: 'Từ có liên quan (phân cách bằng ";")',
                      border: OutlineInputBorder(),
                      hintText: 'VD: vượt đèn đỏ; không tuân thủ tín hiệu; vượt tín hiệu đèn',
                    ),
                  ),

                  const SizedBox(height: 12),
                  TextField(
                    controller: vm.noidungController,
                    maxLines: 6,
                    decoration: const InputDecoration(
                      labelText: 'Nội dung mới',
                      border: OutlineInputBorder(),
                    ),
                  ),

                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: vm.isLoading
                        ? null
                        : () async {
                      final missing = selectedSohieuSafe == null ||
                          vm.noidungController.text.trim().isEmpty ||
                          vm.loaiMucController.text.trim().isEmpty ||
                          int.tryParse(vm.thuTuController.text.trim()) == null;

                      if (missing) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              'Thiếu dữ liệu: cần chọn văn bản, nhập nội dung, chọn loại mục và nhập thứ tự (số).',
                            ),
                            backgroundColor: Colors.red,
                          ),
                        );
                        return;
                      }

                      final ok = await vm.addContent();
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(ok ? 'Đã thêm thành công!' : 'Thêm thất bại.'),
                          backgroundColor: ok ? Colors.green : Colors.red,
                        ),
                      );
                    },
                    child: vm.isLoading
                        ? const SizedBox(
                      height: 22,
                      width: 22,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                        : const Text('Thêm nội dung'),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
