"""API publica de vagas do Lever (api.lever.co/v0/postings)."""
from datetime import datetime, timezone

from prospector.adapters.miners.filters import (
    clean_url, is_engineering_title, is_network_failure, matches_query,
)
from prospector.domain.lead import Lead, Region
from prospector.ports import SourceUnavailable

DEFAULT_COMPANIES = ["spotify", "palantir", "zoox", "binance"]
API = "https://api.lever.co/v0/postings/{company}?mode=json"


def _date_from_ms(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


class LeverMiner:
    name = "lever"
    label = "Lever"

    def __init__(self, http, companies=None):
        self.http = http
        self.companies = companies or DEFAULT_COMPANIES
        self.warnings = []

    def mine(self, options):
        leads, self.warnings = [], []
        for company in self.companies:
            data = self.http.get_json(API.format(company=company))
            if not isinstance(data, list):
                if is_network_failure(self.http):
                    raise SourceUnavailable(f"sem acesso a api.lever.co ({self.http.last_error})")
                self.warnings.append(f"empresa '{company}' não encontrada no Lever")
                continue
            count = 0
            for job in data:
                title = job.get("text", "")
                cats = job.get("categories") or {}
                if not is_engineering_title(title):
                    continue
                if not matches_query(options.query, title, cats.get("team"), cats.get("department")):
                    continue
                name = company.capitalize()
                url = clean_url(job.get("hostedUrl", ""))
                location = cats.get("location") or ""
                if job.get("workplaceType") == "remote" and "remote" not in location.lower():
                    location = f"{location} (Remote)".strip()
                leads.append(Lead(
                    company=name, title=f"{name} - {title}", source=f"Lever ({name})", url=url,
                    region=Region.INTL, ats_links=[url] if url else [],
                    labels=["Lever", "Fast-ATS", "International"], location=location,
                    posted_at=_date_from_ms(job.get("createdAt")),
                    raw_body=(job.get("descriptionPlain") or "")[:4000],
                ))
                count += 1
                if count >= options.limit:
                    break
        if self.companies and len(self.warnings) == len(self.companies):
            raise SourceUnavailable("; ".join(self.warnings))
        return leads
