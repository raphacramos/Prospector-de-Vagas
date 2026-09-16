"""Filtros e extratores compartilhados pelos mineradores."""
import html
import re
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ANTI_PATTERNS = [
    r"gupy\.io", r"kenoby\.com", r"workday\.com", r"myworkdayjobs\.com", r"taleo\.net",
    r"banco de talentos", r"cadastro de reserva",
]

FAST_ATS_PATTERNS = [
    r"https?://jobs\.ashbyhq\.com/[a-zA-Z0-9_\-.]+/[a-zA-Z0-9_\-]+",
    r"https?://boards\.greenhouse\.io/[a-zA-Z0-9_\-]+/jobs/[0-9]+",
    r"https?://job-boards\.greenhouse\.io/[a-zA-Z0-9_\-]+/jobs/[0-9]+",
    r"https?://jobs\.lever\.co/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+",
    r"https?://apply\.workable\.com/[a-zA-Z0-9_\-]+/j/[a-zA-Z0-9_\-]+",
]

FAST_ATS_DOMAINS = ["ashbyhq.com", "greenhouse.io", "lever.co", "workable.com", "bamboohr.com"]

EMAIL_REGEX = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]*[a-zA-Z]"

_IGNORED_EMAIL_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", "github.com", "users.noreply.github.com", "example.com")

REMOTE_KEYWORDS = ["remote", "remoto", "anywhere", "latam", "brazil", "brasil", "home office", "worldwide"]

_TRACKING_PARAMS = ("utm_", "ref", "gh_src")


def clean_html(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_blacklisted(text):
    """Anuncio direciona para portais de triagem demorada (Gupy, Workday...)."""
    text_lower = (text or "").lower()
    return any(re.search(p, text_lower) for p in ANTI_PATTERNS)


def is_fast_ats(url):
    return any(d in (url or "").lower() for d in FAST_ATS_DOMAINS)


def is_remote(location):
    loc = (location or "").lower()
    return any(k in loc for k in REMOTE_KEYWORDS)


def clean_url(url):
    """Remove parametros de rastreamento (utm_*, ref) para a deduplicacao funcionar."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith(_TRACKING_PARAMS)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def extract_contacts(text):
    """Extrai e-mails e links de ATS de etapa unica (ambos sem duplicatas, em ordem)."""
    text = html.unescape(text or "")
    emails = []
    for e in re.findall(EMAIL_REGEX, text):
        if not e.lower().endswith(_IGNORED_EMAIL_SUFFIXES) and e not in emails:
            emails.append(e)
    links = []
    for pat in FAST_ATS_PATTERNS:
        for link in re.findall(pat, text):
            link = clean_url(link)
            if link not in links:
                links.append(link)
    return emails, links


def matches_query(query, *fields):
    if not query:
        return True
    haystack = " ".join(f or "" for f in fields).lower()
    return query.lower() in haystack


def date_from_age(age, today=None):
    """Converte idade do anuncio ('0d', '3d', '2w', '1mo') em data ISO. '' se nao reconhecer."""
    m = re.match(r"^\s*(\d+)\s*(h|d|w|mo)\s*$", age or "")
    if not m:
        return ""
    n, unit = int(m.group(1)), m.group(2)
    days = {"h": 0, "d": n, "w": 7 * n, "mo": 30 * n}[unit]
    return ((today or date.today()) - timedelta(days=days)).isoformat()
