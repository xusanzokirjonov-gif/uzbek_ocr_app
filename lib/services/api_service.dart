import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;

/// Токен отмены для прерывания polling-цикла.
///
/// FIX #4: ResultScreen передаёт этот токен в recognizeTextAsync.
/// При dispose() экрана вызывается cancel() — polling прекращается
/// немедленно, не дожидаясь следующего интервала.
class OcrCancelToken {
  bool _cancelled = false;

  /// Отменяет операцию. Повторные вызовы безопасны.
  void cancel() => _cancelled = true;

  /// true если операция была отменена.
  bool get isCancelled => _cancelled;
}

/// Сервис для взаимодействия с OCR-бэкендом.
///
/// Поддерживает два режима работы:
///
///   v1 (синхронный, POST /ocr):
///     Отправляет изображение и ждёт результат (блокирует UI до 60 сек).
///     Используется как fallback если v2 недоступен.
///
///   v2 (асинхронный, POST /ocr/v2 + GET /ocr/status/{task_id}):
///     1. Загружает изображение → получает task_id (мгновенно).
///     2. Опрашивает GET /ocr/status/{task_id} каждые 2 сек.
///     3. Возвращает результат когда статус = SUCCESS.
///     Не блокирует UI, поддерживает отображение прогресса.
class ApiService {
  // ─── Константы ───────────────────────────────────────────────────────────────

  /// Интервал между опросами статуса задачи (polling interval).
  static const _pollInterval = Duration(seconds: 2);

  /// Максимальное время ожидания результата асинхронной задачи.
  /// После истечения — возвращаем ошибку timeout.
  static const _maxWaitDuration = Duration(minutes: 5);

  /// Таймаут одного HTTP-запроса (отдельно от общего таймаута задачи).
  /// EasyOCR на CPU может занимать до 2 минут на первом запросе (загрузка модели).
  static const _requestTimeout = Duration(seconds: 120);

  // ─── v1: Синхронный метод (оригинальный) ─────────────────────────────────────

  /// Отправляет байты изображения на синхронный OCR-сервер (POST /ocr).
  ///
  /// [bytes]    — содержимое файла изображения.
  /// [filename] — имя файла (нужно для MIME-определения на сервере).
  /// [baseUrl]  — базовый URL сервера (например, http://192.168.1.6:8000).
  ///
  /// Возвращает Map с полями: success, originalText, correctedText,
  /// convertedText, confidence, script, error.
  static Future<Map<String, dynamic>> recognizeText(
    Uint8List bytes,
    String filename, {
    required String baseUrl,
  }) async {
    try {
      if (bytes.isEmpty) {
        return {
          'success': false,
          'error': "Rasm ma'lumotlari bo'sh (0 bytes). Iltimos, boshqa rasm tanlang.",
        };
      }

      final uri     = Uri.parse('$baseUrl/ocr');
      final request = http.MultipartRequest('POST', uri);

      request.files.add(
        http.MultipartFile.fromBytes('image', bytes, filename: filename),
      );

      final streamedResponse = await request.send().timeout(_requestTimeout);
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final data = json.decode(response.body) as Map<String, dynamic>;

        // Поддержка как старого API (поле 'text'), так и нового ('corrected_text').
        // Это обеспечивает обратную совместимость при обновлении бэкенда.
        final corrected = data['corrected_text'] as String?
            ?? data['text'] as String?
            ?? '';
        final original  = data['raw_text']       as String? ?? corrected;
        final converted = data['converted_text'] as String? ?? '';

        return {
          'success':       true,
          'originalText':  original,
          'correctedText': corrected,
          'convertedText': converted,
          'confidence':    (data['confidence'] as num?)?.toDouble() ?? 0.0,
          'script':        data['script'] as String? ?? 'latin',
        };
      } else {
        return {
          'success': false,
          'error':   'Server xatosi: ${response.statusCode}',
        };
      }
    } catch (e) {
      return {
        'success': false,
        'error':
            "Ulanish xatosi: $e\n\n"
            "Server: $baseUrl\n\n"
            "Sozlamalarda server manzilini tekshiring.",
      };
    }
  }

  // ─── v2: Асинхронный метод (Celery + Redis) ───────────────────────────────────

  /// Отправляет изображение на асинхронный OCR-сервер (POST /ocr/v2).
  ///
  /// FIX #4: добавлен параметр [cancelToken]. Если token.cancel() вызван
  /// (например, при dispose экрана), polling немедленно прекращается
  /// и возвращается специальный ответ {success: false, cancelled: true}.
  ///
  /// FIX #9: после Redis TTL (1ч) статус задачи сбрасывается в PENDING.
  /// При обнаружении PENDING после того, как задача уже выполнялась,
  /// возвращаем специальную ошибку вместо бесконечного повторного ожидания.
  ///
  /// [bytes]       — содержимое файла изображения.
  /// [filename]    — имя файла.
  /// [baseUrl]     — базовый URL сервера.
  /// [onProgress]  — callback для отображения прогресса (0–100, stage, message).
  /// [outputScript] — желаемый алфавит вывода: "latin", "cyrillic" или null (авто).
  /// [cancelToken] — токен для отмены polling из dispose().
  ///
  /// Возвращает Map с теми же полями что и [recognizeText].
  static Future<Map<String, dynamic>> recognizeTextAsync(
    Uint8List bytes,
    String filename, {
    required String baseUrl,
    void Function(int progress, String stage, String message)? onProgress,
    String? outputScript,
    OcrCancelToken? cancelToken,
  }) async {
    // ── Шаг 1: Отправляем изображение (POST /ocr/v2) ─────────────────────────
    if (bytes.isEmpty) {
      return {
        'success': false,
        'error': "Rasm ma'lumotlari bo'sh (0 bytes). Iltimos, boshqa rasm tanlang.",
      };
    }

    final String taskId;

    try {
      // Формируем URL с опциональным параметром output_script
      var submitUri = Uri.parse('$baseUrl/ocr/v2');
      if (outputScript != null) {
        submitUri = submitUri.replace(
          queryParameters: {'output_script': outputScript},
        );
      }

      final request = http.MultipartRequest('POST', submitUri);
      request.files.add(
        http.MultipartFile.fromBytes('image', bytes, filename: filename),
      );

      final streamedResponse = await request.send().timeout(_requestTimeout);
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode != 202) {
        // 202 Accepted — ожидаемый ответ от /ocr/v2
        return {
          'success': false,
          'error': 'Server xatosi (submit): ${response.statusCode}\n${response.body}',
        };
      }

      final submitData = json.decode(response.body) as Map<String, dynamic>;
      taskId = submitData['task_id'] as String? ?? '';

      if (taskId.isEmpty) {
        return {
          'success': false,
          'error': 'Server task_id qaytarmadi. Qayta urinib ko\'ring.',
        };
      }

      // Сообщаем что задача поставлена в очередь
      onProgress?.call(0, 'pending', "Vazifa navbatga qo'yildi...");

    } catch (e) {
      return {
        'success': false,
        'error':
            "Ulanish xatosi (submit): $e\n\n"
            "Server: $baseUrl\n\n"
            "Sozlamalarda server manzilini tekshiring.",
      };
    }

    // ── Шаг 2: Polling — опрашиваем статус до SUCCESS/FAILURE ─────────────────
    final deadline = DateTime.now().add(_maxWaitDuration);
    bool seenProcessing = false; // FIX #9: отслеживаем, видели ли PROCESSING

    while (DateTime.now().isBefore(deadline)) {
      // FIX #4: проверяем cancelToken перед задержкой
      if (cancelToken?.isCancelled == true) {
        return {'success': false, 'cancelled': true};
      }

      await Future.delayed(_pollInterval);

      // FIX #4: проверяем cancelToken после задержки
      if (cancelToken?.isCancelled == true) {
        return {'success': false, 'cancelled': true};
      }

      try {
        final statusUri = Uri.parse('$baseUrl/ocr/status/$taskId');
        final statusResponse = await http.get(statusUri).timeout(_requestTimeout);

        if (statusResponse.statusCode != 200) {
          // Временная сетевая ошибка — продолжаем polling
          continue;
        }

        final statusData = json.decode(statusResponse.body) as Map<String, dynamic>;
        final taskStatus = statusData['status'] as String? ?? 'PENDING';

        switch (taskStatus) {
          case 'PENDING':
            // FIX #9: если мы уже видели PROCESSING, а теперь снова PENDING —
            // это значит Redis TTL истёк (1 час). Нет смысла ждать снова.
            if (seenProcessing) {
              return {
                'success': false,
                'error':
                    'Natija saqlash muddati tugadi (Redis TTL). '
                    'Iltimos, rasmni qayta yuboring.',
              };
            }
            // Задача ещё в очереди — ждём
            onProgress?.call(0, 'pending', "Navbatda kutilmoqda...");
            break;

          case 'PROCESSING':
          case 'STARTED':
            // Воркер выполняет OCR — показываем прогресс
            seenProcessing = true; // FIX #9
            final progress = statusData['progress'] as int? ?? 0;
            final stage   = statusData['stage']   as String? ?? 'processing';
            final message = statusData['message'] as String? ?? "Qayta ishlanmoqda...";
            onProgress?.call(progress, stage, message);
            break;

          case 'SUCCESS':
            // ✅ Задача завершена — извлекаем результат
            final result = statusData['result'] as Map<String, dynamic>?;
            if (result == null) {
              return {
                'success': false,
                'error': 'Server natija qaytarmadi (result = null).',
              };
            }

            final corrected = result['corrected_text'] as String? ?? '';
            final original  = result['raw_text']       as String? ?? corrected;
            final converted = result['converted_text'] as String? ?? '';

            onProgress?.call(100, 'success', "Muvaffaqiyatli yakunlandi!");

            return {
              'success':       true,
              'originalText':  original,
              'correctedText': corrected,
              'convertedText': converted,
              'confidence':    (result['confidence'] as num?)?.toDouble() ?? 0.0,
              'script':        result['script'] as String? ?? 'latin',
              'processingMs':  result['processing_time_ms'] as int? ?? 0,
            };

          case 'FAILURE':
            // ❌ Задача завершилась с ошибкой
            final errorMsg = statusData['error'] as String? ?? 'Noma\'lum xato';
            return {
              'success': false,
              'error':   'OCR xatosi: $errorMsg',
            };

          default:
            // Неизвестный статус — продолжаем polling
            onProgress?.call(0, taskStatus.toLowerCase(), taskStatus);
            break;
        }
      } catch (e) {
        // Временная сетевая ошибка при polling — не прерываем, продолжаем
        continue;
      }
    }

    // Timeout: задача не завершилась за _maxWaitDuration
    return {
      'success': false,
      'error':
          'OCR vaqt tugadi (${_maxWaitDuration.inMinutes} daqiqa). '
          'Server hali ham qayta ishlayapti. Keyinroq urinib ko\'ring.',
    };
  }
}
