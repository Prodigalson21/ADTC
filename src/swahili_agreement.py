# src/swahili_agreement.py
"""Deterministic Swahili noun-class agreement for POS commands.
Layer 1 of 3: Zero LLM involvement for known vocabulary.

This pass fixes two real bugs that survived the previous version despite
its changelog claiming they were fixed:
- "nipe chumvi kg 1" (product, unit, number order) failed to match at all.
- "nipe 0.5 g ya pilipili" matched, but silently captured the particle
  "ya" as the product instead of "pilipili" -- a false success that would
  have handed agent.py a record_sale call for a nonexistent product.

Fix: the single ambiguous NIPE pattern (with optional unit fields in two
places) is replaced with three explicit patterns, one per real word order,
each with unambiguous group positions. Verified against all previous test
phrases plus explicit product-correctness checks on both bug cases -- see
the bottom of this file. 37/37 = 100% on the combined test set.

REMAINING TODOs: noun-class entries below marked TODO are still unverified
guesses. Confirm them yourself before trusting this file as ground truth.
"""

import re

NOUN_CLASSES = {
    "sukari": {"class": 9, "prefix": "i", "agreement": "ya"},        # sugar
    "mafuta": {"class": 6, "prefix": "ya", "agreement": "ya"},       # oil
    "mchele": {"class": 3, "prefix": "u", "agreement": "wa"},        # rice
    "unga": {"class": 11, "prefix": "u", "agreement": "wa"},         # flour
    "mayai": {"class": 6, "prefix": "ya", "agreement": "ya"},        # eggs
    "mboga": {"class": 9, "prefix": "i", "agreement": "ya"},         # vegetables
    "matunda": {"class": 6, "prefix": "ya", "agreement": "ya"},      # fruits
    "nyama": {"class": 9, "prefix": "i", "agreement": "ya"},         # meat
    "samaki": {"class": 9, "prefix": "i", "agreement": "ya"},        # fish
    "mkate": {"class": 3, "prefix": "u", "agreement": "wa"},         # bread
    "maji": {"class": 6, "prefix": "ya", "agreement": "ya"},         # water
    "chai": {"class": 9, "prefix": "i", "agreement": "ya"},          # tea
    "kahawa": {"class": 9, "prefix": "i", "agreement": "ya"},        # coffee
    "maziwa": {"class": 6, "prefix": "ya", "agreement": "ya"},       # milk
    "nafaka": {"class": 9, "prefix": "i", "agreement": "ya"},        # cereal
    "dawa": {"class": 9, "prefix": "i", "agreement": "ya"},          # medicine
    "sabuni": {"class": 9, "prefix": "i", "agreement": "ya"},        # soap
    "chumvi": {"class": 9, "prefix": "i", "agreement": "ya"},        # salt  -- TODO: verify
    "pilipili": {"class": 9, "prefix": "i", "agreement": "ya"},      # pepper/chili  -- TODO: verify
    "kitunguu": {"class": 7, "prefix": "ki", "agreement": "cha"},    # onion  -- TODO: verify
    "viazi": {"class": 8, "prefix": "vi", "agreement": "vya"},       # potatoes  -- TODO: verify
    "ndizi": {"class": 10, "prefix": "zi", "agreement": "za"},       # bananas  -- TODO: verify
    "nyanya": {"class": 9, "prefix": "i", "agreement": "ya"},        # tomatoes  -- TODO: verify
    "embe": {"class": 9, "prefix": "i", "agreement": "ya"},          # mango  -- TODO: verify
    "nanasi": {"class": 9, "prefix": "i", "agreement": "ya"},        # pineapple  -- TODO: verify
    "soda": {"class": 9, "prefix": "i", "agreement": "ya"},          # soda  -- TODO: verify
}

_ANY_PARTICLE = r"(?:ya|wa|cha|vya|za|la)"
_UNIT = r"(?:kg|g|gram|gramu|kilo)"

FAST_PATHS = [
    (rf"uza\s+(\d+(?:\.\d+)?)\s*({_UNIT})\s+{_ANY_PARTICLE}\s+(\w+)",
     "record_sale", ["quantity", "unit", "product"]),

    (rf"baki\s+ngapi\s+{_ANY_PARTICLE}\s+(\w+)",
     "check_inventory", ["product"]),

    (r"rudisha\s+(\w+)",
     "resolve_refund_by_product", ["product"]),

    (r"ongezea\s+(\w+)",
     "restock_alert", ["product"]),

    (r"punguzo\s+la\s+(\d+)%?\s+(?:kwa\s+)?(\w+)",
     "apply_discount", ["percent", "product"]),

    (rf"bei\s+gani\s+{_ANY_PARTICLE}\s+(\w+)",
     "check_inventory", ["product"]),

    # NIPE A1: product, then UNIT, then number -- "nipe chumvi kg 1"
    (rf"nipe\s+(\w+)\s+({_UNIT})\s+(\d+(?:\.\d+)?)",
     "record_sale", ["product", "unit", "quantity"]),

    # NIPE A2: product, then number, then optional unit -- "nipe sukari 2 kg"
    (rf"nipe\s+(\w+)\s+(\d+(?:\.\d+)?)\s*({_UNIT})?",
     "record_sale", ["product", "quantity", "unit"]),

    # NIPE B: number, optional unit, optional particle, then product
    # -- "nipe 2 kg sukari" / "nipe 0.5 g ya pilipili" / "nipe 2 sukari"
    (rf"nipe\s+(\d+(?:\.\d+)?)\s*({_UNIT})?\s*(?:{_ANY_PARTICLE}\s+)?(\w+)",
     "record_sale", ["quantity", "unit", "product"]),
]


def is_covered(text: str) -> tuple[bool, dict]:
    """Only FAST_PATHS regex matches count as covered. A sentence merely
    containing a known noun, with no matching action pattern, always
    falls through to Layer 3 (the LLM)."""
    text = text.lower().strip()

    for pattern, action, params in FAST_PATHS:
        match = re.search(pattern, text)
        if match:
            return True, {
                "layer": "regex",
                "action": action,
                "parameters": dict(zip(params, match.groups()))
            }

    return False, {"layer": "none"}


def noun_class_for(product: str):
    """For RESPONSE generation only (Swahili agreement), not request matching."""
    return NOUN_CLASSES.get(product.lower())


if __name__ == "__main__":
    should_match = [
        "uza 2.5 kg ya sukari", "uza 1 kg wa mchele", "uza 0.5 g ya pilipili",
        "uza 1 gramu ya chumvi", "uza 2 kg cha kitunguu", "uza 3 kg vya viazi",
        "uza 1 kg za ndizi",
        "baki ngapi ya mafuta", "baki ngapi wa mkate", "bei gani cha kitunguu",
        "rudisha mayai", "rudisha dawa", "ongezea unga", "ongezea mkate",
        "punguzo la 10% kwa sukari", "punguzo la 5 kwa mkate",
        "punguzo la 15% kwa maziwa",
        "nipe chumvi kg 1", "nipe sukari 2 kg", "nipe mchele 1 kilo",
        "nipe 2 kg sukari", "nipe 0.5 g ya pilipili", "nipe 2 sukari",
    ]

    should_fallthrough = [
        "nataka kununua mayai", "habari za asubuhi", "asante kwa huduma",
        "nimechoka sana leo", "unazo nafaka ngapi", "nipe tano za sukari",
        "tuma bidhaa hii kwa jirani", "sukari ni nzuri", "tafadhali nisaidie",
        "mchele upo kweli", "bei imepanda sana", "nina njaa sasa",
        "nipe soda mbili", "vipi, mambo",
    ]

    match_ok = sum(1 for p in should_match if is_covered(p)[0])
    fall_ok = sum(1 for p in should_fallthrough if not is_covered(p)[0])
    total = len(should_match) + len(should_fallthrough)
    print(f"{match_ok + fall_ok}/{total} = {(match_ok+fall_ok)/total*100:.0f}% "
          f"(matched {match_ok}/{len(should_match)}, ignored {fall_ok}/{len(should_fallthrough)})")

    for phrase, expected_product in [("nipe chumvi kg 1", "chumvi"), ("nipe 0.5 g ya pilipili", "pilipili")]:
        handled, result = is_covered(phrase)
        got = result.get("parameters", {}).get("product") if handled else None
        assert got == expected_product, f"REGRESSION: '{phrase}' -> product='{got}', expected '{expected_product}'"
    print("Both regression checks passed.")