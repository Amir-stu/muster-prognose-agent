"""Step 10b: PowerPoint briefing from prepared slide content."""

from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt

SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)
BLANK_LAYOUT = 6
MARGIN = Inches(0.5)
CONTENT_TOP = Inches(1.3)
CONTENT_WIDTH = Inches(12.3)
TITLE_SIZE = Pt(28)
BODY_SIZE = Pt(16)
TABLE_SIZE = Pt(12)
ROW_HEIGHT = Inches(0.38)


@dataclass(frozen=True)
class SlideContent:
    title: str
    bullets: tuple[str, ...]
    table: tuple[tuple[str, ...], ...] = ()
    image: Path | None = None


def _text_box(slide, left, top, width, height, lines: tuple[str, ...], size) -> None:
    frame = slide.shapes.add_textbox(left, top, width, height).text_frame
    frame.word_wrap = True
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = line
        paragraph.font.size = size
        paragraph.space_after = Pt(8)


def _add_table(slide, rows: tuple[tuple[str, ...], ...], top) -> None:
    shape = slide.shapes.add_table(
        len(rows), len(rows[0]), MARGIN, top, CONTENT_WIDTH, ROW_HEIGHT * len(rows)
    )
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            cell = shape.table.cell(row_index, column_index)
            cell.text = value
            cell.text_frame.paragraphs[0].font.size = TABLE_SIZE


def _add_slide(presentation, content: SlideContent) -> None:
    slide = presentation.slides.add_slide(presentation.slide_layouts[BLANK_LAYOUT])
    _text_box(slide, MARGIN, Inches(0.35), CONTENT_WIDTH, Inches(0.8), (content.title,), TITLE_SIZE)
    slide.shapes[0].text_frame.paragraphs[0].font.bold = True
    if content.image is not None:
        slide.shapes.add_picture(str(content.image), MARGIN, CONTENT_TOP, width=Inches(8.3))
        _text_box(slide, Inches(9.0), CONTENT_TOP, Inches(3.9), Inches(5.6), content.bullets, BODY_SIZE)
        return
    bullet_height = Inches(2.2) if content.table else Inches(5.6)
    _text_box(slide, MARGIN, CONTENT_TOP, CONTENT_WIDTH, bullet_height, content.bullets, BODY_SIZE)
    if content.table:
        _add_table(slide, content.table, CONTENT_TOP + bullet_height + Inches(0.2))


def write_briefing(path: Path, slides: list[SlideContent]) -> int:
    presentation = Presentation()
    presentation.slide_width = SLIDE_WIDTH
    presentation.slide_height = SLIDE_HEIGHT
    for content in slides:
        _add_slide(presentation, content)
    presentation.save(str(path))
    return len(slides)
