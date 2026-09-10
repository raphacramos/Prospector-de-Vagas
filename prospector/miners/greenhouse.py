from datetime import datetime
from prospector.core.config import Color
from prospector.core.utils import fetch_json

GREENHOUSE_COMPANIES = [
    "canonical", "gitlab", "brex", "automattic", "reddit", 
    "elastic", "posthog", "supabase", "cloudflare"
]

def mine_greenhouse(query="Python", companies=None):
    if companies is None:
        companies = GREENHOUSE_COMPANIES
    print(f"{Color.CYAN}🔍 Minerando APIs públicas de ATS Ágeis (Greenhouse Startups & Tech)...{Color.RESET}")
    results = []
    
    for comp in companies:
        url = f"https://boards-api.greenhouse.io/v1/boards/{comp}/jobs"
        data = fetch_json(url)
        if not data or not data.get("jobs"):
            continue

        for j in data.get("jobs", []):
            title = j.get("title", "")
            title_lower = title.lower()

            is_eng = any(k in title_lower for k in [
                "software engineer", "backend", "systems engineer", "platform",
                "data engineer", "infrastructure", "python", "associate"
            ])
            is_non_eng = any(k in title_lower for k in ["counsel", "account executive", "recruiter", "marketing", "sales", "finance", "analyst"])

            if not is_eng or is_non_eng:
                continue

            results.append({
                "source": f"Greenhouse ({comp.capitalize()})",
                "title": f"{comp.capitalize()} - {title}",
                "company": comp.capitalize(),
                "url": j.get("absolute_url", ""),
                "created_at": j.get("updated_at", "")[:10] if j.get("updated_at") else datetime.now().strftime("%Y-%m-%d"),
                "labels": ["Greenhouse", "Remote/Fast-ATS", "International"],
                "emails": [],
                "fast_links": [j.get("absolute_url", "")],
                "raw_body": f"Position at {comp.capitalize()}: {title}. Apply via quick Greenhouse board."
            })
    return results
