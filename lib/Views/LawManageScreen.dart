import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';

import '../ViewModels/LawVM.dart';
import '../Services/EmbeddingService.dart'; // BỔ SUNG IMPORT SERVICE
import 'LawDetailScreen.dart';
import 'AddLawScreen.dart';

class LawManageScreen extends StatefulWidget {
  const LawManageScreen({super.key});

  @override
  State<LawManageScreen> createState() => _LawManageScreenState();
}

class _LawManageScreenState extends State<LawManageScreen> {
  static const String TT_ALL = 'ALL';
  static const String TT_CON = 'CÒN HIỆU LỰC';
  static const String TT_HET = 'HẾT HIỆU LỰC';

  String _selectedTrangThai = TT_ALL;

  String _fmtDate(dynamic d) {
    if (d == null) return '';
    if (d is DateTime) return DateFormat('yyyy-MM-dd').format(d);
    return d.toString().split(' ').first;
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider<LawViewModel>(
      create: (_) {
        final vm = LawViewModel();
        vm.fetchVanBan();
        return vm;
      },
      child: Consumer<LawViewModel>(
        builder: (context, lawVM, _) {
          final filteredVanBan = _selectedTrangThai == TT_ALL
              ? lawVM.vanBan
              : lawVM.vanBan
                  .where((vb) => vb.trangthai == _selectedTrangThai)
                  .toList();

          return Scaffold(
            appBar: AppBar(
              title: const Text("Quản lý văn bản pháp luật"),
              actions: [
                PopupMenuButton<String>(
                  onSelected: (v) => setState(() => _selectedTrangThai = v),
                  itemBuilder: (context) => const [
                    PopupMenuItem(value: TT_ALL, child: Text("Tất cả")),
                    PopupMenuItem(value: TT_CON, child: Text(TT_CON)),
                    PopupMenuItem(value: TT_HET, child: Text(TT_HET)),
                  ],
                  icon: const Icon(Icons.filter_list),
                ),
              ],
            ),
            body: lawVM.isLoading
                ? const Center(child: CircularProgressIndicator())
                : filteredVanBan.isEmpty
                    ? const Center(child: Text("Không có văn bản nào."))
                    : ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: filteredVanBan.length,
                        itemBuilder: (context, index) {
                          final vb = filteredVanBan[index];
                          final backgroundColor =
                              index % 2 == 0 ? Colors.white : Colors.grey[100];

                          final isConHieuLuc = vb.trangthai == TT_CON;

                          return InkWell(
                            onTap: () async {
                              final result = await Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (_) => ChangeNotifierProvider.value(
                                    value: lawVM,
                                    child: LawDetailScreen(law: vb),
                                  ),
                                ),
                              );
                              if (result == true) lawVM.fetchVanBan();
                            },
                            child: Container(
                              padding: const EdgeInsets.all(12),
                              margin: const EdgeInsets.symmetric(vertical: 6),
                              decoration: BoxDecoration(
                                color: backgroundColor,
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(color: Colors.grey.shade300),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    vb.ten,
                                    style: const TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 15,
                                    ),
                                  ),
                                  const SizedBox(height: 6),
                                  Text("Số hiệu: ${vb.sohieu}"),
                                  const SizedBox(height: 4),
                                  Text("Ngày ký: ${_fmtDate(vb.ngayKy)}"),
                                  const SizedBox(height: 4),
                                  Text("Ngày hiệu lực: ${_fmtDate(vb.ngayCoHieuLuc)}"),
                                  const SizedBox(height: 4),
                                  Text("Trạng thái: ${vb.trangthai}"),
                                  const SizedBox(height: 4),
                                  Align(
                                    alignment: Alignment.centerRight,
                                    child: IconButton(
                                      icon: Icon(
                                        isConHieuLuc ? Icons.toggle_on : Icons.toggle_off,
                                        color: isConHieuLuc ? Colors.green : Colors.red,
                                        size: 30,
                                      ),
                                      onPressed: () async {
                                        final newTrangThai = isConHieuLuc ? TT_HET : TT_CON;
                                        await lawVM.updateTrangThai(vb.sohieu, newTrangThai);
                                      },
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
            // --- CỤM NÚT BẤM MỚI Ở GÓC DƯỚI ---
            floatingActionButton: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                // NÚT SYNC VECTOR
                SizedBox(
                  width: 45,
                  height: 45,
                  child: FloatingActionButton(
                    heroTag: 'sync_btn', // Cần có heroTag để tránh lỗi trùng lặp hiệu ứng
                    backgroundColor: Colors.blue,
                    onPressed: () async {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Đang tiến hành nhúng Vector... Xem Terminal!')),
                      );
                      
                      await EmbeddingService.generateAndUpdateAllEmbeddings();
                      
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Hoàn tất đồng bộ Vector!')),
                        );
                      }
                    },
                    child: const Icon(Icons.sync, color: Colors.white),
                  ),
                ),
                
                const SizedBox(width: 12), // Khoảng cách giữa 2 nút
                
                // NÚT ADD VĂN BẢN
                SizedBox(
                  width: 45,
                  height: 45,
                  child: FloatingActionButton(
                    heroTag: 'add_btn',
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => AddLawScreen()),
                      );
                    },
                    child: const Icon(Icons.add),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}