"""Tabela de vagas New Grad do repositorio SimplifyJobs/New-Grad-Positions."""
import re
from html import unescape

from prospector.adapters.miners.filters import (
    clean_url, date_from_age, is_blacklisted, is_fast_ats, matches_query,
)
from prospector.domain.lead import Lead, Region
from prospector.ports import SourceUnavailable

SIMPLIFY_NEW_GRAD_URL = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"


def _strip_tags(s):
    return unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def parse_rows(markdown):
    """Extrai (empresa, cargo, local, url, idade) das tabelas ativas (ignora <details> de inativas)."""
    active = re.sub(r"<details>.*?</details>", "", markdown, flags=re.DOTALL)
    prev_company = ""
    for row in re.findall(r"<tr>(.*?)</tr>", active, re.DOTALL):
        tds = re.findall(r"<td.*?>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 4:
            continue
        company = _strip_tags(tds[0]).replace("🔥", "").strip()
        if company in ("↳", ""):
            company = prev_company
        else:
            prev_company = company
        location = _strip_tags(re.sub(r"<br\s*/?>", " / ", tds[2]))
        links = re.findall(r'href=["\']([^"\']+)["\']', tds[3])
        app_url = next((l for l in links if "simplify.jobs/p/" not in l), links[0] if links else "")
        age = _strip_tags(tds[4]) if len(tds) > 4 else ""
        yield company, _strip_tags(tds[1]), location, unescape(app_url), age


class SimplifyMiner:
    name = "simplify"
    label = "SimplifyJobs New Grad"

    def __init__(self, http, url=SIMPLIFY_NEW_GRAD_URL):
        self.http = http
        self.url = url

    def mine(self, options):
        content = self.http.get_text(self.url)
        if not content:
            raise SourceUnavailable(getattr(self.http, "last_error", None) or "README indisponível")
        leads = []
        for company, title, location, app_url, age in parse_rows(content):
            fast = is_fast_ats(app_url)
            if not options.all_ats and not fast:
                continue
            if is_blacklisted(app_url) and not fast:
                continue
            if not matches_query(options.query, company, title, location):
                continue
            url = clean_url(app_url)
            leads.append(Lead(
                company=company, title=title,
                source=f"Simplify NewGrad ({age})" if age else "Simplify NewGrad",
                url=url, region=Region.INTL, ats_links=[url] if fast else [],
                labels=["New-Grad", "Simplify"], location=location, posted_at=date_from_age(age),
                raw_body=(f"Vaga New Grad / Entry Level na {company}: {title}.\n"
                          f"Localização: {location}\nIdade do anúncio: {age}\nLink direto ATS: {url}"),
            ))
            if len(leads) >= options.limit:
                break
        return leads
