import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

// Import các ViewModel
import 'package:fishy/ViewModels/AddLawContentVM.dart';
import 'package:fishy/ViewModels/AddLawVM.dart';
import 'package:fishy/ViewModels/ChatVM.dart';
import 'package:fishy/ViewModels/AuthVM.dart';
import 'package:fishy/ViewModels/ChatHistoryVM.dart';
import 'package:fishy/ViewModels/LawVM.dart';
import 'package:fishy/ViewModels/LoginVM.dart';
import 'package:fishy/ViewModels/ThemeVM.dart';

// Import các Views
import 'package:fishy/Views/LawManageScreen.dart';
import 'package:fishy/Views/ChatScreen.dart';
import 'package:fishy/Views/LoginScreen.dart';
import 'package:fishy/Views/AddLawContentScreen.dart';
import 'package:fishy/Views/AddLawScreen.dart';
import 'package:fishy/Views/ChatHistoryScreen.dart';
import 'package:fishy/Views/EditContentScreen.dart';
import 'package:fishy/Views/LawDetailScreen.dart';
import 'package:fishy/Views/LogoutScreen.dart';
import 'package:fishy/Views/SettingScreen.dart';
import 'package:fishy/Views/SignupScreen.dart';

// Import Models & Themes
import 'Models/LawContentModel.dart';
import 'Models/LawModel.dart';
import 'Themes/ThemeData.dart';

// QUAN TRỌNG: Import Service để lấy link Dynamic
import 'package:fishy/Services/ChatService.dart';
import 'package:fishy/Services/LocalNotiService.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // 1. Load biến môi trường
  await dotenv.load(fileName: ".env");

  // 2. Khởi tạo Supabase
  // Nên dùng biến môi trường để linh hoạt giữa Local và Cloud
  await Supabase.initialize(
    url: dotenv.get('SUPABASE_URL', fallback: 'YOUR_SUPABASE_URL'),
    anonKey: dotenv.get('SUPABASE_ANON_KEY', fallback: 'YOUR_ANON_KEY'),
  );

  // 3. KHỞI TẠO URL API (Lấy link Ngrok từ Supabase)
  // Bước này đảm bảo ChatService có link đúng trước khi vào màn hình Chat
  await ChatService.initializeApiUrl();
  await LocalNotiService.init();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthViewModel()),
        ChangeNotifierProvider(create: (_) => LoginViewModel()),
        ChangeNotifierProvider(create: (_) => ChatViewModel()),
        ChangeNotifierProvider(create: (_) => ThemeNotifier()),
        ChangeNotifierProvider(create: (_) => AddLawVM()),
        ChangeNotifierProvider(create: (_) => AddContentVM()),
        ChangeNotifierProvider(create: (_) => LawViewModel()),
        ChangeNotifierProvider(create: (_) => ChatHistoryViewModel()),
      ],
      child: const MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Fishy Traffic Law',
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      // Cập nhật ThemeMode dựa trên Provider
      themeMode: Provider.of<ThemeNotifier>(context).isDarkMode
          ? ThemeMode.dark
          : ThemeMode.light,
      
      initialRoute: "/login",
      routes: {
        "/login": (context) => LoginScreen(),
        "/chat": (context) => const ChatScreen(),
        "/logout": (context) => LogoutScreen(),
        "/register": (context) => SignUpScreen(),
        "/setting": (context) => SettingsScreen(),
        "/addLaw": (context) => AddLawScreen(),
        "/addData": (context) => AddLawContentScreen(sohieuvanban: ""),
        "/chatHistory": (context) => ChatHistoryScreen(),
        "/lawMana": (context) => LawManageScreen(),
        
        '/lawDetail': (context) {
          final args = ModalRoute.of(context)!.settings.arguments;

          if (args == null || args is! LawModel) {
            return const Scaffold(
              body: Center(child: Text('Thiếu dữ liệu văn bản (LawModel).')),
            );
          }

          return LawDetailScreen(law: args);
        },

        
        '/editContent': (context) {
          final content = ModalRoute.of(context)!.settings.arguments as LawContentModel;
          return EditContentScreen(content: content);
        }
      },
    );
  }
}