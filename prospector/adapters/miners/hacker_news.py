"""Thread mensal 'Ask HN: Who is hiring?' via API da Algolia."""
import re
import urllib.parse

from prospector.adapters.miners.filters import clean_html, clean_url, extract_contacts
from prospector.domain.lead import Lead, Region
from prospector.ports import SourceUnavailable

STORY_URL = ("https://hn.algolia.com/api/v1/search_by_date"
             "?tags=story,author_whoishiring&query=Who%20is%20hiring&hitsPerPage=5")


def parse_header(comment_html):
    """Primeiro paragrafo no formato 'Empresa | Cargo | Local | ...'."""
    first = re.split(r"<p>", comment_html or "", maxsplit=1)[0]
    parts = [p.strip() for p in clean_html(first).split("|") if p.strip()]
    if len(parts) >= 2:
        location = next((p for p in parts[2:] if re.search(r"remote|onsite|hybrid|,", p, re.I)), "")
        return parts[0], parts[1], location
    text = parts[0] if parts else ""
    return "Startup HN", text[:80] or "HN Opportunity", ""


class HackerNewsMiner:
    name = "hn"
    label = "Hacker News (Who is hiring)"

    def __init__(self, http):
        self.http = http

    def mine(self, options):
        stories = self.http.get_json(STORY_URL)
        hits = (stories or {}).get("hits") or []
        story = next((h for h in hits if "who is hiring" in (h.get("title") or "").lower()), None)
        if not story:
            raise SourceUnavailable(getattr(self.http, "last_error", None) or "thread do mês não encontrada")
        story_id = story["objectID"]
        story_title = clean_html(story.get("title", ""))

        query = urllib.parse.quote(f"{options.query or 'Python'} Remote")
        comments = self.http.get_json(
            f"https://hn.algolia.com/api/v1/search?tags=comment,story_{story_id}"
            f"&query={query}&hitsPerPage={options.limit}"
        )
        if comments is None:
            raise SourceUnavailable(getattr(self.http, "last_error", None) or "falha ao buscar comentários")

        leads = []
        for hit in comments.get("hits", []):
            if str(hit.get("parent_id")) != str(story_id):
                continue  # respostas a outros comentarios nao sao anuncios
            raw_html = hit.get("comment_text") or ""
            company, role, location = parse_header(raw_html)
            clean_text = clean_html(raw_html)
            emails, ats_links = extract_contacts(raw_html)
            labels = ["International", "HN"]
            if re.search(r"\bremote\b", location or clean_text[:200], re.I):
                labels.append("Remote")
            if re.search(r"\b(yc|y combinator)\b", clean_text, re.I):
                labels.append("YC Startup")
            leads.append(Lead(
                company=company, title=f"{company} - {role}", source=f"Hacker News ({story_title[:30]})",
                url=clean_url(f"https://news.ycombinator.com/item?id={hit.get('objectID')}"),
                region=Region.INTL, emails=emails, ats_links=ats_links, labels=labels,
                location=location, posted_at=(hit.get("created_at") or "")[:10], raw_body=clean_text,
            ))
        return leads
