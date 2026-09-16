"""Leitura do curriculo original (PDF, DOCX, TXT/MD) para a importacao."""
import base64
import os
import re
import zipfile
from xml.etree import ElementTree

from prospector.adapters.llm_anthropic import pdf_block, text_block

MAX_PDF_BYTES = 20 * 1024 * 1024
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ResumeFileError(Exception):
    pass


def docx_text(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ResumeFileError(f"DOCX inválido: {e}")
    root = ElementTree.fromstring(xml)
    lines = []
    for para in root.iter(f"{_W}p"):
        text = "".join(t.text or "" for t in para.iter(f"{_W}t"))
        if para.find(f"./{_W}pPr/{_W}numPr") is not None and text:
            text = "• " + text
        lines.append(text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def content_blocks(path):
    """Converte o arquivo em blocos para a IA. PDF vai inteiro (a IA le layout e texto)."""
    if not os.path.exists(path):
        raise ResumeFileError(f"arquivo não encontrado: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        size = os.path.getsize(path)
        if size > MAX_PDF_BYTES:
            raise ResumeFileError("PDF maior que 20 MB")
        with open(path, "rb") as f:
            return [pdf_block(base64.b64encode(f.read()).decode("ascii"))]
    if ext == ".docx":
        return [text_block(docx_text(path))]
    if ext in (".txt", ".md"):
        with open(path, encoding="utf-8") as f:
            return [text_block(f.read())]
    if ext == ".doc":
        raise ResumeFileError("formato .doc antigo não é suportado; salve como .docx ou PDF")
    raise ResumeFileError(f"formato não suportado: {ext} (use PDF, DOCX, TXT ou MD)")
