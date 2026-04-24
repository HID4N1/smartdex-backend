SYSTEM_PROMPT = """
You are writing polished commercial wording for SmartDex quotes.

Rules:
- Do not change calculated prices.
- Do not add features that are not in the selected plan.
- Do not invent discounts.
- Use a professional SmartDex tone.
- Keep wording concise and client-ready.
""".strip()


def build_quote_prompt(*, project_type: str, included_groups: list[dict], totals: dict, recommendation: str, preferred_language: str | None = None) -> str:
    language = preferred_language or "French"
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Write the response in {language}.\n"
        f"Project type: {project_type or 'unknown'}\n"
        f"Included groups: {included_groups}\n"
        f"Totals: {totals}\n"
        f"Recommendation: {recommendation}\n\n"
        "Return JSON only with the fields:\n"
        "title, summary, recommendation, commercial_notes, next_steps"
    )
