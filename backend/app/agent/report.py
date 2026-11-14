"""정책 검토 PDF 생성 (reportlab). 한글 글꼴: 시스템 글꼴을 찾고, 없으면 내장 CID 글꼴로 대체한다."""
from __future__ import annotations

import io
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONT_CANDIDATES = [
    str(Path(__file__).resolve().parent.parent / "assets" / "fonts" / "NanumGothic.ttf"),   # 동봉 글꼴(OFL)
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/Library/Fonts/NanumGothic.ttf",
]
_font_name: str | None = None
_STATUS = {"pass": "통과", "warn": "주의", "fail": "미충족"}
_LEVEL_COLOR = {"A": colors.HexColor("#1b6e4b"), "B": colors.HexColor("#9a6700"), "C": colors.HexColor("#5b616b")}


def _font() -> str:
    global _font_name
    if _font_name:
        return _font_name
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                pdfmetrics.registerFont(TTFont("JPMKorean", path))
                _font_name = "JPMKorean"
                return _font_name
            except Exception:  # noqa: BLE001
                continue
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    _font_name = "HYGothic-Medium"
    return _font_name


def _chart(series: dict, policy_month: str, font: str) -> Drawing:
    w, h, pad = 170 * mm, 62 * mm, 10 * mm
    d = Drawing(w, h)
    months = series["months"]
    values = series["treated"] + series["control"]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0

    def xy(i: int, v: float) -> tuple[float, float]:
        return pad + i * (w - 2 * pad) / max(len(months) - 1, 1), pad + (v - lo) / span * (h - 2 * pad)

    d.add(Line(pad, pad, w - pad, pad, strokeColor=colors.grey, strokeWidth=0.5))
    if policy_month in months:
        x, _ = xy(months.index(policy_month), lo)
        d.add(Line(x, pad, x, h - pad, strokeColor=colors.HexColor("#b42318"), strokeWidth=0.8, strokeDashArray=[3, 2]))
        d.add(String(x + 2, h - pad - 2, f"시행 {policy_month}", fontName=font, fontSize=7, fillColor=colors.HexColor("#b42318")))
    for key, color, dash in (("control", colors.HexColor("#6b7280"), [4, 2]), ("treated", colors.HexColor("#0b5cab"), None)):
        pts: list[float] = []
        for i, v in enumerate(series[key]):
            pts.extend(xy(i, v))
        d.add(PolyLine(pts, strokeColor=color, strokeWidth=1.4, strokeDashArray=dash))
    d.add(String(pad, 1, f"{months[0]} ~ {months[-1]}  |  실선: 대상 지역, 점선: 비교 지역 평균 (시행 전 평균=100)",
                 fontName=font, fontSize=7, fillColor=colors.grey))
    return d


def build_pdf(result: dict) -> bytes:
    font = _font()
    body = ParagraphStyle("body", fontName=font, fontSize=9.5, leading=14.5)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=11.5, textColor=colors.HexColor("#4b5563"))
    h1 = ParagraphStyle("h1", parent=body, fontSize=16, leading=21, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=body, fontSize=11.5, leading=16, spaceBefore=9, spaceAfter=4)

    def p(text: str, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(escape(str(text)), style)   # 사용자 입력은 항상 이스케이프

    spec, verdict = result["spec"], result["verdict"]
    story = [p("정책 검토 보고서", h1), p("Jeju Policy Mirror · 제주 지역정책 효과 검증 에이전트", small), Spacer(1, 4)]
    if result["data_source"]["mode"] == "sample":
        story.append(Paragraph("<b>" + escape("※ 합성 샘플 데이터로 만든 시연 결과입니다. 실제 정책 효과가 아닙니다.") + "</b>",
                               ParagraphStyle("warn", parent=body, textColor=colors.HexColor("#b42318"))))
    story += [p("1. 질문", h2), p(result["question"]),
              p(f"해석: 지역 {spec['area']} / 시행월 {spec['policy_month']} / 업종 {spec['industry']} / 정책 {spec['policy_label']}", small)]

    story.append(p("2. 판정", h2))
    level_style = ParagraphStyle("lvl", parent=body, fontSize=11, textColor=_LEVEL_COLOR[verdict["level"]])
    story += [p(f"[{verdict['level']} 등급] {verdict['title']}", level_style), p(verdict["statement"])]
    if verdict.get("plain_explanation"):
        story.append(p("쉬운 설명: " + verdict["plain_explanation"], small))

    if result.get("series"):
        story += [p("3. 시행 전후 흐름", h2), _chart(result["series"], spec["policy_month"], font)]

    story.append(p("4. 검증 항목", h2))
    rows = [[p("항목", small), p("결과", small), p("내용", small)]]
    for c in result["checks"]:
        label = c["label"] + (" (필수)" if c["required"] else "")
        rows.append([p(label, small), p(_STATUS.get(c["status"], c["status"]), small), p(c["detail"], small)])
    table = Table(rows, colWidths=[48 * mm, 16 * mm, 106 * mm])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(table)

    if result.get("controls"):
        story.append(p("5. 비교 지역", h2))
        story.append(p(", ".join(f"{c['area']}(유사도 {c['score']})" for c in result["controls"])
                       + (f" / 인접 지역 제외: {', '.join(result['excluded_neighbors'])}" if result.get("excluded_neighbors") else "")))

    story.append(p("6. 한계와 유의사항", h2))
    story += [p("· " + item, small) for item in result["limitations"]]
    story.append(p("7. 데이터 출처", h2))
    story += [p("· " + item, small) for item in result["data_source"]["datasets"]]
    story.append(p(f"· 사용 자료: {result['data_source']['label']}", small))

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                      title="Jeju Policy Mirror 정책 검토 보고서").build(story)
    return buf.getvalue()
