import json
import os


def parse_input(data, use_llm=True, llm_config=None):
	if data is None:
		return {}

	if isinstance(data, dict):
		text = str(data.get("text", ""))
	else:
		text = str(data)

	cleaned = " ".join(text.strip().split())

	if not use_llm:
		raise ValueError("LLM mode is required. Regex fallback removed.")

	return _extract_with_llm(cleaned, llm_config or {})


def _extract_with_llm(text, llm_config):
	print("\nLLM FUNCTION CALLED")

	api_key = llm_config.get("api_key") or os.getenv("GROQ_API_KEY")
	if not api_key:
		raise ValueError("GROQ_API_KEY is not set")

	model = llm_config.get("model") or os.getenv(
		"GROQ_MODEL", "llama-3.3-70b-versatile"
	)

	from openai import OpenAI

	client = OpenAI(
		api_key=api_key,
		base_url="https://api.groq.com/openai/v1"
	)

	system_prompt = (
		"You are a strict logistics data extraction engine. "
		"Your job is to extract ALL structured fields from user input. "
		"Return ONLY valid JSON with these keys: "
		"source, destinations, deadline, budget, objective, "
		"packages, vehicle_type, avoid, constraints. "
		"STRICT RULES: "
		"- NEVER omit numeric values (if mentioned, extract them exactly) "
		"- ALWAYS extract package counts if mentioned (e.g., '2 packages') "
		"- constraints MUST include ANY descriptive logistics information such as: "
		"fragile goods, medical supplies, temperature-sensitive cargo, refrigerated transport, urgency, road restrictions "
		"- Do NOT add 'partial load splitting' unless the user explicitly mentions it "
		"- If a field is not present, use null (NOT empty string, NOT missing key) "
		"- destinations MUST always be a list "
		"- constraints MUST always be a list (even empty) "
	)

	user_prompt = f"""
	Extract ALL logistics information from this text:

	{text}

	Make sure to:
	- extract package count if present
	- extract all constraints (fragile, medical, temperature-sensitive, urgency)
	- extract transport type if mentioned

	Return ONLY valid JSON.
	"""

	response = client.chat.completions.create(
		model=model,
		messages=[
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_prompt},
		],
		temperature=0
	)

	content = response.choices[0].message.content
	print("LLM RAW RESPONSE:", content)

	return _safe_json_loads(content)


def _safe_json_loads(value):
	if value is None:
		raise ValueError("Empty response from LLM")

	cleaned = _extract_json_string(str(value))
	if not cleaned:
		raise ValueError(f"Invalid JSON returned by LLM:\n{value}")

	try:
		return json.loads(cleaned)
	except json.JSONDecodeError:
		raise ValueError(f"Invalid JSON returned by LLM:\n{value}")


def _extract_json_string(value):
	text = value.strip()
	if not text:
		return ""

	if text.startswith("```"):
		lines = text.splitlines()
		if lines and lines[0].startswith("```"):
			lines = lines[1:]
		if lines and lines[-1].startswith("```"):
			lines = lines[:-1]
		text = "\n".join(lines).strip()

	if text.startswith("{") or text.startswith("["):
		return text

	obj_start = text.find("{")
	obj_end = text.rfind("}")
	if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
		return text[obj_start:obj_end + 1].strip()

	arr_start = text.find("[")
	arr_end = text.rfind("]")
	if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
		return text[arr_start:arr_end + 1].strip()

	return ""
