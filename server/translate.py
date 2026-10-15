"""Legal translation with guard rails around a local model.

A small model on its own mistranslates legal terms and invents expansions of act names. This module:
  1. protects act names, abbreviations, citations and every number from being rewritten (they are swapped for [[n]] tokens
     before translation and restored afterwards);
  2. gives the model a fixed glossary of legal terms for the target language;
  3. rejects any result that is in the wrong script, contains stray foreign text, or lost or changed a protected item.
If a result fails these checks the caller gets an error, never a wrong translation.
"""
import re

LANGS = {"en": "English", "hi": "Hindi", "mr": "Marathi", "ta": "Tamil", "te": "Telugu", "bn": "Bengali", "gu": "Gujarati", "kn": "Kannada"}

# Languages whose output was read and checked; the others are refused rather than guessed.
SUPPORTED = {"en", "hi"}

SCRIPT = {"hi": r"[ऀ-ॿ]", "mr": r"[ऀ-ॿ]", "bn": r"[ঀ-৿]", "gu": r"[઀-૿]",
          "ta": r"[஀-௿]", "te": r"[ఀ-౿]", "kn": r"[ಀ-೿]"}

# English term -> Hindi legal term (standard usage in Indian courts and statutes).
GLOSSARY_HI = [
    ("anticipatory bail", "अग्रिम जमानत"), ("bail", "जमानत"), ("bond", "बंधपत्र"), ("surety", "जमानतदार"),
    ("accused", "अभियुक्त"), ("complainant", "शिकायतकर्ता"), ("petitioner", "याचिकाकर्ता"), ("respondent", "प्रत्यर्थी"),
    ("appellant", "अपीलार्थी"), ("plaintiff", "वादी"), ("defendant", "प्रतिवादी"), ("witness", "साक्षी"),
    ("first information report", "प्रथम सूचना रिपोर्ट"), ("FIR", "प्रथम सूचना रिपोर्ट (एफआईआर)"), ("charge sheet", "आरोप-पत्र"),
    ("chargesheet", "आरोप-पत्र"), ("police report", "पुलिस रिपोर्ट"), ("court", "न्यायालय"), ("magistrate", "मजिस्ट्रेट"),
    ("judge", "न्यायाधीश"), ("judgment", "निर्णय"), ("order", "आदेश"), ("appeal", "अपील"), ("writ", "रिट"),
    ("affidavit", "शपथ-पत्र"), ("notice", "नोटिस"), ("summons", "समन"), ("warrant", "वारंट"), ("cognizable", "संज्ञेय"),
    ("non-cognizable", "असंज्ञेय"), ("bailable", "जमानतीय"), ("non-bailable", "अजमानतीय"), ("offence", "अपराध"),
    ("imprisonment", "कारावास"), ("life imprisonment", "आजीवन कारावास"), ("fine", "जुर्माना"), ("punishment", "दंड"),
    ("evidence", "साक्ष्य"), ("cheque", "चेक"), ("dishonour", "अनादर"), ("conviction", "दोषसिद्धि"), ("acquittal", "दोषमुक्ति"),
    ("custody", "अभिरक्षा"), ("police custody", "पुलिस अभिरक्षा"), ("judicial custody", "न्यायिक अभिरक्षा"), ("arrest", "गिरफ्तारी"),
    ("trial", "विचारण"), ("investigation", "अन्वेषण"), ("jurisdiction", "क्षेत्राधिकार"), ("section", "धारा"), ("Act", "अधिनियम"),
    ("Code", "संहिता"), ("sub-section", "उप-धारा"), ("agreement", "करार"), ("tenant", "किरायेदार"), ("landlord", "मकान मालिक"),
    ("dishonoured", "अनादृत"), ("arrested", "गिरफ्तार किया गया"), ("registered", "दर्ज"), ("hearing", "सुनवाई"),
    ("power of attorney", "मुख्तारनामा"), ("deponent", "शपथकर्ता"), ("released", "रिहा"), ("furnishing", "प्रस्तुत करने"),
]
GLOSSARY = {"hi": GLOSSARY_HI}

_ACTS = (r"Bharatiya\s+(?:Nyaya|Nagarik\s+Suraksha|Sakshya)\s+(?:Sanhita|Adhiniyam)(?:,?\s*\d{4})?|Indian\s+Penal\s+Code(?:,?\s*\d{4})?|"
         r"Code\s+of\s+(?:Criminal|Civil)\s+Procedure(?:,?\s*\d{4})?|Indian\s+Evidence\s+Act(?:,?\s*\d{4})?|"
         r"Negotiable\s+Instruments\s+Act(?:,?\s*\d{4})?|Constitution\s+of\s+India|"
         r"\bBNSS\b|\bBNS\b|\bBSA\b|\bIPC\b|\bCr\.?\s?P\.?\s?C\.?|\bCPC\b|\bIEA\b|\bNI\s+Act\b|\bN\.I\.\s+Act\b|\bNIA\b")
_CITES = (r"\[\d{4}\]\s*(?:Supp\.?\s*)?\d*\s*S\.?\s?C\.?\s?R\.?\s*\d+|\bAIR\s*(?:\(\d{4}\)\s*|\d{4}\s*)SC\s*\d+|\(\d{4}\)\s*\d+\s*SCC\s*\d+|"
          r"(?!x)x")   # (case names are left to the model; it transliterates them)
_PLACES = r"\b(?:[A-Z][A-Za-z]+\s+){1,3}(?:Police\s+Station|High\s+Court|District\s+Court|Sessions\s+Court|Tribunal|Bench)\b"
_NUMS = r"\d[\d,./-]*\d[A-Z]?(?:\([A-Za-z0-9]+\))*|\d[A-Z]?(?:\([A-Za-z0-9]+\))*"
PROTECT = re.compile("(" + "|".join([_CITES, _PLACES, _ACTS, _NUMS]) + ")")
TOKEN = re.compile(r"\[\[(\d+)\]\]")


class TranslateError(Exception):
    pass


def protect(text: str):
    """Swap protected items for [[n]] tokens. Returns (text, [original items])."""
    items = []

    def sub(m):
        items.append(m.group(0))
        return f"[[{len(items)}]]"
    return PROTECT.sub(sub, text), items


def restore(text: str, items) -> str:
    return TOKEN.sub(lambda m: items[int(m.group(1)) - 1] if 0 < int(m.group(1)) <= len(items) else m.group(0), text)


def glossary_for(src: str, dst: str, text: str):
    """Fixed term pairs to give the model. English to Hindi: English terms found in the text. Hindi to English: Hindi terms found
    in the text (the longest match wins, so "अजमानतीय" non-bailable is never read as the shorter "जमानत" bail inside it)."""
    out = []
    if dst in GLOSSARY:
        low = text.lower()
        hit = [(en, tr) for en, tr in GLOSSARY[dst] if re.search(r"(?<![a-z])" + re.escape(en.lower()) + r"(?![a-z])", low)]
        names = [en.lower() for en, _ in hit]
        out = [f"{en} = {tr}" for en, tr in hit if not any(en.lower() != o and en.lower() in o for o in names)]   # "bailable" is dropped when "non-bailable" matched
    elif src in GLOSSARY:
        found = [(tr, en) for en, tr in GLOSSARY[src] if tr.split(" (")[0] in text]
        terms = {tr.split(" (")[0]: en for tr, en in found}
        keep = [t for t in terms if not any(t != u and t in u for u in terms)]
        out = [f"{t} = {terms[t]}" for t in sorted(keep, key=len, reverse=True)]
    return out[:30]


def build_messages(src: str, dst: str, protected: str, n_items: int, extra: str = ""):
    gloss = glossary_for(src, dst, protected)
    system = (f"You are a careful legal translator from {LANGS[src]} to {LANGS[dst]} for Indian courts. "
              "Translate meaning exactly. Do not add, omit, explain or summarise anything. "
              + ("Tokens written like [[1]], [[2]] stand for act names, citations and numbers: copy every token into the translation unchanged, "
                 "in the right place, exactly once. Never expand or invent the meaning of a token or of any abbreviation. " if n_items else
                 "Never expand or invent the meaning of any abbreviation. ")
              + "Output only the translation, in the " + LANGS[dst] + " script, with no commentary." + extra)
    if gloss:
        system += "\n\nUse these standard legal terms:\n" + "\n".join(gloss)
    return [{"role": "system", "content": system}, {"role": "user", "content": protected}]


def validate(dst: str, out: str, n_items: int):
    """None if the translation passes every check, otherwise the reason it was rejected."""
    if not out.strip():
        return "empty"
    if re.search(r"[　-鿿가-힯]", out):
        return "foreign script"
    found = [int(x) for x in TOKEN.findall(out)]
    if sorted(found) != list(range(1, n_items + 1)):
        return "a protected item was lost or changed"
    plain = TOKEN.sub("", out)
    letters = [c for c in plain if c.isalpha()]
    if letters:
        if dst in SCRIPT:
            if sum(bool(re.match(SCRIPT[dst], c)) for c in letters) / len(letters) < 0.6:
                return "wrong script"
        elif sum(c.isascii() for c in letters) / len(letters) < 0.85:
            return "wrong script"
    return None


_ABBREV = {"No.", "Nos.", "Rs.", "Mr.", "Mrs.", "Ms.", "Dr.", "v.", "vs.", "Sec.", "Art.", "Cr.", "Ltd.", "Pvt.", "Hon.", "Smt.", "Shri."}


def split_sentences(text: str):
    """Split into sentences (English full stops, Hindi danda), without cutting after common abbreviations like 'No.' or 'Rs.'."""
    raw = re.split(r"(?<=[.!?\u0964])\s+(?=[A-Z0-9\"'\u0900-\u097F(])", text.strip())
    out = []
    for part in raw:
        if out and out[-1].split()[-1] in _ABBREV:
            out[-1] += " " + part
        else:
            out.append(part)
    return [x for x in (p.strip() for p in out) if x]
