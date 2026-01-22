import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../ViewModels/LawVM.dart';
import 'LawDetailScreen.dart';
import 'AddLawScreen.dart';

class LawManageScreen extends StatefulWidget {
  const LawManageScreen({super.key});

  @override
  State<LawManageScreen> createState() => _LawManageScreenState();
}

class _LawManageScreenState extends State<LawManageScreen> {
  int _selectedTrangThai = 0;

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
          final filteredVanBan = _selectedTrangThai == 0
              ? lawVM.vanBan
              : lawVM.vanBan
              .where((vb) => vb.matrangthai == _selectedTrangThai)
              .toList();

          return Scaffold(
            appBar: AppBar(
              title: const Text("Quản lý văn bản pháp luật"),
              actions: [
                PopupMenuButton<int>(
                  onSelected: (value) {
                    setState(() {
                      _selectedTrangThai = value;
                    });
                  },
                  itemBuilder: (context) => [
                    const PopupMenuItem(
                      value: 1,
                      child: Text("Còn hiệu lực"),
                    ),
                    const PopupMenuItem(
                      value: 2,
                      child: Text("Hết hiệu lực"),
                    ),
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
                final backgroundColor = index % 2 == 0
                    ? Colors.white
                    : Colors.grey[100];

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
                    if(result == true){
                      lawVM.fetchVanBan();
                    }
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
                        Text("Ngày ký: ${vb.ngayKy}", ),
                        const SizedBox(height: 4),
                        Text("Ngày hiệu lực: ${vb.ngayCoHieuLuc}"),
                        const SizedBox(height: 4),
                        Text("Trạng thái: ${vb.matrangthai == 2 ? 'Hết hiệu lực' : 'Còn hiệu lực'}"),
                        const SizedBox(height: 4),
                        Align(
                          alignment: Alignment.centerRight,
                          child: IconButton(
                            icon: Icon(
                              vb.matrangthai == 1
                                  ? Icons.toggle_on
                                  : Icons.toggle_off,
                              color: vb.matrangthai == 1
                                  ? Colors.green
                                  : Colors.red,
                              size: 30,
                            ),
                            onPressed: () async {
                              final newTrangThai = vb.matrangthai == 1 ? 2 : 1;
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
            floatingActionButton: SizedBox(
              width: 45,
              height: 45,
              child: FloatingActionButton(
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (context) => AddLawScreen(),
                    ),
                  );
                },
                child: const Icon(Icons.add),
              ),
            )
          );
        },
      ),
    );
  }
}