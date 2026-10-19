"""
spelling_corrector.py
=====================
Исправление орфографических ошибок OCR для узбекского языка.

Алгоритм основан на расстоянии Левенштейна с весами ошибок,
специфичных для оптического распознавания символов (OCR).

Структура класса:
  UzbekSpellingCorrector
  ├── load_dictionary()      — загрузка словаря из файла
  ├── correct_word()         — исправление одного слова
  ├── correct_text()         — исправление текста (токенизация + correct_word)
  └── _weighted_edit_distance() — расстояние Левенштейна с OCR-весами

Источники весов ошибок:
  Типичные ошибки EasyOCR при распознавании узбекских текстов,
  зафиксированные в ходе тестирования на датасете.
"""

import re
import logging
from pathlib import Path
from functools import lru_cache
from typing import Union

logger = logging.getLogger("uzbek_ocr.spelling")


# ─── Матрица стоимости OCR-ошибок ─────────────────────────────────────────────
#
# Ключ: (распознанный_символ, правильный_символ)
# Значение: стоимость замены (0.0 = бесплатно, 1.0 = стандартная цена)
#
# Логика: если символ A часто путается с символом B при OCR,
# замена A→B должна стоить дёшево, чтобы алгоритм охотнее
# предлагал правильный вариант.

OCR_SUBSTITUTION_WEIGHTS: dict[tuple[str, str], float] = {
    # ── Потеря апострофа в O' и G' (самая частая ошибка) ──────────────────
    # OCR видит «Ozbekiston» вместо «O'zbekiston»
    ("O",  "O\u2019"): 0.15,   # O → O' почти бесплатно
    ("o",  "o\u2019"): 0.15,
    ("G",  "G\u2019"): 0.15,
    ("g",  "g\u2019"): 0.15,
    ("O",  "O'"): 0.15,
    ("o",  "o'"): 0.15,
    ("G",  "G'"): 0.15,
    ("g",  "g'"): 0.15,

    # ── Гомоглифы: латинские ↔ кириллические визуально похожие ────────────
    ("о",  "o"): 0.1,    # Кириллическая о → латинская o
    ("o",  "о"): 0.1,
    ("а",  "a"): 0.1,
    ("a",  "а"): 0.1,
    ("е",  "e"): 0.1,
    ("e",  "е"): 0.1,
    ("р",  "p"): 0.1,
    ("p",  "р"): 0.1,
    ("с",  "c"): 0.1,
    ("c",  "с"): 0.1,
    ("х",  "x"): 0.1,
    ("x",  "х"): 0.1,

    # ── Цифры, похожие на буквы ────────────────────────────────────────────
    ("0",  "O"): 0.2,    # Ноль → буква O
    ("0",  "o"): 0.2,
    ("1",  "l"): 0.2,    # Единица → строчная L
    ("1",  "I"): 0.2,    # Единица → заглавная I
    ("l",  "1"): 0.3,
    ("I",  "l"): 0.2,    # Заглавная I → строчная l
    ("l",  "I"): 0.2,
    ("5",  "s"): 0.3,    # Пятёрка → s (редко)
    ("5",  "S"): 0.3,

    # ── Типичные путаницы форм символов ───────────────────────────────────
    ("rn", "m"): 0.2,    # «rn» распознаётся как «m» и наоборот
    ("m",  "rn"): 0.2,
    ("cl", "d"): 0.3,
    ("d",  "cl"): 0.3,
    ("li", "h"): 0.3,
    ("h",  "li"): 0.3,

    # ── Специфичные узбекские пары ─────────────────────────────────────────
    # Буква Ш/шу часто путается с III (три единицы)
    ("III", "Ш"): 0.2,
    ("lll", "ш"): 0.2,
    # Ңн путается с НН
    ("НН", "Нн"): 0.1,
    ("нн", "нн"): 0.05,
}


# ─── Токенизатор ──────────────────────────────────────────────────────────────

# Регулярное выражение для разбивки текста на токены.
# Сохраняем пунктуацию и пробелы как отдельные токены,
# чтобы восстановить исходный форматинг после коррекции.
_TOKEN_PATTERN = re.compile(
    r"([A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ][A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ\u2019']*"  # слова
    r"|\d+"                                                          # числа (сохраняются без изменений)
    r"|\s+"                                                          # пробелы
    r"|[^\w\s])",                                                    # пунктуация и спецсимволы
    re.UNICODE
)


class UzbekSpellingCorrector:
    """
    Исправляет орфографические ошибки в OCR-выводе на узбекском языке.

    Использует словарь узбекских слов и расстояние Левенштейна
    с настроенными весами для типичных OCR-ошибок.

    Attributes:
        max_distance: Максимально допустимое расстояние редактирования
                      (слова дальше этого порога не исправляются).
        min_word_length: Слова короче этой длины не исправляются
                         (во избежание ложных срабатываний).
    """

    def __init__(
        self,
        dict_path: Union[str, Path],
        max_distance: float = 1.5,
        min_word_length: int = 3,
        latin_dict_path: Union[str, Path, None] = None,
    ):
        """
        Args:
            dict_path: Путь к основному файлу словаря (кириллица).
            max_distance: Максимальное расстояние редактирования для коррекции.
            min_word_length: Минимальная длина слова для коррекции.
            latin_dict_path: Путь к отдельному файлу латинского словаря (опционально).
        """
        self.max_distance = max_distance
        self.min_word_length = min_word_length

        # Разделяем словарь на два: латиница и кириллица.
        # Это ускоряет поиск и снижает количество ложных замен.
        self._latin_words: set[str] = set()
        self._cyrillic_words: set[str] = set()
        self._english_words: set[str] = set()

        self._load_dictionary(Path(dict_path))

        # Загружаем латинский словарь если указан отдельный файл
        if latin_dict_path is not None:
            self._load_latin_dictionary(Path(latin_dict_path))

        # Загружаем английский словарь для защиты английских слов от искажения
        en_path = Path(dict_path).parent / "enwords.txt"
        if en_path.exists():
            self._load_english_dictionary(en_path)

    def _load_dictionary(self, path: Path) -> None:
        """
        Загружает словарь из текстового файла.

        Формат файла: одно слово на строку, кодировка UTF-8.
        Поддерживаются как строчные, так и прописные слова.

        Args:
            path: Путь к файлу словаря.

        Raises:
            FileNotFoundError: Если файл словаря не найден.
        """
        if not path.exists():
            logger.warning(f"Dictionary not found at {path}. Spelling correction disabled.")
            return

        cyrillic_pattern = re.compile(r"[А-Яа-яЁёЎўҚқҒғҲҳ]")
        latin_pattern    = re.compile(r"[A-Za-z\u2019']")

        with path.open("r", encoding="utf-8") as f:
            for line in f:
                word = line.strip().lower()
                if not word or len(word) < 2:
                    continue

                if cyrillic_pattern.search(word):
                    self._cyrillic_words.add(word)
                elif latin_pattern.search(word):
                    self._latin_words.add(word)

        logger.info(
            f"Loaded Uzbek dictionaries: "
            f"{len(self._cyrillic_words)} Cyrillic, "
            f"{len(self._latin_words)} Latin words."
        )

    def _load_latin_dictionary(self, path: Path) -> None:
        """
        Загружает отдельный файл латинского словаря (uzwords_latin.txt).

        Файл должен содержать одно латинское слово на строку.
        Добавляет слова в self._latin_words дополнительно к уже загруженным.
        """
        if not path.exists():
            logger.warning(f"Latin dictionary not found at {path}. Skipping.")
            return

        count_before = len(self._latin_words)
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                word = line.strip().lower()
                if word and len(word) >= 2:
                    self._latin_words.add(word)

        added = len(self._latin_words) - count_before
        logger.info(
            f"Loaded Latin dictionary: +{added} words "
            f"(total Latin: {len(self._latin_words)})"
        )

    def _load_english_dictionary(self, path: Path) -> None:
        """
        Загружает словарь английских слов (enwords.txt).
        Слова из этого словаря не заменяются на узбекские аналоги при OCR.
        """
        if not path.exists():
            return

        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                word = line.strip().lower()
                if word and len(word) >= 2:
                    self._english_words.add(word)

        logger.info(
            f"Loaded English dictionary: {len(self._english_words)} words."
        )

    # ─── Публичный API ────────────────────────────────────────────────────────

    def correct_text(self, text: str, script: str = "latin") -> str:
        """
        Исправляет орфографию в тексте с сохранением пунктуации и форматирования.

        Args:
            text: Исходный текст от OCR.
            script: Тип письма — "latin" или "cyrillic".

        Returns:
            Текст с исправленными словами.
        """
        if not text.strip():
            return text

        dictionary = (
            self._latin_words if script == "latin"
            else self._cyrillic_words
        )

        if not dictionary:
            return text  # Словарь не загружен — возвращаем как есть

        # Токенизируем, исправляем слова, собираем обратно
        tokens = _TOKEN_PATTERN.findall(text)
        corrected_tokens = []

        for token in tokens:
            if re.match(r"^[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ]", token):
                corrected = self.correct_word(token, script)
                corrected_tokens.append(corrected)
            else:
                corrected_tokens.append(token)  # Пунктуация и пробелы — без изменений

        return "".join(corrected_tokens)

    def correct_word(self, word: str, script: str = "latin") -> str:
        """
        Исправляет одно слово с использованием словаря и расстояния Левенштейна.

        Алгоритм:
          1. Если слово есть в словаре — возвращаем без изменений.
          2. Иначе ищем ближайшее слово в словаре (по взвешенному расстоянию).
          3. Если расстояние ≤ max_distance — возвращаем кандидата.
          4. Иначе — оставляем слово как есть.

        Args:
            word: Слово для проверки.
            script: Тип письма.

        Returns:
            Исправленное слово или исходное, если исправление не найдено.
        """
        if len(word) < self.min_word_length:
            return word

        word_lower = word.lower()
        # Если слово есть в английском словаре — не заменяем его
        if word_lower in self._english_words:
            return word

        dictionary = (
            self._latin_words if script == "latin"
            else self._cyrillic_words
        )

        if not dictionary:
            return word

        # Быстрая проверка — слово уже в словаре
        if word_lower in dictionary:
            return word

        # Ищем наилучшего кандидата
        best_candidate = None
        best_distance  = float("inf")

        # Оптимизация: рассматриваем только слова близкой длины
        # (разница длин > max_distance не может дать лучший результат)
        target_len = len(word_lower)
        len_threshold = int(self.max_distance) + 1

        for candidate in dictionary:
            # Быстрый фильтр по длине
            if abs(len(candidate) - target_len) > len_threshold:
                continue

            dist = self._weighted_edit_distance(word_lower, candidate)

            if dist < best_distance:
                best_distance  = dist
                best_candidate = candidate

            # Ранняя остановка при нахождении идеального совпадения
            if best_distance == 0.0:
                break

        # Применяем исправление только если расстояние в допустимых пределах
        if best_candidate is not None and best_distance <= self.max_distance:
            # Сохраняем регистр первой буквы оригинала
            if word[0].isupper():
                return best_candidate.capitalize()
            return best_candidate

        return word

    # ─── Приватные методы ─────────────────────────────────────────────────────

    def _weighted_edit_distance(self, source: str, target: str) -> float:
        """
        Вычисляет расстояние Левенштейна с весами OCR-ошибок.

        Стандартное расстояние Левенштейна даёт каждой операции
        (вставка, удаление, замена) стоимость 1.0.

        Здесь замены типичных OCR-ошибок стоят меньше,
        что позволяет алгоритму «охотнее» исправлять
        характерные ошибки распознавания.

        Args:
            source: Распознанное слово.
            target: Слово-кандидат из словаря.

        Returns:
            Взвешенное расстояние редактирования (дробное число).
        """
        m, n = len(source), len(target)

        # Матрица стоимостей (динамическое программирование)
        # dp[i][j] = стоимость преобразования source[:i] → target[:j]
        dp = [[float("inf")] * (n + 1) for _ in range(m + 1)]

        # Базовые случаи: преобразование пустой строки
        for i in range(m + 1):
            dp[i][0] = float(i)   # i удалений
        for j in range(n + 1):
            dp[0][j] = float(j)   # j вставок

        # Заполнение матрицы
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                s_char = source[i - 1]
                t_char = target[j - 1]

                if s_char == t_char:
                    # Символы совпадают — без стоимости
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    # Стоимость замены: стандартная или из OCR-таблицы
                    sub_cost = OCR_SUBSTITUTION_WEIGHTS.get(
                        (s_char, t_char),
                        1.0   # Стандартная стоимость замены
                    )
                    dp[i][j] = min(
                        dp[i - 1][j]     + 1.0,      # Удаление
                        dp[i][j - 1]     + 1.0,      # Вставка
                        dp[i - 1][j - 1] + sub_cost, # Замена (взвешенная)
                    )

                # Транспозиция (Damerau-Levenshtein): ab → ba
                if i > 1 and j > 1:
                    s_prev = source[i - 2]
                    t_prev = target[j - 2]
                    if s_char == t_prev and s_prev == t_char:
                        dp[i][j] = min(dp[i][j], dp[i - 2][j - 2] + 0.8)

        return dp[m][n]
