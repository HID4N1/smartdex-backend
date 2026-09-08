SYSTEM_PROMPT = """
You are SmartDex's requirement extraction assistant.

Rules:
- Return JSON only.
- Do not calculate price.
- Do not invent client information.
- Use null for unknown scalar values.
- Use empty lists when no items are present.
- Extract only what is supported by the user request.
- Extract project requirements only. Do not extract, request, or repeat client identity/contact information.
- Extract: project type, requested features, budget, timeline, preferred language, complexity hint, missing information, and a confidence score between 0 and 1.
""".strip()


def build_requirement_prompt(project_context: dict | str) -> str:
    if isinstance(project_context, str):
        project_context = {"description": project_context}

    return (
        f"{SYSTEM_PROMPT}\n\n"
        "AI-safe project context from the backend:\n"
        f"description={project_context.get('description') or 'null'}\n"
        f"project_type={project_context.get('project_type') or 'unknown'}\n"
        f"features={project_context.get('features') or []}\n"
        f"budget_range={project_context.get('budget_range') or 'unknown'}\n"
        f"timeline={project_context.get('timeline') or 'unknown'}\n"
        f"preferred_language={project_context.get('preferred_language') or 'unknown'}\n"
        f"extra_hints={project_context.get('extra_hints') or {}}\n\n"
        "Return a JSON object with the fields:\n"
        "project_type, detected_features, budget_range, timeline, preferred_language, complexity_hint, missing_information, confidence_score"
    )
