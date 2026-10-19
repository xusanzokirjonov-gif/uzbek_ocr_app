import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:provider/provider.dart';
import 'models/history_item.dart';
import 'screens/home_screen.dart';
import 'services/history_service.dart';
import 'services/server_discovery_service.dart';
import 'services/settings_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // ── Инициализация Hive ─────────────────────────────────────────────────
  try {
    await Hive.initFlutter();
    // Проверяем isAdapterRegistered — защита от двойной регистрации
    // (например, при hot restart во время разработки).
    if (!Hive.isAdapterRegistered(0)) {
      Hive.registerAdapter(HistoryItemAdapter());
    }
  } catch (e) {
    // Если Hive не запустился — продолжаем без хранения истории
    debugPrint('[Hive] Initialization failed: $e');
  }

  // ── Инициализация сервисов ─────────────────────────────────────────────
  final settings = SettingsService();
  try {
    await settings.load();
  } catch (e) {
    debugPrint('[Settings] Load failed: $e');
  }

  final historyService = HistoryService();
  try {
    await historyService.init(); // Открывает Hive Box
  } catch (e) {
    debugPrint('[HistoryService] Init failed: $e');
  }

  // ── Автоматическое обнаружение сервера ────────────────────────────────
  final discovery = ServerDiscoveryService();
  // Запускаем поиск в фоне, передавая URL из сохранённых настроек
  discovery.discover(preferredUrl: settings.serverUrl).then((found) {
    if (found != null && found != settings.serverUrl) {
      settings.setServerUrl(found);
    }
  });

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: historyService),
        ChangeNotifierProvider.value(value: settings),
        ChangeNotifierProvider.value(value: discovery),
      ],
      child: const UzbekOCRApp(),
    ),
  );
}

class UzbekOCRApp extends StatelessWidget {
  const UzbekOCRApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<SettingsService>(
      builder: (context, settings, _) {
        // Get system brightness from platform
        final sys = MediaQuery.platformBrightnessOf(context);
        settings.updateSystemBrightness(sys);
        final isDark = settings.brightnessFor(sys) == Brightness.dark;

        return MaterialApp(
          title: 'Uzbek OCR',
          debugShowCheckedModeBanner: false,
          themeMode: settings.theme == AppTheme.system
              ? ThemeMode.system
              : (isDark ? ThemeMode.dark : ThemeMode.light),
          theme: ThemeData(
            useMaterial3: true,
            brightness: Brightness.light,
            scaffoldBackgroundColor: const Color(0xFFF5F5F5),
            colorScheme: const ColorScheme.light(
              primary: Color(0xFF6C63FF),
              secondary: Color(0xFF00D9FF),
              surface: Colors.white,
              onPrimary: Colors.white,
              onSecondary: Colors.white,
              onSurface: Color(0xFF1A1A2E),
            ),
            textTheme: GoogleFonts.interTextTheme(ThemeData.light().textTheme),
            appBarTheme: AppBarTheme(
              backgroundColor: Colors.transparent,
              elevation: 0,
              centerTitle: true,
              titleTextStyle: GoogleFonts.inter(
                fontSize: 20, fontWeight: FontWeight.w700, color: const Color(0xFF1A1A2E),
              ),
            ),
            elevatedButtonTheme: ElevatedButtonThemeData(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF6C63FF),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                textStyle: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w600),
              ),
            ),
          ),
          darkTheme: ThemeData(
            useMaterial3: true,
            brightness: Brightness.dark,
            scaffoldBackgroundColor: const Color(0xFF0A0E21),
            colorScheme: const ColorScheme.dark(
              primary: Color(0xFF6C63FF),
              secondary: Color(0xFF00D9FF),
              surface: Color(0xFF1A1F36),
              onPrimary: Colors.white,
              onSecondary: Colors.white,
              onSurface: Colors.white,
            ),
            textTheme: GoogleFonts.interTextTheme(ThemeData.dark().textTheme),
            appBarTheme: AppBarTheme(
              backgroundColor: Colors.transparent,
              elevation: 0,
              centerTitle: true,
              titleTextStyle: GoogleFonts.inter(
                fontSize: 20, fontWeight: FontWeight.w700, color: Colors.white,
              ),
            ),
            elevatedButtonTheme: ElevatedButtonThemeData(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF6C63FF),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                textStyle: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w600),
              ),
            ),
          ),
          home: const HomeScreen(),
        );
      },
    );
  }
}
