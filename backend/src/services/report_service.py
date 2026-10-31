"""审查报告生成服务 — 将 ContractReviewState 导出为 PDF。"""

from __future__ import annotations

import io
import logging
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# 注册中文 CID 字体（不依赖系统字体文件，内置支持简繁日韩）
_CJK_FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT))

from ..pipeline.state import (
    ComplianceStatus,
    ContractReviewState,
    POSITION_LABELS,
    RiskLevel,
    ReviewStatus,
)

logger = logging.getLogger(__name__)

# ── 颜色定义 ──────────────────────────────────────────────

# 「案头批注」印刷配色：石青为骨，朱砂定凶，藤黄示警，青绿报平安
COLOR_PRIMARY = colors.HexColor("#226976")
COLOR_HIGH = colors.HexColor("#B03225")
COLOR_MEDIUM = colors.HexColor("#B08020")
COLOR_LOW = colors.HexColor("#2F7A58")
COLOR_BG_LIGHT = colors.HexColor("#f3f4f6")
COLOR_BORDER = colors.HexColor("#d1d5db")

RISK_COLORS = {
    "high": COLOR_HIGH,
    "medium": COLOR_MEDIUM,
    "low": COLOR_LOW,
    "none": COLOR_LOW,
}

COMPLIANCE_COLORS = {
    "compliant": COLOR_LOW,
    "non_compliant": COLOR_HIGH,
    "needs_review": COLOR_MEDIUM,
}

STATUS_LABELS = {
    "pending": "待处理",
    "in_progress": "处理中",
    "awaiting_human": "等待人工审核",
    "approved": "已通过",
    "rejected": "已驳回",
    "completed": "已完成",
}

RISK_LABELS = {
    "high": "高风险",
    "medium": "中风险",
    "low": "低风险",
    "none": "无风险",
}

COMPLIANCE_LABELS = {
    "compliant": "合规",
    "non_compliant": "不合规",
    "needs_review": "待审核",
}

SOURCE_LABELS = {
    "rule": "规则引擎",
    "llm": "大模型",
    "conflict": "双引擎分歧",
}


# ── 样式定义 ──────────────────────────────────────────────

def _build_styles():
    """构建 PDF 样式（中文使用 STSong-Light CID 字体）。"""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="CoverTitle",
        parent=styles["Title"],
        fontName=_CJK_FONT,
        fontSize=24,
        leading=30,
        textColor=COLOR_PRIMARY,
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="CoverSubtitle",
        parent=styles["Normal"],
        fontName=_CJK_FONT,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#6b7280"),
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SectionTitle",
        parent=styles["Heading2"],
        fontName=_CJK_FONT,
        fontSize=14,
        leading=18,
        textColor=COLOR_PRIMARY,
        spaceBefore=16,
        spaceAfter=8,
        borderWidth=0,
        borderPadding=0,
    ))
    styles.add(ParagraphStyle(
        name="BodyCN",
        parent=styles["Normal"],
        fontName=_CJK_FONT,
        fontSize=10,
        leading=14,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="SmallGray",
        parent=styles["Normal"],
        fontName=_CJK_FONT,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#9ca3af"),
    ))
    styles.add(ParagraphStyle(
        name="TableCell",
        parent=styles["Normal"],
        fontName=_CJK_FONT,
        fontSize=9,
        leading=12,
    ))
    return styles


# ── 报告生成 ──────────────────────────────────────────────

def _clause_label(state: ContractReviewState, clause_id: str) -> str:
    """把内部条款 ID 译成人读的「第X条 标题」，找不到就原样返回。"""
    for i, c in enumerate(state.clauses):
        if c.id == clause_id:
            no = c.section_number or str(i + 1)
            return f"第{no}条 {c.title}"
    return clause_id


def _draw_seal(canvas, doc, state: ContractReviewState) -> None:
    """封面首页右上角落一枚微斜的朱框定论章。"""
    level = state.overall_risk_level.value
    label = RISK_LABELS.get(level, level)
    color = RISK_COLORS.get(level, COLOR_HIGH)
    canvas.saveState()
    canvas.translate(A4[0] - 3.4 * cm, A4[1] - 3.2 * cm)
    canvas.rotate(-8)
    canvas.setStrokeColor(color)
    canvas.setLineWidth(2.5)
    canvas.roundRect(-1.9 * cm, -1.0 * cm, 3.8 * cm, 2.0 * cm, 0.15 * cm)
    canvas.setFillColor(color)
    canvas.setFont(_CJK_FONT, 14)
    canvas.drawCentredString(0, 0.18 * cm, f"{label} · 定论")
    canvas.setFont(_CJK_FONT, 7)
    canvas.drawCentredString(0, -0.52 * cm, "AI 法务幕僚")
    canvas.restoreState()


def generate_report(state: ContractReviewState) -> bytes:
    """将审查状态生成为 PDF 报告，返回字节流。"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )

    styles = _build_styles()
    story = []

    # 封面
    story.extend(_build_cover(state, styles))
    story.append(Spacer(1, 20))

    # 摘要
    story.extend(_build_summary(state, styles))

    # 风险发现
    story.extend(_build_risk_section(state, styles))

    # 合规检查
    story.extend(_build_compliance_section(state, styles))

    # 修改建议
    story.extend(_build_suggestions_section(state, styles))

    # 人工反馈
    story.extend(_build_feedback_section(state, styles))

    # 页脚
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        styles["SmallGray"],
    ))
    story.append(Paragraph(
        "本报告由 AI 法务幕僚（条款拆解官 · 风险猎手 · 合规法官 · 修订顾问）自动生成，仅供法务参考。",
        styles["SmallGray"],
    ))

    doc.build(story, onFirstPage=lambda c, d: _draw_seal(c, d, state))
    return buf.getvalue()


# ── 封面 ──────────────────────────────────────────────────

def _build_cover(state: ContractReviewState, styles) -> list:
    elements = []
    elements.append(Spacer(1, 60))
    elements.append(Paragraph("合同审查报告", styles["CoverTitle"]))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(f"审查编号：{state.review_id}", styles["CoverSubtitle"]))
    elements.append(Paragraph(f"合同类型：{state.contract_type or '未识别'}", styles["CoverSubtitle"]))
    elements.append(Paragraph(
        f"审查立场：{POSITION_LABELS.get(state.position, '中立')}",
        styles["CoverSubtitle"],
    ))
    elements.append(Paragraph(
        f"审查状态：{STATUS_LABELS.get(state.status.value, state.status.value)}",
        styles["CoverSubtitle"],
    ))
    elements.append(Paragraph(
        f"生成时间：{state.created_at.strftime('%Y-%m-%d %H:%M')}",
        styles["CoverSubtitle"],
    ))

    elements.append(Spacer(1, 30))
    elements.append(HRFlowable(width="100%", color=COLOR_PRIMARY, thickness=2))

    return elements


# ── 摘要 ──────────────────────────────────────────────────

def _build_summary(state: ContractReviewState, styles) -> list:
    elements = []
    elements.append(Paragraph("一、审查摘要", styles["SectionTitle"]))

    risk_label = RISK_LABELS.get(state.overall_risk_level.value, state.overall_risk_level.value)
    compliance_label = COMPLIANCE_LABELS.get(state.overall_compliance.value, state.overall_compliance.value)

    summary_data = [
        ["指标", "结果"],
        ["综合风险等级", risk_label],
        ["合规状态", compliance_label],
        ["提取条款数", str(len(state.clauses))],
        ["风险发现数", str(len(state.risk_findings))],
        ["合规发现数", str(len(state.compliance_findings))],
        ["修改建议数", str(len(state.suggestions))],
        ["缺失条款数", str(len(state.missing_clauses))],
        ["需人工审核", "是" if state.needs_human_review else "否"],
    ]

    table = Table(summary_data, colWidths=[5 * cm, 8 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _CJK_FONT),
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("BACKGROUND", (0, 1), (-1, -1), COLOR_BG_LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_BG_LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)

    if state.risk_summary:
        elements.append(Spacer(1, 8))
        elements.append(Paragraph(f"<b>风险摘要：</b>{state.risk_summary}", styles["BodyCN"]))

    elements.append(Spacer(1, 10))
    return elements


# ── 风险发现 ──────────────────────────────────────────────

def _build_risk_section(state: ContractReviewState, styles) -> list:
    elements = []
    elements.append(Paragraph("二、风险发现", styles["SectionTitle"]))

    if not state.risk_findings:
        elements.append(Paragraph("未发现风险条款。", styles["BodyCN"]))
        elements.append(Spacer(1, 10))
        return elements

    header = ["条款", "风险等级", "风险类型", "来源", "描述"]
    rows = [header]
    for r in state.risk_findings:
        rows.append([
            _clause_label(state, r.clause_id),
            RISK_LABELS.get(r.risk_level.value, r.risk_level.value),
            r.risk_type,
            SOURCE_LABELS.get(getattr(r, "source", "llm"), "大模型"),
            r.description[:60] + ("..." if len(r.description) > 60 else ""),
        ])

    table = Table(rows, colWidths=[3 * cm, 1.6 * cm, 2.4 * cm, 1.8 * cm, 7.2 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _CJK_FONT),
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_BG_LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 10))

    return elements


# ── 合规检查 ──────────────────────────────────────────────

def _build_compliance_section(state: ContractReviewState, styles) -> list:
    elements = []
    elements.append(Paragraph("三、合规检查", styles["SectionTitle"]))

    if not state.compliance_findings:
        elements.append(Paragraph("未发现合规问题。", styles["BodyCN"]))
        elements.append(Spacer(1, 10))
        return elements

    header = ["条款", "状态", "法规依据", "问题"]
    rows = [header]
    for c in state.compliance_findings:
        rows.append([
            _clause_label(state, c.clause_id),
            COMPLIANCE_LABELS.get(c.status.value, c.status.value),
            c.regulation,
            c.issue[:50] + ("..." if len(c.issue) > 50 else ""),
        ])

    table = Table(rows, colWidths=[3 * cm, 1.8 * cm, 3.4 * cm, 7.8 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _CJK_FONT),
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_BG_LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 10))

    if state.missing_clauses:
        elements.append(Paragraph("<b>缺失条款：</b>", styles["BodyCN"]))
        for clause in state.missing_clauses:
            elements.append(Paragraph(f"  - {clause}", styles["BodyCN"]))
        elements.append(Spacer(1, 10))

    return elements


# ── 修改建议 ──────────────────────────────────────────────

def _build_suggestions_section(state: ContractReviewState, styles) -> list:
    elements = []
    elements.append(Paragraph("四、修改建议", styles["SectionTitle"]))

    if not state.suggestions:
        elements.append(Paragraph("无需修改。", styles["BodyCN"]))
        elements.append(Spacer(1, 10))
        return elements

    for i, s in enumerate(state.suggestions, 1):
        priority = RISK_LABELS.get(s.priority.value, s.priority.value)
        elements.append(Paragraph(
            f"<b>建议 {i}</b>（{priority}）— {_clause_label(state, s.clause_id)}",
            styles["BodyCN"],
        ))
        elements.append(Paragraph(f"  原文：{s.original_text}", styles["BodyCN"]))
        elements.append(Paragraph(f"  建议：{s.suggested_text}", styles["BodyCN"]))
        elements.append(Paragraph(f"  原因：{s.reason}", styles["BodyCN"]))
        elements.append(Spacer(1, 6))

    elements.append(Spacer(1, 10))
    return elements


# ── 人工反馈 ──────────────────────────────────────────────

def _build_feedback_section(state: ContractReviewState, styles) -> list:
    elements = []

    if state.human_feedback is None:
        return elements

    fb = state.human_feedback
    elements.append(Paragraph("五、人工审核记录", styles["SectionTitle"]))
    elements.append(Paragraph(f"审核人：{fb.reviewer}", styles["BodyCN"]))
    elements.append(Paragraph(f"审核决定：{fb.decision}", styles["BodyCN"]))
    if fb.comments:
        elements.append(Paragraph(f"审核意见：{fb.comments}", styles["BodyCN"]))
    elements.append(Paragraph(
        f"审核时间：{fb.timestamp.strftime('%Y-%m-%d %H:%M')}",
        styles["BodyCN"],
    ))
    elements.append(Spacer(1, 10))

    return elements


# ── Word (.docx) 报告 ──────────────────────────────────────


def generate_word(state: ContractReviewState) -> bytes:
    """将审查状态生成为 Word (.docx) 报告，返回字节流。"""
    from docx import Document
    from docx.enum.table import WD_ALIGN_VERTICAL
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    doc = Document()

    # 设置默认中文字体（宋体 / SimSun，Office / WPS 默认支持）
    style = doc.styles["Normal"]
    style.font.name = "SimSun"
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "SimSun")

    def _set_cjk(run, name: str = "SimSun", size: int = 10.5, bold: bool = False, color: RGBColor | None = None):
        run.font.name = name
        run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
        run.font.size = Pt(size)
        run.bold = bold
        if color is not None:
            run.font.color.rgb = color

    def _add_heading(text: str, level: int = 1):
        p = doc.add_heading(level=level)
        run = p.add_run(text)
        sizes = {1: 18, 2: 14, 3: 12}
        _set_cjk(run, size=sizes.get(level, 12), bold=True, color=RGBColor(0x22, 0x69, 0x76))
        return p

    def _add_para(text: str, bold: bool = False, size: int = 10.5):
        p = doc.add_paragraph()
        run = p.add_run(text)
        _set_cjk(run, size=size, bold=bold)
        return p

    def _add_table(headers: list[str], rows: list[list[str]], highlight_col: int | None = None, highlight_map: dict | None = None):
        table = doc.add_table(rows=1 + len(rows), cols=len(headers))
        table.style = "Light Grid Accent 1"
        # 表头
        hdr = table.rows[0].cells
        for i, h in enumerate(headers):
            hdr[i].text = ""
            run = hdr[i].paragraphs[0].add_run(h)
            _set_cjk(run, size=10, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
            # 表头底色
            tc_pr = hdr[i]._tc.get_or_add_tcPr()
            from docx.oxml import OxmlElement
            shd = OxmlElement("w:shd")
            shd.set(qn("w:fill"), "226976")
            tc_pr.append(shd)
        # 数据行
        for ri, row in enumerate(rows, start=1):
            cells = table.rows[ri].cells
            for ci, val in enumerate(row):
                cells[ci].text = ""
                run = cells[ci].paragraphs[0].add_run(str(val))
                color = None
                if highlight_col is not None and ci == highlight_col and highlight_map:
                    color = highlight_map.get(str(val))
                _set_cjk(run, size=9, color=color)
                cells[ci].vertical_alignment = WD_ALIGN_VERTICAL.TOP
        return table

    # ── 封面 ──
    title = doc.add_paragraph()
    title.alignment = 1  # center
    r = title.add_run("合同审查报告")
    _set_cjk(r, size=26, bold=True, color=RGBColor(0x22, 0x69, 0x76))
    doc.add_paragraph()

    _add_para(f"审查编号：{state.review_id}")
    _add_para(f"合同类型：{state.contract_type or '未识别'}")
    _add_para(f"审查立场：{POSITION_LABELS.get(state.position, '中立')}")
    _add_para(f"审查状态：{STATUS_LABELS.get(state.status.value, state.status.value)}")
    _add_para(f"生成时间：{state.created_at.strftime('%Y-%m-%d %H:%M')}")

    # 定论章：Word 版以朱砂大字居中呈现，与 PDF 封面落章同一语义
    seal = doc.add_paragraph()
    seal.alignment = 1
    r_seal = seal.add_run(
        f"【 {RISK_LABELS.get(state.overall_risk_level.value, state.overall_risk_level.value)} · 定论 】"
    )
    _set_cjk(r_seal, size=15, bold=True, color=RGBColor(0xB0, 0x32, 0x25))
    doc.add_paragraph()

    # ── 摘要 ──
    _add_heading("一、审查摘要", level=1)
    risk_label = RISK_LABELS.get(state.overall_risk_level.value, state.overall_risk_level.value)
    compliance_label = COMPLIANCE_LABELS.get(state.overall_compliance.value, state.overall_compliance.value)

    _add_table(
        ["指标", "结果"],
        [
            ["综合风险等级", risk_label],
            ["合规状态", compliance_label],
            ["提取条款数", str(len(state.clauses))],
            ["风险发现数", str(len(state.risk_findings))],
            ["合规发现数", str(len(state.compliance_findings))],
            ["修改建议数", str(len(state.suggestions))],
            ["缺失条款数", str(len(state.missing_clauses))],
            ["需人工审核", "是" if state.needs_human_review else "否"],
        ],
    )
    if state.risk_summary:
        doc.add_paragraph()
        p = doc.add_paragraph()
        r1 = p.add_run("风险摘要：")
        _set_cjk(r1, bold=True)
        r2 = p.add_run(state.risk_summary)
        _set_cjk(r2)

    # ── 风险发现 ──
    _add_heading("二、风险发现", level=1)
    if state.risk_findings:
        risk_rows = []
        for r in state.risk_findings:
            desc = r.description
            if len(desc) > 80:
                desc = desc[:80] + "..."
            risk_rows.append([
                _clause_label(state, r.clause_id),
                RISK_LABELS.get(r.risk_level.value, r.risk_level.value),
                r.risk_type,
                SOURCE_LABELS.get(getattr(r, "source", "llm"), "大模型"),
                desc,
            ])
        risk_color_map = {
            "高风险": RGBColor(0xB0, 0x32, 0x25),
            "中风险": RGBColor(0xB0, 0x80, 0x20),
            "低风险": RGBColor(0x2F, 0x7A, 0x58),
            "无风险": RGBColor(0x2F, 0x7A, 0x58),
        }
        _add_table(["条款", "风险等级", "风险类型", "来源", "描述"], risk_rows, highlight_col=1, highlight_map=risk_color_map)
    else:
        _add_para("未发现风险条款。")

    # ── 合规检查 ──
    _add_heading("三、合规检查", level=1)
    if state.compliance_findings:
        comp_rows = []
        for c in state.compliance_findings:
            issue = c.issue
            if len(issue) > 80:
                issue = issue[:80] + "..."
            comp_rows.append([
                _clause_label(state, c.clause_id),
                COMPLIANCE_LABELS.get(c.status.value, c.status.value),
                c.regulation,
                issue,
            ])
        comp_color_map = {
            "合规": RGBColor(0x2F, 0x7A, 0x58),
            "不合规": RGBColor(0xB0, 0x32, 0x25),
            "待审核": RGBColor(0xB0, 0x80, 0x20),
        }
        _add_table(["条款", "状态", "法规依据", "问题"], comp_rows, highlight_col=1, highlight_map=comp_color_map)
    else:
        _add_para("未发现合规问题。")

    if state.missing_clauses:
        doc.add_paragraph()
        _add_para("缺失条款：", bold=True)
        for clause in state.missing_clauses:
            _add_para(f"  • {clause}")

    # ── 修改建议 ──
    _add_heading("四、修改建议", level=1)
    if state.suggestions:
        for i, s in enumerate(state.suggestions, 1):
            priority = RISK_LABELS.get(s.priority.value, s.priority.value)
            _add_heading(f"建议 {i}（{priority}）— {_clause_label(state, s.clause_id)}", level=2)
            _add_para(f"原文：{s.original_text}")
            _add_para(f"建议：{s.suggested_text}")
            _add_para(f"原因：{s.reason}")
    else:
        _add_para("无需修改。")

    # ── 人工反馈 ──
    if state.human_feedback is not None:
        _add_heading("五、人工审核记录", level=1)
        fb = state.human_feedback
        _add_para(f"审核人：{fb.reviewer}")
        _add_para(f"审核决定：{fb.decision}")
        if fb.comments:
            _add_para(f"审核意见：{fb.comments}")
        _add_para(f"审核时间：{fb.timestamp.strftime('%Y-%m-%d %H:%M')}")

    # ── 页脚说明 ──
    doc.add_paragraph()
    p = doc.add_paragraph()
    r = p.add_run(
        f"报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "本报告由 AI 法务幕僚（条款拆解官 · 风险猎手 · 合规法官 · 修订顾问）自动生成，仅供法务参考。"
    )
    _set_cjk(r, size=8, color=RGBColor(0x9C, 0xA3, 0xAF))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── 修订版红线导出 ──────────────────────────────────────────

def generate_redline(state: ContractReviewState) -> bytes:
    """生成「修订版（红线对照）」Word 文档。

    由条款与建议重建全文：建议删除的文字以朱色删除线标出，
    建议新增的文字以青绿下划线标出，缺失条款附于卷尾。
    旧版审查的条款/建议均已入库，不依赖原始文本是否留存。
    """
    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    RED = RGBColor(0xB0, 0x32, 0x25)     # 朱砂：删
    GREEN = RGBColor(0x2F, 0x7A, 0x58)   # 青绿：增
    PRIMARY = RGBColor(0x22, 0x69, 0x76)  # 石青：题

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "SimSun"
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "SimSun")

    def _run(p, text: str, *, strike=False, underline=False,
             bold=False, color=None, size=10.5):
        r = p.add_run(text)
        r.font.name = "SimSun"
        r._element.rPr.rFonts.set(qn("w:eastAsia"), "SimSun")
        r.font.size = Pt(size)
        r.bold = bold
        if strike:
            r.font.strike = True
        if underline:
            r.font.underline = True
        if color is not None:
            r.font.color.rgb = color
        return r

    # 卷头
    title = doc.add_paragraph()
    title.alignment = 1
    _run(title, "合同修订版（红线对照）", bold=True, size=20, color=PRIMARY)
    sub = doc.add_paragraph()
    sub.alignment = 1
    _run(sub,
         f"审查立场：{POSITION_LABELS.get(state.position, '中立')}　"
         f"整体结论：{RISK_LABELS.get(state.overall_risk_level.value, state.overall_risk_level.value)}　"
         f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
         size=9)
    note = doc.add_paragraph()
    _run(note, "凡朱色划删者为建议删除之文字，青绿下划线者为建议新增之文字；采择与否，由把关人定夺。", size=9)

    # 建议按条款归组
    by_clause: dict[str, list] = {}
    for s in state.suggestions:
        by_clause.setdefault(s.clause_id, []).append(s)

    for seq, clause in enumerate(state.clauses, start=1):
        h = doc.add_paragraph()
        label = clause.section_number or f"第{seq}条"
        _run(h, f"{label}　{clause.title}", bold=True, size=12, color=PRIMARY)

        items = by_clause.get(clause.id, [])
        if not items:
            p = doc.add_paragraph()
            _run(p, clause.content)
            continue

        # 原文中能定位到的建议做行内红线；定位不到的作条末修订注
        rest = clause.content
        segs: list[tuple[str, str]] = []
        pending = []
        for s in items:
            pos = rest.find(s.original_text) if s.original_text else -1
            if pos >= 0 and s.suggested_text:
                if rest[:pos]:
                    segs.append(("keep", rest[:pos]))
                segs.append(("del", s.original_text))
                segs.append(("ins", s.suggested_text))
                rest = rest[pos + len(s.original_text):]
            else:
                pending.append(s)
        if rest:
            segs.append(("keep", rest))

        p = doc.add_paragraph()
        for kind, text in segs:
            if kind == "del":
                _run(p, text, strike=True, color=RED)
            elif kind == "ins":
                _run(p, text, underline=True, color=GREEN)
            else:
                _run(p, text)

        for s in pending:
            n = doc.add_paragraph()
            _run(n, "修订注：", bold=True, size=9, color=PRIMARY)
            _run(n, s.original_text or "（整条）", strike=True, color=RED, size=9)
            _run(n, " → ", size=9)
            _run(n, s.suggested_text, underline=True, color=GREEN, size=9)
            if s.reason:
                _run(n, f"（因由：{s.reason}）", size=9)

    # 卷尾：建议增设的条款
    new_items = by_clause.get("new", [])
    if new_items or state.missing_clauses:
        h = doc.add_paragraph()
        _run(h, "附　建议增设之条款", bold=True, size=12, color=PRIMARY)
        for s in new_items:
            p = doc.add_paragraph()
            _run(p, s.suggested_text, underline=True, color=GREEN)
            if s.reason:
                _run(p, f"（{s.reason}）", size=9)
        listed = {s.suggested_text for s in new_items}
        for m in state.missing_clauses:
            if m and not any(m in t for t in listed):
                p = doc.add_paragraph()
                _run(p, f"缺少「{m}」相关条款，建议补充。", size=9)

    # 卷尾署名
    doc.add_paragraph()
    p = doc.add_paragraph()
    _run(p,
         f"由 AI 法务幕僚（条款拆解官 · 风险猎手 · 合规法官 · 修订顾问）生成，仅供法务参考。",
         size=8)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
