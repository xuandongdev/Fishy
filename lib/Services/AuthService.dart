import 'package:supabase_flutter/supabase_flutter.dart';

class AuthService
{
  final SupabaseClient _supabase = Supabase.instance.client;
  String? errorMessage;

  Future<bool> signIn(String email, String password) async
  {
    try
    {
      final AuthResponse response = await _supabase.auth.signInWithPassword
      (
        email: email,
        password: password,
      );

      if (response.session == null || response.user == null)
      {
        print("Đăng nhập thất bại!");
        errorMessage = "Tên đăng nhập hoặc mật khẩu không đúng!";
        return false;
      }
      final userData = await _supabase
          .from('nguoidung')
          .select('userid, email, hoten, mavaitro, matrangthai_tk')
          .eq('email', email)
          .maybeSingle();

      if (userData == null)
      {
        print("Không tìm thấy thông tin người dùng!");
        errorMessage = "Không tìm thấy thông tin người dùng!";
        return false;
      }

      final int trangThaiTaiKhoan = userData['matrangthai_tk'];
      if (trangThaiTaiKhoan == 2)
      {
        print("Tài khoản bị khóa, không thể đăng nhập!");
        errorMessage = "Tài khoản bị khóa, không thể đăng nhập!";
        return false;
      }

      print("Đăng nhập thành công!");
      errorMessage = null;
      return true;
    } catch (e) {
      print("Lỗi đăng nhập: $e");
      errorMessage = "Lỗi hệ thống! Vui lòng thử lại.";
      return false;
    }
  }

  Future<bool> signUp(String email, String password, String fullName, String phone) async
  {
    try
    {
      final AuthResponse res = await _supabase.auth.signUp(
        email: email,
        password: password,
      );

      if (res.user != null)
      {
        await _supabase.from('nguoidung').insert
        ({
          'email': email,
          'hoten': fullName,
          'sodt': phone,
        });

        print("Đăng ký thành công!");
        errorMessage = null;
        return true;
      }

      print("Đăng ký thất bại!");
      errorMessage = "Đăng ký thất bại!";
      return false;
    }
    catch (e)
    {
      print("Lỗi đăng ký: $e");
      errorMessage = "Lỗi hệ thống! Vui lòng thử lại.";
      return false;
    }
  }

  Future<void> signOut() async
  {
    await _supabase.auth.signOut();
  }

  Future<Map<String, dynamic>?> getCurrentUser() async
  {
    final session = _supabase.auth.currentSession;

    if (session == null || session.user == null)
    {
      print("Không tìm thấy phiên đăng nhập. Vui lòng đăng nhập lại!");
      return null;
    }

    print("User email từ session: ${session.user!.email}");

    final userData = await _supabase
        .from('nguoidung')
        .select('userid, email, hoten, mavaitro')
        .eq('email', session.user!.email as Object)
        .maybeSingle();

    if (userData == null)
    {
      print("Không tìm thấy thông tin người dùng trong bảng `nguoidung`!");
      return null;
    }

    print("Dữ liệu user lấy được: $userData");
    return userData;
  }
}
