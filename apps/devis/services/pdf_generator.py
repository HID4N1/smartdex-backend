from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


class DevisPDFGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._build_custom_styles()

    def _build_custom_styles(self):
        self.title_style = ParagraphStyle(
            name="DevisTitle",
            parent=self.styles["Title"],
            fontSize=20,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=12,
            textColor=colors.HexColor("#0F172A"),
        )

        self.section_style = ParagraphStyle(
            name="SectionTitle",
            parent=self.styles["Heading2"],
            fontSize=13,
            leading=16,
            spaceBefore=10,
            spaceAfter=8,
            textColor=colors.HexColor("#0F172A"),
        )

        self.subsection_style = ParagraphStyle(
            name="SubSectionTitle",
            parent=self.styles["Heading3"],
            fontSize=11,
            leading=14,
            spaceBefore=8,
            spaceAfter=6,
            textColor=colors.HexColor("#1E293B"),
        )

        self.normal_style = ParagraphStyle(
            name="NormalCustom",
            parent=self.styles["Normal"],
            fontSize=9.5,
            leading=13,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#334155"),
        )

        self.small_style = ParagraphStyle(
            name="SmallCustom",
            parent=self.styles["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#475569"),
        )

        self.right_style = ParagraphStyle(
            name="RightCustom",
            parent=self.styles["Normal"],
            fontSize=9.5,
            leading=13,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#334155"),
        )

    def _money(self, value: int | float | None) -> str:
        if value is None:
            return "-"
        return f"{int(value):,} MAD".replace(",", " ")

    def _build_items_table(self, items: list[dict]) -> Table:
        data = [
            ["Service", "Description", "Prix min", "Prix max"]
        ]

        for item in items:
            data.append([
                item.get("label", ""),
                item.get("description", ""),
                self._money(item.get("price_min")),
                self._money(item.get("price_max")),
            ])

        table = Table(
            data,
            colWidths=[45 * mm, 78 * mm, 28 * mm, 28 * mm],
            repeatRows=1,
        )

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("LEADING", (0, 0), (-1, -1), 11),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (2, 1), (3, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                colors.white,
                colors.HexColor("#F8FAFC"),
            ]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def _build_totals_table(self, totals: dict) -> Table:
        data = [
            ["Résumé financier", ""],
            ["Inclus min", self._money(totals.get("included_min"))],
            ["Inclus max", self._money(totals.get("included_max"))],
            ["Options min", self._money(totals.get("optional_min"))],
            ["Options max", self._money(totals.get("optional_max"))],
            ["Total global min", self._money(totals.get("grand_total_min"))],
            ["Total global max", self._money(totals.get("grand_total_max"))],
        ]

        table = Table(data, colWidths=[75 * mm, 45 * mm])

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -3), "Helvetica"),
            ("FONTNAME", (0, -2), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                colors.white,
                colors.HexColor("#F8FAFC"),
            ]),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("SPAN", (0, 0), (1, 0)),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def generate(self, context: dict, output_path: str | Path) -> str:
        output_path = str(output_path)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
        )

        story = []

        story.append(Paragraph("DEVIS COMMERCIAL", self.title_style))
        story.append(Spacer(1, 4))

        company_info = (
            "<b>SMARTDEX</b><br/>"
            "Digital Solutions / Web / SaaS / Automation<br/>"
            "Casablanca, Maroc"
        )
        client_info = (
            f"<b>N° Devis :</b> {context.get('devis_number', '-')}"
            f"<br/><b>Date :</b> {context.get('date', '-')}"
            f"<br/><b>Client :</b> {context.get('client_name', '-')}"
            f"<br/><b>Email :</b> {context.get('client_email', '-')}"
            f"<br/><b>Téléphone :</b> {context.get('client_phone', '-')}"
        )

        header_table = Table(
            [[Paragraph(company_info, self.normal_style), Paragraph(client_info, self.right_style)]],
            colWidths=[95 * mm, 75 * mm],
        )
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 12))

        story.append(Paragraph("1. Informations projet", self.section_style))
        story.append(Paragraph(
            f"<b>Type de projet :</b> {context.get('project_type', '-')}",
            self.normal_style
        ))
        if context.get("business_name"):
            story.append(Paragraph(
                f"<b>Entreprise :</b> {context.get('business_name')}",
                self.normal_style
            ))
        if context.get("description"):
            story.append(Paragraph(
                f"<b>Besoin exprimé :</b> {context.get('description')}",
                self.normal_style
            ))
        story.append(Spacer(1, 8))

        estimate = context.get("estimate", {})
        story.append(Paragraph("2. Estimation globale", self.section_style))
        story.append(Paragraph(
            f"<b>Fourchette estimée :</b> "
            f"{self._money(estimate.get('range_min'))} à {self._money(estimate.get('range_max'))}",
            self.normal_style
        ))
        story.append(Paragraph(
            f"<b>Devise :</b> {estimate.get('currency', 'MAD')}",
            self.normal_style
        ))

        recommendation = estimate.get("recommendation")
        if recommendation:
            story.append(Paragraph(
                f"<b>Recommandation :</b> {recommendation}",
                self.normal_style
            ))

        cost_drivers = estimate.get("cost_drivers", [])
        if cost_drivers:
            story.append(Spacer(1, 6))
            story.append(Paragraph("<b>Facteurs de coût :</b>", self.normal_style))
            for driver in cost_drivers:
                story.append(Paragraph(f"• {driver}", self.small_style))

        story.append(Spacer(1, 10))

        story.append(Paragraph("3. Prestations incluses", self.section_style))
        for group in context.get("included_groups", []):
            story.append(Paragraph(group.get("label", "Groupe"), self.subsection_style))
            story.append(self._build_items_table(group.get("items", [])))
            story.append(Spacer(1, 8))

        optional_items = context.get("optional_items", [])
        if optional_items:
            story.append(Paragraph("4. Options complémentaires", self.section_style))
            story.append(self._build_items_table(optional_items))
            story.append(Spacer(1, 10))

        recurring_items = context.get("recurring_items", [])
        if recurring_items:
            story.append(Paragraph("5. Coûts récurrents", self.section_style))
            story.append(self._build_items_table(recurring_items))
            story.append(Spacer(1, 10))

        story.append(Paragraph("6. Totaux", self.section_style))
        story.append(self._build_totals_table(context.get("totals", {})))
        story.append(Spacer(1, 10))

        notes = context.get("notes", [])
        if notes:
            story.append(Paragraph("7. Notes", self.section_style))
            for note in notes:
                story.append(Paragraph(f"• {note}", self.small_style))
            story.append(Spacer(1, 8))

        missing_information = context.get("missing_information", [])
        if missing_information:
            story.append(Paragraph("8. Informations à confirmer", self.section_style))
            for item in missing_information:
                story.append(Paragraph(f"• {item}", self.small_style))
            story.append(Spacer(1, 8))

        story.append(Paragraph(
            "Ce devis reste indicatif et pourra être ajusté après validation complète du périmètre.",
            self.small_style
        ))

        doc.build(story)
        return output_path