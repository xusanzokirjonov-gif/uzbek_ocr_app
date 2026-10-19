/// Uzbek Latin ↔ Cyrillic script converter.
///
/// Supports the official O'zbek lotin alifbosi (Uzbek Latin alphabet)
/// and the Cyrillic alphabet used before 1993.
class UzbekConverter {
  // Latin → Cyrillic mapping (digraphs first, then single chars)
  static const Map<String, String> _latinToCyrillic = {
    // Digraphs (must be checked before single characters)
    "Sh": "Ш",
    "sh": "ш",
    "CH": "Ч",
    "Ch": "Ч",
    "ch": "ч",
    "G'": "Ғ",
    "g'": "ғ",
    "O'": "Ў",
    "o'": "ў",
    "Ng": "Нг",
    "ng": "нг",
    "Yo": "Ё",
    "yo": "ё",
    "Ya": "Я",
    "ya": "я",
    "Yu": "Ю",
    "yu": "ю",
    "Ye": "Е",
    "ye": "е",
    "Ts": "Ц",
    "ts": "ц",
    // Single characters
    "A": "А",
    "a": "а",
    "B": "Б",
    "b": "б",
    "D": "Д",
    "d": "д",
    "E": "Э",
    "e": "э",
    "F": "Ф",
    "f": "ф",
    "G": "Г",
    "g": "г",
    "H": "Ҳ",
    "h": "ҳ",
    "I": "И",
    "i": "и",
    "J": "Ж",
    "j": "ж",
    "K": "К",
    "k": "к",
    "L": "Л",
    "l": "л",
    "M": "М",
    "m": "м",
    "N": "Н",
    "n": "н",
    "O": "О",
    "o": "о",
    "P": "П",
    "p": "п",
    "Q": "Қ",
    "q": "қ",
    "R": "Р",
    "r": "р",
    "S": "С",
    "s": "с",
    "T": "Т",
    "t": "т",
    "U": "У",
    "u": "у",
    "V": "В",
    "v": "в",
    "X": "Х",
    "x": "х",
    "Y": "Й",
    "y": "й",
    "Z": "З",
    "z": "з",
    "'": "ъ",
  };

  // Cyrillic → Latin mapping
  static const Map<String, String> _cyrillicToLatin = {
    // Multi-char Cyrillic
    "Ш": "Sh",
    "ш": "sh",
    "Ч": "Ch",
    "ч": "ch",
    "Ғ": "G'",
    "ғ": "g'",
    "Ў": "O'",
    "ў": "o'",
    "Ё": "Yo",
    "ё": "yo",
    "Я": "Ya",
    "я": "ya",
    "Ю": "Yu",
    "ю": "yu",
    "Е": "Ye",
    "е": "ye",
    "Ц": "Ts",
    "ц": "ts",
    // Single Cyrillic
    "А": "A",
    "а": "a",
    "Б": "B",
    "б": "b",
    "Д": "D",
    "д": "d",
    "Э": "E",
    "э": "e",
    "Ф": "F",
    "ф": "f",
    "Г": "G",
    "г": "g",
    "Ҳ": "H",
    "ҳ": "h",
    "И": "I",
    "и": "i",
    "Ж": "J",
    "ж": "j",
    "К": "K",
    "к": "k",
    "Л": "L",
    "л": "l",
    "М": "M",
    "м": "m",
    "Н": "N",
    "н": "n",
    "О": "O",
    "о": "o",
    "П": "P",
    "п": "p",
    "Қ": "Q",
    "қ": "q",
    "Р": "R",
    "р": "r",
    "С": "S",
    "с": "s",
    "Т": "T",
    "т": "t",
    "У": "U",
    "у": "u",
    "В": "V",
    "в": "v",
    "Х": "X",
    "х": "x",
    "Й": "Y",
    "й": "y",
    "З": "Z",
    "з": "z",
    "ъ": "'",
  };

  /// Detect if text is primarily Latin or Cyrillic
  static bool isCyrillic(String text) {
    int cyrillic = 0;
    int latin = 0;
    for (final c in text.runes) {
      if (c >= 0x0400 && c <= 0x04FF) cyrillic++;
      if ((c >= 0x0041 && c <= 0x005A) || (c >= 0x0061 && c <= 0x007A)) latin++;
    }
    return cyrillic > latin;
  }

  /// Convert Latin Uzbek text to Cyrillic
  static String toCyrillic(String text) {
    final buffer = StringBuffer();
    int i = 0;

    while (i < text.length) {
      bool found = false;

      // Try digraphs first (2 characters)
      if (i + 1 < text.length) {
        final digraph = text.substring(i, i + 2);
        if (_latinToCyrillic.containsKey(digraph)) {
          buffer.write(_latinToCyrillic[digraph]);
          i += 2;
          found = true;
        }
      }

      if (!found) {
        final char = text[i];
        if (_latinToCyrillic.containsKey(char)) {
          buffer.write(_latinToCyrillic[char]);
        } else {
          buffer.write(char); // Keep as-is (numbers, punctuation)
        }
        i++;
      }
    }

    return buffer.toString();
  }

  /// Convert Cyrillic Uzbek text to Latin
  static String toLatin(String text) {
    final buffer = StringBuffer();

    for (final char in text.split('')) {
      if (_cyrillicToLatin.containsKey(char)) {
        buffer.write(_cyrillicToLatin[char]);
      } else {
        buffer.write(char); // Keep as-is
      }
    }

    return buffer.toString();
  }

  /// Auto-convert: detects script and converts to the opposite
  static String autoConvert(String text) {
    if (isCyrillic(text)) {
      return toLatin(text);
    } else {
      return toCyrillic(text);
    }
  }
}
