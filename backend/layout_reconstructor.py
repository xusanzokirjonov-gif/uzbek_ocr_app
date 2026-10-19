"""
layout_reconstructor.py
=======================
Реконструктор разметки текста на основе координат EasyOCR.

EasyOCR возвращает список распознанных блоков вида:
    [ (bounding_box, text, confidence), ... ]

где bounding_box — список из 4 угловых точек [[x1,y1],[x2,y2],[x3,y3],[x4,y4]].

Задача этого модуля — восстановить читаемую текстовую структуру документа:
  ├── Сгруппировать блоки в строки (по вертикальному перекрытию)
  ├── Отсортировать строки сверху вниз, блоки внутри строки — слева направо
  ├── Добавить пробелы между словами пропорционально реальному расстоянию
  └── Добавить разрыв строки между строками пропорционально вертикальному зазору

Принцип работы (поясняется для диплома):

  Алгоритм группировки в строки:
    Для каждого нового блока проверяем, пересекается ли он по вертикали
    (Y-координата) с уже существующими строками. Критерий пересечения:
    вертикальное перекрытие > 45% от высоты меньшего из блоков.
    Если пересечение найдено — добавляем блок в эту строку,
    иначе — создаём новую строку.

  Алгоритм добавления пробелов:
    Пробелы добавляются пропорционально горизонтальному зазору между блоками.
    За единицу измерения берётся «ширина символа» ≈ 0.4 × высота строки.
    Максимум пробелов ограничен, чтобы не создавать избыточные отступы.
"""

from dataclasses import dataclass, field
from typing import Any


# ─── Типы данных ──────────────────────────────────────────────────────────────

# Тип bounding box от EasyOCR: список 4 точек [[x,y], [x,y], [x,y], [x,y]]
BoundingBox = list[list[int]]

# Один результат EasyOCR: (bbox, text, confidence)
OcrResult = tuple[BoundingBox, str, float]


@dataclass
class TextBlock:
    """
    Нормализованное представление одного распознанного блока текста.

    Все координаты вычисляются из bounding box EasyOCR
    и кэшируются для эффективной обработки.
    """
    text:       str
    confidence: float
    x_min:      int   # Левая граница блока (пиксели)
    x_max:      int   # Правая граница блока
    y_min:      int   # Верхняя граница блока
    y_max:      int   # Нижняя граница блока

    @property
    def height(self) -> int:
        """Высота блока в пикселях."""
        return self.y_max - self.y_min

    @property
    def width(self) -> int:
        """Ширина блока в пикселях."""
        return self.x_max - self.x_min

    @property
    def y_center(self) -> float:
        """Вертикальный центр блока."""
        return (self.y_min + self.y_max) / 2.0

    @classmethod
    def from_easyocr(cls, result: OcrResult) -> "TextBlock":
        """
        Создаёт TextBlock из результата EasyOCR.

        Args:
            result: Кортеж (bounding_box, text, confidence) от EasyOCR.

        Returns:
            Нормализованный TextBlock.
        """
        bbox, text, confidence = result
        # Нормализуем координаты: берём крайние значения по X и Y
        xs = [int(pt[0]) for pt in bbox]
        ys = [int(pt[1]) for pt in bbox]
        return cls(
            text=text,
            confidence=float(confidence),
            x_min=min(xs),
            x_max=max(xs),
            y_min=min(ys),
            y_max=max(ys),
        )


@dataclass
class TextLine:
    """Одна строка текста, состоящая из нескольких блоков."""
    blocks: list[TextBlock] = field(default_factory=list)

    @property
    def y_min(self) -> int:
        return min(b.y_min for b in self.blocks)

    @property
    def y_max(self) -> int:
        return max(b.y_max for b in self.blocks)

    @property
    def height(self) -> int:
        return self.y_max - self.y_min

    @property
    def y_center(self) -> float:
        return (self.y_min + self.y_max) / 2.0

    @property
    def avg_confidence(self) -> float:
        """Средняя точность блоков в строке."""
        return sum(b.confidence for b in self.blocks) / len(self.blocks)


# ─── Основная функция ─────────────────────────────────────────────────────────

def reconstruct_layout(
    results: list[OcrResult],
    overlap_threshold: float = 0.45,
    max_spaces: int = 15,
    paragraph_gap_ratio: float = 1.5,
) -> str:
    """
    Реконструирует текстовую разметку из результатов EasyOCR.

    Args:
        results: Список результатов EasyOCR [(bbox, text, conf), ...].
        overlap_threshold: Минимальная доля вертикального перекрытия
                           для отнесения блоков к одной строке (0.0–1.0).
        max_spaces: Максимальное количество пробелов между блоками.
        paragraph_gap_ratio: Если вертикальный зазор между строками
                             больше этого коэффициента × средняя высота строки,
                             вставляется пустая строка (новый абзац).

    Returns:
        Восстановленный текст с переносами строк и пробелами.
    """
    if not results:
        return ""

    # ── Шаг 1: Преобразуем результаты в TextBlock ─────────────────────────
    blocks = [TextBlock.from_easyocr(r) for r in results]

    # Сортируем блоки по вертикальному центру (сверху вниз)
    blocks.sort(key=lambda b: b.y_center)

    # ── Шаг 2: Группируем блоки в строки ──────────────────────────────────
    lines: list[TextLine] = _group_into_lines(blocks, overlap_threshold)

    # Сортируем строки по вертикальному центру
    lines.sort(key=lambda ln: ln.y_center)

    # Сортируем блоки внутри каждой строки слева направо
    for line in lines:
        line.blocks.sort(key=lambda b: b.x_min)

    # ── Шаг 3: Вычисляем метрики документа ───────────────────────────────
    all_heights = [b.height for b in blocks if b.height > 0]
    avg_block_height = sum(all_heights) / len(all_heights) if all_heights else 12.0

    # Ширина одного символа ≈ 40% высоты строки (эмпирическая формула)
    char_width = max(1.0, avg_block_height * 0.4)

    # Глобальный левый отступ (X-координата самого левого блока)
    global_x_min = min(b.x_min for b in blocks)

    # ── Шаг 4: Собираем текст строка за строкой ───────────────────────────
    output_lines: list[str] = []

    for line_idx, line in enumerate(lines):
        line_str = _render_line(line, char_width, global_x_min, max_spaces)
        output_lines.append(line_str)

        # Проверяем зазор до следующей строки — если большой, добавляем абзац
        if line_idx < len(lines) - 1:
            next_line = lines[line_idx + 1]
            gap = next_line.y_min - line.y_max
            if gap > paragraph_gap_ratio * avg_block_height:
                output_lines.append("")  # Пустая строка = новый абзац

    return "\n".join(output_lines)


def reconstruct_layout_with_meta(results: list[OcrResult]) -> dict[str, Any]:
    """
    Реконструирует разметку и возвращает дополнительные метаданные.

    Args:
        results: Список результатов EasyOCR.

    Returns:
        Словарь с полями:
          - text: str — восстановленный текст
          - blocks_count: int — количество блоков
          - lines_count: int — количество строк
          - avg_confidence: float — средняя точность
          - blocks: list — детальная информация о блоках
    """
    if not results:
        return {
            "text": "",
            "blocks_count": 0,
            "lines_count": 0,
            "avg_confidence": 0.0,
            "blocks": [],
        }

    text = reconstruct_layout(results)
    avg_conf = sum(r[2] for r in results) / len(results)

    # Детальная информация о блоках для фронтенда
    blocks_info = [
        {
            "text": r[1],
            "confidence": round(float(r[2]), 4),
            "bbox": [[int(x) for x in pt] for pt in r[0]],
        }
        for r in results
    ]

    return {
        "text": text,
        "blocks_count": len(results),
        "lines_count": len([ln for ln in text.split("\n") if ln.strip()]),
        "avg_confidence": round(avg_conf, 4),
        "blocks": blocks_info,
    }


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _group_into_lines(
    blocks: list[TextBlock],
    overlap_threshold: float,
) -> list[TextLine]:
    """
    Группирует блоки текста в строки по вертикальному перекрытию.

    Алгоритм (жадный, O(n²)):
      Для каждого блока ищем строку, у которой вертикальное перекрытие
      с этим блоком превышает threshold. Если такая строка найдена —
      добавляем блок в неё. Иначе — создаём новую строку.

    Этот алгоритм хорошо работает при условии, что блоки уже отсортированы
    по вертикальному центру (что мы делаем перед вызовом).

    Args:
        blocks: Отсортированные блоки.
        overlap_threshold: Минимальная доля перекрытия (0.0–1.0).

    Returns:
        Список строк с блоками.
    """
    lines: list[TextLine] = []

    for block in blocks:
        placed = False

        for line in lines:
            # Вычисляем вертикальное перекрытие блока и строки
            overlap_top    = max(block.y_min, line.y_min)
            overlap_bottom = min(block.y_max, line.y_max)
            overlap        = overlap_bottom - overlap_top

            # Нормируем перекрытие на высоту меньшего из двух объектов
            min_height = min(block.height, line.height)

            if min_height > 0 and (overlap / min_height) >= overlap_threshold:
                line.blocks.append(block)
                placed = True
                break

        if not placed:
            new_line = TextLine()
            new_line.blocks.append(block)
            lines.append(new_line)

    return lines


def _render_line(
    line: TextLine,
    char_width: float,
    global_x_min: int,
    max_spaces: int,
) -> str:
    """
    Преобразует строку текста в строку с пропорциональными пробелами.

    Args:
        line: Объект строки с блоками.
        char_width: Ширина одного символа в пикселях.
        global_x_min: Минимальная X-координата на всей странице (для отступов).
        max_spaces: Максимум пробелов между блоками.

    Returns:
        Строка текста с пробелами.
    """
    result = ""

    for i, block in enumerate(line.blocks):
        if i == 0:
            # Для первого блока добавляем отступ от левого края страницы
            indent = max(0, block.x_min - global_x_min)
            indent_spaces = int(round(indent / char_width))
            result += " " * min(max_spaces, indent_spaces)
            result += block.text
        else:
            # Для последующих блоков добавляем пробелы пропорционально зазору
            prev_block = line.blocks[i - 1]
            gap = block.x_min - prev_block.x_max

            if gap > 0:
                spaces_count = int(round(gap / char_width))
                spaces = " " * min(max_spaces, max(1, spaces_count))
            else:
                # Блоки перекрываются — минимум 1 пробел
                spaces = " "

            result += spaces + block.text

    return result
