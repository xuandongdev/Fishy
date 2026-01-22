import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../Models/AddLawModel.dart';
import '../ViewModels/addlawVM.dart';

class WebAddLaw extends StatefulWidget {
  @override
  _WebAddLawState createState() => _WebAddLawState();
}

class _WebAddLawState extends State<WebAddLaw> {
  final _formKey = GlobalKey<FormState>();
  final _soHieuController = TextEditingController();
  final _tenVanBanController = TextEditingController();
  final _ngayKyController = TextEditingController();
  final _ngayHieuLucController = TextEditingController();

  Future<void> _selectDate(BuildContext context, TextEditingController controller) async {
    final DateTime? picked = await showDatePicker(
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

  @override
  Widget build(BuildContext context) {
    final vm = Provider.of<AddLawVM>(context);

    return Scaffold(
      appBar: AppBar(
        title: Text("Thêm Văn Bản Pháp Luật Mới"),
        elevation: 0,
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        automaticallyImplyLeading: false,
      ),
      body: SingleChildScrollView(
        padding: EdgeInsets.all(30),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Hàng 1: Số hiệu & Tên văn bản
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    flex: 1,
                    child: TextFormField(
                      controller: _soHieuController,
                      decoration: InputDecoration(labelText: 'Số hiệu văn bản', border: OutlineInputBorder()),
                      validator: (v) => v!.isEmpty ? 'Nhập số hiệu' : null,
                    ),
                  ),
                  SizedBox(width: 20),
                  Expanded(
                    flex: 2,
                    child: TextFormField(
                      controller: _tenVanBanController,
                      decoration: InputDecoration(labelText: 'Tên/Trích yếu văn bản', border: OutlineInputBorder()),
                      validator: (v) => v!.isEmpty ? 'Nhập tên văn bản' : null,
                    ),
                  ),
                ],
              ),
              SizedBox(height: 20),

              // Hàng 2: Ngày ký & Ngày hiệu lực & Trạng thái
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _ngayKyController,
                      decoration: InputDecoration(labelText: 'Ngày ký', icon: Icon(Icons.calendar_today), border: OutlineInputBorder()),
                      readOnly: true,
                      onTap: () => _selectDate(context, _ngayKyController),
                    ),
                  ),
                  SizedBox(width: 20),
                  Expanded(
                    child: TextFormField(
                      controller: _ngayHieuLucController,
                      decoration: InputDecoration(labelText: 'Ngày hiệu lực', icon: Icon(Icons.event_available), border: OutlineInputBorder()),
                      readOnly: true,
                      onTap: () => _selectDate(context, _ngayHieuLucController),
                    ),
                  ),
                  SizedBox(width: 20),
                  Expanded(
                    child: DropdownButtonFormField<int>(
                      value: vm.selectedTrangThai,
                      decoration: InputDecoration(labelText: 'Trạng thái', border: OutlineInputBorder()),
                      items: vm.trangThaiList.map((e) => DropdownMenuItem<int>(
                        value: e['matrangthai'],
                        child: Text(e['tentrangthai']),
                      )).toList(),
                      onChanged: vm.setSelectedTrangThai,
                    ),
                  ),
                ],
              ),
              SizedBox(height: 20),

              // Hàng 3: Cơ quan & Loại văn bản
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<int>(
                      value: vm.selectedCoQuan,
                      decoration: InputDecoration(labelText: 'Cơ quan ban hành', border: OutlineInputBorder()),
                      items: vm.coQuanList.map((e) => DropdownMenuItem<int>(
                        value: e['macoquan'],
                        child: Text(e['tencoquan']),
                      )).toList(),
                      onChanged: vm.setSelectedCoQuan,
                    ),
                  ),
                  SizedBox(width: 20),
                  Expanded(
                    child: DropdownButtonFormField<int>(
                      value: vm.selectedLoaiVanBan,
                      decoration: InputDecoration(labelText: 'Loại văn bản', border: OutlineInputBorder()),
                      items: vm.loaiVanBanList.map((e) => DropdownMenuItem<int>(
                        value: e['maloai'],
                        child: Text(e['tenloai']),
                      )).toList(),
                      onChanged: vm.setSelectedLoaiVanBan,
                    ),
                  ),
                ],
              ),
              SizedBox(height: 40),

              // Nút Submit
              Center(
                child: SizedBox(
                  width: 200,
                  height: 50,
                  child: ElevatedButton.icon(
                    icon: Icon(Icons.save),
                    label: Text("LƯU DỮ LIỆU"),
                    style: ElevatedButton.styleFrom(backgroundColor: Colors.blueAccent, foregroundColor: Colors.white),
                    onPressed: () async {
                      if (_formKey.currentState!.validate() &&
                          vm.selectedCoQuan != null &&
                          vm.selectedLoaiVanBan != null &&
                          vm.selectedTrangThai != null) {

                        final newLaw = AddLawModel(
                          sohieu: _soHieuController.text,
                          tenVanBan: _tenVanBanController.text,
                          ngayKy: _ngayKyController.text,
                          ngayHieuLuc: _ngayHieuLucController.text,
                          matrangthai: vm.selectedTrangThai!,
                          macoquan: vm.selectedCoQuan!,
                          maloai: vm.selectedLoaiVanBan!,
                        );

                        bool success = await vm.addLaw(newLaw);
                        if (success) {
                          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Thêm thành công!')));
                          // Clear form logic here
                        } else {
                          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Lỗi khi thêm!')));
                        }
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
}