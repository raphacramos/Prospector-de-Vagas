"""GitHub Issues de repositorios de vagas brasileiros (backend-br, datascience-br...)."""
import re

from prospector.adapters.miners.filters import (
    clean_html, clean_url, extract_contacts, is_blacklisted, matches_query,
)
from prospector.domain.lead import Lead, Region
from prospector.ports import SourceUnavailable

DEFAULT_REPOS = ["backend-br/vagas", "datascience-br/vagas", "react-brasil/vagas"]
UNKNOWN_COMPANY = "Empresa não identificada"

# Antes o filtro usava a substring "eng", que casava com "english", "length" etc.
BACKEND_PATTERNS = [
    r"\bpython\b", r"\bback-?end\b", r"\bdados\b", r"\bdata (?:engineer|platform|pipeline)",
    r"\bengenh\w* de dados\b", r"\bnode(?:\.?js)?\b", r"\bpostgres(?:ql)?\b",
    r"\bdjango\b", r"\bfastapi\b", r"\bflask\b",
]
JUNIOR_KEYWORDS = ["júnior", "junior", "estágio", "estagio", "entry level", "trainee", "associate", "pleno"]

# Issues abertas com o template sem preencher.
PLACEHOLDER_TITLE = re.compile(r"nome\s*da\s*empresa", re.IGNORECASE)
TEMPLATE_SENTENCES = [
    "informe a descrição da empresa",
    "informe a descrição da vaga",
    "informe se é remoto, híbrido ou presencial",
    "informe os requisitos obrigatórios",
]


def is_backend_role(text):
    text_lower = (text or "").lower()
    return any(re.search(p, text_lower) for p in BACKEND_PATTERNS)


def is_unfilled_template(title, body):
    if PLACEHOLDER_TITLE.search(title or ""):
        return True
    body_lower = (body or "").lower()
    return sum(s in body_lower for s in TEMPLATE_SENTENCES) >= 2


_COMPANY_SEPARATORS = re.compile(r"\s[-–—|]\s")
_COMPANY_PREFIX = re.compile(r"\s(?:na|no|@|at)\s+", re.IGNORECASE)
# Termos que so aparecem em prosa sobre a equipe/area, nunca no nome de uma empresa real
# (diferente de conectivos como "of"/"do", que aparecem em nomes reais: "Bank of America").
_PROSE_HINTS = re.compile(r"\b(?:squad|time|área|area|setor|departamento|equipe)\b", re.IGNORECASE)
MAX_COMPANY_WORDS = 6


def _clean_company(text):
    """Remove ruido de local no final ('(Remoto)', '[SP]') sem corromper o nome."""
    text = re.sub(r"\s*[\(\[][^)\]]*[\)\]]\s*$", "", text)
    return text.strip(" -|–—").strip()


def _looks_like_company(candidate):
    """Primeira palavra parece nome proprio: maiuscula inicial ('Acme') ou minuscula seguida
    de maiuscula ('iFood', 'eBay'). Prosa comum ('squad', 'a', 'de') fica de fora."""
    first = candidate.split()[0] if candidate else ""
    return bool(first[:1].isupper() or re.match(r"^[a-z]+[A-Z]", first))


def parse_title(title):
    """'[Remoto] Dev Backend na Acme' -> ('Dev Backend na Acme', 'Remoto', 'Acme').

    Separadores explicitos (-, |, travessao) sao o formato do template e tem prioridade.
    "na/no/@/at" e so um fallback: usa a ultima ocorrencia (a mais proxima do nome real) e
    descarta a captura quando parece prosa (minuscula, com conectivos, ou longa demais).
    """
    brackets = re.findall(r"^\s*\[([^\]]*)\]", title or "")
    location = brackets[0].strip() if brackets else ""
    rest = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", title or "").strip()

    company = ""
    parts = _COMPANY_SEPARATORS.split(rest)
    if len(parts) > 1:
        company = _clean_company(parts[-1])
    else:
        seps = list(_COMPANY_PREFIX.finditer(rest))
        if seps:
            candidate = _clean_company(rest[seps[-1].end():])
            if (candidate and len(candidate.split()) <= MAX_COMPANY_WORDS
                    and _looks_like_company(candidate) and not _PROSE_HINTS.search(candidate)):
                company = candidate
    return rest, location, company


class GithubMiner:
    name = "github"
    label = "GitHub Issues"

    def __init__(self, http, repos=None):
        self.http = http
        self.repos = repos or DEFAULT_REPOS

    def mine(self, options):
        leads, failures = [], []
        for repo in self.repos:
            data = self.http.get_json(
                f"https://api.github.com/repos/{repo}/issues?state=open&per_page={min(options.limit, 100)}"
            )
            if not isinstance(data, list):
                failures.append(f"{repo}: {getattr(self.http, 'last_error', None) or 'resposta inesperada'}")
                continue
            for issue in data:
                lead = self._to_lead(repo, issue, options)
                if lead:
                    leads.append(lead)
        if failures and len(failures) == len(self.repos):
            raise SourceUnavailable("; ".join(failures))
        return leads

    def _to_lead(self, repo, issue, options):
        if "pull_request" in issue:
            return None
        title = clean_html(issue.get("title", ""))
        body = issue.get("body") or ""
        labels = [l.get("name", "") for l in issue.get("labels", []) if l.get("name")]
        full_text = f"{title} {body} {' '.join(labels)}"
        lower = full_text.lower()

        if is_unfilled_template(title, body):
            return None
        if not options.all_levels and not any(k in lower for k in JUNIOR_KEYWORDS):
            return None
        if not is_backend_role(full_text):
            return None
        if is_blacklisted(body) and not ("email" in lower or "e-mail" in lower):
            return None
        if not matches_query(options.query, full_text):
            return None

        _, location, company = parse_title(title)
        if not company:
            company = UNKNOWN_COMPANY
            labels.append("empresa-nao-identificada")
        emails, ats_links = extract_contacts(body)
        return Lead(
            company=company, title=title, source=f"GitHub ({repo})",
            url=clean_url(issue.get("html_url", "")), region=Region.BR,
            emails=emails, ats_links=ats_links, labels=labels, location=location,
            posted_at=(issue.get("created_at") or "")[:10], raw_body=clean_html(body),
        )
