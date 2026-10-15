"""Standard Indian drafting templates (affidavits, notices, agreements) with fill-in fields.

Each template is fixed text with {{field}} placeholders, so drafts never depend on what a language model remembers.
Unfilled fields stay visible as [BRACKETED CAPITALS] for the user to complete.

Body mini-format (one item per line, blank line between paragraphs):
    # TITLE            centred heading
    ## Heading         sub-heading
    @ text             auto-numbered paragraph (1., 2., ...)
    ?key text          line printed only if field `key` is filled (works with @ too: "?key @ text")
    !key text          line printed only if field `key` is empty
    {{key}}            field value; [LABEL] if empty

These are general starting points, not legal advice. Stamp duty, registration and format rules differ by State.
"""
import html
import re

DISCLAIMER = ("General template, not legal advice. Check the facts, stamp-paper value and registration rules for your State, "
              "and have a lawyer review it before use.")

STAMP = "Print on non-judicial stamp paper of the value required in your State."
OATH = "Sign in front of a Notary Public or Oath Commissioner (Oaths Act, 1969 allows affidavits to be sworn before authorised officers)."


def F(key, label, hint="", kind="text", required=True, choices=None):
    d = {"key": key, "label": label, "hint": hint, "kind": kind, "required": required}
    if choices:
        d["choices"] = choices
    return d


REL = ["son of", "daughter of", "wife of", "husband of"]

VERIFY = """## VERIFICATION

Verified at {{place}} on this {{date}} that the contents of the above affidavit are true and correct to the best of my knowledge and belief, that no part of it is false, and that nothing material has been concealed therefrom.

DEPONENT"""

TEMPLATES = [
    {
        "id": "affidavit_residence", "category": "Affidavits", "title": "Affidavit: residence / address proof",
        "description": "States where you live and since when. Used for school admission, passport, bank, gas connection and similar.",
        "fields": [F("name", "Your full name"), F("relation", "Relation", kind="choice", choices=REL), F("relative_name", "Father's / mother's / spouse's name"),
                   F("age", "Age (years)", kind="number"), F("address", "Present residential address", kind="textarea"),
                   F("since", "Living there since (date or year)"), F("ownership", "Ownership of the premises", kind="choice",
                                                                        choices=["owned by me", "taken on rent by me", "owned by my parent or relative, with whom I reside"]),
                   F("previous_address", "Previous address (optional)", kind="textarea", required=False),
                   F("purpose", "Purpose of the affidavit"), F("documents", "Documents attached (optional)", required=False),
                   F("place", "Place of signing"), F("date", "Date of signing")],
        "notes": [STAMP, OATH, "Attach a copy of a document that shows the address (electricity bill, rent agreement, Aadhaar)."],
        "body": """# AFFIDAVIT

I, {{name}}, {{relation}} {{relative_name}}, aged about {{age}} years, resident of {{address}}, do hereby solemnly affirm and state on oath as under:

@ That I am a citizen of India and the deponent of this affidavit, and I am competent to swear it.

@ That I am presently residing at {{address}} and have been residing there continuously since {{since}}.

@ That the said premises are {{ownership}}.

?previous_address @ That before shifting to the above address I resided at {{previous_address}}.

@ That this affidavit is being made for the purpose of {{purpose}}.

?documents @ That I have attached copies of {{documents}} in support of my residence at the above address.

""" + VERIFY},

    {
        "id": "affidavit_general", "category": "Affidavits", "title": "Affidavit: general (statement of facts)",
        "description": "A plain affidavit for stating facts on oath, to be filed with an authority, court or institution.",
        "fields": [F("name", "Your full name"), F("relation", "Relation", kind="choice", choices=REL), F("relative_name", "Father's / mother's / spouse's name"),
                   F("age", "Age (years)", kind="number"), F("address", "Your address", kind="textarea"),
                   F("facts", "The facts you are stating, one per line", kind="textarea"), F("purpose", "Purpose of the affidavit"),
                   F("place", "Place of signing"), F("date", "Date of signing")],
        "notes": [STAMP, OATH, "Each fact should be something you know yourself. Mark anything you only believe as 'on information and belief' and say from whom."],
        "body": """# AFFIDAVIT

I, {{name}}, {{relation}} {{relative_name}}, aged about {{age}} years, resident of {{address}}, do hereby solemnly affirm and state on oath as under:

@ That I am the deponent of this affidavit and am competent to swear it.

{{facts:numbered}}

@ That this affidavit is made for the purpose of {{purpose}}.

""" + VERIFY},

    {
        "id": "affidavit_name_change", "category": "Affidavits", "title": "Affidavit: change of name",
        "description": "Declares a change of name, or that two names are of one person. Usually followed by a newspaper notice and a Gazette notification.",
        "fields": [F("old_name", "Old name (as in records)"), F("new_name", "New name"), F("relation", "Relation", kind="choice", choices=REL),
                   F("relative_name", "Father's / mother's / spouse's name"), F("age", "Age (years)", kind="number"),
                   F("address", "Your address", kind="textarea"), F("reason", "Reason for the change"),
                   F("place", "Place of signing"), F("date", "Date of signing")],
        "notes": [STAMP, OATH, "Most offices also ask for a public notice in a newspaper and publication in the Gazette. Check which your authority needs."],
        "body": """# AFFIDAVIT FOR CHANGE OF NAME

I, {{new_name}} (earlier known as {{old_name}}), {{relation}} {{relative_name}}, aged about {{age}} years, resident of {{address}}, do hereby solemnly affirm and state on oath as under:

@ That I was born with / have been known by the name {{old_name}}.

@ That I have, of my own free will, changed my name from {{old_name}} to {{new_name}} with effect from the date of this affidavit, for the reason that {{reason}}.

@ That I shall hereafter be known and called by the name {{new_name}} in all records, documents, dealings and transactions.

@ That {{old_name}} and {{new_name}} are one and the same person.

@ That I have not changed my name for any illegal or fraudulent purpose and I am not doing so to avoid any legal liability.

""" + VERIFY},

    {
        "id": "affidavit_lost_document", "category": "Affidavits", "title": "Affidavit: lost document",
        "description": "Declares that a document is lost, for applying for a duplicate. Used with a police complaint or online lost report.",
        "fields": [F("name", "Your full name"), F("relation", "Relation", kind="choice", choices=REL), F("relative_name", "Father's / mother's / spouse's name"),
                   F("age", "Age (years)", kind="number"), F("address", "Your address", kind="textarea"),
                   F("document", "Document lost (with number, if known)"), F("lost_when", "When it was lost (date or approximate)"),
                   F("lost_where", "Where or how it was lost"), F("report", "Police / lost-report reference (optional)", required=False),
                   F("place", "Place of signing"), F("date", "Date of signing")],
        "notes": [STAMP, OATH, "Many authorities want a police complaint or an online lost report first. Attach it."],
        "body": """# AFFIDAVIT

I, {{name}}, {{relation}} {{relative_name}}, aged about {{age}} years, resident of {{address}}, do hereby solemnly affirm and state on oath as under:

@ That I was the lawful holder of the following document: {{document}}.

@ That the said document was lost on or about {{lost_when}}, at or in the circumstances described here: {{lost_where}}.

@ That I have made diligent search for it, but it could not be found.

?report @ That I have reported the loss, reference: {{report}}.

@ That the lost document has not been pledged, mortgaged, sold or handed over to anyone, and I will not use it if it is found later; I will return it to the issuing authority.

@ That I am applying for a duplicate and I indemnify the issuing authority against any loss caused by misuse of the original.

""" + VERIFY},

    {
        "id": "affidavit_income", "category": "Affidavits", "title": "Affidavit: income",
        "description": "Declares your annual income, for scholarships, fee waivers, certificates and similar.",
        "fields": [F("name", "Your full name"), F("relation", "Relation", kind="choice", choices=REL), F("relative_name", "Father's / mother's / spouse's name"),
                   F("age", "Age (years)", kind="number"), F("address", "Your address", kind="textarea"),
                   F("occupation", "Occupation or source of income"), F("income", "Annual income (Rs.)"),
                   F("year", "Financial year (e.g. 2025-26)"), F("purpose", "Purpose of the affidavit"),
                   F("place", "Place of signing"), F("date", "Date of signing")],
        "notes": [STAMP, OATH, "A false income declaration can have serious legal consequences. State only what is correct."],
        "body": """# AFFIDAVIT

I, {{name}}, {{relation}} {{relative_name}}, aged about {{age}} years, resident of {{address}}, do hereby solemnly affirm and state on oath as under:

@ That I am engaged in {{occupation}}.

@ That my total annual income from all sources for the financial year {{year}} is Rs. {{income}}.

@ That I have no other source of income beyond what is stated above.

@ That this affidavit is being made for the purpose of {{purpose}}.

""" + VERIFY},

    {
        "id": "legal_notice_general", "category": "Notices", "title": "Legal notice: demand / breach",
        "description": "A formal notice demanding payment or performance, with a deadline, before you go to court.",
        "fields": [F("date", "Date of notice"), F("sender", "Your name (sender)"), F("sender_address", "Your address", kind="textarea"),
                   F("recipient", "Recipient's name"), F("recipient_address", "Recipient's address", kind="textarea"),
                   F("background", "What happened (dates, agreement, payments)", kind="textarea"),
                   F("breach", "How the recipient failed", kind="textarea"), F("demand", "What you demand (amount or action)"),
                   F("days", "Days to comply", kind="number"), F("consequence", "What you will do if they do not comply", required=False),
                   F("advocate", "Advocate sending the notice (optional)", "Name, e.g. Priya Nair. Leave blank if you are sending it yourself", required=False), F("advocate_details", "Advocate's enrolment no. / office address (optional)", kind="textarea", required=False)],
        "notes": ["Send by registered post AD and by email, and keep the receipts and delivery proof.",
                  "Keep the facts accurate and avoid threats beyond legal remedies. Have a lawyer review before sending."],
        "body": """# LEGAL NOTICE

Date: {{date}}

To,
{{recipient}}
{{recipient_address}}

Subject: Notice demanding {{demand}}

Sir / Madam,

!advocate I, {{sender}}, resident of {{sender_address}}, hereby give you notice as follows:

?advocate Under instructions from and on behalf of my client {{sender}}, resident of {{sender_address}}, I, {{advocate}}, Advocate, hereby give you notice as follows:

@ {{background}}

@ That you have failed to honour your obligations in that: {{breach}}.

@ That I hereby call upon you to {{demand}} within {{days}} days of receipt of this notice.

?consequence @ That if you fail to do so, {{consequence}}, at your risk as to costs and consequences.

@ That this notice is without prejudice to all rights and remedies available in law, all of which are reserved.

Yours faithfully,

!advocate {{sender}}

?advocate {{advocate}}
?advocate {{advocate_details}}
?advocate (for {{sender}})"""},

    {
        "id": "legal_notice_cheque", "category": "Notices", "title": "Legal notice: cheque dishonour (Section 138, NI Act)",
        "description": "The demand notice that must precede a cheque-bounce complaint under Section 138 of the Negotiable Instruments Act, 1881.",
        "fields": [F("date", "Date of notice"), F("sender", "Payee's name (sender)"), F("sender_address", "Payee's address", kind="textarea"),
                   F("recipient", "Drawer's name"), F("recipient_address", "Drawer's address", kind="textarea"),
                   F("cheque_no", "Cheque number"), F("cheque_date", "Cheque date"), F("amount", "Cheque amount (Rs.)"),
                   F("drawn_on", "Drawer's bank and branch"), F("payee_bank", "Bank where you presented it"),
                   F("presented_on", "Date presented"), F("returned_on", "Date returned / memo received"), F("reason", "Reason given in the return memo (e.g. funds insufficient)"),
                   F("liability", "Debt or liability the cheque was for", kind="textarea"),
                   F("advocate", "Advocate sending the notice (optional)", "Name, e.g. Priya Nair. Leave blank if you are sending it yourself", required=False), F("advocate_details", "Advocate's enrolment no. / office address (optional)", kind="textarea", required=False)],
        "notes": ["Timing matters. The notice must be sent within 30 days of receiving the bank's information that the cheque was returned unpaid. "
                  "The drawer then has 15 days from receiving the notice to pay. A complaint can be filed only after those 15 days pass without payment, "
                  "and within one month after that. Confirm the current rules and limits with a lawyer.",
                  "Send by registered post AD and keep the postal receipt, tracking and the bank's return memo."],
        "body": """# LEGAL NOTICE UNDER SECTION 138 OF THE NEGOTIABLE INSTRUMENTS ACT, 1881

Date: {{date}}

To,
{{recipient}}
{{recipient_address}}

Subject: Notice for dishonour of cheque no. {{cheque_no}} dated {{cheque_date}} for Rs. {{amount}}

Sir / Madam,

!advocate I, {{sender}}, resident of {{sender_address}}, give you notice as follows:

?advocate Under instructions from and on behalf of my client {{sender}}, resident of {{sender_address}}, I, {{advocate}}, Advocate, give you notice as follows:

@ That you issued cheque no. {{cheque_no}} dated {{cheque_date}} for Rs. {{amount}}, drawn on {{drawn_on}}, in favour of {{sender}} in discharge of the following legally enforceable debt or liability: {{liability}}.

@ That the cheque was presented through {{payee_bank}} on {{presented_on}} and was returned unpaid on {{returned_on}} with the remark: "{{reason}}".

@ That the dishonour of the cheque amounts to an offence under Section 138 of the Negotiable Instruments Act, 1881.

@ That I hereby call upon you to pay Rs. {{amount}}, being the cheque amount, within fifteen (15) days of receipt of this notice.

!advocate @ That if you fail to make the payment within the said period, I shall initiate criminal proceedings against you under Section 138 read with Section 142 of the said Act, in addition to civil remedies for recovery, at your risk as to costs and consequences.

?advocate @ That if you fail to make the payment within the said period, my client shall initiate criminal proceedings against you under Section 138 read with Section 142 of the said Act, in addition to civil remedies for recovery, at your risk as to costs and consequences.

Yours faithfully,

!advocate {{sender}}

?advocate {{advocate}}
?advocate {{advocate_details}}
?advocate (for {{sender}})"""},

    {
        "id": "rent_agreement", "category": "Agreements", "title": "Rent agreement (residential, 11 months)",
        "description": "Residential leave-and-licence style rent agreement for 11 months, with rent, deposit, notice and standard terms.",
        "fields": [F("date", "Date of agreement"), F("place", "Place"),
                   F("landlord", "Landlord's full name"), F("landlord_address", "Landlord's address", kind="textarea"),
                   F("tenant", "Tenant's full name"), F("tenant_address", "Tenant's permanent address", kind="textarea"),
                   F("premises", "Address of the rented premises", kind="textarea"), F("start", "Start date"),
                   F("rent", "Monthly rent (Rs.)"), F("due_day", "Rent due by (day of month)"), F("deposit", "Security deposit (Rs.)"),
                   F("notice_months", "Notice period (months)", kind="number"), F("increase", "Annual rent increase (%)", required=False)],
        "notes": [STAMP + " Stamp duty on rent agreements differs widely by State.",
                  "A lease longer than one year must be registered under the Registration Act, 1908. This 11-month form is commonly used to stay under that limit, "
                  "though some States require registration or have specific rules anyway. Check yours.",
                  "Both parties and two witnesses should sign. Keep the landlord's ownership proof and tenant's ID proof with the agreement."],
        "body": """# RENT AGREEMENT

This Rent Agreement is made at {{place}} on {{date}}

BETWEEN

{{landlord}}, resident of {{landlord_address}} (hereinafter called the "LANDLORD"), of the one part,

AND

{{tenant}}, resident of {{tenant_address}} (hereinafter called the "TENANT"), of the other part.

The Landlord is the owner of the premises at {{premises}} (the "Premises") and has agreed to let it to the Tenant on the following terms:

@ Term. The tenancy is for a period of eleven (11) months starting from {{start}}. It may be renewed only by a fresh written agreement signed by both parties.

@ Rent. The Tenant shall pay a monthly rent of Rs. {{rent}} on or before the {{due_day}} day of each month, by bank transfer or cheque, and shall obtain a receipt.

?increase @ Increase. The rent shall increase by {{increase}}% on any renewal.

@ Security deposit. The Tenant has paid an interest-free refundable security deposit of Rs. {{deposit}}. It shall be returned within thirty (30) days of vacating, after deducting only unpaid rent, utility dues and the cost of damage beyond normal wear and tear.

@ Use. The Premises shall be used only as a private residence. The Tenant shall not carry on any business, sub-let, or part with possession, and shall not do anything unlawful or a nuisance to neighbours.

@ Utilities and upkeep. The Tenant shall pay electricity, water, gas, internet and maintenance charges for the period of occupation. The Tenant shall keep the Premises in good condition and make no structural changes without the Landlord's written consent.

@ Inspection. The Landlord may inspect the Premises at reasonable times after giving reasonable notice.

@ Termination. Either party may end the tenancy by giving {{notice_months}} month(s) written notice. The Landlord may end it earlier if the Tenant fails to pay rent for two consecutive months or breaches a material term and does not remedy it within fifteen (15) days of written notice.

@ Handing back. On ending the tenancy the Tenant shall hand over peaceful, vacant possession with all fixtures in the condition received, apart from normal wear and tear.

@ Law and disputes. This agreement is governed by the laws of India. The parties shall first try to settle any dispute by discussion; failing that, the courts at {{place}} shall have jurisdiction.

IN WITNESS WHEREOF the parties have signed this agreement on the date first written above.

LANDLORD: ______________________    TENANT: ______________________

WITNESSES:

1. ______________________

2. ______________________"""},

    {
        "id": "nda", "category": "Agreements", "title": "Non-disclosure agreement (NDA)",
        "description": "Protects confidential information shared between two parties. Mutual or one-way.",
        "fields": [F("date", "Date of agreement"), F("place", "Place"),
                   F("party1", "First party (name and address)", kind="textarea"), F("party2", "Second party (name and address)", kind="textarea"),
                   F("type", "Type", kind="choice", choices=["mutual (both parties disclose)", "one-way (first party discloses)"]),
                   F("purpose", "Purpose of sharing the information"), F("years", "Confidentiality lasts (years)", kind="number"),
                   F("jurisdiction", "City whose courts have jurisdiction")],
        "notes": [STAMP, "An NDA is only as good as its definition of 'Confidential Information' and the remedies. Have a lawyer tailor it to your deal.",
                  "Do not use an NDA to hide unlawful conduct. Clauses that stop someone from working at all are generally not enforceable in India."],
        "body": """# NON-DISCLOSURE AGREEMENT

This Agreement is made at {{place}} on {{date}}

BETWEEN

{{party1}} (the "First Party"),

AND

{{party2}} (the "Second Party").

This is a {{type}} agreement. The parties wish to exchange confidential information for the purpose of {{purpose}} (the "Purpose").

@ Confidential Information means all non-public information, in any form, that is disclosed under this Agreement and is marked confidential or would reasonably be understood to be confidential, including business, technical, financial and customer information.

@ Obligations. The receiving party shall use the Confidential Information only for the Purpose, keep it confidential with at least reasonable care, and disclose it only to its employees and advisers who need to know it and are bound by equivalent duties.

@ Exceptions. These obligations do not apply to information that is or becomes public without breach of this Agreement; was already lawfully known to the receiving party; is independently developed without using the Confidential Information; or is lawfully received from a third party without restriction.

@ Legal compulsion. A receiving party may disclose Confidential Information if required by law or a court, after giving the other party prompt notice where permitted, and only to the extent required.

@ Return. On request, or when the Purpose ends, the receiving party shall return or destroy all Confidential Information and confirm this in writing.

@ Term. The duties of confidentiality continue for {{years}} years from the date of this Agreement.

@ No licence. No right in any Confidential Information is granted except as stated here. This Agreement does not oblige either party to enter any further transaction.

@ Remedies. Each party acknowledges that breach may cause harm that damages alone cannot repair, and the other party may seek injunctive relief in addition to other remedies.

@ Law and disputes. This Agreement is governed by the laws of India, and the courts at {{jurisdiction}} shall have exclusive jurisdiction.

IN WITNESS WHEREOF the parties have signed this Agreement on the date first written above.

FIRST PARTY: ______________________    SECOND PARTY: ______________________

WITNESSES:

1. ______________________

2. ______________________"""},

    {
        "id": "poa_general", "category": "Agreements", "title": "Power of attorney (general)",
        "description": "Authorises another person to act for you in stated matters. Can be limited to specific tasks.",
        "fields": [F("date", "Date"), F("place", "Place"), F("principal", "Your name (principal)"),
                   F("relation", "Relation", kind="choice", choices=REL), F("relative_name", "Father's / mother's / spouse's name"),
                   F("principal_address", "Your address", kind="textarea"),
                   F("attorney", "Attorney's name"), F("attorney_relation", "Attorney's relation", kind="choice", choices=REL),
                   F("attorney_relative", "Attorney's father's / spouse's name"), F("attorney_address", "Attorney's address", kind="textarea"),
                   F("powers", "Powers granted, one per line", kind="textarea"), F("valid_until", "Valid until (date), or leave blank until revoked", required=False)],
        "notes": [STAMP + " The duty rate for a power of attorney is set by each State.",
                  "If the powers include dealing with immovable property (sale, lease, mortgage), the power of attorney generally needs registration, "
                  "and a power of attorney alone does not transfer ownership of property. A lawyer should handle this.",
                  "The principal can revoke it in writing at any time, and it normally ends on the principal's death. Keep the powers as narrow as you can."],
        "body": """# POWER OF ATTORNEY

KNOW ALL MEN BY THESE PRESENTS that I, {{principal}}, {{relation}} {{relative_name}}, resident of {{principal_address}} (the "Principal"), do hereby appoint {{attorney}}, {{attorney_relation}} {{attorney_relative}}, resident of {{attorney_address}} (the "Attorney"), as my true and lawful attorney to act for me and in my name, in the following matters:

{{powers:numbered}}

@ The Attorney shall act only within the powers stated above and shall exercise them in good faith and in my interest.

?valid_until @ This Power of Attorney shall remain valid until {{valid_until}}, unless revoked earlier.

@ I may revoke this Power of Attorney at any time by written notice to the Attorney.

@ I agree to ratify and confirm all lawful acts done by the Attorney within these powers.

IN WITNESS WHEREOF I have signed this Power of Attorney at {{place}} on {{date}}.

PRINCIPAL: ______________________

ACCEPTED BY ATTORNEY: ______________________

WITNESSES:

1. ______________________

2. ______________________"""},
]

BY_ID = {t["id"]: t for t in TEMPLATES}

# --------------------------------------------------------------------------- rendering
_FIELD = re.compile(r"\{\{(\w+)(?::(\w+))?\}\}")


def _label(t, key):
    for f in t["fields"]:
        if f["key"] == key:
            return f["label"]
    return key


def public_list():
    return [{k: v for k, v in t.items() if k != "body"} | {"disclaimer": DISCLAIMER} for t in TEMPLATES]


def render(template_id: str, values: dict) -> dict:
    t = BY_ID.get(template_id)
    if not t:
        raise KeyError(template_id)
    vals = {k: str(v).strip() for k, v in (values or {}).items() if v is not None and str(v).strip()}
    filled_keys = set(vals)
    missing = [f["key"] for f in t["fields"] if f["required"] and f["key"] not in filled_keys]
    n = 0
    out = []    # (kind, text)
    kept_lines = []
    for ln in t["body"].strip().split("\n"):     # conditions apply line by line
        cm = re.match(r"([?!])(\w+)\s+(.*)", ln.lstrip(), re.S)
        if cm:
            if (cm.group(2) in filled_keys) != (cm.group(1) == "?"):
                continue
            ln = cm.group(3)
        kept_lines.append(ln)
    body_text = "\n".join(kept_lines)
    for block in re.split(r"\n\s*\n", body_text):
        if not block.strip():
            continue
        lines = [ln for ln in block.split("\n")]
        first = lines[0].lstrip()
        cond = re.match(r"([?!])(\w+)\s+(.*)", first, re.S)
        if cond:
            present = cond.group(2) in filled_keys
            if present != (cond.group(1) == "?"):
                continue
            lines[0] = cond.group(3)
            first = lines[0].lstrip()
        # numbered list expansion: {{key:numbered}} -> one auto-numbered paragraph per line of the value
        m = re.fullmatch(r"\{\{(\w+):numbered\}\}", first.strip())
        if m:
            items = [x.strip(" -*•\t") for x in vals.get(m.group(1), "").split("\n") if x.strip()]
            for x in (items or [f"[{_label(t, m.group(1)).upper()}]"]):
                n += 1
                out.append(("p", f"{n}. That {x}" if not x.lower().startswith("that ") and t["id"].startswith("affidavit") else f"{n}. {x}"))
            continue
        text = "\n".join(lines)

        def sub(mm):
            key = mm.group(1)
            return vals[key] if key in vals else f"[{_label(t, key).upper()}]"
        kind = "p"
        if text.startswith("# "):
            kind, text = "h1", text[2:]
        elif text.startswith("## "):
            kind, text = "h2", text[3:]
        elif text.startswith("@ "):
            n += 1
            text = f"{n}. " + text[2:]
        out.append((kind, _FIELD.sub(sub, text)))
    plain = "\n\n".join(x for _, x in out)
    parts = []
    for kind, x in out:
        body = html.escape(x).replace("\n", "<br>")
        parts.append({"h1": f'<h2 style="text-align:center">{body}</h2>', "h2": f'<h3 style="text-align:center">{body}</h3>'}.get(kind, f"<p>{body}</p>"))
    return {"id": t["id"], "title": t["title"], "html": "".join(parts), "text": plain, "missing": missing,
            "notes": t["notes"], "disclaimer": DISCLAIMER}


# --------------------------------------------------------------------------- matching a chat request to a template
_DRAFT = re.compile(r"(?i)\b(?:draft|write|prepare|make|create|generate|need|want|give me|format of|sample|template)\b")
_RULES = [
    ("legal_notice_cheque", re.compile(r"(?i)(?:cheque|check)\b.*\b(?:notice|bounce|dishonou?r|138)\b|\b(?:notice|138)\b.*\b(?:cheque|check)\b|section\s*138\b.*notice")),
    ("legal_notice_general", re.compile(r"(?i)\blegal\s+notice\b|\bdemand\s+notice\b")),
    ("affidavit_name_change", re.compile(r"(?i)affidavit\b.*\bname\b|\bname\s+change\b.*affidavit|change\s+of\s+name")),
    ("affidavit_lost_document", re.compile(r"(?i)affidavit\b.*\blost\b|\blost\b.*\baffidavit|lost\s+(?:document|certificate|passport|licen[cs]e)")),
    ("affidavit_income", re.compile(r"(?i)income\s+affidavit|affidavit\b.*\bincome\b")),
    ("affidavit_residence", re.compile(r"(?i)(?:home|residence|residential|address|residing|resident)\b.*\baffidavit|affidavit\b.*(?:home|residence|residential|address\s+proof)")),
    ("affidavit_general", re.compile(r"(?i)\baffidavit\b")),
    ("rent_agreement", re.compile(r"(?i)\brent(?:al)?\s+agreement\b|\blease\s+agreement\b|\bleave\s+and\s+licen[cs]e\b|\brent\s+deed\b")),
    ("nda", re.compile(r"(?i)\bnda\b|non[- ]?disclosure|confidentiality\s+agreement")),
    ("poa_general", re.compile(r"(?i)power\s+of\s+attorney|\bpoa\b|\bgpa\b")),
]


def match_template(message: str):
    """Template id when the message asks to draft one of the standard documents, else None."""
    if not _DRAFT.search(message):
        return None
    for tid, rx in _RULES:
        if rx.search(message):
            return tid
    return None


def chat_reply(template_id: str) -> str:
    r = render(template_id, {})
    notes = "\n".join(f"- {n}" for n in r["notes"])
    return (f"Here is a standard Indian format for **{r['title']}**. Fill in the [BRACKETED] details. "
            f"In the editor, the Templates button lets you fill them in a form and insert the finished document.\n\n"
            f"---\n\n{r['text']}\n\n---\n\n**Before you use it**\n{notes}\n- {DISCLAIMER}")
