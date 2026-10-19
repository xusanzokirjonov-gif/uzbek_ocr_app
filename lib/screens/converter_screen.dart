import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../services/converter_service.dart';
import '../services/settings_service.dart';

class ConverterScreen extends StatefulWidget {
  const ConverterScreen({super.key});

  @override
  State<ConverterScreen> createState() => _ConverterScreenState();
}

class _ConverterScreenState extends State<ConverterScreen> {
  final TextEditingController _inputController = TextEditingController();
  String _outputText = '';
  bool _isLatinToCyrillic = true;

  @override
  void dispose() {
    _inputController.dispose();
    super.dispose();
  }

  void _convert() {
    final input = _inputController.text.trim();
    if (input.isEmpty) {
      setState(() => _outputText = '');
      return;
    }
    setState(() {
      _outputText = _isLatinToCyrillic
          ? UzbekConverter.toCyrillic(input)
          : UzbekConverter.toLatin(input);
    });
  }

  void _autoDetectAndConvert() {
    final input = _inputController.text.trim();
    if (input.isEmpty) return;
    final isCyrillic = UzbekConverter.isCyrillic(input);
    setState(() {
      _isLatinToCyrillic = !isCyrillic;
      _outputText = UzbekConverter.autoConvert(input);
    });
  }

  void _swapDirection() {
    setState(() {
      _isLatinToCyrillic = !_isLatinToCyrillic;
      if (_outputText.isNotEmpty) {
        _inputController.text = _outputText;
        _convert();
      }
    });
  }

  void _copyOutput(SettingsService settings) {
    if (_outputText.isEmpty) return;
    Clipboard.setData(ClipboardData(text: _outputText));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Row(
          children: [
            const Icon(Icons.check_circle, color: Colors.white, size: 20),
            const SizedBox(width: 8),
            Text(settings.t('copied'), style: GoogleFonts.inter()),
          ],
        ),
        backgroundColor: const Color(0xFF6C63FF),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _clearAll() {
    setState(() {
      _inputController.clear();
      _outputText = '';
    });
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
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                    child: Row(
                      children: [
                        IconButton(
                          onPressed: () => Navigator.pop(context),
                          icon: Icon(Icons.arrow_back_ios_rounded, color: settings.textColor),
                        ),
                        Text(
                          settings.t('converter'),
                          style: GoogleFonts.inter(
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                            color: settings.textColor,
                          ),
                        ),
                        const Spacer(),
                        if (_inputController.text.isNotEmpty)
                          IconButton(
                            onPressed: _clearAll,
                            icon: Icon(Icons.clear_all_rounded, color: settings.subtitleColor),
                          ),
                      ],
                    ),
                  ),

                  Expanded(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.symmetric(horizontal: 20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const SizedBox(height: 8),

                          // Direction switch
                          _buildDirectionSwitch(settings)
                              .animate()
                              .fadeIn(duration: 400.ms),

                          const SizedBox(height: 20),

                          // Input field
                          _buildInputField(settings)
                              .animate()
                              .fadeIn(delay: 200.ms, duration: 400.ms),

                          const SizedBox(height: 16),

                          // Convert buttons
                          Row(
                            children: [
                              Expanded(
                                child: _buildConvertButton(
                                  label: settings.t('conv_btn'),
                                  icon: Icons.translate_rounded,
                                  color: const Color(0xFF6C63FF),
                                  onTap: _convert,
                                ),
                              ),
                              const SizedBox(width: 12),
                              _buildConvertButton(
                                label: settings.t('conv_auto'),
                                icon: Icons.auto_fix_high_rounded,
                                color: const Color(0xFF00D9FF),
                                onTap: _autoDetectAndConvert,
                                isCompact: true,
                              ),
                            ],
                          ).animate().fadeIn(delay: 400.ms, duration: 400.ms),

                          const SizedBox(height: 20),

                          if (_outputText.isNotEmpty)
                            _buildOutputSection(settings)
                                .animate()
                                .fadeIn(duration: 500.ms)
                                .slideY(begin: 0.1),

                          const SizedBox(height: 24),
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

  Widget _buildDirectionSwitch(SettingsService settings) {
    return GestureDetector(
      onTap: _swapDirection,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        decoration: BoxDecoration(
          color: settings.cardColor,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: settings.borderColor),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _buildScriptBadge(
              _isLatinToCyrillic ? settings.t('conv_latin') : settings.t('conv_cyrillic'),
              _isLatinToCyrillic ? "Aa" : "Аа",
              const Color(0xFF6C63FF),
              settings,
            ),
            const SizedBox(width: 16),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: const Color(0xFF00D9FF).withValues(alpha: 0.15),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.swap_horiz_rounded, color: Color(0xFF00D9FF), size: 24),
            ),
            const SizedBox(width: 16),
            _buildScriptBadge(
              _isLatinToCyrillic ? settings.t('conv_cyrillic') : settings.t('conv_latin'),
              _isLatinToCyrillic ? "Аа" : "Aa",
              const Color(0xFF00D9FF),
              settings,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildScriptBadge(String label, String example, Color color, SettingsService settings) {
    return Column(
      children: [
        Text(example, style: GoogleFonts.inter(fontSize: 24, fontWeight: FontWeight.w800, color: color)),
        const SizedBox(height: 4),
        Text(label, style: GoogleFonts.inter(fontSize: 12, color: settings.subtitleColor)),
      ],
    );
  }

  Widget _buildInputField(SettingsService settings) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      decoration: BoxDecoration(
        color: settings.cardColor,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: settings.borderColor),
        boxShadow: settings.brightness == Brightness.dark
            ? []
            : [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.03),
                  blurRadius: 10,
                  offset: const Offset(0, 4),
                ),
              ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
            child: Row(
              children: [
                Icon(Icons.edit_rounded, color: settings.subtitleColor, size: 18),
                const SizedBox(width: 8),
                Text(settings.t('conv_input_label'), style: GoogleFonts.inter(fontSize: 13, color: settings.subtitleColor)),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
            child: TextField(
              controller: _inputController,
              maxLines: 6,
              minLines: 3,
              style: GoogleFonts.inter(fontSize: 16, color: settings.textColor, height: 1.6),
              decoration: InputDecoration(
                border: InputBorder.none,
                hintText: _isLatinToCyrillic
                    ? "O'zbekiston — ajoyib mamlakat..."
                    : "Ўзбекистон — ажойиб мамлакат...",
                hintStyle: GoogleFonts.inter(fontSize: 16, color: settings.subtitleColor.withValues(alpha: 0.4)),
              ),
              onChanged: (_) => _convert(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildConvertButton({
    required String label,
    required IconData icon,
    required Color color,
    required VoidCallback onTap,
    bool isCompact = false,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: EdgeInsets.symmetric(horizontal: isCompact ? 16 : 24, vertical: 16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            gradient: LinearGradient(colors: [color, color.withValues(alpha: 0.7)]),
            boxShadow: [BoxShadow(color: color.withValues(alpha: 0.3), blurRadius: 12, offset: const Offset(0, 4))],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, color: Colors.white, size: 22),
              const SizedBox(width: 8),
              Text(label, style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w700, color: Colors.white)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildOutputSection(SettingsService settings) {
    final isDark = settings.brightness == Brightness.dark;
    final accentColor = isDark ? const Color(0xFF00D9FF) : const Color(0xFF0077B6);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: settings.cardColor,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: accentColor.withValues(alpha: isDark ? 0.2 : 0.25),
          width: isDark ? 1.0 : 1.2,
        ),
        boxShadow: isDark
            ? []
            : [
                BoxShadow(
                  color: accentColor.withValues(alpha: 0.04),
                  blurRadius: 12,
                  offset: const Offset(0, 4),
                ),
              ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.check_circle_rounded, color: accentColor, size: 20),
              const SizedBox(width: 8),
              Text(settings.t('result'), style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: settings.textColor)),
              const Spacer(),
              GestureDetector(
                onTap: () => _copyOutput(settings),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: const Color(0xFF6C63FF).withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.copy_rounded, size: 14, color: Color(0xFF6C63FF)),
                      const SizedBox(width: 4),
                      Text(settings.t('copy_btn'), style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w600, color: const Color(0xFF6C63FF))),
                    ],
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          SelectableText(
            _outputText,
            style: GoogleFonts.inter(
              fontSize: 16,
              color: accentColor,
              height: 1.7,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}
