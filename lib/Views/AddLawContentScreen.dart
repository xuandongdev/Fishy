import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../ViewModels/AddLawContentVM.dart';

class AddLawContentScreen extends StatelessWidget {
  const AddLawContentScreen({super.key, required String sohieuvanban});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AddContentVM(),
      child: Consumer<AddContentVM>(
        builder: (context, vm, child) {
          return Scaffold(
            appBar: AppBar(title: Text('Thêm Nội Dung Văn Bản')),
            body: Padding(
              padding: const EdgeInsets.all(16.0),
              child: ListView(
                children: [
                  const Text('Chọn số hiệu văn bản:'),
                  SizedBox(
                    height: 55,
                    child: DropdownButton<String>(
                      isExpanded: true,
                      value: vm.selectedSohieu,
                      hint: const Text('- Chọn số hiệu -'),
                      items: vm.vanBanList.map((vb) {
                        return DropdownMenuItem<String>(
                          value: vb['sohieuvanban'],
                          child: Text('${vb['sohieuvanban']} - ${vb['tenvanban']}'),
                        );
                      }).toList(),
                      onChanged: vm.setSelectedSohieu,
                    ),
                  ),

                  if (vm.selectedSohieu != null) ...[
                    const SizedBox(height: 16),
                    const Text('Chọn CHƯƠNG (hoặc để thêm chương mới):'),
                    DropdownButton<int>(
                      isExpanded: true,
                      value: vm.selectedChuong,
                      hint: const Text('- Chọn chương -'),
                      items: [
                        const DropdownMenuItem<int>(
                          value: null,
                          child: Text('- Chọn chương -'),
                        ),
                        ...vm.chuongList.map((c) {
                          return DropdownMenuItem<int>(
                            value: c['sothutund'],
                            child: Text(c['noidung']),
                          );
                        }).toList(),
                      ],
                      onChanged: vm.setSelectedChuong,
                    ),
                  ],

                  if (vm.selectedChuong != null) ...[
                    const SizedBox(height: 16),
                    const Text('Chọn MỤC (hoặc thêm mục mới/ không chọn để thêm điều mới):'),
                    DropdownButton<int>(
                      isExpanded: true,
                      value: vm.selectedMuc,
                      hint: const Text('- Chọn mục -'),
                      items: [
                        const DropdownMenuItem<int>(
                          value: null,
                          child: Text('- Chọn mục -'),
                        ),
                        ...vm.mucList.map((m) {
                          return DropdownMenuItem<int>(
                            value: m['sothutund'],
                            child: Text(m['noidung']),
                          );
                        }).toList(),
                      ],
                      onChanged: vm.setSelectedMuc,
                    ),
                  ],

                  if (vm.selectedMuc != null || vm.selectedChuong != null) ...[
                    const SizedBox(height: 16),
                    const Text('Chọn ĐIỀU (hoặc thêm điều luật mới):'),
                    DropdownButton<int>(
                      isExpanded: true,
                      value: vm.selectedDieu,
                      hint: const Text('- Chọn điều -'),
                      items: [
                        const DropdownMenuItem<int>(
                          value: null,
                          child: Text('- Chọn điều -'),
                        ),
                        ...vm.dieuList.map((d) {
                          return DropdownMenuItem<int>(
                            value: d['sothutund'],
                            child: Text(d['noidung']),
                          );
                        }).toList(),
                      ],
                      onChanged: vm.setSelectedDieu,
                    ),
                  ],

                  if (vm.selectedDieu != null) ...[
                    const SizedBox(height: 16),
                    const Text('Chọn KHOẢN (hoặc thêm khoản luật mới):'),
                    DropdownButton<int>(
                      isExpanded: true,
                      value: vm.selectedKhoan,
                      hint: const Text('- Chọn khoản -'),
                      items: [
                        const DropdownMenuItem<int>(
                          value: null,
                          child: Text('- Chọn khoản -'),
                        ),
                        ...vm.khoanList.map((k) {
                          return DropdownMenuItem<int>(
                            value: k['sothutund'],
                            child: Text(k['noidung']),
                          );
                        }).toList(),
                      ],
                      onChanged: vm.setSelectedKhoan,
                    ),
                  ],

                  if (vm.selectedKhoan != null) ...[
                    const SizedBox(height: 16),
                    const Text('Chọn ĐIỂM(hoặc thêm điểm luật mới):'),
                    DropdownButton<int>(
                      isExpanded: true,
                      value: vm.selectedDiem,
                      hint: const Text('- Chọn điểm -'),
                      items: [
                        const DropdownMenuItem<int>(
                          value: null,
                          child: Text('- Chọn điểm -'),
                        ),
                        ...vm.diemList.map((d) {
                          return DropdownMenuItem<int>(
                            value: d['sothutund'],
                            child: Text(d['noidung']),
                          );
                        }).toList(),
                      ],
                      onChanged: vm.setSelectedDiem,
                    ),
                  ],

                  const SizedBox(height: 16),
                  TextField(
                    controller: vm.noidungController,
                    maxLines: 5,
                    decoration: const InputDecoration(
                      labelText: 'Nội dung mới',
                      border: OutlineInputBorder(),
                    ),
                  ),

                  const SizedBox(height: 16),
                  TextField(
                    controller: vm.tocdoMinController,
                    keyboardType: TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Tốc độ tối thiểu (tùy chọn)',
                      border: OutlineInputBorder(),
                    ),
                  ),

                  const SizedBox(height: 16),
                  TextField(
                    controller: vm.tocdoMaxController,
                    keyboardType: TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Tốc độ tối đa (tùy chọn)',
                      border: OutlineInputBorder(),
                    ),
                  ),

                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: vm.isLoading
                        ? null
                        : () async {
                      if (vm.selectedSohieu == null ||
                          vm.noidungController.text.trim().isEmpty) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Vui lòng chọn văn bản và nhập nội dung.'),
                            backgroundColor: Colors.red,
                          ),
                        );
                        return;
                      }

                      final result = await vm.addContent();
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(result ? 'Đã thêm thành công!' : 'Thêm thất bại.'),
                        backgroundColor: result ? Colors.green : Colors.red,
                      ));
                    },
                    child: vm.isLoading
                        ? const CircularProgressIndicator()
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
