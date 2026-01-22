import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

class ChatDetailPage extends StatelessWidget {
  final Map<String, dynamic> chatData;

  const ChatDetailPage({super.key, required this.chatData});

  @override
  Widget build(BuildContext context) {
    final supabase = Supabase.instance.client;

    void deleteChat() async {
      final confirm = await showDialog<bool>(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Xác nhận xoá'),
          content: const Text('Bạn có chắc muốn xoá lịch sử này không?'),
          actions: [
            TextButton(
              child: const Text('Huỷ'),
              onPressed: () => Navigator.pop(context, false),
            ),
            TextButton(
              child: const Text('Xoá'),
              onPressed: () => Navigator.pop(context, true),
            ),
          ],
        ),
      );

      if (confirm == true) {
        await supabase
            .from('lich_su_tro_chuyen')
            .delete()
            .eq('id', chatData['id']);

        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Đã xoá lịch sử trò chuyện.')),
          );
          Navigator.pop(context, true);
        }
      }
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text("Chi tiết trò chuyện"),
        actions: [
          IconButton(
            icon: const Icon(Icons.delete),
            onPressed: deleteChat,
          )
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: ListView(
          children: [
            Text(
              "Câu hỏi:",
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(chatData['cauhoi'] ?? "", style: const TextStyle(fontSize: 16)),

            const SizedBox(height: 24),
            Text(
              "Trả lời:",
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(chatData['traloi'] ?? "", style: const TextStyle(fontSize: 16)),

            const SizedBox(height: 24),
            Text(
              "Thời điểm: ${chatData['thoidiem']?.toString().substring(0, 19)}",
              style: const TextStyle(color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }
}
