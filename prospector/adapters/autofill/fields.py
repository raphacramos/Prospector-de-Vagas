"""Classificacao dos campos do formulario pelo rotulo. Puro Python (testavel sem navegador)."""
import re
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FormField:
    pid: str                 # data-prospector-id atribuido no navegador
    tag: str                 # input | textarea | select
    type: str                # text, email, tel, file, checkbox, radio, url...
    label: str
    name: str = ""
    required: bool = False
    has_value: bool = False
    options: List[str] = field(default_factory=list)


# ordem importa: o primeiro padrao que casar define o significado
RULES = [
    ("resume", re.compile(r"\b(resume|résumé|curr[ií]culo|\bcv\b)", re.I)),
    ("cover_letter", re.compile(r"cover\s*letter|carta( de apresenta[cç][aã]o)?|motivation letter", re.I)),
    ("first_name", re.compile(r"first\s*name|given\s*name|primeiro nome|preferred (first )?name|name you.d prefer", re.I)),
    ("last_name", re.compile(r"last\s*name|family\s*name|surname|sobrenome", re.I)),
    ("full_name", re.compile(r"full\s*name|^\s*(name|nome)\s*\*?\s*$|nome completo|legal name", re.I)),
    ("email", re.compile(r"e-?mail", re.I)),
    ("phone", re.compile(r"phone|telefone|celular|mobile|whatsapp", re.I)),
    ("linkedin", re.compile(r"linked\s*in", re.I)),
    ("github", re.compile(r"git\s*hub", re.I)),
    ("website", re.compile(r"website|portfolio|portf[oó]lio|personal site|\bsite\b|other url|blog", re.I)),
    ("location", re.compile(r"^\s*(current\s*)?(location|city)\b|cidade|localiza[cç][aã]o|where are you (based|located)", re.I)),
    ("company", re.compile(r"^\s*(current\s*(company|employer)|empresa atual)", re.I)),
    ("country", re.compile(r"country of residence|^\s*country\b|pa[ií]s( de resid[eê]ncia)?", re.I)),
]

# Regras que valem mesmo em rotulos longos ou com "?" (o resto so em rotulos curtos,
# para nao responder "Voce ja trabalhou na empresa atual?" com o nome da empresa).
ALWAYS = {"resume", "cover_letter", "first_name"}

TEXT_TYPES = {"text", "email", "tel", "url", "search", "number", ""}
QUESTION_HINT = re.compile(r"\?|why|how|what|describe|tell us|explain|por que|como|qual|descreva|conte", re.I)


def _classify_text(text, f):
    looks_like_question = "?" in text or len(text.strip()) > 60
    for key, pattern in RULES:
        if looks_like_question and key not in ALWAYS:
            continue
        if pattern.search(text):
            if key == "resume" and f.type != "file" and f.tag != "textarea":
                continue  # "resume" num campo de texto costuma ser link; tratar como pergunta
            if key == "cover_letter" and f.type != "file" and f.tag != "textarea":
                continue
            if key not in ("resume", "cover_letter") and f.type == "file":
                continue
            return key
    return None


def classify(f: FormField) -> Optional[str]:
    """Usa o rotulo; o atributo name so desempata quando o rotulo nao diz nada."""
    key = _classify_text(f.label or "", f) if f.label else None
    if key is None and f.name:
        name = re.sub(r"[_\-\[\]]+", " ", f.name)
        key = _classify_text(name, f)
    return key


def profile_values(profile, master, package):
    """Valores fixos que o formulario pode pedir."""
    cand = profile.candidato
    contact = master.contact if master else None
    return {
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "full_name": profile.nome,
        "email": profile.email,
        "phone": str(cand.get("telefone") or (contact.phone if contact else "")),
        "linkedin": str(cand.get("linkedin") or ""),
        "github": str(cand.get("github") or ""),
        "website": str(cand.get("site") or cand.get("github") or ""),
        "location": str(cand.get("cidade") or (contact.location if contact else "")),
        "country": str(cand.get("pais") or ""),
        "company": str(master.experiences[0].company if master and master.experiences else ""),
        "resume": package.cv_pdf if package else "",
        "cover_letter": package.cover_letter if package else "",
    }


@dataclass
class FillPlan:
    fills: Dict[str, str] = field(default_factory=dict)       # pid -> texto
    files: Dict[str, str] = field(default_factory=dict)       # pid -> caminho
    questions: Dict[str, str] = field(default_factory=dict)   # pid -> rotulo (para a IA)
    manual: List[FormField] = field(default_factory=list)     # voce precisa preencher


def plan_fields(fields: List[FormField], values: Dict[str, str], cover_letter_path: str = "") -> FillPlan:
    plan = FillPlan()
    used = set()
    # "Name"/"Nome" ao lado de um campo de sobrenome e o primeiro nome
    has_last_name = any(classify(f) == "last_name" for f in fields)
    for f in fields:
        if f.has_value and f.type != "file":
            continue
        if f.type in ("hidden", "submit", "button", "password"):
            continue
        key = classify(f)
        if key == "resume" and f.type == "file" and values.get("resume"):
            if "resume" not in used:
                plan.files[f.pid] = values["resume"]
                used.add("resume")
            continue
        if key == "cover_letter":
            if f.type == "file" and cover_letter_path:
                plan.files[f.pid] = cover_letter_path
            elif f.tag == "textarea" and values.get("cover_letter"):
                plan.fills[f.pid] = values["cover_letter"]
            elif f.required:
                plan.manual.append(f)
            continue
        if key == "full_name" and has_last_name and re.fullmatch(r"\s*(name|nome)\s*\*?\s*", f.label, re.I):
            key = "first_name"
        if key and f.tag in ("input", "textarea") and f.type in TEXT_TYPES and values.get(key):
            plan.fills[f.pid] = values[key]
            continue
        if f.tag == "select" or f.type in ("checkbox", "radio", "file"):
            if f.required:
                plan.manual.append(f)
            continue
        if f.tag in ("input", "textarea") and f.label and (f.required or f.tag == "textarea" or QUESTION_HINT.search(f.label)):
            plan.questions[f.pid] = f.label
        elif f.required:
            plan.manual.append(f)
    return plan


def detect_ats(url):
    u = urlparse(url or "").netloc.lower()
    for name in ("greenhouse", "lever", "ashbyhq", "workable"):
        if name in u:
            return "ashby" if name == "ashbyhq" else name
    return "generic"


def application_url(url):
    """Leva direto ao formulario quando o ATS separa descricao e aplicacao."""
    ats = detect_ats(url)
    clean = (url or "").split("#")[0].rstrip("/")
    if ats == "lever" and not clean.endswith("/apply"):
        return clean + "/apply"
    if ats == "ashby" and not clean.endswith("/application"):
        return clean + "/application"
    return url
