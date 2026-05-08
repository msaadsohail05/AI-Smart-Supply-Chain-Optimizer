import json
import os
import re


def parse_input(data, use_llm=True, llm_config=None):
    if data is None:
        return {}

    if isinstance(data, dict):
        text = str(data.get("text", ""))
    else:
        text = str(data)

    cleaned = " ".join(text.strip().split())

    if use_llm:
        try:
            return _extract_with_openai(cleaned, llm_config or {})
        except Exception:
            pass

    return _regex_parse(cleaned)


def _extract_with_openai(text, llm_config):
    api_key = llm_config.get("api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    model = llm_config.get("model") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    system_prompt = (
        "You extract structured delivery constraints from user text. "
        "Return a JSON object with keys: source, destinations, deadline, budget, "
        "objective, packages, vehicle_type, avoid. Use null for missing fields."
    )
    user_prompt = (
        "Extract delivery constraints from this input. "
        "If destinations are in a list, return them as an array. "
        "Deadline should be in 24h HH:MM format when possible. "
        f"Input: {text}"
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content or "{}"
    payload = _safe_json_loads(content)
    return _normalize_extraction(payload, text)


def _safe_json_loads(value):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _normalize_extraction(payload, text):
    if not isinstance(payload, dict):
        payload = {}

    normalized = {
        "source": payload.get("source"),
        "destinations": payload.get("destinations") or [],
        "deadline": payload.get("deadline"),
        "budget": payload.get("budget"),
        "objective": payload.get("objective"),
        "packages": payload.get("packages"),
        "vehicle_type": payload.get("vehicle_type"),
        "avoid": payload.get("avoid"),
    }

    if not isinstance(normalized["destinations"], list):
        normalized["destinations"] = [str(normalized["destinations"])]

    objective = normalized.get("objective")
    if isinstance(objective, str):
        lowered = objective.lower()
        if "fast" in lowered or "time" in lowered:
            normalized["objective"] = "min_time"
        elif "cheap" in lowered or "cost" in lowered:
            normalized["objective"] = "min_cost"
        elif "balance" in lowered:
            normalized["objective"] = "balanced"

    for numeric_key in ("budget", "packages"):
        value = normalized.get(numeric_key)
        if isinstance(value, str):
            cleaned = "".join(ch for ch in value if ch.isdigit())
            if cleaned:
                normalized[numeric_key] = int(cleaned)

    fallback = _regex_parse(text)
    for key, value in normalized.items():
        if value in (None, "", [], {}):
            normalized[key] = fallback.get(key)

    return normalized


def _regex_parse(text):
    lower = text.lower()

    source = _extract_source(text)
    destinations = _extract_destinations(text)
    deadline = _extract_deadline(text)
    budget = _extract_budget(text)
    objective = _extract_objective(lower)
    packages = _extract_packages(text)
    vehicle_type = _extract_vehicle_type(lower)
    avoid = _extract_avoid(lower)

    return {
        "source": source,
        "destinations": destinations,
        "deadline": deadline,
        "budget": budget,
        "objective": objective,
        "packages": packages,
        "vehicle_type": vehicle_type,
        "avoid": avoid,
    }


def _extract_source(text):
    match = re.search(r"from\s+(.*?)(?:\s+to\s+|\s+deliver\b|$)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip(" ,.")
    return None


def _extract_destinations(text):
    match = re.search(r"to\s+(.*?)(?:\s+before\b|\s+by\b|\s+deadline\b|\s+under\b|\s+budget\b|\s+cost\b|\s+use\b|\s+avoid\b|$)", text, re.IGNORECASE)
    if not match:
        return []

    raw = match.group(1).strip(" .")
    raw = raw.replace(" and ", ", ")
    parts = [part.strip(" ,.") for part in raw.split(",")]
    return [part for part in parts if part]


def _extract_deadline(text):
    # Handles "before 5 PM", "by 17:00", "deadline 18:30".
    time_match = re.search(r"(?:before|by|deadline)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text, re.IGNORECASE)
    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2) or 0)
    meridiem = (time_match.group(3) or "").lower()

    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0

    return f"{hour:02d}:{minute:02d}"


def _extract_budget(text):
    match = re.search(r"(?:under|below|budget|cost)\s*(?:of\s*)?(\d+[\d,]*)", text, re.IGNORECASE)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def _extract_objective(lower_text):
    if "fastest" in lower_text or "minimize time" in lower_text or "minimise time" in lower_text:
        return "min_time"
    if "cheapest" in lower_text or "minimize cost" in lower_text or "minimise cost" in lower_text:
        return "min_cost"
    if "balanced" in lower_text or "balance" in lower_text:
        return "balanced"
    return None


def _extract_packages(text):
    match = re.search(r"(\d+)\s+(?:packages|parcels|deliveries|items)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _extract_vehicle_type(lower_text):
    if "bike" in lower_text or "bikes" in lower_text:
        return "bike"
    if "truck" in lower_text or "trucks" in lower_text:
        return "truck"
    if "van" in lower_text or "vans" in lower_text:
        return "van"
    return None


def _extract_avoid(lower_text):
    if "avoid" in lower_text and "traffic" in lower_text:
        return "high_traffic_zones"
    return None
