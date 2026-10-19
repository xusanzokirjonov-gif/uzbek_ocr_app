// lib/services/history_service.dart
//
// Сервис истории OCR на базе Hive (локальная NoSQL база данных).
//
// Преимущества Hive перед SharedPreferences для хранения истории:
//   ✅ Хранит сложные объекты (не только примитивы)
//   ✅ Быстрее на больших данных (бинарный формат)
//   ✅ Поддерживает ленивую загрузку (LazyBox)
//   ✅ Не нужна сериализация в JSON вручную
//   ✅ Атомарные операции (put/delete без перезаписи всего файла)
//
// Архитектура:
//   HistoryService extends ChangeNotifier
//     ├── init()         — открыть Box при старте приложения
//     ├── addItem()      — добавить новую запись
//     ├── getAllItems()   — получить все записи (новые первые)
//     ├── deleteItem()   — удалить запись по id
//     └── clearHistory() — очистить всю историю

import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:uuid/uuid.dart';  // FIX #5: UUID для гарантированной уникальности ID
import '../models/history_item.dart';

// FIX #5: синглтон-генератор UUID—создаётся один раз, стоимость занулевая
const _uuid = Uuid();

class HistoryService extends ChangeNotifier {
  // Hive Box — аналог «таблицы» в реляционной БД.
  // Box<HistoryItem> хранит записи с ключом типа String (id).
  Box<HistoryItem>? _box;
  final List<HistoryItem> _inMemoryItems = [];

  /// Инициализирует Hive Box.
  ///
  /// Должен вызываться один раз при старте приложения (в main.dart),
  /// после Hive.initFlutter() и регистрации адаптеров.
  Future<void> init() async {
    try {
      _box = await Hive.openBox<HistoryItem>(kHistoryBoxName);
      debugPrint('[HistoryService] Hive box opened successfully.');
    } catch (e) {
      debugPrint('[HistoryService] Failed to open box: $e. Falling back to in-memory storage.');
      _box = null;
    }
  }

  // ─── Публичный API ─────────────────────────────────────────────────────────

  /// Возвращает все записи истории, отсортированные от новых к старым.
  ///
  /// Hive хранит записи в порядке вставки, поэтому сортируем явно.
  List<HistoryItem> getAllItems() {
    if (_box == null) {
      final items = List<HistoryItem>.from(_inMemoryItems);
      items.sort((a, b) => b.dateTime.compareTo(a.dateTime));
      return items;
    }
    try {
      final items = _box!.values.toList();
      items.sort((a, b) => b.dateTime.compareTo(a.dateTime));
      return items;
    } catch (e) {
      debugPrint('[HistoryService] Failed to get items from Hive: $e');
      final items = List<HistoryItem>.from(_inMemoryItems);
      items.sort((a, b) => b.dateTime.compareTo(a.dateTime));
      return items;
    }
  }

  /// Добавляет новую запись истории.
  ///
  /// В качестве ключа Hive используем [item.id] — это позволяет
  /// находить записи по id без полного перебора.
  Future<void> addItem(HistoryItem item) async {
    if (_box == null) {
      _inMemoryItems.add(item);
      notifyListeners();
      return;
    }
    try {
      await _box!.put(item.id, item);
    } catch (e) {
      debugPrint('[HistoryService] Failed to add item to Hive: $e. Falling back to in-memory.');
      _inMemoryItems.add(item);
    }
    notifyListeners();
  }

  /// Удаляет запись по уникальному идентификатору.
  Future<void> deleteItem(String id) async {
    if (_box == null) {
      _inMemoryItems.removeWhere((item) => item.id == id);
      notifyListeners();
      return;
    }
    try {
      await _box!.delete(id);
    } catch (e) {
      debugPrint('[HistoryService] Failed to delete item from Hive: $e');
      _inMemoryItems.removeWhere((item) => item.id == id);
    }
    notifyListeners();
  }

  /// Очищает всю историю.
  Future<void> clearHistory() async {
    if (_box == null) {
      _inMemoryItems.clear();
      notifyListeners();
      return;
    }
    try {
      await _box!.clear();
    } catch (e) {
      debugPrint('[HistoryService] Failed to clear history in Hive: $e');
      _inMemoryItems.clear();
    }
    notifyListeners();
  }

  /// Количество записей в истории (для UI).
  int get itemCount {
    if (_box == null) return _inMemoryItems.length;
    try {
      return _box!.length;
    } catch (e) {
      return _inMemoryItems.length;
    }
  }

  /// True если история пуста.
  bool get isEmpty {
    if (_box == null) return _inMemoryItems.isEmpty;
    try {
      return _box!.isEmpty;
    } catch (e) {
      return _inMemoryItems.isEmpty;
    }
  }
}

// ─── Вспомогательная функция ──────────────────────────────────────────────────

/// Создаёт новый [HistoryItem] из данных OCR-ответа.
///
/// Используется в ResultScreen после получения ответа от сервера.
///
/// FIX #5: [id] генерируется через UUID v4, а не миллисекунды.
/// millisecondsSinceEpoch могут совпадать при быстром сохранении (Hive
/// молча перезапишет запись с тем же ключом).
HistoryItem createHistoryItem({
  required String originalText,
  required String correctedText,
  required String convertedText,
  required double confidence,
  String? imagePath,
}) {
  return HistoryItem(
    id:            _uuid.v4(),   // FIX #5: UUID v4 — гарантированно уникален
    dateTime:      DateTime.now(),
    originalText:  originalText,
    correctedText: correctedText,
    convertedText: convertedText,
    confidence:    confidence,
    imagePath:     imagePath,
  );
}
