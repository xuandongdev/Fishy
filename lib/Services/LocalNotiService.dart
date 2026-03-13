import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class LocalNotiService {
  static final FlutterLocalNotificationsPlugin _notiPlugin = FlutterLocalNotificationsPlugin();

  static Future<void> init() async {
    const AndroidInitializationSettings androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
    const DarwinInitializationSettings iosInit = DarwinInitializationSettings();
    const InitializationSettings initSettings = InitializationSettings(android: androidInit, iOS: iosInit);
    await _notiPlugin.initialize(initSettings);
  }

  static Future<void> showWarningNotification(String body) async {
    const AndroidNotificationDetails androidDetails = AndroidNotificationDetails(
      'traffic_warning', // channel id
      'Cảnh báo giao thông', // channel name
      importance: Importance.max,
      priority: Priority.high,
      icon: '@mipmap/ic_launcher',
    );
    const NotificationDetails details = NotificationDetails(android: androidDetails);

    // Gửi thông báo
    await _notiPlugin.show(
      DateTime.now().millisecond,
      '⚠️ Chú ý biển báo',
      body,
      details,
    );
  }
}