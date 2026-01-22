import 'package:flutter/material.dart';

class AppTheme
{
  static ThemeData get lightTheme
  {
    return ThemeData
    (
      brightness: Brightness.light,
      primaryColor: navyBlue,
      scaffoldBackgroundColor: lightGray,
      appBarTheme: AppBarTheme
      (
        backgroundColor: navyBlue,
        foregroundColor: Colors.white,
        elevation: 0,
        titleTextStyle: TextStyle
        (
          color: Colors.white,
          fontSize: 20,
          fontWeight: FontWeight.bold,
        ),
      ),
      textTheme: TextTheme
      (
        bodyLarge: TextStyle(color: navyBlue, fontSize: 16),
        bodyMedium: TextStyle(color: Colors.black54, fontSize: 14),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData
      (
        style: ElevatedButton.styleFrom
        (
          backgroundColor: navyBlue,
          foregroundColor: Colors.white,
          padding: EdgeInsets.symmetric(vertical: 12, horizontal: 20),
          shape: RoundedRectangleBorder
          (
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme
      (
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder
        (
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: navyBlue),
        ),
        focusedBorder: OutlineInputBorder
        (
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: navyBlue, width: 2),
        ),
      ),
    );
  }

  static ThemeData get darkTheme
  {
    return ThemeData
    (
      brightness: Brightness.dark,
      primaryColor: darkBlue,
      scaffoldBackgroundColor: darkGray,
      appBarTheme: AppBarTheme
      (
        backgroundColor: darkBlue,
        foregroundColor: Colors.white,
        elevation: 0,
        titleTextStyle: TextStyle
        (
          color: Colors.white,
          fontSize: 20,
          fontWeight: FontWeight.bold,
        ),
      ),
      textTheme: TextTheme
      (
        bodyLarge: TextStyle(color: Colors.white, fontSize: 16),
        bodyMedium: TextStyle(color: Colors.white70, fontSize: 14),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData
      (
        style: ElevatedButton.styleFrom
        (
          backgroundColor: darkBlue,
          foregroundColor: Colors.white,
          padding: EdgeInsets.symmetric(vertical: 12, horizontal: 20),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))
        ),
      ),
      inputDecorationTheme: InputDecorationTheme
      (
        filled: true,
        fillColor: darkBlue,
        border: OutlineInputBorder
        (
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: Colors.white70)
        ),
        focusedBorder: OutlineInputBorder
        (
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: Colors.white, width: 2)
        )
      )
    );
  }

  static const Color navyBlue = Color(0xFF1E3A8A);
  static const Color lightGray = Color(0xFFF5F5F5);

  static const Color darkBlue = Color(0xFF0A192F);
  static const Color darkGray = Color(0xFF121212);
}
