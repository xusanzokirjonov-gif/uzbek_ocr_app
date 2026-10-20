
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../services/api_service.dart';
import '../services/history_service.dart';
import '../services/converter_service.dart';
import '../services/server_discovery_service.dart';
import '../services/settings_service.dart';
import '../widgets/ios26_glass.dart';

class ResultScreen extends StatefulWidget {
  final Uint8List imageBytes;
  final String imagePath;

  const ResultScreen({super.key, required this.imageBytes, required this.imagePath});

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  bool _isLoading = true;
  String _recognizedText = '';
  double _confidence = 0.0;
  bool _isDemo = false;
  String? _error;
  bool _isEditing = false;
  late TextEditingController _editController;

  // FIX #4: токен отмены для прерывания polling-цикла при dispose()
  final OcrCancelToken _cancelToken = OcrCancelToken();

  // ── Поля для асинхронного OCR-прогресса ───────────────────────────────
  int _ocrProgress = 0;
  String _ocrStage   = 'pending';
  String _ocrMessage = '';

  @override
  void initState() {
    super.initState();
    _editController = TextEditingController();
    _performOCR();
  }

  @override
  void dispose() {
    // FIX #4: отменяем polling-цикл чтобы он не вызывал setState
    // после того как виджет уже unmounted (crash / setState on dead widget)
    _cancelToken.cancel();
    _editController.dispose();
    super.dispose();
  }

  void _openFullscreen(BuildContext context) {
    Navigator.of(context).push(
      PageRouteBuilder(
        opaque: false,
        barrierColor: Colors.black,
        pageBuilder: (_, _, _) => _FullscreenImagePage(imageBytes: widget.imageBytes),
        transitionsBuilder: (_, anim, _, child) => FadeTransition(opacity: anim, child: child),
      ),
    );
  }

  Future<void> _performOCR() async {
    setState(() {
      _isLoading = true;
      _error     = null;
      _ocrProgress = 0;
      _ocrStage    = 'pending';
      _ocrMessage  = '';
    });

    final settings = context.read<SettingsService>();
    final discovery = context.read<ServerDiscoveryService>();

    // Получаем URL: авто-обнаруженный или из сохранённых настроек
    final serverUrl = discovery.discoveredUrl ?? settings.serverUrl;

    // ── Выбор метода: v2 (асинхронный) или v1 (синхронный) ────────────────
    //
    // useAsyncOcr читается из SettingsService.
    // Если true — используем /ocr/v2 (Celery + Redis).
    // Если false — используем /ocr (cинхронный блокирующий).
    final Map<String, dynamic> result;

    if (settings.useAsyncOcr) {
      // v2: асинхронный режим с polling и progress-индикатором
      result = await ApiService.recognizeTextAsync(
        widget.imageBytes,
        widget.imagePath.split('/').last,
        baseUrl: serverUrl,
        // FIX #4: передаём cancelToken — при dispose() polling немедленно остановится
        cancelToken: _cancelToken,
        onProgress: (progress, stage, message) {
          if (mounted) {
            setState(() {
              _ocrProgress = progress;
              _ocrStage    = stage;
              _ocrMessage  = message;
            });
          }
        },
      );

      // FIX #4: если polling был отменён (пользователь нажал «Назад») — молча выходим
      if (result['cancelled'] == true) return;
    } else {
      // v1: синхронный режим (POST /ocr)
      result = await ApiService.recognizeText(
        widget.imageBytes,
        widget.imagePath.split('/').last,
        baseUrl: serverUrl,
      );
    }

    if (!mounted) return;

    setState(() {
      _isLoading = false;
      if (result['success'] == true) {
        _recognizedText = result['correctedText'] as String? ?? '';
        _confidence     = (result['confidence']   as num?)?.toDouble() ?? 0.0;
        _isDemo         = false;

        // Сохраняем запись в Hive через HistoryService
        final item = createHistoryItem(
          originalText:  result['originalText']  as String? ?? _recognizedText,
          correctedText: result['correctedText'] as String? ?? _recognizedText,
          convertedText: result['convertedText'] as String? ?? '',
          confidence:    _confidence,
          imagePath:     widget.imagePath,
        );
        context.read<HistoryService>().addItem(item);
      } else {
        final settings = context.read<SettingsService>();
        _error = result['error'] as String? ?? settings.t('unknown_error');
      }
    });
  }

  void _copyText(SettingsService settings) {
    Clipboard.setData(ClipboardData(text: _recognizedText));
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

  void _toggleEdit() {
    setState(() {
      if (_isEditing) {
        _recognizedText = _editController.text;
      } else {
        _editController.text = _recognizedText;
      }
      _isEditing = !_isEditing;
    });
  }

  void _convertText() {
    setState(() {
      _recognizedText = UzbekConverter.autoConvert(_recognizedText);
      if (_isEditing) {
        _editController.text = _recognizedText;
      }
    });
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
                  // Glass App Bar
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    child: Row(
                      children: [
                        GestureDetector(
                          onTap: () => Navigator.pop(context),
                          child: Container(
                            width: 38,
                            height: 38,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.05),
                              border: Border.all(
                                color: isDark ? Colors.white.withValues(alpha: 0.15) : Colors.white.withValues(alpha: 0.6),
                                width: 0.8,
                              ),
                            ),
                            child: Icon(Icons.arrow_back_ios_new_rounded, size: 16, color: settings.textColor),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Text(
                          settings.t('result'),
                          style: GoogleFonts.inter(
                            fontSize: 21,
                            fontWeight: FontWeight.w800,
                            letterSpacing: -0.4,
                            color: settings.textColor,
                          ),
                        ),
                        const Spacer(),
                        if (!_isLoading && _recognizedText.isNotEmpty)
                          GestureDetector(
                            onTap: () => _copyText(settings),
                            child: Container(
                              width: 38,
                              height: 38,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.05),
                                border: Border.all(
                                  color: isDark ? Colors.white.withValues(alpha: 0.15) : Colors.white.withValues(alpha: 0.6),
                                  width: 0.8,
                                ),
                              ),
                              child: Icon(Icons.copy_rounded, size: 18, color: settings.subtitleColor),
                            ),
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
                          // Image Preview — tap to fullscreen
                          GestureDetector(
                            onTap: () => _openFullscreen(context),
                            child: Hero(
                              tag: 'ocr_image',
                              child: ClipRRect(
                                borderRadius: BorderRadius.circular(20),
                                child: Stack(
                                  children: [
                                    Container(
                                      constraints: const BoxConstraints(maxHeight: 250),
                                      width: double.infinity,
                                      child: Image.memory(widget.imageBytes, fit: BoxFit.cover),
                                    ),
                                    Positioned(
                                      right: 10,
                                      bottom: 10,
                                      child: Container(
                                        padding: const EdgeInsets.all(6),
                                        decoration: BoxDecoration(
                                          color: Colors.black.withValues(alpha: 0.5),
                                          borderRadius: BorderRadius.circular(8),
                                        ),
                                        child: const Icon(Icons.fullscreen_rounded, color: Colors.white, size: 20),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ).animate().fadeIn(duration: 500.ms).scaleXY(begin: 0.95),

                          const SizedBox(height: 20),

                          // Confidence Badge
                          if (!_isLoading && _error == null)
                            _buildConfidenceBadge(settings)
                                .animate()
                                .fadeIn(delay: 300.ms, duration: 500.ms),

                          const SizedBox(height: 16),

                          // Demo Warning
                          if (_isDemo)
                            Container(
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: Colors.orange.withValues(alpha: 0.1),
                                borderRadius: BorderRadius.circular(14),
                                border: Border.all(color: Colors.orange.withValues(alpha: 0.3)),
                              ),
                              child: Row(
                                children: [
                                  const Icon(Icons.science_rounded, color: Colors.orange, size: 22),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Text(
                                      settings.t('demo_mode'),
                                      style: GoogleFonts.inter(fontSize: 13, color: Colors.orange, fontWeight: FontWeight.w500),
                                    ),
                                  ),
                                ],
                              ),
                            ).animate().fadeIn(delay: 400.ms, duration: 500.ms),

                          if (_isDemo) const SizedBox(height: 16),

                          // Result Section
                          if (_isLoading)
                            _buildLoadingState(settings)
                          else if (_error != null)
                            _buildErrorState(settings)
                          else
                            _isEditing ? _buildEditableText(settings) : _buildResultText(settings),

                          const SizedBox(height: 24),

                          // Copy button
                          if (!_isLoading && _recognizedText.isNotEmpty)
                            _buildBottomButton(
                              icon: Icons.copy_all_rounded,
                              label: settings.t('copy'),
                              color: const Color(0xFF6C63FF),
                              onTap: () => _copyText(settings),
                            ).animate().fadeIn(delay: 600.ms, duration: 500.ms).slideY(begin: 0.2),

                          // Edit & Convert row
                          if (!_isLoading && _recognizedText.isNotEmpty) const SizedBox(height: 12),
                          if (!_isLoading && _recognizedText.isNotEmpty)
                            Row(
                              children: [
                                Expanded(
                                  child: _buildBottomButton(
                                    icon: _isEditing ? Icons.check_rounded : Icons.edit_rounded,
                                    label: _isEditing ? settings.t('save') : settings.t('edit'),
                                    color: const Color(0xFF7C4DFF),
                                    onTap: _toggleEdit,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: _buildBottomButton(
                                    icon: Icons.translate_rounded,
                                    label: UzbekConverter.isCyrillic(_recognizedText)
                                        ? settings.t('to_latin')
                                        : settings.t('to_cyrillic'),
                                    color: const Color(0xFFFF6D00),
                                    onTap: _convertText,
                                  ),
                                ),
                              ],
                            ).animate().fadeIn(delay: 700.ms, duration: 500.ms).slideY(begin: 0.2),

                          const SizedBox(height: 32),
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

  Widget _buildConfidenceBadge(SettingsService settings) {
    final Color badgeColor;
    final String label;
    if (_confidence >= 0.9) {
      badgeColor = const Color(0xFF00E676);
      label = settings.t('high_accuracy');
    } else if (_confidence >= 0.7) {
      badgeColor = Colors.orange;
      label = settings.t('mid_accuracy');
    } else {
      badgeColor = Colors.redAccent;
      label = settings.t('low_accuracy');
    }

    final bool isDark = settings.isDark(settings.systemBrightness);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: badgeColor.withValues(alpha: isDark ? 0.16 : 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: badgeColor.withValues(alpha: 0.35), width: 0.9),
        boxShadow: [
          BoxShadow(
            color: badgeColor.withValues(alpha: 0.14),
            blurRadius: 16,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: badgeColor,
              boxShadow: [
                BoxShadow(color: badgeColor.withValues(alpha: 0.8), blurRadius: 6),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(
            '$label: ${(_confidence * 100).toStringAsFixed(1)}%',
            style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: badgeColor),
          ),
        ],
      ),
    );
  }

  /// Прогресс-виджет для асинхронного OCR.
  ///
  /// Показывает:
  ///   - Анимированный LinearProgressIndicator с процентами.
  ///   - Название текущего этапа (например, "Распознавание Dual-Reader").
  ///   - Обычный spinner если прогресс = 0 (ожидание в очереди).
  Widget _buildLoadingState(SettingsService settings) {
    final bool hasProgress = _ocrProgress > 0;
    final bool isAsync = settings.useAsyncOcr;

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 32),
        child: Column(
          children: [
            // Иконка состояния
            if (hasProgress)
              Stack(
                alignment: Alignment.center,
                children: [
                  SizedBox(
                    width: 72,
                    height: 72,
                    child: CircularProgressIndicator(
                      value: _ocrProgress / 100,
                      color: const Color(0xFF6C63FF),
                      backgroundColor: const Color(0xFF6C63FF).withValues(alpha: 0.15),
                      strokeWidth: 5,
                    ),
                  ),
                  Text(
                    '$_ocrProgress%',
                    style: GoogleFonts.inter(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      color: const Color(0xFF6C63FF),
                    ),
                  ),
                ],
              )
            else
              const SizedBox(
                width: 52,
                height: 52,
                child: CircularProgressIndicator(
                  color: Color(0xFF6C63FF),
                  strokeWidth: 3,
                ),
              ),

            const SizedBox(height: 20),

            // Сообщение о текущем этапе
            Text(
              _ocrMessage.isNotEmpty ? _ocrMessage : settings.t('loading'),
              style: GoogleFonts.inter(
                fontSize: 15,
                fontWeight: FontWeight.w600,
                color: settings.textColor,
              ),
              textAlign: TextAlign.center,
            ),

            const SizedBox(height: 8),

            // Подсказка режима
            Text(
              isAsync
                  ? settings.t('async_mode_hint')  // FIX #11: убрали хардкод "Асинх режим (Celery + Redis)"
                  : settings.t('please_wait'),
              style: GoogleFonts.inter(
                fontSize: 12,
                color: settings.subtitleColor.withValues(alpha: 0.6),
              ),
            ),

            // LinearProgressIndicator для async-режима
            if (isAsync) ...[
              const SizedBox(height: 16),
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: LinearProgressIndicator(
                  value: hasProgress ? _ocrProgress / 100 : null,
                  minHeight: 6,
                  backgroundColor: const Color(0xFF6C63FF).withValues(alpha: 0.12),
                  valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF6C63FF)),
                ),
              ),
              const SizedBox(height: 8),
              // Название этапа (stage)
              Text(
                _stageLabel(_ocrStage),
                style: GoogleFonts.inter(
                  fontSize: 11,
                  color: const Color(0xFF6C63FF).withValues(alpha: 0.7),
                  letterSpacing: 0.3,
                ),
              ),
            ],
          ],
        ),
      ),
    ).animate().fadeIn(duration: 500.ms);
  }

  /// Преобразует machine-название этапа в человечески читаемый текст.
  String _stageLabel(String stage) {
    switch (stage) {
      case 'pending':          return 'Очередь задач...'; 
      case 'started':          return 'Воркер запускается...';
      case 'loading_image':    return 'Загрузка изображения...';
      case 'loading_models':   return 'Инициализация OCR-моделей...';
      case 'text_detection':   return 'CRAFT: обнаружение текстовых блоков...';
      case 'ocr_recognition':  return 'Распознавание (Dual-Reader)...';
      case 'normalization':    return 'Нормализация гомоглифов...';
      case 'spell_correction': return 'Исправление орфографии...';
      case 'script_conversion':return 'Конвертация алфавита...';
      case 'success':          return 'Готово ✔';
      default:                 return stage;
    }
  }

  Widget _buildErrorState(SettingsService settings) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 40),
        child: Column(
          children: [
            const Icon(Icons.error_outline_rounded, color: Colors.redAccent, size: 56),
            const SizedBox(height: 16),
            Text(settings.t('error'), style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w600, color: Colors.redAccent)),
            const SizedBox(height: 8),
            Text(_error!, style: GoogleFonts.inter(fontSize: 14, color: settings.subtitleColor), textAlign: TextAlign.center),
            const SizedBox(height: 20),
            ElevatedButton.icon(
              onPressed: _performOCR,
              icon: const Icon(Icons.refresh_rounded),
              label: Text(settings.t('retry')),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildResultText(SettingsService settings) {
    final bool isDark = settings.isDark(settings.systemBrightness);
    return IOS26GlassCard(
      isDark: isDark,
      borderRadius: 24,
      padding: const EdgeInsets.all(22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(7),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(10),
                  gradient: const LinearGradient(colors: [Color(0xFF7928CA), Color(0xFF00DFD8)]),
                ),
                child: const Icon(Icons.text_fields_rounded, color: Colors.white, size: 18),
              ),
              const SizedBox(width: 12),
              Text(
                settings.t('detected_text'),
                style: GoogleFonts.inter(
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.3,
                  color: settings.textColor,
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          SelectableText(
            _recognizedText,
            style: GoogleFonts.inter(
              fontSize: 15.5,
              fontWeight: FontWeight.w400,
              color: settings.textColor.withValues(alpha: 0.9),
              height: 1.7,
              letterSpacing: -0.1,
            ),
          ),
        ],
      ),
    ).animate().fadeIn(delay: 400.ms, duration: 600.ms).slideY(begin: 0.1);
  }

  Widget _buildEditableText(SettingsService settings) {
    final bool isDark = settings.isDark(settings.systemBrightness);
    return IOS26GlassCard(
      isDark: isDark,
      borderRadius: 24,
      padding: const EdgeInsets.all(22),
      customBorder: Border.all(color: const Color(0xFF7928CA).withValues(alpha: 0.4), width: 1.2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(7),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(10),
                  gradient: const LinearGradient(colors: [Color(0xFF7928CA), Color(0xFFB388FF)]),
                ),
                child: const Icon(Icons.edit_rounded, color: Colors.white, size: 18),
              ),
              const SizedBox(width: 12),
              Text(
                settings.t('edit'),
                style: GoogleFonts.inter(
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.3,
                  color: settings.textColor,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _editController,
            maxLines: null,
            style: GoogleFonts.inter(fontSize: 15.5, color: settings.textColor.withValues(alpha: 0.85), height: 1.7),
            decoration: InputDecoration(
              border: InputBorder.none,
              hintText: settings.t('edit_hint'),
              hintStyle: GoogleFonts.inter(color: settings.subtitleColor.withValues(alpha: 0.4)),
            ),
          ),
        ],
      ),
    ).animate().fadeIn(duration: 300.ms);
  }

  Widget _buildBottomButton({
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        onTap();
      },
      child: Container(
        height: 52,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          color: color.withValues(alpha: 0.16),
          border: Border.all(color: color.withValues(alpha: 0.35), width: 0.9),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: 0.12),
              blurRadius: 18,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(width: 8),
            Text(
              label,
              style: GoogleFonts.inter(
                fontSize: 15,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.2,
                color: color,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Fullscreen Image Viewer ─────────────────────────────────────────────────

class _FullscreenImagePage extends StatelessWidget {
  final Uint8List imageBytes;

  const _FullscreenImagePage({required this.imageBytes});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: [
          // Pinch-to-zoom image
          GestureDetector(
            onTap: () => Navigator.pop(context),
            child: Center(
              child: Hero(
                tag: 'ocr_image',
                child: InteractiveViewer(
                  minScale: 0.5,
                  maxScale: 5.0,
                  child: Image.memory(
                    imageBytes,
                    fit: BoxFit.contain,
                  ),
                ),
              ),
            ),
          ),

          // Close button
          SafeArea(
            child: Align(
              alignment: Alignment.topRight,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: GestureDetector(
                  onTap: () => Navigator.pop(context),
                  child: Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.6),
                      shape: BoxShape.circle,
                      border: Border.all(color: Colors.white24),
                    ),
                    child: const Icon(Icons.close_rounded, color: Colors.white, size: 22),
                  ),
                ),
              ),
            ),
          ),

          // Hint
          SafeArea(
            child: Align(
              alignment: Alignment.bottomCenter,
              child: Padding(
                padding: const EdgeInsets.only(bottom: 24),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    '🔍  Pinch to zoom',
                    style: GoogleFonts.inter(fontSize: 13, color: Colors.white60),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
