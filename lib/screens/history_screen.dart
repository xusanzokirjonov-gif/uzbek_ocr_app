// lib/screens/history_screen.dart
//
// Экран истории OCR-распознавания.
//
// Отображает список карточек (Card) с записями из Hive базы данных.
// Поддерживает:
//   - Удаление по свайпу (Dismissible)
//   - Раскрытие карточки для просмотра всех вариантов текста
//   - Копирование текста в буфер обмена
//   - Очистку всей истории через диалог подтверждения
//
// Стейт-менеджмент: Provider (Consumer<HistoryService>).
// При каждом вызове addItem/deleteItem/clearHistory в HistoryService
// вызывается notifyListeners(), что перестраивает Consumer.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../models/history_item.dart';
import '../services/history_service.dart';
import '../services/settings_service.dart';

class HistoryScreen extends StatelessWidget {
  const HistoryScreen({super.key});

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
                  // ── App Bar ──────────────────────────────────────────────
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                    child: Row(
                      children: [
                        IconButton(
                          onPressed: () => Navigator.pop(context),
                          icon: Icon(Icons.arrow_back_ios_rounded, color: settings.textColor),
                        ),
                        Text(
                          settings.t('hist_title'),
                          style: GoogleFonts.inter(
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                            color: settings.textColor,
                          ),
                        ),
                        const Spacer(),
                        // Кнопка очистки появляется только если история не пуста
                        Consumer<HistoryService>(
                          builder: (_, history, _) {
                            if (history.isEmpty) return const SizedBox();
                            return IconButton(
                              onPressed: () => _showClearDialog(context, history, settings),
                              icon: Icon(Icons.delete_sweep_rounded, color: settings.subtitleColor),
                              tooltip: settings.t('hist_clear'),
                            );
                          },
                        ),
                      ],
                    ),
                  ).animate().fadeIn(duration: 400.ms).slideY(begin: -0.2),

                  // ── Список записей ──────────────────────────────────────
                  Expanded(
                    child: Consumer<HistoryService>(
                      builder: (context, history, _) {
                        final items = history.getAllItems();

                        if (items.isEmpty) {
                          return _buildEmptyState(settings);
                        }

                        return ListView.builder(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                          itemCount: items.length,
                          itemBuilder: (context, index) => _HistoryCard(
                            item:     items[index],
                            index:    index,
                            history:  history,
                            settings: settings,
                          ),
                        );
                      },
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

  // ── Пустое состояние ──────────────────────────────────────────────────────

  Widget _buildEmptyState(SettingsService settings) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.history_rounded,
            size: 80,
            color: settings.subtitleColor.withValues(alpha: 0.3),
          ),
          const SizedBox(height: 16),
          Text(
            settings.t('hist_empty'),
            style: GoogleFonts.inter(
              fontSize: 20,
              fontWeight: FontWeight.w600,
              color: settings.subtitleColor,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            settings.t('hist_empty_sub'),
            style: GoogleFonts.inter(
              fontSize: 14,
              color: settings.subtitleColor.withValues(alpha: 0.6),
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    ).animate().fadeIn(duration: 600.ms);
  }

  // ── Диалог подтверждения очистки ─────────────────────────────────────────

  void _showClearDialog(
    BuildContext context,
    HistoryService history,
    SettingsService settings,
  ) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: settings.cardColor,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(color: settings.borderColor),
        ),
        title: Text(
          settings.t('hist_clear'),
          style: GoogleFonts.inter(
            color: settings.textColor,
            fontWeight: FontWeight.w700,
          ),
        ),
        content: Text(
          settings.t('hist_clear_msg'),
          style: GoogleFonts.inter(color: settings.subtitleColor),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(
              settings.t('cancel'),
              style: GoogleFonts.inter(color: settings.subtitleColor),
            ),
          ),
          TextButton(
            onPressed: () {
              history.clearHistory();
              Navigator.pop(ctx);
            },
            child: Text(
              settings.t('delete'),
              style: GoogleFonts.inter(
                color: Colors.redAccent,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}


// ─── Карточка записи истории ──────────────────────────────────────────────────
//
// Вынесена в отдельный StatefulWidget для управления состоянием раскрытия.
// Каждая карточка независима — раскрытие одной не влияет на другие.

class _HistoryCard extends StatefulWidget {
  final HistoryItem item;
  final int index;
  final HistoryService history;
  final SettingsService settings;

  const _HistoryCard({
    required this.item,
    required this.index,
    required this.history,
    required this.settings,
  });

  @override
  State<_HistoryCard> createState() => _HistoryCardState();
}

class _HistoryCardState extends State<_HistoryCard> {
  /// Раскрыта ли карточка (показаны дополнительные поля).
  bool _isExpanded = false;

  // ── Цвета уровня точности ─────────────────────────────────────────────────

  Color get _confidenceColor {
    switch (widget.item.confidenceLevel) {
      case ConfidenceLevel.high:   return const Color(0xFF00E676);
      case ConfidenceLevel.medium: return Colors.orange;
      case ConfidenceLevel.low:    return Colors.redAccent;
    }
  }

  // ── Форматирование времени ────────────────────────────────────────────────

  String get _timeAgo {
    final diff = DateTime.now().difference(widget.item.dateTime);
    final s = widget.settings;
    if (diff.inMinutes < 1)  return s.t('just_now');
    if (diff.inMinutes < 60) return '${diff.inMinutes} ${s.t('min_ago')}';
    if (diff.inHours   < 24) return '${diff.inHours} ${s.t('hours_ago')}';
    if (diff.inDays    < 7)  return '${diff.inDays} ${s.t('days_ago')}';
    final d = widget.item.dateTime;
    return '${d.day}.${d.month.toString().padLeft(2,'0')}.${d.year}';
  }

  // ── Копирование текста ────────────────────────────────────────────────────

  void _copyText(String text) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Row(
          children: [
            const Icon(Icons.check_circle, color: Colors.white, size: 18),
            const SizedBox(width: 8),
            Text(widget.settings.t('copied'), style: GoogleFonts.inter()),
          ],
        ),
        backgroundColor: const Color(0xFF6C63FF),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.settings;

    return Dismissible(
      // Ключ: уникальный ID из Hive — гарантирует корректное удаление
      key: Key(widget.item.id),
      // Свайп только справа налево (стандарт iOS/Android)
      direction: DismissDirection.endToStart,
      // Удаляем из Hive при свайпе
      onDismissed: (_) => widget.history.deleteItem(widget.item.id),
      // Фон при свайпе: красный контейнер с иконкой корзины
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 24),
        margin: const EdgeInsets.only(bottom: 12),
        decoration: BoxDecoration(
          color: Colors.redAccent.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.redAccent.withValues(alpha: 0.3)),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.delete_rounded, color: Colors.redAccent, size: 26),
            const SizedBox(height: 4),
            Text(
              s.t('delete'),
              style: GoogleFonts.inter(
                fontSize: 11,
                color: Colors.redAccent,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        margin: const EdgeInsets.only(bottom: 12),
        decoration: BoxDecoration(
          color: s.cardColor,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: s.borderColor),
          boxShadow: s.brightness == Brightness.dark
              ? []
              : [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.04),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: BorderRadius.circular(18),
            onTap: () => setState(() => _isExpanded = !_isExpanded),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // ── Заголовок карточки ──────────────────────────────
                  Row(
                    children: [
                      // Бейдж точности
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 5,
                        ),
                        decoration: BoxDecoration(
                          color: _confidenceColor.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: _confidenceColor.withValues(alpha: 0.3),
                          ),
                        ),
                        child: Text(
                          widget.item.confidencePercent,
                          style: GoogleFonts.inter(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: _confidenceColor,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      // Скрипт (латиница / кириллица)
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 5,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xFF6C63FF).withValues(alpha: 0.08),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          'OCR',
                          style: GoogleFonts.inter(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: const Color(0xFF6C63FF).withValues(alpha: 0.7),
                          ),
                        ),
                      ),
                      const Spacer(),
                      Text(
                        _timeAgo,
                        style: GoogleFonts.inter(
                          fontSize: 12,
                          color: s.subtitleColor,
                        ),
                      ),
                      const SizedBox(width: 4),
                      // Иконка раскрытия
                      AnimatedRotation(
                        turns: _isExpanded ? 0.5 : 0.0,
                        duration: const Duration(milliseconds: 250),
                        child: Icon(
                          Icons.keyboard_arrow_down_rounded,
                          size: 20,
                          color: s.subtitleColor,
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 12),

                  // ── Основной текст (correctedText) ──────────────────
                  Text(
                    widget.item.correctedText,
                    maxLines: _isExpanded ? null : 3,
                    overflow: _isExpanded
                        ? TextOverflow.visible
                        : TextOverflow.ellipsis,
                    style: GoogleFonts.inter(
                      fontSize: 14,
                      color: s.textColor.withValues(alpha: 0.85),
                      height: 1.6,
                    ),
                  ),

                  // ── Раскрытое содержимое ────────────────────────────
                  if (_isExpanded) ...[
                    const SizedBox(height: 16),
                    const Divider(height: 1),
                    const SizedBox(height: 16),

                    // Конвертированный текст
                    if (widget.item.convertedText.isNotEmpty)
                      _buildTextSection(
                        label:  '↔ ${s.t('converter')}',
                        text:   widget.item.convertedText,
                        color:  const Color(0xFF00D9FF),
                        icon:   Icons.translate_rounded,
                        settings: s,
                      ),

                    if (widget.item.convertedText.isNotEmpty)
                      const SizedBox(height: 12),

                    // Оригинальный (сырой) текст
                    if (widget.item.originalText != widget.item.correctedText)
                      _buildTextSection(
                        label:  'Original (raw)',
                        text:   widget.item.originalText,
                        color:  Colors.orange,
                        icon:   Icons.text_fields_rounded,
                        settings: s,
                      ),
                  ],

                  const SizedBox(height: 12),

                  // ── Кнопки действий ────────────────────────────────
                  Row(
                    children: [
                      _buildActionButton(
                        icon:  Icons.copy_rounded,
                        label: s.t('copy_btn'),
                        onTap: () => _copyText(widget.item.correctedText),
                        settings: s,
                      ),
                      if (widget.item.convertedText.isNotEmpty) ...[
                        const SizedBox(width: 16),
                        _buildActionButton(
                          icon:  Icons.copy_rounded,
                          label: s.t('copy_conv'),
                          onTap: () => _copyText(widget.item.convertedText),
                          settings: s,
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ).animate().fadeIn(delay: (80 * widget.index).ms, duration: 400.ms).slideX(begin: 0.08);
  }

  // ── Секция дополнительного текста ─────────────────────────────────────────

  Widget _buildTextSection({
    required String label,
    required String text,
    required Color color,
    required IconData icon,
    required SettingsService settings,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 14, color: color),
              const SizedBox(width: 6),
              Text(
                label,
                style: GoogleFonts.inter(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: color,
                  letterSpacing: 0.3,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SelectableText(
            text,
            style: GoogleFonts.inter(
              fontSize: 13,
              color: settings.textColor.withValues(alpha: 0.75),
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  // ── Кнопка действия ──────────────────────────────────────────────────────

  Widget _buildActionButton({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
    required SettingsService settings,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: settings.subtitleColor),
          const SizedBox(width: 4),
          Text(
            label,
            style: GoogleFonts.inter(
              fontSize: 12,
              color: settings.subtitleColor,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}
