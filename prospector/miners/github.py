import re
from prospector.core.config import Color
from prospector.core.utils import clean_html, fetch_json
from prospector.miners.base import is_blacklisted, extract_contacts

# Antes o filtro usava a substring "eng", que casava com "english", "length" etc.
BACKEND_PATTERNS = [
    r"\bpython\b", r"\bback-?end\b", r"\bdados\b", r"\bdata (?:engineer|platform|pipeline)",
    r"\bengenh\w* de dados\b", r"\bnode(?:\.?js)?\b", r"\bpostgres(?:ql)?\b",
    r"\bdjango\b", r"\bfastapi\b", r"\bflask\b",
]


def is_backend_role(text):
    text_lower = (text or "").lower()
    return any(re.search(p, text_lower) for p in BACKEND_PATTERNS)


def mine_github(repos=None, max_per_repo=50, junior_only=True, query=None):
    if repos is None:
        repos = ["backend-br/vagas", "datascience-br/vagas", "react-brasil/vagas"]
    results = []
    print(f"{Color.CYAN}🔍 Minerando GitHub Issues em {', '.join(repos)}...{Color.RESET}")

    for repo in repos:
        url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page={max_per_repo}"
        data = fetch_json(url)
        if not data or not isinstance(data, list):
            continue

        for issue in data:
            if "pull_request" in issue:
                continue
            title = clean_html(issue.get("title", ""))
            body = issue.get("body", "") or ""
            labels = [l.get("name", "") for l in issue.get("labels", [])]
            labels_str = " ".join(labels)
            full_text = f"{title} {body} {labels_str}"

            is_junior = any(k in full_text.lower() for k in ["júnior", "junior", "estágio", "estagio", "entry level", "trainee", "associate", "pleno"])
            is_python_backend = is_backend_role(full_text)

            if junior_only and not is_junior:
                continue
            if not is_python_backend:
                continue
            if query and query.lower() not in full_text.lower():
                continue
            if is_blacklisted(body) and not ("email" in body.lower() or "e-mail" in body.lower()):
                continue

            emails, fast_links = extract_contacts(body)
            company = repo.split("/")[0]
            if "[" in title and "]" in title:
                parts = re.findall(r"\[(.*?)\]", title)
                for p in parts:
                    if not any(k in p.lower() for k in ["remoto", "híbrido", "hibrido", "sp", "rj", "clt", "pj", "vaga", "são paulo"]):
                        company = p.strip()
                        break
            elif " na " in title.lower() or " no " in title.lower():
                parts = re.split(r"\s+na\s+|\s+no\s+", title, flags=re.IGNORECASE)
                if len(parts) > 1:
                    company = parts[-1].strip()

            results.append({
                "source": f"GitHub ({repo})",
                "title": title,
                "company": company,
                "url": issue.get("html_url", ""),
                "created_at": issue.get("created_at", "")[:10],
                "labels": labels,
                "emails": emails,
                "fast_links": fast_links,
                "raw_body": clean_html(body)
            })
    return results
