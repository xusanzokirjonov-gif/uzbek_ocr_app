#!/usr/bin/env python3
"""
generate_latin_dict.py
======================
Генерирует латинский узбекский словарь из кириллического
методом транслитерации по стандарту UzLat-1995.

Использование:
    python generate_latin_dict.py

Создаёт файл: model/uzwords_latin.txt
"""

from pathlib import Path

# ─── Таблица кириллица → латиница (UzLat-1995) ───────────────────────────────

_CYR_TO_LAT = [
    # Специфические узбекские буквы (в первую очередь — многобуквенные замены)
    ("Ў",  "Oʻ"), ("ў",  "oʻ"),
    ("Ғ",  "Gʻ"), ("ғ",  "gʻ"),
    ("Қ",  "Q"),  ("қ",  "q"),
    ("Ҳ",  "H"),  ("ҳ",  "h"),
    ("Ш",  "Sh"), ("ш",  "sh"),
    ("Ч",  "Ch"), ("ч",  "ch"),
    # Стандартный кириллический алфавит
    ("А",  "A"),  ("а",  "a"),
    ("Б",  "B"),  ("б",  "b"),
    ("В",  "V"),  ("в",  "v"),
    ("Г",  "G"),  ("г",  "g"),
    ("Д",  "D"),  ("д",  "d"),
    ("Е",  "E"),  ("е",  "e"),
    ("Ж",  "J"),  ("ж",  "j"),
    ("З",  "Z"),  ("з",  "z"),
    ("И",  "I"),  ("и",  "i"),
    ("Й",  "Y"),  ("й",  "y"),
    ("К",  "K"),  ("к",  "k"),
    ("Л",  "L"),  ("л",  "l"),
    ("М",  "M"),  ("м",  "m"),
    ("Н",  "N"),  ("н",  "n"),
    ("О",  "O"),  ("о",  "o"),
    ("П",  "P"),  ("п",  "p"),
    ("Р",  "R"),  ("р",  "r"),
    ("С",  "S"),  ("с",  "s"),
    ("Т",  "T"),  ("т",  "t"),
    ("У",  "U"),  ("у",  "u"),
    ("Ф",  "F"),  ("ф",  "f"),
    ("Х",  "X"),  ("х",  "x"),
    ("Ц",  "Ts"), ("ц",  "ts"),
    ("Щ",  "Sh"), ("щ",  "sh"),
    ("Ъ",  ""),   ("ъ",  ""),
    ("Ы",  "I"),  ("ы",  "i"),
    ("Ь",  ""),   ("ь",  ""),
    ("Э",  "E"),  ("э",  "e"),
    ("Ю",  "Yu"), ("ю",  "yu"),
    ("Я",  "Ya"), ("я",  "ya"),
    ("Ё",  "Yo"), ("ё",  "yo"),
    ("Нг", "Ng"), ("нг", "ng"),
]


def cyr_to_lat(word: str) -> str:
    """Транслитерирует слово из кириллицы в узбекскую латиницу."""
    result = word
    for cyr, lat in _CYR_TO_LAT:
        result = result.replace(cyr, lat)
    return result


def main():
    model_dir = Path(__file__).parent / "model"
    src_path  = model_dir / "uzwords.txt"
    dst_path  = model_dir / "uzwords_latin.txt"

    if not src_path.exists():
        print(f"❌ Файл не найден: {src_path}")
        return

    print(f"📖 Читаем кириллический словарь: {src_path}")
    latin_words: set[str] = set()

    with src_path.open("r", encoding="utf-8") as f:
        for line in f:
            word = line.strip()
            if not word or len(word) < 2:
                continue
            lat = cyr_to_lat(word).lower()
            if lat and all(ch.isascii() or ch in "ʻʼ'" for ch in lat):
                latin_words.add(lat)

    print(f"✅ Сгенерировано {len(latin_words):,} латинских слов")
    print(f"💾 Записываем в: {dst_path}")

    with dst_path.open("w", encoding="utf-8") as f:
        for word in sorted(latin_words):
            f.write(word + "\n")

    print("✅ Готово!")


if __name__ == "__main__":
    main()
