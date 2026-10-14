"""Build the static legal pages (web/legal/*.html) from legal/config.json.

Run:  python3 scripts/build_legal.py
Fill in legal/config.json (registered entity, address, grievance officer, city for jurisdiction, hosting region)
and run it again before launch. Empty fields are left out of the pages rather than shown as blanks.
These are drafts written to match what the software actually does. Have an Indian advocate review them.
"""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = json.loads((ROOT / "legal" / "config.json").read_text())
OUT = ROOT / "web" / "legal"
OUT.mkdir(parents=True, exist_ok=True)

E = html.escape
P = C["product"]; A = C["assistant"]
OP = C["entity_name"].strip() or P                     # who we are in the text
MAIL = C["contact_email"]
GRIEV = C["grievance_officer_email"].strip() or MAIL
GRIEV_NAME = C["grievance_officer_name"].strip()
CITY = C["jurisdiction_city"].strip()
HOST = C["hosting_region"].strip()

PAGES = [("terms-conditions", "Terms of Service"), ("privacy-policy", "Privacy Policy"), ("acceptable-use", "Acceptable Use"),
         ("refund-policy", "Refund Policy"), ("legal-notice", "Legal Notice"), ("security", "Security"), ("delete-data", "Delete your data")]


def operator_block() -> str:
    lines = [f"<strong>{E(OP)}</strong>"]
    if C["entity_address"].strip():
        lines.append(E(C["entity_address"].strip()))
    lines.append(f'Email: <a href="mailto:{E(MAIL)}">{E(MAIL)}</a>')
    return "<p>" + "<br>".join(lines) + "</p>"


def page(slug: str, title: str, body: str) -> str:
    nav = " · ".join(f'<a href="/{s}"{" aria-current=page" if s == slug else ""}>{E(t)}</a>' for s, t in PAGES)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark"><title>{E(title)} · {E(P)}</title>
<style>
:root{{--bg:#fafaf9;--fg:#1c1917;--mut:#6b6761;--line:#e7e5e4;--acc:#b04a12}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141413;--fg:#f0eeeb;--mut:#a09b94;--line:#33312f;--acc:#f08a4b}}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);font:17px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:760px;margin:0 auto;padding:28px 18px 70px}} a{{color:var(--acc)}}
header a.brand{{font:600 22px Georgia,serif;text-decoration:none;color:var(--fg)}}
nav{{font-size:14px;color:var(--mut);margin:10px 0 26px;line-height:2}} nav a[aria-current]{{color:var(--fg);font-weight:600;text-decoration:none}}
h1{{font:600 32px/1.2 Georgia,serif;margin:0 0 4px}} h2{{font-size:20px;margin:30px 0 6px}} .meta{{color:var(--mut);font-size:14px;margin:0 0 22px}}
ul{{padding-left:22px}} li{{margin:4px 0}} .box{{border:1px solid var(--line);border-radius:10px;padding:2px 16px;margin:16px 0}}
footer{{margin-top:44px;color:var(--mut);font-size:14px;border-top:1px solid var(--line);padding-top:16px}}
</style></head><body><main>
<header><a class="brand" href="/">{E(P)}</a></header><nav aria-label="Legal pages">{nav}</nav>
<h1>{E(title)}</h1><p class="meta">Effective {E(C['effective'])}</p>
{body}
<footer>Questions? <a href="mailto:{E(MAIL)}">{E(MAIL)}</a>. {E(P)} is a research aid and does not give legal advice.</footer>
</main></body></html>"""


# --------------------------------------------------------------------------------------------- Terms
TERMS = f"""
<p>These terms apply when you use {E(P)} (the "Service"), including the research tools and the {E(A)} assistant. By creating an account or using the Service you agree to them. If you do not agree, please do not use the Service.</p>
<div class="box"><h2 style="margin-top:12px">Who we are</h2>{operator_block()}</div>

<h2>1. What the Service is, and what it is not</h2>
<p>{E(P)} helps you look up Indian statutes and court judgments and ask questions about them. Answers from {E(A)} are produced by a computer language model from the sources shown to it. The model can make mistakes, miss relevant material or misstate what a provision or judgment says.</p>
<ul>
<li><strong>It is not legal advice.</strong> {E(OP)} is not a law firm and is not an advocate. Using the Service does not create an advocate–client relationship.</li>
<li>Always check anything you rely on against the official text of the statute or the full judgment. Citations the Service shows are there to help you find the source, not to replace reading it.</li>
<li>If you are a legal professional, your duties to your clients and to the courts remain yours. You are responsible for how you use any output, including anything you put before a court.</li>
</ul>

<h2>2. Your account</h2>
<ul>
<li>You must be at least 18 years old and able to enter a binding contract.</li>
<li>Give accurate details, keep your password private and tell us at once if you think someone else has used your account. You are responsible for activity under it.</li>
<li>One account per person. Do not share logins.</li>
</ul>

<h2>3. Acceptable use</h2>
<p>You agree to follow our <a href="/acceptable-use">Acceptable Use Policy</a>. In short: no unlawful use, no attempts to break, overload or bypass the Service or its limits, and no bulk copying of the library.</p>

<h2>4. Your content</h2>
<p>This covers the questions you type and the documents you save in the editor. You keep your rights in it. You give us permission to store and process it only to run the Service for you, including sending your questions to the language model to produce an answer, and to keep the Service secure. We do not sell your content and we do not use it to advertise to you.</p>
<p><strong>Confidentiality:</strong> do not enter anything you are not entitled to share, such as a client's confidential details, unless you have the right and any consent needed. See the <a href="/privacy-policy">Privacy Policy</a> for how we handle data.</p>

<h2>5. Our content and the sources we use</h2>
<ul>
<li>The Service's software, design and name belong to {E(OP)} or its licensors.</li>
<li>Legal texts and judgments come from the Open India Law dataset by Vaquill AI, published under the <a href="https://creativecommons.org/licenses/by/4.0/">Creative Commons Attribution 4.0</a> licence, which in turn collects them from official government and court sources. Those texts remain subject to the rights of their original publishers. We credit the dataset and make no claim to own it.</li>
<li>The texts may be incomplete, out of date, or contain errors from conversion. Some Acts are not included. Check the official source.</li>
</ul>

<h2>6. Free use and limits</h2>
<p>The Service is currently free. We limit use, for example to {C['free_daily_questions']} {E(A)} questions per account per day, to keep it available to everyone. We may change or end any feature, and we do not promise the Service will always be available or error-free. If we introduce paid plans we will tell you first, and nothing is charged without your agreement.</p>

<h2>7. Disclaimers</h2>
<p>To the extent the law allows, the Service is provided "as is" and "as available", without promises that it is accurate, complete, current or fit for a particular purpose.</p>

<h2>8. Limit of liability</h2>
<p>To the extent the law allows, {E(OP)} is not liable for indirect or consequential loss, loss of profit, or loss arising from your reliance on any output of the Service, including a missed deadline, a wrong citation or an adverse court outcome. Where liability cannot be excluded, it is limited to the amount you paid us in the 12 months before the claim, or ₹1,000 if you paid nothing. Nothing in these terms limits rights you have under law that cannot be waived, including under the Consumer Protection Act, 2019.</p>

<h2>9. Suspension and ending</h2>
<p>You can stop using the Service and delete your account at any time (see <a href="/delete-data">Delete your data</a>). We may suspend or close an account that breaks these terms or puts others or the Service at risk, and will say why where we reasonably can.</p>

<h2>10. Changes to these terms</h2>
<p>We may update these terms. If a change matters to you we will ask you to accept it again or give notice before it applies. Continuing to use the Service after notice means you accept the update.</p>

<h2>11. Governing law</h2>
<p>These terms are governed by the laws of India. {('Disputes are subject to the courts at ' + E(CITY) + ', India, ') if CITY else 'Disputes are subject to the courts of India '}without limiting any right you have to approach a consumer forum where the law gives you one.</p>

<h2>12. Contact</h2>
<p>Write to <a href="mailto:{E(MAIL)}">{E(MAIL)}</a>. For a privacy complaint see the Grievance Officer details in the <a href="/privacy-policy">Privacy Policy</a>.</p>
"""

# ------------------------------------------------------------------------------------------- Privacy
PRIVACY = f"""
<p>This policy explains what personal data {E(P)} collects, why, how long we keep it, and the choices you have. It is written to meet the requirements of India's Digital Personal Data Protection Act, 2023 (the "DPDP Act").</p>
<div class="box"><h2 style="margin-top:12px">Who is responsible for your data</h2>{operator_block()}
<p><strong>Grievance Officer:</strong> {(E(GRIEV_NAME) + ', ') if GRIEV_NAME else ''}<a href="mailto:{E(GRIEV)}">{E(GRIEV)}</a></p></div>

<h2>What we collect, and why</h2>
<ul>
<li><strong>Account details:</strong> your name and email address, and a one-way scrambled form of your password (we cannot read your password). We use them to create and secure your account and to email you account messages such as confirmation and password-reset links.</li>
<li><strong>Your consent record:</strong> that you accepted the Terms and this Policy, which version, and when.</li>
<li><strong>What you ask and save:</strong> the questions you ask {E(A)}, the answers, and documents you save in the editor. We use them to give you the Service, show you your history and let you return to your work.</li>
<li><strong>Use counts:</strong> how many questions you have asked today, to apply the daily limit.</li>
<li><strong>Technical and security data:</strong> your IP address and the pages and requests made to our servers. These help us keep the Service secure and stop abuse. They are held in server logs for up to {C['log_retention_days']} days.</li>
<li><strong>On your device:</strong> a sign-in token and small settings are kept in your browser's storage so you stay signed in. We do not use advertising or analytics cookies and do not run third-party trackers.</li>
</ul>
<p>We do not ask for, and you should not enter, sensitive identifiers such as Aadhaar, PAN or bank details.</p>

<h2>Your consent</h2>
<p>We process your data on the basis of the consent you give when you create an account, and for the limited purposes the DPDP Act allows without consent, such as meeting legal obligations. You can withdraw consent at any time by deleting your account. Withdrawing means we can no longer provide the Service to you.</p>

<h2>How the AI part works</h2>
<p>When you ask a question, we search our library of statutes and judgments for relevant passages and send your question and those passages to a language model, which writes the answer. {('The model runs on infrastructure we control' + (' in ' + E(HOST) if HOST else '') + '.') if True else ''} We do not use your questions or documents to train a model, and we do not sell them.</p>

<h2>Who else sees your data</h2>
<ul>
<li><strong>Service providers</strong> that help us run the Service, such as our hosting provider and our email-delivery provider (which sees your email address and the message). They may use data only to provide their service to us.</li>
<li><strong>Bot protection</strong>, if switched on at sign-up, is provided by Cloudflare Turnstile, which receives your IP address and browser details to tell people from bots.</li>
<li><strong>Authorities</strong>, where the law requires us to disclose data.</li>
</ul>
<p>We do not sell personal data or share it for advertising.</p>

<h2>How long we keep it</h2>
<ul>
<li><strong>Chats:</strong> deleted automatically after {C['chat_retention_days']} days. You can delete them earlier.</li>
<li><strong>Saved documents and account details:</strong> kept until you delete them or your account.</li>
<li><strong>Deleted accounts:</strong> when you ask us to delete your account we keep it for {C['deletion_grace_days']} days so you can change your mind, then permanently delete the account, your chats and your documents. Backups, if any, are overwritten on a regular cycle.</li>
<li><strong>Server logs:</strong> up to {C['log_retention_days']} days.</li>
<li>We may keep limited records for longer where the law requires it.</li>
</ul>

<h2>Your rights</h2>
<p>Under the DPDP Act you can:</p>
<ul>
<li><strong>Get a copy of your data</strong>: Account settings, then <strong>Privacy &amp; data</strong>, then <strong>Export as JSON</strong>.</li>
<li><strong>Correct or update it</strong>: change details in Account settings, or write to us.</li>
<li><strong>Have it erased</strong>: Account settings, then <strong>Close this account</strong>, then <strong>Delete my account</strong> (see <a href="/delete-data">Delete your data</a>).</li>
<li><strong>Complain</strong>: write to our Grievance Officer above. We will acknowledge your complaint and aim to resolve it within 30 days. If you are not satisfied you may complain to the Data Protection Board of India.</li>
<li><strong>Nominate</strong> another person to exercise these rights for you if you die or become incapacitated.</li>
</ul>

<h2>How we protect it</h2>
<p>Passwords are stored only as salted one-way hashes. Sign-in tokens expire and can be revoked, and logging out or changing your password ends other sessions. We limit sign-in attempts and the rate of requests, and we only collect data we need. No system is perfectly secure. If a breach affects your personal data we will tell you and the Data Protection Board of India as the law requires. See also <a href="/security">Security</a>.</p>

<h2>Children</h2>
<p>The Service is for people aged 18 and over. We do not knowingly collect data from children. If you think a child has given us data, write to us and we will delete it.</p>

<h2>Where data is processed</h2>
<p>{('Your data is stored and processed in ' + E(HOST) + '.') if HOST else 'Your data is stored and processed on servers chosen by the operator; we will name the region here.'} If this changes we will update this policy.</p>

<h2>Changes</h2>
<p>If we change this policy in a way that matters, we will tell you and, where required, ask for your consent again.</p>
"""

# --------------------------------------------------------------------------------------------- AUP
AUP = f"""
<p>This policy sets out what you may not do with {E(P)}. It forms part of the <a href="/terms-conditions">Terms of Service</a>.</p>
<h2>You must not</h2>
<ul>
<li>Break the law, or help someone else do so, using the Service.</li>
<li>Copy the library in bulk, scrape it, or use the Service to build a competing database or to train a model.</li>
<li>Try to get around limits, sign-in, rate controls or other protections, or probe, overload or attack the Service.</li>
<li>Use someone else's account, create accounts to avoid limits, or give false details when signing up.</li>
<li>Upload malware, or content you have no right to share, including confidential material you are not allowed to disclose.</li>
<li>Harass, threaten or impersonate anyone.</li>
<li>Present AI output to a court, a client or any other person as verified fact without checking it against the official source.</li>
</ul>
<h2>What we may do</h2>
<p>We may warn you, limit access, suspend or close an account, and report unlawful activity to the authorities. To report a problem, write to <a href="mailto:{E(MAIL)}">{E(MAIL)}</a>.</p>
"""

# -------------------------------------------------------------------------------------------- Refund
REFUND = f"""
<p>{E(P)} is currently <strong>free</strong>, so there is nothing to refund.</p>
<h2>If we introduce paid plans</h2>
<p>We will show the price, what is included, how to cancel and the refund terms before you pay, and we will not charge you without your agreement. Nothing in this page reduces any right you have under the Consumer Protection Act, 2019 or other law.</p>
<h2>If you were charged by mistake</h2>
<p>Write to <a href="mailto:{E(MAIL)}">{E(MAIL)}</a> with the details and we will look into it promptly.</p>
"""

# ---------------------------------------------------------------------------------------- Legal notice
NOTICE = f"""
<h2>No legal advice</h2>
<p>Everything on {E(P)}, including answers from {E(A)}, is general information to help you research. It is not legal advice and does not create an advocate–client relationship. {E(OP)} is not a law firm and does not practise law. Speak to a qualified advocate about your situation.</p>
<h2>Accuracy of sources</h2>
<p>Statutes and judgments are drawn from public sources through the Open India Law dataset (Vaquill AI, licensed <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>). We have not independently verified every text. They may be incomplete, outdated or contain conversion errors. Confirm anything important against the official gazette or the certified judgment.</p>
<h2>No solicitation</h2>
<p>Nothing on this site is an advertisement or a solicitation of work for any advocate, and it should not be read as one under the Bar Council of India's rules.</p>
<h2>Names and marks</h2>
<p>Other organisations' names are used only to identify them. They belong to their owners, and we claim no connection with them unless we say so.</p>
<h2>Operator</h2>
{operator_block()}
"""

# ----------------------------------------------------------------------------------------------- Security
SECURITY = f"""
<p>This page says plainly what we do to protect your account and data, and what we do not claim.</p>
<h2>What we do</h2>
<ul>
<li>Passwords are never stored as text. They are stored only as salted one-way hashes (scrypt).</li>
<li>Sign-in uses signed tokens that expire. Logging out, changing your password or disabling an account ends the sessions.</li>
<li>Sign-in attempts are limited, and repeated failures lock the account for a while. Sign-up and password-reset emails are rate limited and their links work once and expire.</li>
<li>Your chats and saved documents are visible only to your account.</li>
<li>Connections are encrypted with HTTPS.</li>
<li>Chats are deleted automatically after {C['chat_retention_days']} days, and you can export or delete your data yourself.</li>
<li>We do not run advertising or analytics trackers on the site.</li>
</ul>
<h2>What we do not claim</h2>
<p>We do not hold third-party security certifications, and we have not yet had an independent security audit. No online service is perfectly secure.</p>
<h2>Report a problem</h2>
<p>If you find a security issue, please write to <a href="mailto:{E(MAIL)}">{E(MAIL)}</a> with the details. Give us reasonable time to fix it before you share it publicly. Please do not access other people's data while testing.</p>
"""

DELETE = f"""
<p>You are in control of your data.</p>
<h2>Delete your account</h2>
<ol>
<li>Sign in and open <strong>Account settings</strong>.</li>
<li>Under <strong>Close this account</strong>, choose <strong>Delete my account</strong>.</li>
</ol>
<p>We keep the account for {C['deletion_grace_days']} days in case you change your mind, and you can cancel it from the same page (choose <strong>Keep my account</strong>) during that time. After that your account, your chats and your saved documents are permanently deleted.</p>
<h2>Export first</h2>
<p>In <strong>Account settings</strong>, open <strong>Privacy &amp; data</strong> and choose <strong>Export as JSON</strong> to download a copy of your information.</p>
<h2>Can't sign in?</h2>
<p>Write to <a href="mailto:{E(MAIL)}">{E(MAIL)}</a> from the email address on the account and we will help. We may ask you to confirm it is you before we delete anything.</p>
"""

BODIES = {"terms-conditions": TERMS, "privacy-policy": PRIVACY, "acceptable-use": AUP, "refund-policy": REFUND,
          "legal-notice": NOTICE, "security": SECURITY, "delete-data": DELETE}

for slug, title in PAGES:
    (OUT / f"{slug}.html").write_text(page(slug, title, BODIES[slug]), encoding="utf-8")
print("built", len(PAGES), "pages in", OUT.relative_to(ROOT))
missing = [k for k in ("entity_name", "entity_address", "grievance_officer_name", "grievance_officer_email", "jurisdiction_city", "hosting_region") if not C[k].strip()]
if missing:
    print("NOTE: fill these in legal/config.json before launch:", ", ".join(missing))
