"""APIs publicas de job boards do Greenhouse."""
from prospector.adapters.miners.filters import clean_url, matches_query
from prospector.domain.lead import Lead, Region
from prospector.ports import SourceUnavailable

# automattic, posthog e supabase sairam do Greenhouse (a API responde erro).
DEFAULT_COMPANIES = ["canonical", "gitlab", "brex", "reddit", "elastic", "cloudflare"]

ENG_KEYWORDS = ["software engineer", "backend", "back-end", "systems engineer", "platform",
                "data engineer", "infrastructure", "python", "associate"]
NON_ENG_KEYWORDS = ["counsel", "account executive", "recruiter", "marketing", "sales", "finance", "analyst"]


def is_engineering_title(title):
    t = (title or "").lower()
    return any(k in t for k in ENG_KEYWORDS) and not any(k in t for k in NON_ENG_KEYWORDS)


class GreenhouseMiner:
    name = "greenhouse"
    label = "Greenhouse"

    def __init__(self, http, companies=None):
        self.http = http
        self.companies = companies or DEFAULT_COMPANIES
        self.warnings = []

    def mine(self, options):
        leads, self.warnings = [], []
        for comp in self.companies:
            data = self.http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{comp}/jobs")
            if not isinstance(data, dict) or "jobs" not in data:
                self.warnings.append(f"board '{comp}' indisponível")
                continue
            count = 0
            for job in data["jobs"]:
                title = job.get("title", "")
                location = ((job.get("location") or {}).get("name") or "").strip()
                if not is_engineering_title(title) or not matches_query(options.query, title):
                    continue
                name = comp.capitalize()
                url = clean_url(job.get("absolute_url", ""))
                leads.append(Lead(
                    company=name, title=f"{name} - {title}", source=f"Greenhouse ({name})", url=url,
                    region=Region.INTL, ats_links=[url] if url else [],
                    labels=["Greenhouse", "Fast-ATS", "International"], location=location,
                    posted_at=(job.get("updated_at") or "")[:10],
                    raw_body=f"Position at {name}: {title}. Location: {location or 'n/a'}.",
                ))
                count += 1
                if count >= options.limit:
                    break
        if len(self.warnings) == len(self.companies):
            raise SourceUnavailable("; ".join(self.warnings))
        return leads
