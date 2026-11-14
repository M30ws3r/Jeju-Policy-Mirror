"""노선 단위 정책 검토 PDF.

새 파일로 만든 이유: 기존 report.py 는 '대상 지역·업종·비교 지역' 문구가 박혀 있는 지역 단위(합성 샘플) 보고서다.
노선 단위 실데이터 결과는 '대상 노선·집계 조건·비교 노선'으로 표기해야 해서, 기존 보고서를 바꾸지 않고 따로 둔다.
글꼴 등록과 표 스타일은 report.py 의 것을 그대로 쓴다.
"""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .report import _LEVEL_COLOR, _STATUS, _font


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
    d.add(String(pad, 1, f"{months[0]} ~ {months[-1]}  |  실선: 대상 노선, 점선: 비교 노선 평균 (시행 전 평균=100)",
                 fontName=font, fontSize=7, fillColor=colors.grey))
    return d


def build_pdf(result: dict) -> bytes:
    font = _font()
    body = ParagraphStyle("body", fontName=font, fontSize=9.5, leading=14.5)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=11.5, textColor=colors.HexColor("#4b5563"))
    h1 = ParagraphStyle("h1", parent=body, fontSize=16, leading=21, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=body, fontSize=11.5, leading=16, spaceBefore=9, spaceAfter=4)

    def p(text: str, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(escape(str(text)), style)

    spec, verdict, obs = result["spec"], result["verdict"], result["observed"]
    story = [p("정책 검토 보고서", h1), p("Jeju Policy Mirror · 제주 지역정책 효과 검증 에이전트", small), Spacer(1, 4)]
    story += [p("1. 질문", h2), p(result["question"]),
              p(f"대상 노선: {spec['area']} / 정책: {spec['policy_label']} / 시행월: {spec['policy_month']} / 집계 조건: {spec['industry']}", small)]

    story.append(p("2. 판정", h2))
    level_style = ParagraphStyle("lvl", parent=body, fontSize=11, textColor=_LEVEL_COLOR[verdict["level"]])
    story += [p(f"[{verdict['level']} 등급] {verdict['title']}", level_style), p(verdict["statement"])]

    story.append(p("3. 관측된 사실", h2))
    rows = [[p("항목", small), p("시행 전", small), p("시행 후", small), p("변화", small)],
            [p("대상 노선 하루 평균 승차 인원", small), p(f"{obs['target_daily_pre']:,.0f}명", small),
             p(f"{obs['target_daily_post']:,.0f}명", small), p(f"{obs['before_after_pct']:+.1f}%", small)],
            [p("전체 노선 합계 (참고)", small), p("", small), p("", small), p(f"{obs['island_before_after_pct']:+.1f}%", small)]]
    t = Table(rows, colWidths=[70 * mm, 30 * mm, 30 * mm, 40 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6"))]))
    story.append(t)

    if result.get("series"):
        story += [p("4. 시행 전후 흐름", h2), _chart(result["series"], spec["policy_month"], font)]

    story.append(p("5. 검증 항목", h2))
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
        story.append(p("6. 비교 노선", h2))
        story.append(p(", ".join(f"{c['area']}(유사도 {c['score']})" for c in result["controls"])))

    story.append(p("7. 한계와 유의사항", h2))
    story += [p("· " + item, small) for item in result["limitations"]]
    story.append(p("8. 데이터 출처", h2))
    story += [p("· " + item, small) for item in result["data_source"]["datasets"]]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                      title="Jeju Policy Mirror 정책 검토 보고서 (노선)").build(story)
    return buf.getvalue()
