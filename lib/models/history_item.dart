// lib/models/history_item.dart
//
// Модель данных для хранения записи истории OCR в базе данных Hive.
//
// Hive хранит данные как бинарные объекты (Box). Для каждого класса
// необходим TypeAdapter — сериализатор/десериализатор.
//
// Два подхода к TypeAdapter:
//   1. Кодогенерация: добавить аннотации @HiveType/@HiveField и запустить:
//      flutter pub run build_runner build
//      Тогда адаптер генерируется автоматически в history_item.g.dart.
//
//   2. Ручное написание: реализовать TypeAdapter<HistoryItem> вручную.
//      Это более прозрачно и не требует build_runner. Именно этот подход
//      используется здесь (для понимания внутренней работы Hive).

import 'package:hive/hive.dart';

// ─── Константы ────────────────────────────────────────────────────────────────

/// Имя Box (таблицы) в базе данных Hive.
const String kHistoryBoxName = 'history';

/// Уникальный идентификатор TypeAdapter.
/// Каждый класс в Hive должен иметь уникальный typeId (0–223).
const int kHistoryItemTypeId = 0;


// ─── Модель данных ────────────────────────────────────────────────────────────

/// Запись истории OCR-распознавания.
///
/// Хранит все варианты текста (оригинальный, исправленный, конвертированный),
/// точность распознавания, дату и путь к изображению.
class HistoryItem extends HiveObject {
  /// Уникальный идентификатор записи (UUID на основе timestamp).
  final String id;

  /// Дата и время сканирования.
  final DateTime dateTime;

  /// Текст, распознанный OCR до исправления (сырой вывод).
  final String originalText;

  /// Текст после нормализации гомоглифов и исправления орфографии.
  final String correctedText;

  /// Текст, конвертированный в другой алфавит (латиница ↔ кириллица).
  final String convertedText;

  /// Точность распознавания (0.0 – 1.0).
  final double confidence;

  /// Путь к локально сохранённому изображению (может быть null).
  final String? imagePath;

  HistoryItem({
    required this.id,
    required this.dateTime,
    required this.originalText,
    required this.correctedText,
    required this.convertedText,
    required this.confidence,
    this.imagePath,
  });

  /// Точность в процентах для отображения в UI.
  String get confidencePercent =>
      '${(confidence * 100).toStringAsFixed(1)}%';

  /// Определяет цвет бейджа точности для UI.
  ConfidenceLevel get confidenceLevel {
    if (confidence >= 0.9) return ConfidenceLevel.high;
    if (confidence >= 0.7) return ConfidenceLevel.medium;
    return ConfidenceLevel.low;
  }

  @override
  String toString() => 'HistoryItem(id: $id, confidence: $confidence)';
}

/// Уровень точности распознавания (для UI-цветов).
enum ConfidenceLevel { high, medium, low }


// ─── TypeAdapter ──────────────────────────────────────────────────────────────

/// TypeAdapter отвечает за бинарную сериализацию объектов HistoryItem.
///
/// Hive хранит данные в бинарном формате для максимальной производительности.
/// TypeAdapter определяет, как объект преобразуется в байты (write) и
/// восстанавливается из байтов (read).
///
/// Схема полей (field indices):
///   0 → id           (String)
///   1 → dateTime     (DateTime)
///   2 → originalText  (String)
///   3 → correctedText (String)
///   4 → convertedText (String)
///   5 → confidence   (double)
///   6 → imagePath    (String?)
///
/// ВАЖНО: Индексы полей нельзя менять после выпуска приложения,
/// так как они используются для десериализации существующих данных.
class HistoryItemAdapter extends TypeAdapter<HistoryItem> {
  @override
  final int typeId = kHistoryItemTypeId;

  @override
  HistoryItem read(BinaryReader reader) {
    // Читаем количество сохранённых полей
    final numOfFields = reader.readByte();

    // Считываем все поля в Map: { fieldIndex → value }
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };

    return HistoryItem(
      id:            fields[0] as String,
      dateTime:      fields[1] as DateTime,
      originalText:  fields[2] as String,
      correctedText: fields[3] as String,
      convertedText: fields[4] as String,
      confidence:    fields[5] as double,
      imagePath:     fields[6] as String?,
    );
  }

  @override
  void write(BinaryWriter writer, HistoryItem obj) {
    // Записываем количество полей (7)
    writer.writeByte(7);

    // Записываем каждое поле как пару: [индекс][значение]
    writer
      ..writeByte(0)
      ..write(obj.id)
      ..writeByte(1)
      ..write(obj.dateTime)
      ..writeByte(2)
      ..write(obj.originalText)
      ..writeByte(3)
      ..write(obj.correctedText)
      ..writeByte(4)
      ..write(obj.convertedText)
      ..writeByte(5)
      ..write(obj.confidence)
      ..writeByte(6)
      ..write(obj.imagePath);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is HistoryItemAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}
