"""Extrai titulo e texto da Job Description a partir da URL da vaga."""
import json
import re

from prospector.adapters.miners.filters import clean_html


class JobDescriptionFetcher:
    def __init__(self, http):
        self.http = http

    def fetch(self, url):
        """Retorna (titulo, texto). ('', '') se nao conseguir."""
        if not url:
            return "", ""
        m = re.search(r"greenhouse\.io/([^/?#]+)/jobs/([0-9]+)", url)
        if m:
            data = self.http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}")
            if isinstance(data, dict) and data.get("content"):
                return data.get("title", ""), clean_html(data["content"])

        m = re.search(r"jobs\.lever\.co/([^/?#]+)/([a-zA-Z0-9_\-]+)", url)
        if m:
            data = self.http.get_json(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}")
            if isinstance(data, dict) and (data.get("descriptionPlain") or data.get("description")):
                parts = [data.get("descriptionPlain") or clean_html(data.get("description", ""))]
                parts += [f"{l.get('text', '')} {clean_html(l.get('content', ''))}" for l in data.get("lists", [])]
                parts.append(data.get("additionalPlain", ""))
                return data.get("text", ""), " ".join(p for p in parts if p).strip()

        raw_html = self.http.get_text(url)
        if not raw_html:
            return "", ""
        posting = self._json_ld_posting(raw_html)
        if posting:
            return posting.get("title", ""), clean_html(posting.get("description", ""))
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
        return "", clean_html(body)

    @staticmethod
    def _json_ld_posting(raw_html):
        for block in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", raw_html,
                                re.DOTALL | re.IGNORECASE):
            try:
                data = json.loads(block.strip())
            except ValueError:
                continue
            for item in data if isinstance(data, list) else [data]:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    return item
        return None
