"""Read an uploaded file (txt, rtf, docx, pdf, image) and return its text for the editor's Import dialog.

PDFs use poppler's pdftotext; scanned PDFs and images use tesseract (OCR). Both are system programs, not Python packages:
    brew install poppler tesseract tesseract-lang        (macOS)
Word (.docx) is read with the standard library. Legacy .doc is not supported.
Result shape (what the front end expects): {content: html, plainText, metadata: {title, pageCount, isScanned, wordCount}}.
"""
import html
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024
MAX_OCR_PAGES = 30
MAX_PDF_PAGES = 400
OCR_TIMEOUT = 180


class ParseError(Exception):
    pass


def _run(cmd, timeout=60):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError:
        raise ParseError(f"{cmd[0]} is not installed on the server, so this file type can't be read.")
    except subprocess.TimeoutExpired:
        raise ParseError("Reading the file took too long. Try a smaller file.")


def _lang(code: str) -> str:
    code = (code or "eng").strip().lower()
    if not re.fullmatch(r"[a-z]{3}(?:_[a-z]{3,4})?(?:\+[a-z]{3}(?:_[a-z]{3,4})?){0,2}", code):
        return "eng"
    return code


def _ocr_image(path: Path, lang: str) -> str:
    if not shutil.which("tesseract"):
        raise ParseError("Text recognition (OCR) isn't set up on the server, so scanned pages and images can't be read.")
    r = _run(["tesseract", str(path), "stdout", "-l", lang, "--psm", "3"], OCR_TIMEOUT)
    if r.returncode != 0 and lang != "eng":   # language pack not installed: fall back to English
        r = _run(["tesseract", str(path), "stdout", "-l", "eng", "--psm", "3"], OCR_TIMEOUT)
    return r.stdout.decode("utf-8", "replace")


def _pdf(path: Path, force_ocr: bool, lang: str):
    info = _run(["pdfinfo", str(path)], 30)
    m = re.search(rb"Pages:\s+(\d+)", info.stdout)
    pages = int(m.group(1)) if m else 0
    if pages > MAX_PDF_PAGES:
        raise ParseError(f"This PDF has {pages} pages; the limit is {MAX_PDF_PAGES}.")
    text = ""
    if not force_ocr:
        r = _run(["pdftotext", "-enc", "UTF-8", "-nopgbrk", str(path), "-"], 120)
        text = r.stdout.decode("utf-8", "replace")
    scanned = force_ocr or len(re.sub(r"\s", "", text)) < max(40, 25 * max(pages, 1))
    if scanned:
        n = min(pages or 1, MAX_OCR_PAGES)
        with tempfile.TemporaryDirectory() as d:
            _run(["pdftoppm", "-r", "200", "-png", "-f", "1", "-l", str(n), str(path), f"{d}/p"], 180)
            parts = [_ocr_image(p, lang) for p in sorted(Path(d).glob("p*.png"))]
        text = "\n\n".join(parts)
        if pages > MAX_OCR_PAGES:
            text += f"\n\n[Only the first {MAX_OCR_PAGES} of {pages} pages were read.]"
    return text, pages or 1, scanned


def _docx(data_path: Path):
    try:
        with zipfile.ZipFile(data_path) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > 60 * 1024 * 1024:
                raise ParseError("This Word file is too large to read.")
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError):
        raise ParseError("This doesn't look like a valid .docx file.")
    paras = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
        p = re.sub(r"<w:tab/>", "\t", p)
        p = re.sub(r"<w:br[^>]*/>", "\n", p)
        t = "".join(x or y for x, y in re.findall(r"<w:t[^>]*>(.*?)</w:t>|(\t|\n)", p, flags=re.S))
        paras.append(html.unescape(t))
    return "\n\n".join(x for x in paras if x.strip()), max(1, len(paras) // 40)


def _rtf(raw: str) -> str:
    t = re.sub(r"\\par[d]?\b", "\n\n", raw)
    t = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252", "replace"), t)
    t = re.sub(r"\{\\\*[^{}]*\}", "", t)
    t = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", t)
    return re.sub(r"[{}]", "", t)


def _to_html(text: str, legal: bool) -> str:
    text = text.replace("\r\n", "\n").replace("\x0c", "\n\n")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    out = []
    for b in blocks:
        lines = [ln.strip() for ln in b.split("\n") if ln.strip()]
        joined = " ".join(lines)                      # re-flow lines that were wrapped by the page
        esc = html.escape(joined)
        if legal and len(joined) < 90 and joined.upper() == joined and re.search(r"[A-Z]", joined):
            out.append(f"<h3>{esc}</h3>")
        else:
            out.append(f"<p>{esc}</p>")
    return "".join(out)


def parse(filename: str, data: bytes, force_ocr=False, ocr_lang="eng", legal=False) -> dict:
    if len(data) > MAX_BYTES:
        raise ParseError(f"This file is {len(data) // (1024 * 1024)} MB; the limit is {MAX_BYTES // (1024 * 1024)} MB.")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    lang = _lang(ocr_lang)
    pages, scanned = 1, False
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / f"upload.{ext or 'bin'}"
        path.write_bytes(data)
        if ext == "txt":
            text = data.decode("utf-8", "replace")
        elif ext == "rtf":
            text = _rtf(data.decode("latin-1"))
        elif ext == "docx":
            text, pages = _docx(path)
        elif ext == "doc":
            raise ParseError("Old .doc files can't be read. Open it in Word and save it as .docx, then import that.")
        elif ext == "pdf":
            text, pages, scanned = _pdf(path, force_ocr, lang)
        elif ext in ("png", "jpg", "jpeg", "webp", "tiff", "tif"):
            text, scanned = _ocr_image(path, lang), True
        else:
            raise ParseError("Unsupported file type. Use PDF, Word (.docx), text, RTF or an image.")
    if not re.search(r"\w", text):
        raise ParseError("No text could be found in this file." + (" It may be a blank or very low-quality scan." if scanned else ""))
    plain = re.sub(r"\n{3,}", "\n\n", text).strip()
    title = Path(filename).stem[:120]
    return {"content": _to_html(plain, legal), "plainText": plain,
            "metadata": {"title": title, "pageCount": pages, "isScanned": scanned, "wordCount": len(plain.split())}}
