import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Статус поиска сервера
enum DiscoveryStatus { idle, searching, found, failed }

/// Результат поиска сервера
class ServerDiscoveryResult {
  final String url;
  final bool isReachable;

  const ServerDiscoveryResult({required this.url, required this.isReachable});
}

/// Сервис автоматического обнаружения OCR-сервера в локальной сети.
///
/// Алгоритм поиска:
///   1. Проверяем preferredUrl (из настроек)
///   2. Проверяем известный IP Mac (192.168.1.6:8000, 192.168.0.100:8000)
///   3. Пробуем mDNS: http://uzbek-ocr.local:8000/health
///   4. Быстрое чередующееся сканирование популярных домашних подсетей
///      (192.168.1.x, 192.168.0.x, 192.168.31.x, 192.168.100.x)
///   5. Fallback на localhost
class ServerDiscoveryService extends ChangeNotifier {
  DiscoveryStatus _status = DiscoveryStatus.idle;
  String? _discoveredUrl;
  String? _error;

  DiscoveryStatus get status => _status;
  String? get discoveredUrl => _discoveredUrl;
  String? get error => _error;
  bool get isSearching => _status == DiscoveryStatus.searching;
  bool get isFound => _status == DiscoveryStatus.found;

  static const int _port = 8000;
  static const Duration _connectTimeout = Duration(milliseconds: 800);
  static const Duration _totalTimeout = Duration(seconds: 15);

  /// Устанавливает адрес вручную (например, при подтверждении пользователем в настройках)
  void setManualUrl(String url) {
    _discoveredUrl = url;
    _status = DiscoveryStatus.found;
    _error = null;
    notifyListeners();
  }

  /// Список адресов для проверки в приоритетном порядке.
  Future<List<String>> _buildCandidates([String? preferredUrl]) async {
    final candidates = <String>[];

    void addCandidate(String url) {
      final clean = url.trim().replaceAll(RegExp(r'/+$'), '');
      if (clean.isNotEmpty && !candidates.contains(clean)) {
        candidates.add(clean);
      }
    }

    // 1. Предпочитаемый URL из настроек
    if (preferredUrl != null && preferredUrl.isNotEmpty) {
      addCandidate(preferredUrl);
    }

    // 2. Текущий и известные IP Mac
    addCandidate('http://192.168.100.11:$_port');
    addCandidate('http://192.168.1.6:$_port');
    addCandidate('http://192.168.0.100:$_port');

    // 3. mDNS через DNS-резолюцию
    try {
      final addrs = await InternetAddress.lookup('uzbek-ocr.local')
          .timeout(const Duration(seconds: 1));
      for (final a in addrs) {
        addCandidate('http://${a.address}:$_port');
      }
    } catch (_) {
      addCandidate('http://uzbek-ocr.local:$_port');
    }

    // 4. Сканирование подсети активных сетевых интерфейсов
    final discoveredSubnets = <String>[];
    try {
      final interfaces = await NetworkInterface.list(
        type: InternetAddressType.IPv4,
        includeLinkLocal: false,
      );

      for (final iface in interfaces) {
        for (final addr in iface.addresses) {
          final parts = addr.address.split('.');
          if (parts.length == 4) {
            final subnet = '${parts[0]}.${parts[1]}.${parts[2]}';
            if (!discoveredSubnets.contains(subnet)) {
              discoveredSubnets.add(subnet);
            }
          }
        }
      }
    } catch (e) {
      debugPrint('[Discovery] NetworkInterface.list not available: $e');
    }

    // Популярные подсети роутеров
    final allSubnets = {
      ...discoveredSubnets,
      '192.168.1',
      '192.168.0',
      '192.168.31',
      '192.168.100',
      '10.0.0',
    }.toList();

    // Быстрый приоритетный список хостов (шлюзы, первые ПК, Mac, DHCP)
    final priorityHosts = [
      '6', '1', '2', '3', '4', '5', '7', '8', '9', '10',
      '11', '12', '13', '14', '15', '20', '50', '100', '101', '102', '105'
    ];

    // Фаза 1: Приоритетные хосты по всем подсетям
    for (final host in priorityHosts) {
      for (final subnet in allSubnets) {
        addCandidate('http://$subnet.$host:$_port');
      }
    }

    // Фаза 2: Остальные адреса подсетей
    for (final subnet in allSubnets) {
      for (int i = 16; i <= 99; i++) {
        if (!priorityHosts.contains('$i')) {
          addCandidate('http://$subnet.$i:$_port');
        }
      }
      for (int i = 106; i <= 254; i++) {
        if (!priorityHosts.contains('$i')) {
          addCandidate('http://$subnet.$i:$_port');
        }
      }
    }

    // Localhost как последний fallback
    addCandidate('http://localhost:$_port');
    addCandidate('http://127.0.0.1:$_port');

    return candidates;
  }

  /// Проверяет доступность сервера по /health эндпоинту.
  Future<bool> _ping(String baseUrl) async {
    try {
      final uri = Uri.parse('$baseUrl/health');
      final response = await http
          .get(uri)
          .timeout(_connectTimeout);
      if (response.statusCode == 200) {
        final body = response.body;
        return body.contains('"status"') && body.contains('"healthy"');
      }
    } catch (_) {
      // Недоступен — продолжаем поиск
    }
    return false;
  }

  /// Запускает автоматический поиск сервера.
  /// Если сервер уже найден — ничего не делает (используйте [rediscover] для повторного поиска).
  Future<String?> discover({String? preferredUrl}) async {
    if (_status == DiscoveryStatus.searching) return _discoveredUrl;
    if (_status == DiscoveryStatus.found && _discoveredUrl != null) {
      return _discoveredUrl;
    }
    return _runDiscovery(preferredUrl);
  }

  /// Принудительный повторный поиск (игнорирует кэш).
  Future<String?> rediscover({String? preferredUrl}) async {
    _discoveredUrl = null;
    _status = DiscoveryStatus.idle;
    return _runDiscovery(preferredUrl);
  }

  Future<String?> _runDiscovery([String? preferredUrl]) async {
    _status = DiscoveryStatus.searching;
    _error = null;
    notifyListeners();

    try {
      final candidates = await _buildCandidates(preferredUrl);
      debugPrint('[Discovery] Scanning ${candidates.length} candidates...');

      // Пробуем кандидатов пачками по 25 параллельно
      const batchSize = 25;
      final deadline = DateTime.now().add(_totalTimeout);

      for (int i = 0; i < candidates.length; i += batchSize) {
        if (DateTime.now().isAfter(deadline)) break;

        final batch = candidates.sublist(
          i,
          (i + batchSize).clamp(0, candidates.length),
        );

        // Запускаем все проверки в пачке параллельно
        final futures = batch.map((url) async {
          final ok = await _ping(url);
          return ok ? url : null;
        });

        final results = await Future.wait(futures);
        final found = results.firstWhere((r) => r != null, orElse: () => null);

        if (found != null) {
          debugPrint('[Discovery] ✅ Found server at: $found');
          _discoveredUrl = found;
          _status = DiscoveryStatus.found;
          notifyListeners();
          return found;
        }
      }

      debugPrint('[Discovery] ❌ Server not found');
      _status = DiscoveryStatus.failed;
      _error = 'Сервер не найден в локальной сети';
      notifyListeners();
      return null;
    } catch (e) {
      debugPrint('[Discovery] Error: $e');
      _status = DiscoveryStatus.failed;
      _error = e.toString();
      notifyListeners();
      return null;
    }
  }
}
