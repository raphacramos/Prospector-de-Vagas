import re

ANTI_PATTERNS = [
    r"gupy\.io",
    r"kenoby\.com",
    r"workday\.com",
    r"myworkdayjobs\.com",
    r"taleo\.net",
    r"banco de talentos",
    r"cadastro de reserva"
]

FAST_ATS_PATTERNS = [
    r"https?://jobs\.ashbyhq\.com/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+",
    r"https?://boards\.greenhouse\.io/[a-zA-Z0-9_\-]+/jobs/[0-9]+",
    r"https?://job-boards\.greenhouse\.io/[a-zA-Z0-9_\-]+/jobs/[0-9]+",
    r"https?://jobs\.lever\.co/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+",
    r"https?://apply\.workable\.com/[a-zA-Z0-9_\-]+/j/[a-zA-Z0-9_\-]+"
]

EMAIL_REGEX = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

def is_blacklisted(text):
    """Verifica se o anúncio direciona para portais de triagem demorada (Gupy, Workday)."""
    text_lower = text.lower()
    for pattern in ANTI_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def extract_contacts(text):
    """Extrai e-mails de engenharia e links de ATS de etapa única."""
    emails = list(set(re.findall(EMAIL_REGEX, text)))
    filtered_emails = [e for e in emails if not e.endswith((".png", ".jpg", "github.com", "users.noreply.github.com"))]
    fast_links = []
    for pat in FAST_ATS_PATTERNS:
        fast_links.extend(re.findall(pat, text))
    return filtered_emails, list(set(fast_links))
