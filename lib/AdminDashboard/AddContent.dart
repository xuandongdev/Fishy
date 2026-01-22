import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../ViewModels/AddLawContentVM.dart';

class WebAddContent extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text("Soạn Thảo Nội Dung Chi Tiết"),
        elevation: 0,
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        automaticallyImplyLeading: false,
      ),
      body: Consumer<AddContentVM>(
        builder: (context, vm, child) {
          return Padding(
            padding: const EdgeInsets.all(20.0),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // --- CỘT TRÁI: ĐIỀU HƯỚNG CẤU TRÚC (Chiếm 40%) ---
                Expanded(
                  flex: 2,
                  child: Card(
                    elevation: 2,
                    child: Padding(
                      padding: EdgeInsets.all(15),
                      child: SingleChildScrollView(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text("1. Chọn vị trí cần thêm", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                            Divider(),

                            // Dropdown Văn bản (Kiểu String)
                            _buildDropdown<String>(
                              label: "Văn bản",
                              value: vm.selectedSohieu,
                              items: vm.vanBanList,
                              idKey: 'sohieuvanban',
                              labelKey: 'tenvanban',
                              onChanged: vm.setSelectedSohieu,
                            ),

                            // Các Dropdown cấp con (Kiểu int)
                            if (vm.selectedSohieu != null)
                              _buildDropdown<int>(
                                label: "Chương",
                                value: vm.selectedChuong,
                                items: vm.chuongList,
                                idKey: 'sothutund',
                                labelKey: 'noidung',
                                onChanged: vm.setSelectedChuong,
                              ),

                            if (vm.selectedChuong != null)
                              _buildDropdown<int>(
                                label: "Mục",
                                value: vm.selectedMuc,
                                items: vm.mucList,
                                idKey: 'sothutund',
                                labelKey: 'noidung',
                                onChanged: vm.setSelectedMuc,
                              ),

                            if (vm.selectedChuong != null || vm.selectedMuc != null)
                              _buildDropdown<int>(
                                label: "Điều",
                                value: vm.selectedDieu,
                                items: vm.dieuList,
                                idKey: 'sothutund',
                                labelKey: 'noidung',
                                onChanged: vm.setSelectedDieu,
                              ),

                            if (vm.selectedDieu != null)
                              _buildDropdown<int>(
                                label: "Khoản",
                                value: vm.selectedKhoan,
                                items: vm.khoanList,
                                idKey: 'sothutund',
                                labelKey: 'noidung',
                                onChanged: vm.setSelectedKhoan,
                              ),

                            if (vm.selectedKhoan != null)
                              _buildDropdown<int>(
                                label: "Điểm",
                                value: vm.selectedDiem,
                                items: vm.diemList,
                                idKey: 'sothutund',
                                labelKey: 'noidung',
                                onChanged: vm.setSelectedDiem,
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),

                SizedBox(width: 20),

                // --- CỘT PHẢI: FORM NHẬP LIỆU (Chiếm 60%) ---
                Expanded(
                  flex: 3,
                  child: Card(
                    elevation: 2,
                    child: Padding(
                      padding: EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text("2. Nhập nội dung mới", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Colors.green[700])),
                          SizedBox(height: 5),
                          Text(
                            "Nội dung sẽ được thêm vào cấp con của mục bạn chọn bên trái.",
                            style: TextStyle(fontSize: 12, fontStyle: FontStyle.italic, color: Colors.grey),
                          ),
                          Divider(),
                          SizedBox(height: 10),

                          TextField(
                            controller: vm.noidungController,
                            decoration: InputDecoration(
                              labelText: 'Nội dung chi tiết',
                              border: OutlineInputBorder(),
                              alignLabelWithHint: true,
                              filled: true,
                              fillColor: Colors.grey[50],
                            ),
                            maxLines: 10,
                            minLines: 5,
                          ),
                          SizedBox(height: 20),

                          Row(
                            children: [
                              Expanded(
                                child: TextField(
                                  controller: vm.tocdoMinController,
                                  decoration: InputDecoration(labelText: 'Tốc độ Min (nếu có)', border: OutlineInputBorder()),
                                  keyboardType: TextInputType.number,
                                ),
                              ),
                              SizedBox(width: 20),
                              Expanded(
                                child: TextField(
                                  controller: vm.tocdoMaxController,
                                  decoration: InputDecoration(labelText: 'Tốc độ Max (nếu có)', border: OutlineInputBorder()),
                                  keyboardType: TextInputType.number,
                                ),
                              ),
                            ],
                          ),
                          SizedBox(height: 30),

                          Align(
                            alignment: Alignment.centerRight,
                            child: vm.isLoading
                                ? CircularProgressIndicator()
                                : ElevatedButton.icon(
                              style: ElevatedButton.styleFrom(
                                padding: EdgeInsets.symmetric(horizontal: 30, vertical: 20),
                                backgroundColor: Colors.green,
                                foregroundColor: Colors.white,
                              ),
                              icon: Icon(Icons.add_circle),
                              label: Text("THÊM VÀO DATABASE"),
                              onPressed: () async {
                                if (vm.selectedSohieu == null) {
                                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Chưa chọn văn bản!")));
                                  return;
                                }
                                bool success = await vm.addContent();
                                if (success) {
                                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Thêm thành công!")));
                                } else {
                                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Lỗi!")));
                                }
                              },
                            ),
                          )
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

  // --- Widget helper Dropdown (Đã sửa lỗi Generic T) ---
  Widget _buildDropdown<T>({
    required String label,
    required T? value,
    required List<Map<String, dynamic>> items,
    required String idKey,
    required String labelKey,
    required void Function(T?) onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 15.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontWeight: FontWeight.w500)),
          SizedBox(height: 5),
          Container(
            padding: EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              border: Border.all(color: Colors.grey),
              borderRadius: BorderRadius.circular(5),
            ),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<T>(
                value: value,
                isExpanded: true,
                hint: Text("Chọn $label..."),
                items: items.map((e) {
                  // Xử lý hiển thị text quá dài để không vỡ layout
                  String text = e[labelKey].toString();
                  if (text.length > 80) text = text.substring(0, 80) + '...';

                  return DropdownMenuItem<T>(
                    value: e[idKey] as T,
                    child: Text(text),
                  );
                }).toList(),
                onChanged: onChanged,
              ),
            ),
          ),
        ],
      ),
    );
  }
}