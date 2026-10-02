"""Build the Russian application manual from reviewed, versioned JSON content."""

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[1]
NAVY = colors.HexColor("#172B46")
TEAL = colors.HexColor("#087E8B")
INK = colors.HexColor("#26384B")
MUTED = colors.HexColor("#607184")
PALE = colors.HexColor("#EDF5F7")
LINE = colors.HexColor("#D9E4EC")
PAGE_W, PAGE_H = 210 * mm, 297 * mm
WIDTH = PAGE_W - 40 * mm


def fonts(directory=None):
    candidates = [
        ("/System/Library/Fonts/Supplemental", "Arial.ttf", "Arial Bold.ttf"),
        ("/usr/share/fonts/truetype/dejavu", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
        ("C:/Windows/Fonts", "arial.ttf", "arialbd.ttf"),
    ]
    if directory:
        candidates = [(directory, normal, bold) for _, normal, bold in candidates]
    for folder, normal, bold in candidates:
        if (Path(folder) / normal).is_file() and (Path(folder) / bold).is_file():
            pdfmetrics.registerFont(TTFont("Manual", str(Path(folder) / normal)))
            pdfmetrics.registerFont(TTFont("ManualBold", str(Path(folder) / bold)))
            pdfmetrics.registerFontFamily("Manual", normal="Manual", bold="ManualBold")
            return
    raise SystemExit("Cyrillic fonts not found. Use --font-dir with Arial or DejaVu Sans fonts.")


def styles():
    base = dict(fontName="Manual", textColor=INK, fontSize=10, leading=14.3, spaceAfter=7)
    return {
        "body": ParagraphStyle("Body", **base),
        "small": ParagraphStyle("Small", **(base | dict(fontSize=8.5, leading=12, textColor=MUTED))),
        "h1": ParagraphStyle(
            "H1", fontName="ManualBold", fontSize=23, leading=28, textColor=NAVY, spaceAfter=15
        ),
        "h2": ParagraphStyle(
            "H2",
            fontName="ManualBold",
            fontSize=12,
            leading=16,
            textColor=TEAL,
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "eyebrow": ParagraphStyle(
            "Eyebrow", fontName="ManualBold", fontSize=8.5, leading=12, textColor=TEAL, spaceAfter=8
        ),
        "cell": ParagraphStyle("Cell", **(base | dict(fontSize=9, leading=12.4, spaceAfter=0))),
        "th": ParagraphStyle("TH", fontName="ManualBold", fontSize=9, leading=12.5, textColor=colors.white),
        "callout": ParagraphStyle("Callout", **(base | dict(fontSize=9.5, leading=14, spaceAfter=0))),
        "code": ParagraphStyle(
            "Code", fontName="Manual", fontSize=8.1, leading=12, textColor=NAVY, spaceAfter=0
        ),
        "toc": ParagraphStyle(
            "TOC",
            fontName="Manual",
            fontSize=9.5,
            leading=12,
            spaceBefore=1,
            textColor=INK,
            leftIndent=0,
            firstLineIndent=0,
            rightIndent=20,
        ),
    }


class Workflow(Flowable):
    def __init__(self, labels):
        super().__init__()
        self.labels = labels
        self.width = WIDTH
        self.height = 61

    def draw(self):
        count = len(self.labels)
        gap = 14
        box = (self.width - gap * (count - 1)) / count
        c = self.canv
        for i, text in enumerate(self.labels):
            x = i * (box + gap)
            c.setFillColor(PALE)
            c.roundRect(x, 8, box, 45, 5, fill=1, stroke=0)
            c.setFillColor(TEAL)
            c.setFont("ManualBold", 9)
            for line_no, line in enumerate(text.split("\n")):
                c.drawCentredString(x + box / 2, 35 - line_no * 12, line)
            if i < count - 1:
                c.setStrokeColor(TEAL)
                c.line(x + box + 2, 30, x + box + gap - 2, 30)
                c.line(x + box + gap - 6, 33, x + box + gap - 2, 30)
                c.line(x + box + gap - 6, 27, x + box + gap - 2, 30)


class ManualDoc(BaseDocTemplate):
    def __init__(self, filename, metadata):
        super().__init__(
            filename,
            pagesize=(PAGE_W, PAGE_H),
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=22 * mm,
            bottomMargin=19 * mm,
            title=metadata["title"],
            author="Проект «Сюрвейер»",
            subject="Руководство пользователя и администратора",
            pageCompression=1,
            invariant=1,
            allowSplitting=1,
        )
        self.metadata = metadata
        self.addPageTemplates(
            PageTemplate(
                id="manual",
                frames=[
                    Frame(
                        self.leftMargin,
                        self.bottomMargin,
                        WIDTH,
                        PAGE_H - self.topMargin - self.bottomMargin,
                        leftPadding=0,
                        rightPadding=0,
                        topPadding=0,
                        bottomPadding=0,
                    )
                ],
                onPage=self.decorate,
            )
        )

    def decorate(self, c, doc):
        c.saveState()
        if doc.page > 1:
            c.setFont("ManualBold", 8)
            c.setFillColor(NAVY)
            c.drawString(20 * mm, PAGE_H - 13 * mm, "СЮРВЕЙЕР / РУКОВОДСТВО")
            c.setFont("Manual", 8)
            c.setFillColor(MUTED)
            c.drawRightString(PAGE_W - 20 * mm, PAGE_H - 13 * mm, self.metadata["date_display"])
            c.setStrokeColor(LINE)
            c.line(20 * mm, PAGE_H - 16 * mm, PAGE_W - 20 * mm, PAGE_H - 16 * mm)
        c.setStrokeColor(LINE)
        c.line(20 * mm, 14 * mm, PAGE_W - 20 * mm, 14 * mm)
        c.setFillColor(MUTED)
        c.setFont("Manual", 8)
        c.drawString(
            20 * mm, 9 * mm, "Редакция 1.1 · Вымышленные примеры · " + self.metadata["source_commit"]
        )
        c.drawRightString(PAGE_W - 20 * mm, 9 * mm, str(doc.page))
        c.restoreState()

    def afterFlowable(self, flowable):
        if hasattr(flowable, "section_key"):
            self.canv.bookmarkPage(flowable.section_key)
            self.canv.addOutlineEntry(flowable.getPlainText(), flowable.section_key, level=0)
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page, flowable.section_key))


def build(source, output, font_dir=None):
    fonts(font_dir)
    data = json.loads(source.read_text(encoding="utf-8"))
    ss = styles()

    def p(text, style="body"):
        return Paragraph(escape(text).replace("\n", "<br/>"), ss[style])

    def panel(text, code=False):
        result = Table([[p(text, "code" if code else "callout")]], colWidths=[WIDTH])
        result.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), PALE),
                    ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        return [result, Spacer(1, 9)]

    story = [Spacer(1, 26 * mm), p("INSON · СТРАХОВОЙ ОСМОТР", "eyebrow")]
    cover_style = ParagraphStyle(
        "Cover", fontName="ManualBold", fontSize=42, leading=48, textColor=NAVY, spaceAfter=17
    )
    story += [
        Paragraph("Сюрвейер", cover_style),
        p("Как работает приложение", "h1"),
        p("Подробное руководство пользователя, андеррайтера, актуария и администратора"),
        Spacer(1, 13 * mm),
        Workflow(["Документы\nи фото", "Проверка\nи расчёт", "Акт\nи решение"]),
        Spacer(1, 14 * mm),
    ]
    story += panel(
        "Одна система для браузера и Telegram Mini App. Документы подтверждают факты, код рассчитывает значения, сотрудник проверяет результат, андеррайтер фиксирует решение."
    )
    story += [
        Spacer(1, 12 * mm),
        p("Дата описания: " + data["date_display"]),
        p("Версия приложения: 0.1.0 · исходный код " + data["source_commit"]),
        p(
            "Руководство описывает реализованные функции. Числа в учебных примерах не являются тарифами INSON. Постоянное размещение, рабочие данные страховщика и отдельные приёмочные проверки остаются внешними этапами.",
            "small",
        ),
        PageBreak(),
        p("Содержание", "h1"),
        p(
            "Сотруднику: разделы 1–15 и 20. Администратору и актуарию: также 16–19. Статус готовности и источники: 21–22.",
            "small",
        ),
    ]
    toc = TableOfContents()
    toc.levelStyles = [ss["toc"]]
    toc.dotsMinLevel = 0
    story += [toc]
    for index, section in enumerate(data["sections"], 1):
        story += [PageBreak(), p(section["audience"], "eyebrow")]
        title = p(f"{index:02d}. {section['title']}", "h1")
        title.section_key = f"section-{index}"
        story.append(title)
        for block in section["blocks"]:
            kind = block["type"]
            if kind in {"p", "h2", "small"}:
                story.append(p(block["text"], {"p": "body", "h2": "h2", "small": "small"}[kind]))
            elif kind in {"callout", "code"}:
                story.extend(panel(block["text"], kind == "code"))
            elif kind == "flow":
                story.append(Workflow(block["items"]))
            elif kind in {"steps", "bullets"}:
                for number, item in enumerate(block["items"], 1):
                    prefix = f"{number}. " if kind == "steps" else "• "
                    story.append(p(prefix + item))
            elif kind == "table":
                rows = [[p(cell, "th") for cell in block["headers"]]]
                rows += [[p(cell, "cell") for cell in row] for row in block["rows"]]
                ratios = block.get("widths", [1] * len(block["headers"]))
                table = Table(
                    rows,
                    colWidths=[WIDTH * ratio / sum(ratios) for ratio in ratios],
                    repeatRows=1,
                    hAlign="LEFT",
                )
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 7),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                        ]
                    )
                )
                story += [table, Spacer(1, 9)]
            elif kind == "links":
                for entry in block["items"]:
                    label = escape(entry["label"])
                    url = escape(entry["url"], {'"': "&quot;"})
                    link = Paragraph(f'<link href="{url}" color="#087E8B">{label}</link>', ss["body"])
                    story.append(KeepTogether([link, p(entry["note"], "small")]))
            else:
                raise ValueError(f"Unknown block type: {kind}")
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = ManualDoc(str(output), data)
    doc.multiBuild(story)
    print(f"Created {output} ({doc.page} pages)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "docs/manual-ru.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/Surveyor-Manual-RU.pdf")
    parser.add_argument("--font-dir")
    args = parser.parse_args()
    build(args.source, args.output, args.font_dir)
