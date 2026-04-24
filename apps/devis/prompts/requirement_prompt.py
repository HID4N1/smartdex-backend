SYSTEM_PROMPT = """
You are SmartDex's requirement extraction assistant.

Rules:
- Return JSON only.
- Do not calculate price.
- Do not invent client information.
- Use null for unknown scalar values.
- Use empty lists when no items are present.
- Extract only what is supported by the user request.
- Extract: project type, requested features, budget, timeline, contact info, preferred language, complexity hint, missing information, and a confidence score between 0 and 1.
""".strip()


def build_requirement_prompt(user_message: str, client_info: dict | None = None) -> str:
    client_info = client_info or {}
    return (
        f"{SYSTEM_PROMPT}\n\n"
        "User request:\n"
        f"{user_message.strip()}\n\n"
        "Known client info from the backend (do not invent missing values):\n"
        f"name={client_info.get('name') or 'null'}\n"
        f"email={client_info.get('email') or 'null'}\n"
        f"phone={client_info.get('phone') or 'null'}\n\n"
        "Return a JSON object with the fields:\n"
        "project_type, detected_features, budget_range, timeline, client_name, client_email, client_phone, preferred_language, complexity_hint, missing_information, confidence_score"
    )
