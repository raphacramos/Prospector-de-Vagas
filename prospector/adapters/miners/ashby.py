"""API publica de job boards do Ashby (api.ashbyhq.com/posting-api)."""
from prospector.adapters.miners.filters import (
    clean_url, is_engineering_title, is_network_failure, matches_query,
)
from prospector.domain.lead import Lead, Region
from prospector.ports import SourceUnavailable

DEFAULT_ORGS = ["posthog", "supabase", "linear", "ramp", "replit", "notion"]
API = "https://api.ashbyhq.com/posting-api/job-board/{org}"


class AshbyMiner:
    name = "ashby"
    label = "Ashby"

    def __init__(self, http, orgs=None):
        self.http = http
        self.orgs = orgs or DEFAULT_ORGS
        self.warnings = []

    def mine(self, options):
        leads, self.warnings = [], []
        for org in self.orgs:
            data = self.http.get_json(API.format(org=org))
            if not isinstance(data, dict) or "jobs" not in data:
                if is_network_failure(self.http):
                    raise SourceUnavailable(f"sem acesso a api.ashbyhq.com ({self.http.last_error})")
                self.warnings.append(f"board '{org}' indisponível")
                continue
            count = 0
            for job in data["jobs"]:
                title = job.get("title", "")
                if job.get("isListed") is False or not is_engineering_title(title):
                    continue
                if not matches_query(options.query, title, job.get("department"), job.get("team")):
                    continue
                name = org.capitalize()
                url = clean_url(job.get("jobUrl") or job.get("applyUrl") or "")
                location = job.get("location") or ""
                if job.get("isRemote") and "remote" not in location.lower():
                    location = f"{location} (Remote)".strip()
                leads.append(Lead(
                    company=name, title=f"{name} - {title}", source=f"Ashby ({name})", url=url,
                    region=Region.INTL, ats_links=[url] if url else [],
                    labels=["Ashby", "Fast-ATS", "International"], location=location,
                    posted_at=(job.get("publishedAt") or "")[:10],
                    raw_body=(job.get("descriptionPlain") or "")[:4000],
                ))
                count += 1
                if count >= options.limit:
                    break
        if self.orgs and len(self.warnings) == len(self.orgs):
            raise SourceUnavailable("; ".join(self.warnings))
        return leads
