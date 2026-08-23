cat > src/swahili_glossary.py << 'PYEOF'
"""
swahili_glossary.py -- system-prompt fragment for the Layer 3 LLM
fallback (Qwen2.5-3B). Only reached when the lookup table and regex
fast-path both fail to cover the input.
"""

GLOSSARY = """
Products:
- sukari = sugar
- mchele = rice
- sabuni = soap
- mafuta = oil
- kitabu = book
- mandazi = donut
- kikombe = cup
- sahani = plate
- majani ya chai = tea leaves
- kahawa = coffee

Unit words:
- kilo / kg = kilogram
- gramu / g = gram
- kilo nusu / nusu kilo = half a kilogram
- kilo robo / robo ya kilo = quarter of a kilogram

Disambiguation notes (words that mean different things by context):
- "mafuta" usually means cooking oil, but can also mean cream/lotion
  depending on context -- check surrounding words (kupika = cooking,
  ngozi/mwili = skin/body) before assuming which product is meant.
- "maziwa" is the product milk, but in some urban contexts "maziwa",
  "fulusi", or "doe" can be slang for money instead. This is a real
  conflict with the "maziwa" product entry -- if a sentence about
  "maziwa" doesn't fit a milk-purchase context, consider it may be
  referring to money instead, not the dairy product.
- "nijenge" literally means "build me," but is commonly used
  colloquially to mean "give me" / "hook me up."
"""

FEW_SHOT_EXAMPLES = [
    {
        "input": "nimenunua sukari kidogo",
        "expected_tool": "record_sale",
        "expected_params": {"product": "sukari"},
    },
    {
        "input": "je mchele umebaki kiasi gani",
        "expected_tool": "check_inventory",
        "expected_params": {"product": "mchele"},
    },
    {
        "input": "nimenunua mayai mbili",
        "expected_tool": "record_sale",
        "expected_params": {"product": "mayai"},
    },
    {
        "input": "uko na sabuni ya kuoga",
        "expected_tool": "check_inventory",
        "expected_params": {"product": "sabuni"},
    },
    {
        "input": "uko na mafuta ya kupika",
        "expected_tool": "check_inventory",
        "expected_params": {"product": "mafuta ya kupika"},
    },
]

REGISTER_GUARDRAIL = """
Speak in polite, standard coastal Swahili (Kiswahili cha Sanifu).
Match the user's register if they use informal or street phrasing first.
"""


def build_system_prompt() -> str:
    examples_text = "\n".join(
        f"Input: {ex['input']}\n"
        f"Expected tool: {ex['expected_tool']}\n"
        f"Expected params: {ex['expected_params']}"
        for ex in FEW_SHOT_EXAMPLES
    )
    return f"{GLOSSARY}\n\n{REGISTER_GUARDRAIL}\n\nExamples:\n{examples_text}"


if __name__ == "__main__":
    print(build_system_prompt())
PYEOF
