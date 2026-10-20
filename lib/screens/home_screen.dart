import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import '../services/server_discovery_service.dart';
import '../services/settings_service.dart';
import '../widgets/ios26_glass.dart';
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
      final XFile? pickedFile = await _picker.pickImage(source: source);
      if (pickedFile == null) return;

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
        final bool isDark = settings.isDark(sys);

        return Scaffold(
          body: IOS26AuroraBackground(
            isDark: isDark,
            child: SafeArea(
              child: Column(
                children: [
                  // ── Top Glass App Bar ─────────────────────────────────────
                  IOS26GlassAppBar(
                    title: settings.t('app_name'),
                    isDark: isDark,
                    actions: [
                      _buildHeaderCircleButton(
                        icon: Icons.history_rounded,
                        isDark: isDark,
                        onTap: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => const HistoryScreen()),
                          );
                        },
                      ),
                      const SizedBox(width: 8),
                      _buildHeaderCircleButton(
                        icon: Icons.tune_rounded,
                        isDark: isDark,
                        onTap: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => const SettingsScreen()),
                          );
                        },
                      ),
                    ],
                  ).animate().fadeIn(duration: 400.ms).slideY(begin: -0.2),

                  // ── Dynamic Island Status Capsule ─────────────────────────
                  Consumer<ServerDiscoveryService>(
                    builder: (context, discovery, _) {
                      final isFound = discovery.isFound;
                      final isSearching = discovery.isSearching;
                      final Color statusColor = isFound
                          ? const Color(0xFF00F5D4)
                          : (isSearching ? const Color(0xFFFFB703) : const Color(0xFFFF4D6D));
                      final IconData statusIcon = isFound
                          ? Icons.wifi_tethering_rounded
                          : (isSearching ? Icons.radar_rounded : Icons.wifi_off_rounded);
                      final String mainText = isFound
                          ? (discovery.discoveredUrl ?? settings.serverUrl)
                              .replaceAll('http://', '')
                          : (isSearching
                              ? (settings.isRussian ? 'Поиск узла...' : 'Qidirilmoqda...')
                              : (settings.isRussian ? 'Офлайн (настроить)' : 'Ulanmagan'));
                      final String? subText = isFound ? 'LIVE' : null;

                      return IOS26DynamicIsland(
                        text: mainText,
                        subtext: subText,
                        icon: statusIcon,
                        statusColor: statusColor,
                        isLive: isFound,
                        isPulsing: isFound || isSearching,
                        isDark: isDark,
                        onTap: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => const SettingsScreen()),
                          );
                        },
                      );
                    },
                  ).animate().fadeIn(delay: 150.ms, duration: 400.ms),

                  // ── Scrollable Body Content ───────────────────────────────
                  Expanded(
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      padding: const EdgeInsets.only(top: 8, bottom: 20),
                      child: Column(
                        children: [
                          // ── Holographic OCR Scanner Viewport ──────────────
                          IOS26HoloScanner(
                            title: settings.t('scan_text'),
                            subtitle: 'AI SPATIAL OCR 2026',
                            isDark: isDark,
                            onCameraTap: () => _pickImage(ImageSource.camera),
                            onGalleryTap: () => _pickImage(ImageSource.gallery),
                          ).animate().fadeIn(delay: 250.ms, duration: 600.ms).scaleXY(begin: 0.95),

                          const SizedBox(height: 12),

                          // ── Primary Action Buttons (iOS 26 Liquid Glass) ─
                          IOS26LiquidButton(
                            icon: Icons.camera_alt_rounded,
                            label: settings.t('camera'),
                            subtitle: settings.t('camera_sub'),
                            gradientColors: const [Color(0xFF7928CA), Color(0xFF4361EE)],
                            isDark: isDark,
                            onTap: () => _pickImage(ImageSource.camera),
                          ).animate().fadeIn(delay: 350.ms, duration: 500.ms).slideY(begin: 0.1),

                          IOS26LiquidButton(
                            icon: Icons.photo_library_rounded,
                            label: settings.t('gallery'),
                            subtitle: settings.t('gallery_sub'),
                            gradientColors: const [Color(0xFF00DFD8), Color(0xFF007CF0)],
                            isDark: isDark,
                            onTap: () => _pickImage(ImageSource.gallery),
                          ).animate().fadeIn(delay: 450.ms, duration: 500.ms).slideY(begin: 0.1),

                          IOS26LiquidButton(
                            icon: Icons.translate_rounded,
                            label: settings.t('converter'),
                            subtitle: settings.t('converter_sub'),
                            gradientColors: const [Color(0xFFFF007A), Color(0xFF7928CA)],
                            isDark: isDark,
                            onTap: () {
                              Navigator.push(
                                context,
                                MaterialPageRoute(builder: (_) => const ConverterScreen()),
                              );
                            },
                          ).animate().fadeIn(delay: 550.ms, duration: 500.ms).slideY(begin: 0.1),

                          const SizedBox(height: 14),

                          // ── Spatial Info Card ─────────────────────────────
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 20),
                            child: IOS26GlassCard(
                              isDark: isDark,
                              borderRadius: 20,
                              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
                              child: Row(
                                children: [
                                  Container(
                                    padding: const EdgeInsets.all(8),
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      color: isDark
                                          ? const Color(0xFF00F5D4).withValues(alpha: 0.15)
                                          : const Color(0xFF6C63FF).withValues(alpha: 0.12),
                                    ),
                                    child: Icon(
                                      Icons.auto_awesome_rounded,
                                      size: 18,
                                      color: isDark ? const Color(0xFF00F5D4) : const Color(0xFF6C63FF),
                                    ),
                                  ),
                                  const SizedBox(width: 14),
                                  Expanded(
                                    child: Text(
                                      settings.t('both_scripts'),
                                      style: GoogleFonts.inter(
                                        fontSize: 13,
                                        fontWeight: FontWeight.w500,
                                        letterSpacing: -0.2,
                                        color: isDark ? Colors.white70 : const Color(0xFF4B5563),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ).animate().fadeIn(delay: 650.ms, duration: 500.ms),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildHeaderCircleButton({
    required IconData icon,
    required bool isDark,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: isDark
              ? Colors.white.withValues(alpha: 0.08)
              : Colors.black.withValues(alpha: 0.05),
          border: Border.all(
            color: isDark
                ? Colors.white.withValues(alpha: 0.15)
                : Colors.white.withValues(alpha: 0.6),
            width: 0.8,
          ),
        ),
        child: Icon(
          icon,
          size: 20,
          color: isDark ? Colors.white : const Color(0xFF1E2235),
        ),
      ),
    );
  }
}
