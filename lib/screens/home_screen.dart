import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import '../services/server_discovery_service.dart';
import '../services/settings_service.dart';
import 'result_screen.dart';
import 'history_screen.dart';
import 'converter_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ImagePicker _picker = ImagePicker();

  Future<void> _pickImage(ImageSource source) async {
    try {
      final XFile? pickedFile = await _picker.pickImage(
        source: source,
      );

      if (pickedFile == null) return;

      // Read bytes directly from the picked XFile (vital on iOS to ensure lazy asset loading)
      final Uint8List bytes = await pickedFile.readAsBytes();

      if (!mounted) return;

      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ResultScreen(
            imageBytes: bytes,
            imagePath: pickedFile.path,
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Xatolik yuz berdi: $e'),
          backgroundColor: Colors.redAccent,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SettingsService>(
      builder: (context, settings, _) {
        final sys = MediaQuery.platformBrightnessOf(context);
        settings.updateSystemBrightness(sys);
        return Scaffold(
          body: AnimatedContainer(
            duration: const Duration(milliseconds: 400),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: settings.backgroundGradient,
              ),
            ),
            child: SafeArea(
              child: Column(
                children: [
                  // App Bar
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          settings.t('app_name'),
                          style: GoogleFonts.inter(
                            fontSize: 24,
                            fontWeight: FontWeight.w800,
                            color: settings.textColor,
                          ),
                        ),
                        Row(
                          children: [
                            IconButton(
                              onPressed: () {
                                Navigator.push(
                                  context,
                                  MaterialPageRoute(builder: (_) => const HistoryScreen()),
                                );
                              },
                              icon: Icon(Icons.history_rounded, color: settings.subtitleColor, size: 26),
                            ),
                            IconButton(
                              onPressed: () {
                                Navigator.push(
                                  context,
                                  MaterialPageRoute(builder: (_) => const SettingsScreen()),
                                );
                              },
                              icon: Icon(Icons.settings_rounded, color: settings.subtitleColor, size: 26),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ).animate().fadeIn(duration: 500.ms).slideY(begin: -0.3),

                  // Server Connection Status Pill
                  Consumer<ServerDiscoveryService>(
                    builder: (context, discovery, _) {
                      final isFound = discovery.isFound;
                      final isSearching = discovery.isSearching;
                      final Color pillColor = isFound
                          ? const Color(0xFF00BFA5)
                          : (isSearching ? const Color(0xFFFFA726) : const Color(0xFFEF5350));
                      final IconData pillIcon = isFound
                          ? Icons.cloud_done_rounded
                          : (isSearching ? Icons.wifi_find_rounded : Icons.cloud_off_rounded);
                      final String pillText = isFound
                          ? 'Сервер: ${(discovery.discoveredUrl ?? settings.serverUrl).replaceAll('http://', '')}'
                          : (isSearching
                              ? (settings.isRussian ? 'Поиск сервера...' : 'Server qidirilmoqda...')
                              : (settings.isRussian ? 'Сервер не найден (настроить)' : 'Server topilmadi (sozlash)'));

                      return GestureDetector(
                        onTap: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => const SettingsScreen()),
                          );
                        },
                        child: Container(
                          margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                          decoration: BoxDecoration(
                            color: pillColor.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(
                              color: pillColor.withValues(alpha: 0.3),
                              width: 1,
                            ),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (isSearching)
                                SizedBox(
                                  width: 12,
                                  height: 12,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: pillColor,
                                  ),
                                )
                              else
                                Icon(pillIcon, size: 14, color: pillColor),
                              const SizedBox(width: 7),
                              Text(
                                pillText,
                                style: GoogleFonts.inter(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                  color: pillColor,
                                ),
                              ),
                              const SizedBox(width: 4),
                              Icon(Icons.chevron_right_rounded, size: 14, color: pillColor),
                            ],
                          ),
                        ),
                      ).animate().fadeIn(duration: 400.ms);
                    },
                  ),

                  const SizedBox(height: 8),

                  // Hero Section
                  Expanded(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.symmetric(horizontal: 24),
                      child: Column(
                        children: [
                          // Animated Icon
                          Container(
                            width: 100,
                            height: 100,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              gradient: const LinearGradient(
                                colors: [Color(0xFF6C63FF), Color(0xFF00D9FF)],
                              ),
                              boxShadow: [
                                BoxShadow(
                                  color: const Color(0xFF6C63FF).withValues(alpha: 0.4),
                                  blurRadius: 30,
                                  spreadRadius: 5,
                                ),
                              ],
                            ),
                            child: const Icon(
                              Icons.document_scanner_rounded,
                              color: Colors.white,
                              size: 56,
                            ),
                          )
                              .animate(onPlay: (c) => c.repeat(reverse: true))
                              .scaleXY(end: 1.05, duration: 2000.ms, curve: Curves.easeInOut)
                              .animate()
                              .fadeIn(duration: 800.ms)
                              .scaleXY(begin: 0.5),

                          const SizedBox(height: 32),

                          // Title
                          Text(
                            settings.t('scan_text'),
                            style: GoogleFonts.inter(
                              fontSize: 28,
                              fontWeight: FontWeight.w800,
                              color: settings.textColor,
                            ),
                            textAlign: TextAlign.center,
                          ).animate().fadeIn(delay: 200.ms, duration: 600.ms),

                          const SizedBox(height: 12),

                          // Subtitle
                          Text(
                            settings.t('scan_subtitle'),
                            style: GoogleFonts.inter(
                              fontSize: 15,
                              color: settings.subtitleColor,
                              height: 1.5,
                            ),
                            textAlign: TextAlign.center,
                          ).animate().fadeIn(delay: 400.ms, duration: 600.ms),

                          const SizedBox(height: 48),

                          // Camera Button
                          _buildActionButton(
                            icon: Icons.camera_alt_rounded,
                            label: settings.t('camera'),
                            subtitle: settings.t('camera_sub'),
                            gradient: const [Color(0xFF6C63FF), Color(0xFF5A52E0)],
                            onTap: () => _pickImage(ImageSource.camera),
                            settings: settings,
                          ).animate().fadeIn(delay: 600.ms, duration: 600.ms).slideX(begin: -0.2),

                          const SizedBox(height: 16),

                          // Gallery Button
                          _buildActionButton(
                            icon: Icons.photo_library_rounded,
                            label: settings.t('gallery'),
                            subtitle: settings.t('gallery_sub'),
                            gradient: const [Color(0xFF00D9FF), Color(0xFF00B4D8)],
                            onTap: () => _pickImage(ImageSource.gallery),
                            settings: settings,
                          ).animate().fadeIn(delay: 800.ms, duration: 600.ms).slideX(begin: 0.2),

                          const SizedBox(height: 16),

                          // Converter Button
                          _buildActionButton(
                            icon: Icons.translate_rounded,
                            label: settings.t('converter'),
                            subtitle: settings.t('converter_sub'),
                            gradient: const [Color(0xFF7C4DFF), Color(0xFFB388FF)],
                            onTap: () {
                              Navigator.push(
                                context,
                                MaterialPageRoute(builder: (_) => const ConverterScreen()),
                              );
                            },
                            settings: settings,
                          ).animate().fadeIn(delay: 1000.ms, duration: 600.ms).slideX(begin: -0.2),
                        ],
                      ),
                    ),
                  ),

                  // Bottom Info
                  Padding(
                    padding: const EdgeInsets.all(20),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 300),
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                      decoration: BoxDecoration(
                        color: settings.cardColor,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: settings.borderColor),
                        boxShadow: settings.brightness == Brightness.dark
                            ? []
                            : [
                                BoxShadow(
                                  color: Colors.black.withValues(alpha: 0.02),
                                  blurRadius: 8,
                                  offset: const Offset(0, 3),
                                ),
                              ],
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.info_outline_rounded, color: settings.subtitleColor, size: 20),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              settings.t('both_scripts'),
                              style: GoogleFonts.inter(
                                fontSize: 13,
                                color: settings.subtitleColor,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ).animate().fadeIn(delay: 1000.ms, duration: 600.ms),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildActionButton({
    required IconData icon,
    required String label,
    required String subtitle,
    required List<Color> gradient,
    required VoidCallback onTap,
    required SettingsService settings,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            gradient: LinearGradient(
              colors: settings.brightness == Brightness.dark
                  ? [
                      gradient[0].withValues(alpha: 0.15),
                      gradient[1].withValues(alpha: 0.05),
                    ]
                  : [
                      gradient[0].withValues(alpha: 0.06),
                      gradient[1].withValues(alpha: 0.02),
                    ],
            ),
            border: Border.all(
              color: settings.brightness == Brightness.dark
                  ? gradient[0].withValues(alpha: 0.3)
                  : gradient[0].withValues(alpha: 0.2),
              width: 1.2,
            ),
            boxShadow: settings.brightness == Brightness.dark
                ? []
                : [
                    BoxShadow(
                      color: gradient[0].withValues(alpha: 0.05),
                      blurRadius: 12,
                      offset: const Offset(0, 4),
                    ),
                  ],
          ),
          child: Row(
            children: [
              Container(
                width: 52,
                height: 52,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(14),
                  gradient: LinearGradient(colors: gradient),
                ),
                child: Icon(icon, color: Colors.white, size: 26),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      label,
                      style: GoogleFonts.inter(
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                        color: settings.textColor,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: GoogleFonts.inter(
                        fontSize: 13,
                        color: settings.subtitleColor,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(Icons.arrow_forward_ios_rounded, color: gradient[0], size: 20),
            ],
          ),
        ),
      ),
    );
  }
}
