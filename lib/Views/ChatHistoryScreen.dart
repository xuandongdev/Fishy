import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fishy/ViewModels/AuthVM.dart';
import 'package:fishy/ViewModels/ChatHistoryVM.dart';
import 'ChatHistoryDetail.dart';

class ChatHistoryScreen extends StatelessWidget {
  const ChatHistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final authVM = Provider.of<AuthViewModel>(context);
    final userId = authVM.userData?['userid'];

    return ChangeNotifierProvider(
      create: (_) {
        final vm = ChatHistoryViewModel();
        if (userId != null) vm.fetchChatHistory(userId);
        return vm;
      },
      child: Consumer<ChatHistoryViewModel>(
        builder: (context, chatVM, _) {
          return Scaffold(
            appBar: AppBar(
              title: const Text('Lịch sử trò chuyện'),
            ),
            body: chatVM.isLoading
                ? const Center(child: CircularProgressIndicator())
                : ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: chatVM.chatHistory.length,
              itemBuilder: (context, index) {
                final chat = chatVM.chatHistory[index];
                final backgroundColor =
                index % 2 == 0 ? Colors.white : Colors.grey[100];

                return GestureDetector(
                  onTap: () async {
                    final isDeleted = await Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => ChatDetailPage(chatData: chat),
                      ),
                    );
                    if (isDeleted == true) {
                      final userId = Provider.of<AuthViewModel>(context,
                          listen: false)
                          .userData?['userid'];
                      if (userId != null) {
                        chatVM.fetchChatHistory(userId);
                      }
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
                          "Trả lời: ${chat['traloi']}",
                          style: const TextStyle(
                              fontWeight: FontWeight.bold),
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          "Câu hỏi: ${chat['cauhoi']}",
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(color: Colors.black87),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          "Thời điểm: ${chat['thoidiem']?.toString().substring(0, 19)}",
                          style: const TextStyle(
                              fontSize: 12, color: Colors.grey),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}
