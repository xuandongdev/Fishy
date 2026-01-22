import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../Models/LawContentModel.dart';
import '../ViewModels/AuthVM.dart';
import '../ViewModels/LawVM.dart';

class EditContentScreen extends StatefulWidget {
  final LawContentModel content;

  const EditContentScreen({super.key, required this.content});

  @override
  State<EditContentScreen> createState() => _EditContentScreenState();
}

class _EditContentScreenState extends State<EditContentScreen> {
  final _formKey = GlobalKey<FormState>();
  late TextEditingController _newContentController;
  late LawContentModel _currentContent;

  @override
  void initState() {
    super.initState();
    _newContentController = TextEditingController(text: widget.content.noidung);
    _currentContent = widget.content;
    _fetchContentWithEditor();
  }

  Future<void> _fetchContentWithEditor() async {
    final viewModel = Provider.of<LawViewModel>(context, listen: false);
    final content = await viewModel.fetchContentWithEditor(_currentContent.sothutund);

    if (content != null) {
      setState(() {
        _currentContent = content;
      });
    }
  }

  Future<void> _saveContent() async {
    if (!_formKey.currentState!.validate()) return;

    final updatedContent = _newContentController.text.trim();
    final lawVM = Provider.of<LawViewModel>(context, listen: false);
    final authVM = Provider.of<AuthViewModel>(context, listen: false);

    final modifiedById = authVM.userData?['userid'];

    final updatedModel = await lawVM.updateLawContent(
      _currentContent.sothutund,
      updatedContent,
      modifiedBy: modifiedById,
    );

    if (updatedModel != null) {
      setState(() {
        _currentContent = updatedModel;
        _newContentController.text = _currentContent.noidung;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Cập nhật nội dung thành công'),
          backgroundColor: Colors.green,
        ),
      );
      Navigator.pop(context, true);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Cập nhật nội dung thất bại'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }


  @override
  Widget build(BuildContext context) {
    final isLoading = Provider.of<LawViewModel>(context).isLoading;
    return Scaffold(
      resizeToAvoidBottomInset: true,
      appBar: AppBar(title: const Text("Chỉnh sửa nội dung")),
      body: isLoading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                "Nội dung cũ:",
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.grey[200],
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  _currentContent.noidung,
                  style: const TextStyle(fontSize: 15),
                ),
              ),
              const SizedBox(height: 24),
              const Text(
                "Nội dung mới:",
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              TextFormField(
                controller: _newContentController,
                maxLines: null,
              ),
              const SizedBox(height: 24),
              Text(
                "Người sửa: ${_currentContent.modified_by_name ?? 'Chưa cập nhật'}",
                style: const TextStyle(fontSize: 16),
              ),
              const SizedBox(height: 8),
              Text(
                "Thời gian sửa: ${_currentContent.modified_at != null ? DateFormat('yyyy-MM-dd HH:mm:ss').format(_currentContent.modified_at!.toLocal()) : 'Chưa cập nhật'}",
                style: const TextStyle(fontSize: 16),
              ),
            ],
          ),
        ),
      ),
      bottomNavigationBar: Padding(
        padding: const EdgeInsets.all(16),
        child: ElevatedButton.icon(
          icon: const Icon(Icons.save),
          label: const Text("Lưu"),
          onPressed: _saveContent,
          style: ElevatedButton.styleFrom(
            minimumSize: const Size.fromHeight(50),
          ),
        ),
      ),
    );
  }
}