import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uzbek_ocr_app/main.dart';
import 'package:uzbek_ocr_app/services/history_service.dart';
import 'package:uzbek_ocr_app/services/server_discovery_service.dart';
import 'package:uzbek_ocr_app/services/settings_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  GoogleFonts.config.allowRuntimeFetching = false;

  testWidgets('App launches successfully', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    final settings = SettingsService();
    final history = HistoryService();
    final discovery = ServerDiscoveryService();

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<SettingsService>.value(value: settings),
          ChangeNotifierProvider<HistoryService>.value(value: history),
          ChangeNotifierProvider<ServerDiscoveryService>.value(value: discovery),
        ],
        child: const UzbekOCRApp(),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(MaterialApp), findsOneWidget);
  });
}
