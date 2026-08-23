"""
lookup_coverage_probe.py -- Day 5 validation: re-run the Swahili
fast-path coverage test against a bigger, harder phrasing set than
Day 1's original 7-sentence check.
"""
import sys
sys.path.insert(0, ".")
from src.swahili_agreement import is_covered

COVERED_PHRASES = [
    "uza 2.5 kg ya sukari", "uza 1 kg wa mchele", "uza 0.5 g ya pilipili",
    "uza 1 gramu ya chumvi", "uza 2 kg cha kitunguu", "uza 3 kg vya viazi",
    "uza 1 kg za ndizi", "uza 5 kg ya unga", "uza 2 kg ya mafuta",
    "baki ngapi ya mafuta", "baki ngapi wa mkate", "baki ngapi ya sukari",
    "baki ngapi ya chai", "baki ngapi ya kahawa",
    "bei gani cha kitunguu", "bei gani ya nyama", "bei gani ya samaki",
    "bei gani ya maziwa", "bei gani ya nafaka",
    "rudisha mayai", "rudisha dawa", "rudisha sabuni", "rudisha soda",
    "ongezea unga", "ongezea mkate", "ongezea maji", "ongezea embe",
    "punguzo la 10% kwa sukari", "punguzo la 5 kwa mkate",
    "punguzo la 15% kwa maziwa", "punguzo la 20% kwa nyanya",
    "nipe chumvi kg 1", "nipe sukari 2 kg", "nipe mchele 1 kilo",
    "nipe 2 kg sukari", "nipe 0.5 g ya pilipili", "nipe 2 sukari",
]

NOT_COVERED_PHRASES = [
    "nataka kununua mayai", "habari za asubuhi", "asante kwa huduma",
    "nimechoka sana leo", "unazo nafaka ngapi", "nipe tano za sukari",
    "tuma bidhaa hii kwa jirani", "sukari ni nzuri", "tafadhali nisaidie",
    "mchele upo kweli", "bei imepanda sana", "nina njaa sasa",
    "nipe soda mbili", "vipi, mambo", "duka linafunguliwa saa ngapi",
    "unauza wapi", "hii ni bidhaa mpya", "sina pesa ya kutosha",
]

if __name__ == "__main__":
    print("=== Day 5: expanded lookup/fast-path coverage probe ===\n")
    covered_ok = sum(1 for p in COVERED_PHRASES if is_covered(p)[0])
    not_covered_ok = sum(1 for p in NOT_COVERED_PHRASES if not is_covered(p)[0])

    total = len(COVERED_PHRASES) + len(NOT_COVERED_PHRASES)
    correct = covered_ok + not_covered_ok

    print(f"Real transactions correctly matched: {covered_ok}/{len(COVERED_PHRASES)}")
    print(f"Non-actions correctly NOT matched:    {not_covered_ok}/{len(NOT_COVERED_PHRASES)}")
    print(f"\nOverall correctness: {correct}/{total} = {correct/total*100:.1f}%")
    print(f"Fast-path bypass rate on real transactions: {covered_ok/len(COVERED_PHRASES)*100:.1f}%")

    if covered_ok < len(COVERED_PHRASES):
        print("\n--- Failures worth investigating: ---")
        for p in COVERED_PHRASES:
            handled, _ = is_covered(p)
            if not handled:
                print(f"  MISSED: '{p}'")
    if not_covered_ok < len(NOT_COVERED_PHRASES):
        print("\n--- False positives worth investigating: ---")
        for p in NOT_COVERED_PHRASES:
            handled, result = is_covered(p)
            if handled:
                print(f"  FALSE MATCH: '{p}' -> {result}")
