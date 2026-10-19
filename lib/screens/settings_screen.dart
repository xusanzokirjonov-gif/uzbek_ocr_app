import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../services/server_discovery_service.dart';
import '../services/settings_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _serverUrlController;
  bool _isTestingServer = false;
  bool? _serverTestOk;
  String? _serverTestMsg;

  @override
  void initState() {
    super.initState();
    final settings = context.read<SettingsService>();
    _serverUrlController = TextEditingController(text: settings.serverUrl);
  }

  @override
  void dispose() {
    _serverUrlController.dispose();
    super.dispose();
  }

  Future<void> _testAndSaveServer(String url, SettingsService settings) async {
    final cleanUrl = url.trim().replaceAll(RegExp(r'/+$'), '');
    setState(() {
      _isTestingServer = true;
      _serverTestOk = null;
      _serverTestMsg = null;
    });

    try {
      final uri = Uri.parse('$cleanUrl/health');
      final resp = await http.get(uri).timeout(const Duration(seconds: 4));
      if (resp.statusCode == 200 && resp.body.contains('"healthy"')) {
        await settings.setServerUrl(cleanUrl);
        if (mounted) {
          context.read<ServerDiscoveryService>().setManualUrl(cleanUrl);
          setState(() {
            _serverTestOk = true;
            _serverTestMsg = settings.isRussian ? 'Сервер доступен!' : 'Server ishlamoqda!';
          });
        }
      } else {
        if (mounted) {
          setState(() {
            _serverTestOk = false;
            _serverTestMsg = 'HTTP ${resp.statusCode}';
          });
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _serverTestOk = false;
          _serverTestMsg = settings.isRussian ? 'Недоступен' : 'Ulanib bo‘lmadi';
        });
      }
    } finally {
      if (mounted) {
        setState(() => _isTestingServer = false);
      }
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
                colors: settings.backgroundGradientFor(sys),
              ),
            ),
            child: SafeArea(
              child: Column(
                children: [
                  // App Bar
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                    child: Row(
                      children: [
                        IconButton(
                          onPressed: () => Navigator.pop(context),
                          icon: Icon(Icons.arrow_back_ios_rounded, color: settings.textColor),
                        ),
                        Text(
                          settings.t('settings'),
                          style: GoogleFonts.inter(
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                            color: settings.textColor,
                          ),
                        ),
                      ],
                    ),
                  ).animate().fadeIn(duration: 400.ms).slideY(begin: -0.2),

                  Expanded(
                    child: ListView(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                      children: [
                        // --- APPEARANCE ---
                        _buildSectionHeader(settings.t('appearance'), settings),

                        // Theme selector
                        _buildCard(
                          settings,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              _buildRowLabel(
                                icon: Icons.palette_rounded,
                                label: settings.t('theme'),
                                color: const Color(0xFF6C63FF),
                                settings: settings,
                              ),
                              const SizedBox(height: 16),
                                Row(
                                  children: [
                                    _buildThemeChip(
                                      label: settings.t('dark'),
                                      icon: Icons.nightlight_round,
                                      selected: settings.theme == AppTheme.dark,
                                      chipStyle: _ChipStyle.dark,
                                      onTap: () => settings.setTheme(AppTheme.dark),
                                      sys: sys,
                                      settings: settings,
                                    ),
                                    const SizedBox(width: 10),
                                    _buildThemeChip(
                                      label: settings.t('light'),
                                      icon: Icons.wb_sunny_rounded,
                                      selected: settings.theme == AppTheme.light,
                                      chipStyle: _ChipStyle.light,
                                      onTap: () => settings.setTheme(AppTheme.light),
                                      sys: sys,
                                      settings: settings,
                                    ),
                                    const SizedBox(width: 10),
                                    _buildThemeChip(
                                      label: settings.t('system'),
                                      icon: Icons.phone_android_rounded,
                                      selected: settings.theme == AppTheme.system,
                                      chipStyle: _ChipStyle.system,
                                      onTap: () => settings.setTheme(AppTheme.system),
                                      sys: sys,
                                      settings: settings,
                                    ),
                                  ],
                                ),
                            ],
                          ),
                        ).animate().fadeIn(delay: 100.ms, duration: 400.ms).slideY(begin: 0.1),

                        const SizedBox(height: 24),

                        // --- LANGUAGE ---
                        _buildSectionHeader(settings.t('language'), settings),

                        _buildCard(
                          settings,
                          child: Column(
                            children: [
                              _buildRowLabel(
                                icon: Icons.language_rounded,
                                label: settings.t('language'),
                                color: const Color(0xFF00D9FF),
                                settings: settings,
                              ),
                              const SizedBox(height: 16),
                              Row(
                                children: [
                                  Expanded(
                                    child: _buildToggleButton(
                                      label: settings.t('uzbek'),
                                      emoji: '🇺🇿',
                                      selected: settings.language == AppLanguage.uzbek,
                                      color: const Color(0xFF00D9FF),
                                      onTap: () => settings.setLanguage(AppLanguage.uzbek),
                                      settings: settings,
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: _buildToggleButton(
                                      label: settings.t('russian'),
                                      emoji: '🇷🇺',
                                      selected: settings.language == AppLanguage.russian,
                                      color: const Color(0xFF00D9FF),
                                      onTap: () => settings.setLanguage(AppLanguage.russian),
                                      settings: settings,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ).animate().fadeIn(delay: 200.ms, duration: 400.ms).slideY(begin: 0.1),

                        // --- SCRIPT (only for Uzbek) ---
                        AnimatedSize(
                          duration: const Duration(milliseconds: 350),
                          curve: Curves.easeInOut,
                          child: settings.isRussian
                              ? const SizedBox.shrink()
                              : Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const SizedBox(height: 24),
                                    _buildSectionHeader(settings.t('script'), settings),
                                    _buildCard(
                                      settings,
                                      child: Column(
                                        children: [
                                          _buildRowLabel(
                                            icon: Icons.translate_rounded,
                                            label: settings.t('script'),
                                            color: const Color(0xFF7C4DFF),
                                            settings: settings,
                                          ),
                                          const SizedBox(height: 16),
                                          Row(
                                            children: [
                                              Expanded(
                                                child: _buildToggleButton(
                                                  label: settings.t('latin'),
                                                  sublabel: 'Aa',
                                                  selected: settings.script == AppScript.latin,
                                                  color: const Color(0xFF7C4DFF),
                                                  onTap: () => settings.setScript(AppScript.latin),
                                                  settings: settings,
                                                ),
                                              ),
                                              const SizedBox(width: 12),
                                              Expanded(
                                                child: _buildToggleButton(
                                                  label: settings.t('cyrillic'),
                                                  sublabel: 'Аа',
                                                  selected: settings.script == AppScript.cyrillic,
                                                  color: const Color(0xFF7C4DFF),
                                                  onTap: () => settings.setScript(AppScript.cyrillic),
                                                  settings: settings,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ],
                                      ),
                                    ).animate().fadeIn(delay: 300.ms, duration: 400.ms).slideY(begin: 0.1),
                                  ],
                                ),
                        ),


                        // --- SERVER ---
                        const SizedBox(height: 24),
                        _buildSectionHeader(settings.t('server'), settings),
                        Consumer<ServerDiscoveryService>(
                          builder: (context, discovery, _) {
                            final Color statusColor;
                            final IconData statusIcon;
                            final String statusLabel;
                            final String statusSub;

                            switch (discovery.status) {
                              case DiscoveryStatus.searching:
                                statusColor = const Color(0xFFFFA726);
                                statusIcon  = Icons.wifi_find_rounded;
                                statusLabel = settings.isRussian
                                    ? 'Поиск сервера...'
                                    : 'Server qidirilmoqda...';
                                statusSub   = settings.isRussian
                                    ? 'Сканирование локальной сети'
                                    : 'Lokal tarmoq skanlanmoqda';
                              case DiscoveryStatus.found:
                                statusColor = const Color(0xFF00BFA5);
                                statusIcon  = Icons.wifi_rounded;
                                statusLabel = settings.isRussian
                                    ? 'Сервер найден'
                                    : 'Server topildi';
                                statusSub   = discovery.discoveredUrl ?? '';
                              case DiscoveryStatus.failed:
                                statusColor = const Color(0xFFEF5350);
                                statusIcon  = Icons.wifi_off_rounded;
                                statusLabel = settings.isRussian
                                    ? 'Сервер не найден'
                                    : 'Server topilmadi';
                                statusSub   = settings.isRussian
                                    ? 'Убедитесь что сервер запущен в той же сети'
                                    : 'Server bir xil tarmoqda ishlayotganiga ishonch hosil qiling';
                              case DiscoveryStatus.idle:
                                statusColor = const Color(0xFF9E9E9E);
                                statusIcon  = Icons.dns_rounded;
                                statusLabel = settings.isRussian
                                    ? 'Ожидание...'
                                    : 'Kutilmoqda...';
                                statusSub   = '';
                            }

                            return _buildCard(
                              settings,
                              child: Row(
                                children: [
                                  // Иконка статуса
                                  Container(
                                    width: 44,
                                    height: 44,
                                    decoration: BoxDecoration(
                                      color: statusColor.withValues(alpha: 0.15),
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: discovery.status == DiscoveryStatus.searching
                                        ? Padding(
                                            padding: const EdgeInsets.all(10),
                                            child: CircularProgressIndicator(
                                              strokeWidth: 2.5,
                                              color: statusColor,
                                            ),
                                          )
                                        : Icon(statusIcon, color: statusColor, size: 24),
                                  ),
                                  const SizedBox(width: 14),
                                  // Текст статуса
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          statusLabel,
                                          style: GoogleFonts.inter(
                                            fontSize: 15,
                                            fontWeight: FontWeight.w600,
                                            color: settings.textColor,
                                          ),
                                        ),
                                        if (statusSub.isNotEmpty) ...[
                                          const SizedBox(height: 3),
                                          Text(
                                            statusSub,
                                            style: GoogleFonts.inter(
                                              fontSize: 12,
                                              color: discovery.status == DiscoveryStatus.found
                                                  ? statusColor
                                                  : settings.subtitleColor,
                                              fontWeight: discovery.status == DiscoveryStatus.found
                                                  ? FontWeight.w600
                                                  : FontWeight.w400,
                                            ),
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                          ),
                                        ],
                                      ],
                                    ),
                                  ),
                                  // Кнопка повторного поиска
                                  if (discovery.status != DiscoveryStatus.searching)
                                    GestureDetector(
                                      onTap: () => discovery.rediscover(preferredUrl: settings.serverUrl),
                                      child: Container(
                                        width: 36,
                                        height: 36,
                                        decoration: BoxDecoration(
                                          color: statusColor.withValues(alpha: 0.12),
                                          borderRadius: BorderRadius.circular(10),
                                        ),
                                        child: Icon(
                                          Icons.refresh_rounded,
                                          color: statusColor,
                                          size: 20,
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                            );
                          },
                        ).animate().fadeIn(delay: 350.ms, duration: 400.ms).slideY(begin: 0.1),

                        const SizedBox(height: 10),

                        // --- MANUAL SERVER URL INPUT ---
                        _buildCard(
                          settings,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  const Icon(Icons.link_rounded, size: 20, color: Color(0xFF6C63FF)),
                                  const SizedBox(width: 8),
                                  Text(
                                    settings.isRussian ? 'Адрес сервера (ручной ввод)' : 'Server manzili (qo‘lda)',
                                    style: GoogleFonts.inter(
                                      fontSize: 14,
                                      fontWeight: FontWeight.w600,
                                      color: settings.textColorFor(sys),
                                    ),
                                  ),
                                  const Spacer(),
                                  if (_serverTestMsg != null)
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                      decoration: BoxDecoration(
                                        color: (_serverTestOk == true ? const Color(0xFF00BFA5) : const Color(0xFFEF5350)).withValues(alpha: 0.15),
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      child: Text(
                                        _serverTestMsg!,
                                        style: GoogleFonts.inter(
                                          fontSize: 11,
                                          fontWeight: FontWeight.w600,
                                          color: _serverTestOk == true ? const Color(0xFF00BFA5) : const Color(0xFFEF5350),
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              Row(
                                children: [
                                  Expanded(
                                    child: Container(
                                      height: 44,
                                      padding: const EdgeInsets.symmetric(horizontal: 12),
                                      decoration: BoxDecoration(
                                        color: settings.isDark(sys) ? Colors.white.withValues(alpha: 0.05) : const Color(0xFFF4F4F8),
                                        borderRadius: BorderRadius.circular(10),
                                        border: Border.all(
                                          color: settings.borderColorFor(sys),
                                          width: 1,
                                        ),
                                      ),
                                      child: TextField(
                                        controller: _serverUrlController,
                                        style: GoogleFonts.jetBrainsMono(
                                          fontSize: 13,
                                          color: settings.textColorFor(sys),
                                        ),
                                        decoration: InputDecoration(
                                          border: InputBorder.none,
                                          hintText: 'http://192.168.1.6:8000',
                                          hintStyle: GoogleFonts.jetBrainsMono(
                                            fontSize: 13,
                                            color: settings.subtitleColorFor(sys).withValues(alpha: 0.5),
                                          ),
                                          isDense: true,
                                          contentPadding: const EdgeInsets.symmetric(vertical: 12),
                                        ),
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  SizedBox(
                                    height: 44,
                                    child: ElevatedButton(
                                      onPressed: _isTestingServer
                                          ? null
                                          : () => _testAndSaveServer(_serverUrlController.text, settings),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: const Color(0xFF6C63FF),
                                        foregroundColor: Colors.white,
                                        elevation: 0,
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(10),
                                        ),
                                        padding: const EdgeInsets.symmetric(horizontal: 14),
                                      ),
                                      child: _isTestingServer
                                          ? const SizedBox(
                                              width: 18,
                                              height: 18,
                                              child: CircularProgressIndicator(
                                                strokeWidth: 2,
                                                color: Colors.white,
                                              ),
                                            )
                                          : Text(
                                              settings.isRussian ? 'Сохранить' : 'Saqlash',
                                              style: GoogleFonts.inter(
                                                fontSize: 13,
                                                fontWeight: FontWeight.w600,
                                              ),
                                            ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 10),
                              // Быстрый выбор частых адресов
                              Wrap(
                                spacing: 8,
                                runSpacing: 6,
                                children: [
                                  _buildQuickIpChip(
                                    label: '192.168.100.11:8000',
                                    badge: 'Этот Mac',
                                    settings: settings,
                                    onTap: () {
                                      _serverUrlController.text = 'http://192.168.100.11:8000';
                                      _testAndSaveServer('http://192.168.100.11:8000', settings);
                                    },
                                  ),
                                  _buildQuickIpChip(
                                    label: '192.168.1.6:8000',
                                    badge: 'Прежний IP',
                                    settings: settings,
                                    onTap: () {
                                      _serverUrlController.text = 'http://192.168.1.6:8000';
                                      _testAndSaveServer('http://192.168.1.6:8000', settings);
                                    },
                                  ),
                                  _buildQuickIpChip(
                                    label: '192.168.0.100:8000',
                                    badge: 'Резерв',
                                    settings: settings,
                                    onTap: () {
                                      _serverUrlController.text = 'http://192.168.0.100:8000';
                                      _testAndSaveServer('http://192.168.0.100:8000', settings);
                                    },
                                  ),
                                  _buildQuickIpChip(
                                    label: 'uzbek-ocr.local:8000',
                                    badge: 'mDNS',
                                    settings: settings,
                                    onTap: () {
                                      _serverUrlController.text = 'http://uzbek-ocr.local:8000';
                                      _testAndSaveServer('http://uzbek-ocr.local:8000', settings);
                                    },
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ).animate().fadeIn(delay: 370.ms, duration: 400.ms).slideY(begin: 0.1),

                        const SizedBox(height: 12),

                        // --- ASYNC OCR TOGGLE ---
                        _buildCard(
                          settings,
                          child: Row(
                            children: [
                              Container(
                                width: 40,
                                height: 40,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(11),
                                  gradient: LinearGradient(
                                    colors: settings.useAsyncOcr
                                        ? [const Color(0xFF6C63FF), const Color(0xFF00D9FF)]
                                        : [Colors.grey.shade600, Colors.grey.shade500],
                                  ),
                                ),
                                child: Icon(
                                  settings.useAsyncOcr
                                      ? Icons.bolt_rounded
                                      : Icons.sync_rounded,
                                  color: Colors.white,
                                  size: 22,
                                ),
                              ),
                              const SizedBox(width: 14),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      'Async OCR (v2)',
                                      style: GoogleFonts.inter(
                                        fontSize: 15,
                                        fontWeight: FontWeight.w600,
                                        color: settings.textColor,
                                      ),
                                    ),
                                    const SizedBox(height: 3),
                                    Text(
                                      settings.useAsyncOcr
                                          ? 'Celery + Redis (фоновая обработка)'
                                          : 'Синхронный режим (POST /ocr)',
                                      style: GoogleFonts.inter(
                                        fontSize: 12,
                                        color: settings.subtitleColor,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              Switch.adaptive(
                                value: settings.useAsyncOcr,
                                onChanged: (val) => settings.setUseAsyncOcr(val),
                                activeThumbColor: const Color(0xFF6C63FF),
                              ),
                            ],
                          ),
                        ).animate().fadeIn(delay: 400.ms, duration: 400.ms).slideY(begin: 0.1),



                        // --- ABOUT ---
                        _buildSectionHeader(settings.t('about'), settings),

                        _buildCard(
                          settings,
                          child: Row(
                            children: [
                              Container(
                                width: 44,
                                height: 44,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(12),
                                  gradient: const LinearGradient(
                                    colors: [Color(0xFF6C63FF), Color(0xFF00D9FF)],
                                  ),
                                ),
                                child: const Icon(Icons.info_outline_rounded, color: Colors.white, size: 22),
                              ),
                              const SizedBox(width: 16),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      'Uzbek OCR',
                                      style: GoogleFonts.inter(
                                        fontSize: 16,
                                        fontWeight: FontWeight.w700,
                                        color: settings.textColor,
                                      ),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      '${settings.t("version")} 1.0.0',
                                      style: GoogleFonts.inter(
                                        fontSize: 13,
                                        color: settings.subtitleColor,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ).animate().fadeIn(delay: 400.ms, duration: 400.ms).slideY(begin: 0.1),

                        const SizedBox(height: 32),
                      ],
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

  Widget _buildSectionHeader(String title, SettingsService settings) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Text(
        title.toUpperCase(),
        style: GoogleFonts.inter(
          fontSize: 12,
          fontWeight: FontWeight.w700,
          letterSpacing: 1.2,
          color: settings.subtitleColor,
        ),
      ),
    );
  }

  Widget _buildCard(SettingsService settings, {required Widget child}) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: settings.cardColor,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: settings.borderColor),
        boxShadow: settings.brightness == Brightness.dark
            ? []
            : [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.02),
                  blurRadius: 10,
                  offset: const Offset(0, 4),
                ),
              ],
      ),
      child: child,
    );
  }

  Widget _buildRowLabel({
    required IconData icon,
    required String label,
    required Color color,
    required SettingsService settings,
  }) {
    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, color: color, size: 20),
        ),
        const SizedBox(width: 12),
        Text(
          label,
          style: GoogleFonts.inter(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: settings.textColor,
          ),
        ),
      ],
    );
  }

  Widget _buildThemeChip({
    required String label,
    required IconData icon,
    required bool selected,
    required _ChipStyle chipStyle,
    required VoidCallback onTap,
    required Brightness sys,
    required SettingsService settings,
  }) {
    // Visual design per chip style
    final Decoration chipDecoration;
    final Color iconColor;
    final Color textColor;

    final bool isDarkBehavior;
    if (chipStyle == _ChipStyle.system) {
      isDarkBehavior = (sys == Brightness.dark);
    } else {
      isDarkBehavior = (chipStyle == _ChipStyle.dark);
    }

    if (isDarkBehavior) {
      chipDecoration = BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF1A1040), Color(0xFF0A0E21)],
        ),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: selected ? const Color(0xFF6C63FF) : Colors.white12,
          width: selected ? 2.5 : 1,
        ),
        boxShadow: selected
            ? [BoxShadow(color: const Color(0xFF6C63FF).withValues(alpha: 0.45), blurRadius: 14)]
            : [],
      );
      iconColor = Colors.white;
      textColor = Colors.white;
    } else {
      chipDecoration = BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFFFFFFFF), Color(0xFFEEEEF8)],
        ),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: selected ? const Color(0xFF6C63FF) : const Color(0xFFDDDDEE),
          width: selected ? 2.5 : 1,
        ),
        boxShadow: selected
            ? [BoxShadow(color: const Color(0xFF6C63FF).withValues(alpha: 0.25), blurRadius: 14)]
            : [const BoxShadow(color: Color(0x15000000), blurRadius: 6, offset: Offset(0, 2))],
      );
      iconColor = const Color(0xFF4A4A6E);
      textColor = const Color(0xFF2A2A4E);
    }

    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: chipDecoration,
          child: Column(
            children: [
              Icon(icon, color: iconColor, size: 20),
              const SizedBox(height: 6),
              Text(
                label,
                style: GoogleFonts.inter(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: textColor,
                ),
                textAlign: TextAlign.center,
              ),
              if (selected) ...[
                const SizedBox(height: 4),
                Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(
                    color: Color(0xFF6C63FF),
                    shape: BoxShape.circle,
                  ),
                ),
              ]
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildToggleButton({
    required String label,
    required bool selected,
    required Color color,
    required VoidCallback onTap,
    required SettingsService settings,
    String? emoji,
    String? sublabel,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          color: selected ? color.withValues(alpha: 0.15) : Colors.transparent,
          border: Border.all(
            color: selected ? color : settings.borderColor,
            width: selected ? 1.5 : 1,
          ),
        ),
        child: Column(
          children: [
            if (emoji != null)
              Text(emoji, style: const TextStyle(fontSize: 22))
            else
              Text(
                sublabel ?? '',
                style: GoogleFonts.inter(
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  color: selected ? color : settings.subtitleColor,
                ),
              ),
            const SizedBox(height: 6),
            Text(
              label,
              style: GoogleFonts.inter(
                fontSize: 13,
                fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                color: selected ? color : settings.subtitleColor,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickIpChip({
    required String label,
    required String badge,
    required SettingsService settings,
    required VoidCallback onTap,
  }) {
    final sys = MediaQuery.platformBrightnessOf(context);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: const Color(0xFF6C63FF).withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: const Color(0xFF6C63FF).withValues(alpha: 0.25),
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: GoogleFonts.jetBrainsMono(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: settings.textColorFor(sys),
              ),
            ),
            const SizedBox(width: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
              decoration: BoxDecoration(
                color: const Color(0xFF6C63FF).withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                badge,
                style: GoogleFonts.inter(
                  fontSize: 9,
                  fontWeight: FontWeight.w700,
                  color: const Color(0xFF6C63FF),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

enum _ChipStyle { dark, light, system }
