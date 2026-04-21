from datetime import datetime


class PDFContextBuilder:
    @staticmethod
    def build(devis_request, payload: dict) -> dict:
        estimate = payload.get("estimate", {})
        quote = payload.get("quote", {})
        totals = quote.get("totals", {})

        created_at = getattr(devis_request, "created_at", None)
        if created_at:
            date_str = created_at.strftime("%d/%m/%Y")
        else:
            date_str = datetime.now().strftime("%d/%m/%Y")

        return {
            "devis_number": f"DV-{devis_request.id:04d}",
            "date": date_str,
            "client_name": getattr(devis_request, "client_name", "") or "Client",
            "client_email": getattr(devis_request, "client_email", "") or "",
            "client_phone": getattr(devis_request, "client_phone", "") or "",
            "business_name": getattr(devis_request, "business_name", "") or "",
            "project_type": getattr(devis_request, "project_type", "") or "",
            "description": getattr(devis_request, "description", "") or "",
            "estimate": estimate,
            "included_groups": quote.get("included_groups", []),
            "optional_items": quote.get("optional_items", []),
            "recurring_items": quote.get("recurring_items", []),
            "totals": totals,
            "notes": quote.get("notes", []),
            "missing_information": quote.get("missing_information", []),
        }