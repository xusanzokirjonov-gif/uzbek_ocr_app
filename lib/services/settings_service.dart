import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum AppLanguage { uzbek, russian }

enum AppScript { latin, cyrillic }

enum AppTheme { dark, light, system }

class SettingsService extends ChangeNotifier {
  AppLanguage _language = AppLanguage.uzbek;
  AppScript _script = AppScript.latin;
  AppTheme _theme = AppTheme.dark;
  Brightness _systemBrightness = Brightness.dark;
  String _serverUrl = 'http://192.168.100.11:8000';

  // Режим OCR-обработки:
  //   true  → асинхронный (POST /ocr/v2, Celery + Redis) — показывает прогресс
  //   false → синхронный (POST /ocr, блокирующий)
  bool _useAsyncOcr = true;  // v2 по умолчанию — показывает прогресс обработки

  AppLanguage get language => _language;
  AppScript get script => _script;
  AppTheme get theme => _theme;
  Brightness get systemBrightness => _systemBrightness;
  String get serverUrl => _serverUrl;
  bool get useAsyncOcr => _useAsyncOcr;

  bool get isCyrillic => _script == AppScript.cyrillic;
  bool get isRussian => _language == AppLanguage.russian;

  void updateSystemBrightness(Brightness sys) {
    if (_systemBrightness != sys) {
      _systemBrightness = sys;
    }
  }

  // Translations
  String t(String key) {
    final Map<String, Map<String, String>> strings = {
      'app_name':       {'uz_lat': 'Uzbek OCR',       'uz_cyr': 'Uzbek OCR',              'ru': 'Uzbek OCR'},
      'scan_text':      {'uz_lat': 'Matnni aniqlash', 'uz_cyr': 'Матнни аниқлаш',         'ru': 'Распознать текст'},
      'scan_subtitle':  {
        'uz_lat': "O'zbek tilida matnni rasmdan avtomatik aniqlash uchun rasmga oling yoki galereyadan tanlang",
        'uz_cyr': "Ўзбек тилидаги матнни расмдан автоматик аниқлаш учун расмга олинг ёки галерейадан танланг",
        'ru':     'Автоматическое распознавание узбекского текста с фото или из галереи',
      },
      'camera':         {'uz_lat': 'Rasmga olish',        'uz_cyr': 'Расмга олиш',         'ru': 'Сфотографировать'},
      'camera_sub':     {'uz_lat': 'Kamerani ishga tushirish', 'uz_cyr': 'Камерани ишга тушириш', 'ru': 'Открыть камеру'},
      'gallery':        {'uz_lat': 'Galereyadan tanlash', 'uz_cyr': 'Галерейадан танлаш',  'ru': 'Выбрать из галереи'},
      'gallery_sub':    {'uz_lat': 'Mavjud rasmni yuklash', 'uz_cyr': 'Мавжуд расмни юклаш', 'ru': 'Загрузить существующее фото'},
      'converter':      {'uz_lat': 'Konvertor',           'uz_cyr': 'Конвертор',           'ru': 'Конвертер'},
      'converter_sub':  {'uz_lat': 'Lotin ↔ Kirill',      'uz_cyr': 'Лотин ↔ Кирилл',     'ru': 'Латиница ↔ Кириллица'},
      'history':        {'uz_lat': 'Tarix',               'uz_cyr': 'Тарих',               'ru': 'История'},
      'settings':       {'uz_lat': 'Sozlamalar',          'uz_cyr': 'Созламалар',          'ru': 'Настройки'},
      'both_scripts':   {'uz_lat': 'Lotin va kirill alifbolarida ishlaydi', 'uz_cyr': 'Лотин ва кирилл алифболарида ишлайди', 'ru': 'Работает с латиницей и кириллицей'},
      'result':         {'uz_lat': 'Natija',              'uz_cyr': 'Натижа',              'ru': 'Результат'},
      'copy':           {'uz_lat': 'Nusxalash',           'uz_cyr': 'Нусхалаш',           'ru': 'Копировать'},
      'copied':         {'uz_lat': 'Matn nusxalandi!',    'uz_cyr': 'Матн нусхаланди!',   'ru': 'Текст скопирован!'},
      'edit':           {'uz_lat': 'Tahrirlash',          'uz_cyr': 'Таҳрирлаш',          'ru': 'Редактировать'},
      'save':           {'uz_lat': 'Saqlash',             'uz_cyr': 'Сақлаш',             'ru': 'Сохранить'},
      'to_latin':       {'uz_lat': 'Lotinga',             'uz_cyr': 'Лотинга',            'ru': 'В латиницу'},
      'to_cyrillic':    {'uz_lat': 'Kirillga',            'uz_cyr': 'Кириллга',           'ru': 'В кириллицу'},
      'high_accuracy':  {'uz_lat': 'Yuqori aniqlik',      'uz_cyr': 'Юқори аниқлик',      'ru': 'Высокая точность'},
      'mid_accuracy':   {'uz_lat': "O'rtacha aniqlik",    'uz_cyr': 'Ўртача аниқлик',     'ru': 'Средняя точность'},
      'low_accuracy':   {'uz_lat': 'Past aniqlik',        'uz_cyr': 'Паст аниқлик',       'ru': 'Низкая точность'},
      'detected_text':  {'uz_lat': 'Aniqlangan matn',     'uz_cyr': 'Аниқланган матн',    'ru': 'Распознанный текст'},
      'loading':        {'uz_lat': 'Matn aniqlanmoqda...','uz_cyr': 'Матн аниқланмоқда...','ru': 'Распознавание...'},
      'please_wait':    {'uz_lat': 'Iltimos, kuting',     'uz_cyr': 'Илтимос, кутинг',   'ru': 'Пожалуйста, подождите'},
      'error':          {'uz_lat': 'Xatolik yuz berdi',   'uz_cyr': 'Хatolik yuz berdi',  'ru': 'Произошла ошибка'},
      'retry':          {'uz_lat': 'Qayta urinish',       'uz_cyr': 'Қайта уриниш',       'ru': 'Повторить'},
      'no_text':        {'uz_lat': 'Matn topilmadi',      'uz_cyr': 'Матн топилмади',     'ru': 'Текст не найден'},
      'demo_mode':      {'uz_lat': 'Demo rejim — server ishlamayapti', 'uz_cyr': 'Демо режим — сервер ишламаяпти', 'ru': 'Демо режим — сервер недоступен'},
      // Settings
      'appearance':     {'uz_lat': "Ko'rinish",           'uz_cyr': 'Кўриниш',            'ru': 'Оформление'},
      'theme':          {'uz_lat': 'Mavzu',               'uz_cyr': 'Мавзу',              'ru': 'Тема'},
      'dark':           {'uz_lat': "Qorong'u",            'uz_cyr': 'Қоронғу',            'ru': 'Тёмная'},
      'light':          {'uz_lat': "Yorug'",              'uz_cyr': 'Ёруғ',               'ru': 'Светлая'},
      'system':         {'uz_lat': 'Tizim',              'uz_cyr': 'Тизим',               'ru': 'Системная'},
      'language':       {'uz_lat': 'Ilova tili',          'uz_cyr': 'Илова тили',         'ru': 'Язык приложения'},
      'uzbek':          {'uz_lat': "O'zbek tili",         'uz_cyr': 'Ўзбек тили',         'ru': 'Узбекский'},
      'russian':        {'uz_lat': 'Rus tili',            'uz_cyr': 'Рус тили',           'ru': 'Русский'},
      'script':         {'uz_lat': 'Yozuv turi',          'uz_cyr': 'Ёзув тури',          'ru': 'Тип письма'},
      'latin':          {'uz_lat': 'Lotin alifbosi',      'uz_cyr': 'Лотин алифбоси',     'ru': 'Латиница'},
      'cyrillic':       {'uz_lat': 'Kirill alifbosi',     'uz_cyr': 'Кирилл алифбоси',    'ru': 'Кириллица'},
      'about':          {'uz_lat': 'Ilova haqida',        'uz_cyr': 'Илова ҳақида',       'ru': 'О приложении'},
      'version':        {'uz_lat': 'Versiya',             'uz_cyr': 'Версия',              'ru': 'Версия'},
      // History screen
      'hist_title':     {'uz_lat': 'Tarix',               'uz_cyr': 'Тарих',               'ru': 'История'},
      'hist_empty':     {'uz_lat': "Tarix bo'sh",         'uz_cyr': 'Тарих бўш',           'ru': 'История пуста'},
      'hist_empty_sub': {'uz_lat': "Skanerlangan matnlar bu yerda ko'rinadi", 'uz_cyr': 'Сканерланган матнлар бу ерда кўринади', 'ru': 'Здесь будут распознанные тексты'},
      'hist_clear':     {'uz_lat': 'Tarixni tozalash',   'uz_cyr': 'Тарихни тозалаш',    'ru': 'Очистить историю'},
      'hist_clear_msg': {'uz_lat': "Barcha skanerlash tarixi o'chiriladi. Davom etasizmi?", 'uz_cyr': "Барча сканерлаш тарихи ўчирилади. Давом этасизми?", 'ru': 'Вся история будет удалена. Продолжить?'},
      'cancel':         {'uz_lat': 'Bekor qilish',        'uz_cyr': 'Бекор қилиш',         'ru': 'Отмена'},
      'delete':         {'uz_lat': "O'chirish",           'uz_cyr': 'Ўчириш',              'ru': 'Удалить'},
      'copy_btn':       {'uz_lat': 'Nusxalash',           'uz_cyr': 'Нусхалаш',            'ru': 'Копировать'},
      'copy_conv':      {'uz_lat': 'Nusxalash (Konvert.)', 'uz_cyr': 'Нусхалаш (Конверт.)', 'ru': 'Копировать (Конверт.)'},
      'just_now':       {'uz_lat': 'Hozirgina',           'uz_cyr': 'Ҳозиргина',           'ru': 'Только что'},
      'min_ago':        {'uz_lat': 'daqiqa oldin',        'uz_cyr': 'дақиқа олдин',         'ru': 'мин назад'},
      'hours_ago':      {'uz_lat': 'soat oldin',          'uz_cyr': 'соат олдин',           'ru': 'ч назад'},
      'days_ago':       {'uz_lat': 'kun oldin',           'uz_cyr': 'кун олдин',            'ru': 'дн назад'},
      // Result screen
      // FIX #7: добавлен ключ async_mode_hint (ранее был русский хардкод в result_screen.dart)
      'async_mode_hint':  {'uz_lat': 'Asinxron rejim (Celery + Redis)', 'uz_cyr': 'Асинхрон режим (Celery + Redis)', 'ru': 'Асинхронный режим (Celery + Redis)'},
      'edit_hint':        {'uz_lat': 'Matnni tahrirlang...', 'uz_cyr': 'Матнни таҳрирланг...', 'ru': 'Редактируйте текст...'},
      'unknown_error':    {'uz_lat': "Noma'lum xatolik",    'uz_cyr': 'Номаълум хatolик',      'ru': 'Неизвестная ошибка'},
      // Converter screen
      'conv_btn':         {'uz_lat': 'Konvertatsiya',       'uz_cyr': 'Конвертация',           'ru': 'Конвертировать'},
      'conv_auto':        {'uz_lat': 'Avto',                'uz_cyr': 'Авто',                  'ru': 'Авто'},
      'conv_latin':       {'uz_lat': 'Lotin',               'uz_cyr': 'Лотин',                 'ru': 'Латиница'},
      'conv_cyrillic':    {'uz_lat': 'Kirill',              'uz_cyr': 'Кирилл',                'ru': 'Кириллица'},
      'conv_input_label': {'uz_lat': 'Matn kiriting',       'uz_cyr': 'Матн киринг',           'ru': 'Введите текст'},
      // Server settings
      'server':           {'uz_lat': 'Server',               'uz_cyr': 'Сервер',                'ru': 'Сервер'},
      'server_url':       {'uz_lat': 'Server manzili (URL)', 'uz_cyr': 'Сервер манзили (URL)',  'ru': 'Адрес сервера (URL)'},
      'server_url_hint':  {'uz_lat': 'http://192.168.x.x:8000', 'uz_cyr': 'http://192.168.x.x:8000', 'ru': 'http://192.168.x.x:8000'},
      'server_saved':     {'uz_lat': 'Saqlandi!',             'uz_cyr': 'Сақланди!',             'ru': 'Сохранено!'},
    };
    if (_language == AppLanguage.russian) {
      return strings[key]?['ru'] ?? key;
    } else if (_script == AppScript.cyrillic) {
      return strings[key]?['uz_cyr'] ?? key;
    } else {
      return strings[key]?['uz_lat'] ?? key;
    }
  }

  // Theme helpers
  // Returns true when effective theme is dark (considering system)
  bool isDark(Brightness systemBrightness) {
    if (_theme == AppTheme.light) return false;
    if (_theme == AppTheme.dark) return true;
    return systemBrightness == Brightness.dark; // system
  }
  bool _isDark(Brightness systemBrightness) => isDark(systemBrightness);

  List<Color> backgroundGradientFor(Brightness sys) {
    if (_theme == AppTheme.light) {
      return [const Color(0xFFF8F8FF), const Color(0xFFEEEEFB), const Color(0xFFE8E8F4)];
    }
    if (_isDark(sys)) {
      return [const Color(0xFF0A0E21), const Color(0xFF151A30), const Color(0xFF1A1040)];
    }
    // system + light device
    return [const Color(0xFFF8F8FF), const Color(0xFFEEEEFB), const Color(0xFFE8E8F4)];
  }

  // Fallback getters (use system brightness instead of dark as default)
  List<Color> get backgroundGradient => backgroundGradientFor(_systemBrightness);

  Color textColorFor(Brightness sys) =>
      _isDark(sys) ? Colors.white : const Color(0xFF1A1A2E);
  Color get textColor => textColorFor(_systemBrightness);

  Color subtitleColorFor(Brightness sys) =>
      _isDark(sys) ? Colors.white60 : const Color(0xFF666688);
  Color get subtitleColor => subtitleColorFor(_systemBrightness);

  Color cardColorFor(Brightness sys) =>
      _isDark(sys) ? const Color(0xFF15192E) : Colors.white;
  Color get cardColor => cardColorFor(_systemBrightness);

  Color borderColorFor(Brightness sys) =>
      _isDark(sys) ? Colors.white.withValues(alpha: 0.1) : const Color(0xFFDDDDEE);
  Color get borderColor => borderColorFor(_systemBrightness);

  Brightness brightnessFor(Brightness sys) =>
      _isDark(sys) ? Brightness.dark : Brightness.light;
  Brightness get brightness => brightnessFor(_systemBrightness);

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _language     = AppLanguage.values[prefs.getInt('language') ?? 0];
    _script       = AppScript.values[prefs.getInt('script') ?? 0];
    _theme        = AppTheme.values[prefs.getInt('theme') ?? 0];
    final savedUrl = prefs.getString('server_url');
    if (savedUrl == null ||
        savedUrl == 'http://uzbek-ocr.local:8000' ||
        savedUrl == 'http://192.168.0.100:8000' ||
        savedUrl == 'http://192.168.1.6:8000') {
      _serverUrl = 'http://192.168.100.11:8000';
    } else {
      _serverUrl = savedUrl;
    }
    _useAsyncOcr  = prefs.getBool('use_async_ocr') ?? false;
    notifyListeners();
  }

  Future<void> setServerUrl(String url) async {
    _serverUrl = url;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_url', url);
    notifyListeners();
  }

  Future<void> setLanguage(AppLanguage lang) async {
    _language = lang;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('language', lang.index);
    notifyListeners();
  }

  Future<void> setScript(AppScript s) async {
    _script = s;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('script', s.index);
    notifyListeners();
  }

  Future<void> setTheme(AppTheme t) async {
    _theme = t;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('theme', t.index);
    notifyListeners();
  }

  /// Переключает режим OCR-обработки.
  ///
  /// [value] = true  → POST /ocr/v2 (Celery + Redis, асинхронный)
  /// [value] = false → POST /ocr   (синхронный, блокирующий)
  Future<void> setUseAsyncOcr(bool value) async {
    _useAsyncOcr = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('use_async_ocr', value);
    notifyListeners();
  }
}
