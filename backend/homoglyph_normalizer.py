"""
homoglyph_normalizer.py
=======================
Нормализатор гомоглифов для узбекского OCR.

Гомоглифы — это символы из разных алфавитов, которые выглядят одинаково,
но имеют разные коды Unicode. Например:
  - Латинская 'o' (U+006F) vs Кириллическая 'о' (U+043E)
  - Латинская 'a' (U+0061) vs Кириллическая 'а' (U+0430)
  - Латинская 'e' (U+0065) vs Кириллическая 'е' (U+0435)

OCR-движки часто путают эти символы, что приводит к «смешанному» тексту,
который выглядит правильно, но содержит символы из чужого алфавита.
"""

import re
import unicodedata
from enum import Enum
from typing import Optional


class Script(Enum):
    """Тип письма узбекского языка."""
    LATIN = "latin"
    CYRILLIC = "cyrillic"
    UNKNOWN = "unknown"


# ─── Таблицы замен ────────────────────────────────────────────────────────────

# Кириллические символы, которые визуально совпадают с латинскими.
# Ключ — кириллический символ, значение — латинский эквивалент.
CYRILLIC_TO_LATIN_HOMOGLYPHS: dict[str, str] = {
    # Гласные
    "а": "a",   # U+0430 → U+0061
    "е": "e",   # U+0435 → U+0065
    "о": "o",   # U+043E → U+006F
    "р": "p",   # U+0440 → U+0070
    "с": "c",   # U+0441 → U+0063
    "у": "y",   # U+0443 → U+0079  (в узбекском y ≈ у)
    "х": "x",   # U+0445 → U+0078
    "А": "A",   # U+0410 → U+0041
    "В": "B",   # U+0412 → U+0042
    "Е": "E",   # U+0415 → U+0045
    "К": "K",   # U+041A → U+004B
    "М": "M",   # U+041C → U+004D
    "Н": "H",   # U+041D → U+0048
    "О": "O",   # U+041E → U+004F
    "Р": "P",   # U+0420 → U+0050
    "С": "C",   # U+0421 → U+0043
    "Т": "T",   # U+0422 → U+0054
    "Х": "X",   # U+0425 → U+0058
    "У": "Y",   # U+0423 → U+0059
}

# Латинские символы, которые путают с кириллическими.
# Ключ — латинский символ, значение — кириллический эквивалент.
LATIN_TO_CYRILLIC_HOMOGLYPHS: dict[str, str] = {
    v: k for k, v in CYRILLIC_TO_LATIN_HOMOGLYPHS.items()
}

# Нормализация апострофов для узбекских букв O' и G'.
# В узбекском языке апостроф обозначает «тухум» (знак мягкости).
APOSTROPHE_VARIANTS: list[str] = [
    "\u2018",  # ' LEFT SINGLE QUOTATION MARK
    "\u2019",  # ' RIGHT SINGLE QUOTATION MARK
    "\u02BC",  # ʼ MODIFIER LETTER APOSTROPHE
    "\u0060",  # ` GRAVE ACCENT
    "\u00B4",  # ´ ACUTE ACCENT
    "\u02B9",  # ʹ MODIFIER LETTER PRIME
    "\u02BB",  # ʻ MODIFIER LETTER TURNED COMMA
    "\u02BE",  # ʾ MODIFIER LETTER RIGHT HALF RING
    "\u02BF",  # ʿ MODIFIER LETTER LEFT HALF RING
]

# Стандартный апостроф Unicode для узбекского языка (рекомендован UzStandard)
STANDARD_APOSTROPHE = "\u2019"  # '

# Узбекские буквы, которые требуют апостроф
APOSTROPHE_LETTERS_LATIN  = {"O", "o", "G", "g"}
APOSTROPHE_LETTERS_CYRILLIC = {"Ў", "ў", "Қ", "қ", "Ғ", "ғ", "Ҳ", "ҳ"}


# ─── Определение типа письма ───────────────────────────────────────────────────

# Символы для определения типа письма
_CYRILLIC_CHARS = set(
    "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    "ЎўҚқҒғҲҳ"  # Специфичные для узбекского кириллицы
)
_LATIN_CHARS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "\u02BC"  # Апостроф в O' и G'
)


def detect_script(text: str) -> Script:
    """
    Определяет преобладающий тип письма в строке.

    Args:
        text: Входная строка.

    Returns:
        Script.LATIN если преобладает латиница,
        Script.CYRILLIC если преобладает кириллица,
        Script.UNKNOWN если не удалось определить.
    """
    cyrillic_count = sum(1 for ch in text if ch in _CYRILLIC_CHARS)
    latin_count    = sum(1 for ch in text if ch in _LATIN_CHARS)

    if cyrillic_count == 0 and latin_count == 0:
        return Script.UNKNOWN
    if cyrillic_count > latin_count:
        return Script.CYRILLIC
    return Script.LATIN


# ─── Основной класс ───────────────────────────────────────────────────────────

class HomoglyphNormalizer:
    """
    Нормализует гомоглифы в OCR-выводе узбекского текста.

    Алгоритм работы:
      1. Определяет преобладающий тип письма (латиница / кириллица).
      2. Нормализует апострофы к единому стандарту Unicode.
      3. Заменяет символы чужого алфавита на символы нужного алфавита.
      4. Исправляет специфичные для узбекского OCR ошибки.
    """

    def __init__(self, prefer_standard_apostrophe: bool = True):
        """
        Args:
            prefer_standard_apostrophe: Если True, нормализует все варианты
                апострофа к Unicode RIGHT SINGLE QUOTATION MARK (U+2019).
        """
        self.prefer_standard_apostrophe = prefer_standard_apostrophe

    def normalize(self, text: str, script: Optional[Script] = None) -> str:
        """
        Выполняет полную нормализацию текста.

        Args:
            text: Входной текст от OCR.
            script: Явно задать тип письма. Если None — определяется автоматически.

        Returns:
            Нормализованный текст.
        """
        if not text:
            return text

        # Шаг 1: Нормализация Unicode (NFC — каноническая композиция)
        text = unicodedata.normalize("NFC", text)

        # Шаг 2: Нормализация апострофов
        text = self._normalize_apostrophes(text)

        # Шаг 3: Определяем тип письма, если не задан явно
        if script is None:
            script = detect_script(text)

        # Шаг 4: Исправляем гомоглифы в зависимости от типа письма
        if script == Script.LATIN:
            text = self._fix_latin_text(text)
        elif script == Script.CYRILLIC:
            text = self._fix_cyrillic_text(text)

        # Шаг 5: Исправляем специфичные OCR-ошибки для узбекского
        text = self._fix_uzbek_specific(text, script)

        return text

    def normalize_word(self, word: str, script: "Script") -> str:
        """
        Нормализует одно слово. Используется в SpellingCorrector.

        Args:
            word: Слово от OCR.
            script: Тип письма.

        Returns:
            Нормализованное слово.
        """
        word = self._normalize_apostrophes(word)
        if script == Script.LATIN:
            word = self._fix_latin_text(word)
        elif script == Script.CYRILLIC:
            word = self._fix_cyrillic_text(word)
        return word

    # ─── Приватные методы ─────────────────────────────────────────────────────

    def _normalize_apostrophes(self, text: str) -> str:
        """Нормализует все варианты апострофа к единому виду."""
        for variant in APOSTROPHE_VARIANTS:
            text = text.replace(variant, STANDARD_APOSTROPHE)
        # ASCII апостроф оставляем только если prefer_standard = False
        if self.prefer_standard_apostrophe:
            text = text.replace("'", STANDARD_APOSTROPHE)
        return text

    def _fix_latin_text(self, text: str) -> str:
        """
        Исправляет кириллические гомоглифы в латинском тексте.

        Например: «oʻzbek» с кириллической 'о' → «oʻzbek» с латинской 'o'.
        """
        result = []
        for char in text:
            result.append(CYRILLIC_TO_LATIN_HOMOGLYPHS.get(char, char))
        return "".join(result)

    def _fix_cyrillic_text(self, text: str) -> str:
        """
        Исправляет латинские гомоглифы в кириллическом тексте.

        Например: «Узбекистон» с латинской 'о' → «Узбекистон» с кириллической 'о'.
        """
        result = []
        for char in text:
            result.append(LATIN_TO_CYRILLIC_HOMOGLYPHS.get(char, char))
        return "".join(result)

    def _fix_uzbek_specific(self, text: str, script: Script) -> str:
        """
        Исправляет специфичные для узбекского языка OCR-ошибки.

        Типичные ошибки EasyOCR на узбекском тексте:
          Латиница:
            - «0'» (ноль + апостроф) → «O'»
            - «1» в начале слова вместо «l»
          Кириллица:
            - «0» вместо кириллической «О»
            - «Ф» вместо «қ» (EasyOCR путает из-за формы)
            - «Ф» вместо «ғ» (хвостик вниз похож)
            - «Ф» вместо «ҳ» (похожи по форме)
            - «Ф» вместо «ў» (хвостик)
            - «ф» → «қ»/«ғ»/«ҳ» в нижнем регистре
            - «6» вместо «б»
            - «|» или «l» вместо «і» / «ш»
        """
        if script == Script.LATIN:
            # Ноль вместо O перед апострофом
            text = re.sub(r"0(['\u2019])", r"O\1", text)
            text = re.sub(r"0(['\u2019])([a-z])", r"O\1\2", text, flags=re.IGNORECASE)
            # Цифра 1 вместо l в начале слова
            text = re.sub(r"\b1([a-z])", r"l\1", text)

        elif script == Script.CYRILLIC:
            # Цифра 0 вместо кириллической О
            text = re.sub(r"\b0([а-яА-ЯёЁ])", r"О\1", text)
            text = re.sub(r"([а-яА-ЯёЁ])0\b", r"\1О", text)

            # «€» иногда появляется при сбоях распознавания кириллицы
            text = text.replace("€", "қ")

            # «б» иногда читается как «6»
            text = re.sub(r"\b6([а-яёА-ЯЁ])", r"б\1", text)
            text = re.sub(r"([а-яёА-ЯЁ])6\b", r"\1б", text)

            # Двойные пробелы после исправлений
            text = re.sub(r"  +", " ", text)

        return text


# ─── Глобальный экземпляр (singleton) ────────────────────────────────────────

_normalizer: Optional[HomoglyphNormalizer] = None


def get_normalizer() -> HomoglyphNormalizer:
    """Возвращает глобальный экземпляр нормализатора (lazy singleton)."""
    global _normalizer
    if _normalizer is None:
        _normalizer = HomoglyphNormalizer()
    return _normalizer
