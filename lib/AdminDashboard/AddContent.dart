import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../ViewModels/AddLawContentVM.dart';

class WebAddContent extends StatelessWidget {
  const WebAddContent({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Soạn Thảo Nội Dung Chi Tiết"),
        elevation: 0,
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        automaticallyImplyLeading: false,
      ),
      body: Consumer<AddContentVM>(
        builder: (context, vm, child) {
          const loaiMucOptions = <String>[
            'CHUONG',
            'MUC',
            'DIEU',
            'KHOAN',
            'DIEM',
          ];

          final currentLoai = vm.loaiMucController.text.trim().toUpperCase();
          final String? selectedLoaiMuc =
              loaiMucOptions.contains(currentLoai) ? currentLoai : null;

          return Padding(
            padding: const EdgeInsets.all(20.0),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // --- CỘT TRÁI: ĐIỀU HƯỚNG CẤU TRÚC (40%) ---
                Expanded(
                  flex: 2,
                  child: Card(
                    elevation: 2,
                    child: Padding(
                      padding: const EdgeInsets.all(15),
                      child: SingleChildScrollView(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              "1. Chọn vị trí cần thêm",
                              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                            ),
                            const Divider(),

                            // Dropdown Văn bản
                            _buildDropdownWithNull<String>(
                              label: "Văn bản",
                              value: vm.selectedSohieu,
                              items: vm.vanBanList,
                              idKey: 'sohieuvanban',
                              labelKey: 'tenvanban',
                              onChanged: vm.isLoading ? null : vm.setSelectedSohieu,
                              nullLabel: "- Chọn văn bản -",
                              showNullItem: false, // văn bản bắt buộc nên không cần null item
                            ),

                            if (vm.selectedSohieu != null)
                              _buildDropdownWithNull<int>(
                                label: "Chương",
                                value: vm.selectedChuong,
                                items: vm.chuongList,
                                idKey: 'sothutund',
                                labelKey: 'noidung',
                                onChanged: vm.isLoading ? null : vm.setSelectedChuong,
                                nullLabel: "- (Không chọn) -",
                                showNullItem: true,
                              ),

                            if (vm.selectedChuong != null)
                              _buildDropdownWithNull<int>(
                                label: "Mục",
                                value: vm.selectedMuc,
                                items: vm.mucList,
                                idKey: 'sothutund',
                                labelKey: 'noidung',
                                onChanged: vm.isLoading ? null : vm.setSelectedMuc,
                                nullLabel: "- (Không chọn) -",
                                showNullItem: true,
                              ),

                            if (vm.selectedChuong != null)
                              _buildDropdownWithNull<int>(
                                label: "Điều",
                                value: vm.selectedDieu,
                                items: vm.dieuList,
                                idKey: 'sothutund',
                                labelKey: 'noidung',
                                onChanged: vm.isLoading ? null : vm.setSelectedDieu,
                                nullLabel: "- (Không chọn) -",
                                showNullItem: true,
                              ),

                            if (vm.selectedDieu != null)
                              _buildDropdownWithNull<int>(
                                label: "Khoản",
                                value: vm.selectedKhoan,
                                items: vm.khoanList,
                                idKey: 'sothutund',
                                labelKey: 'noidung',
                                onChanged: vm.isLoading ? null : vm.setSelectedKhoan,
                                nullLabel: "- (Không chọn) -",
                                showNullItem: true,
                              ),

                            if (vm.selectedKhoan != null)
                              _buildDropdownWithNull<int>(
                                label: "Điểm",
                                value: vm.selectedDiem,
                                items: vm.diemList,
                                idKey: 'sothutund',
                                labelKey: 'noidung',
                                onChanged: vm.isLoading ? null : vm.setSelectedDiem,
                                nullLabel: "- (Không chọn) -",
                                showNullItem: true,
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),

                const SizedBox(width: 20),

                // --- CỘT PHẢI: FORM NHẬP LIỆU (60%) ---
                Expanded(
                  flex: 3,
                  child: Card(
                    elevation: 2,
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            "2. Nhập nội dung mới",
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 16,
                              color: Colors.green[700],
                            ),
                          ),
                          const SizedBox(height: 5),
                          const Text(
                            "Nội dung sẽ được thêm theo loai_muc bạn chọn, và gắn parent theo cây bên trái.",
                            style: TextStyle(fontSize: 12, fontStyle: FontStyle.italic, color: Colors.grey),
                          ),
                          const Divider(),
                          const SizedBox(height: 10),

                          // ===== loai_muc dropdown =====
                          const Text("Loại mục (bắt buộc)"),
                          const SizedBox(height: 6),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10),
                            decoration: BoxDecoration(
                              border: Border.all(color: Colors.grey),
                              borderRadius: BorderRadius.circular(5),
                            ),
                            child: DropdownButtonHideUnderline(
                              child: DropdownButton<String>(
                                value: selectedLoaiMuc,
                                isExpanded: true,
                                hint: const Text("- Chọn loại mục -"),
                                items: loaiMucOptions
                                    .map((x) => DropdownMenuItem<String>(
                                          value: x,
                                          child: Text(x),
                                        ))
                                    .toList(),
                                onChanged: vm.isLoading ? null : vm.setLoaiMuc,
                              ),
                            ),
                          ),

                          const SizedBox(height: 12),

                          // ky_hieu + thu_tu
                          Row(
                            children: [
                              Expanded(
                                flex: 2,
                                child: TextField(
                                  controller: vm.kyHieuController,
                                  decoration: const InputDecoration(
                                    labelText: 'Ký hiệu (VD: ĐIỀU 1, KHOẢN 5, ĐIỂM a...)',
                                    border: OutlineInputBorder(),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 20),
                              Expanded(
                                flex: 1,
                                child: TextField(
                                  controller: vm.thuTuController,
                                  decoration: const InputDecoration(
                                    labelText: 'thứ tự (VD: 1,2,3..)',
                                    border: OutlineInputBorder(),
                                  ),
                                  keyboardType: TextInputType.number,
                                ),
                              ),
                            ],
                          ),

                          const SizedBox(height: 12),

                          // rela
                          TextField(
                            controller: vm.relaController,
                            decoration: InputDecoration(
                              labelText: 'Từ có liên quan (phân cách bằng ";")',
                              border: const OutlineInputBorder(),
                              filled: true,
                              fillColor: Colors.grey[50],
                              hintText: 'VD: vượt đèn đỏ; không tuân thủ tín hiệu; vượt tín hiệu đèn',
                            ),
                          ),

                          const SizedBox(height: 12),

                          // noidung
                          TextField(
                            controller: vm.noidungController,
                            decoration: InputDecoration(
                              labelText: 'Nội dung chi tiết',
                              border: const OutlineInputBorder(),
                              alignLabelWithHint: true,
                              filled: true,
                              fillColor: Colors.grey[50],
                            ),
                            maxLines: 12,
                            minLines: 6,
                          ),

                          const SizedBox(height: 20),

                          Align(
                            alignment: Alignment.centerRight,
                            child: vm.isLoading
                                ? const CircularProgressIndicator()
                                : ElevatedButton.icon(
                                    style: ElevatedButton.styleFrom(
                                      padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 20),
                                      backgroundColor: Colors.green,
                                      foregroundColor: Colors.white,
                                    ),
                                    icon: const Icon(Icons.add_circle),
                                    label: const Text("THÊM VÀO DATABASE"),
                                    onPressed: () async {
                                      if (vm.selectedSohieu == null) {
                                        ScaffoldMessenger.of(context).showSnackBar(
                                          const SnackBar(content: Text("Chưa chọn văn bản!")),
                                        );
                                        return;
                                      }

                                      // validate nhanh (VM cũng validate thêm)
                                      if (vm.noidungController.text.trim().isEmpty ||
                                          vm.loaiMucController.text.trim().isEmpty ||
                                          int.tryParse(vm.thuTuController.text.trim()) == null) {
                                        ScaffoldMessenger.of(context).showSnackBar(
                                          const SnackBar(
                                            content: Text("Thiếu: loại mục, thứ tự (số), hoặc nội dung!"),
                                          ),
                                        );
                                        return;
                                      }

                                      final success = await vm.addContent();
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        SnackBar(
                                          content: Text(success ? "Thêm thành công!" : "Lỗi!"),
                                        ),
                                      );
                                    },
                                  ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  // ===== Dropdown helper: hỗ trợ null item ("- (Không chọn) -") =====
  Widget _buildDropdownWithNull<T>({
    required String label,
    required T? value,
    required List<Map<String, dynamic>> items,
    required String idKey,
    required String labelKey,
    required void Function(T?)? onChanged,
    required String nullLabel,
    required bool showNullItem,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 15.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontWeight: FontWeight.w500)),
          const SizedBox(height: 5),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              border: Border.all(color: Colors.grey),
              borderRadius: BorderRadius.circular(5),
            ),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<T?>(
                value: value,
                isExpanded: true,
                hint: Text("Chọn $label..."),
                items: [
                  if (showNullItem)
                    DropdownMenuItem<T?>(
                      value: null,
                      child: Text(nullLabel),
                    ),
                  ...items.map((e) {
                    String text = (e[labelKey] ?? '').toString();
                    if (text.length > 80) text = '${text.substring(0, 80)}...';

                    return DropdownMenuItem<T?>(
                      value: e[idKey] as T?,
                      child: Text(text),
                    );
                  }).toList(),
                ],
                onChanged: onChanged,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
