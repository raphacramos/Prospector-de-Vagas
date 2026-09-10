import urllib.parse
from prospector.core.config import Color
from prospector.core.utils import clean_html, fetch_json
from prospector.miners.base import extract_contacts

def mine_hacker_news(query="Python", hits=25):
    print(f"{Color.CYAN}🔍 Buscando no 'Ask HN: Who is hiring?' do mês...{Color.RESET}")
    search_url = "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&query=Who%20is%20hiring&hitsPerPage=1"
    story_data = fetch_json(search_url)
    if not story_data or not story_data.get("hits"):
        return []

    story = story_data["hits"][0]
    story_id = story["objectID"]
    story_title = clean_html(story["title"])

    comments_url = f"https://hn.algolia.com/api/v1/search?tags=comment,story_{story_id}&query={urllib.parse.quote(query + ' Remote')}&hitsPerPage={hits}"
    comments_data = fetch_json(comments_url)
    if not comments_data or not comments_data.get("hits"):
        return []

    results = []
    for hit in comments_data.get("hits", []):
        raw_html = hit.get("comment_text", "")
        clean_text = clean_html(raw_html)
        lines = [l.strip() for l in clean_text.split(".") if l.strip()]
        first_sentence = lines[0] if lines else "HN Opportunity"

        parts = [p.strip() for p in first_sentence.split("|")]
        company = parts[0] if len(parts) > 1 else "Startup HN"
        role = parts[1] if len(parts) > 1 else first_sentence[:50]
        emails, fast_links = extract_contacts(raw_html)

        labels = ["Remote", "International", "HN"]
        if any(k in clean_text.lower() for k in ["yc", "y combinator", "yc s", "yc w"]):
            labels.append("YC Startup")

        results.append({
            "source": f"Hacker News ({story_title[:22]}...)",
            "title": f"{company} - {role}",
            "company": company,
            "url": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            "created_at": hit.get("created_at", "")[:10],
            "labels": labels,
            "emails": emails,
            "fast_links": fast_links,
            "raw_body": clean_text
        })
    return results
