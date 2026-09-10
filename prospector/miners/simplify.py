import re
from html import unescape
from datetime import datetime

from prospector.core.config import Color
from prospector.core.utils import fetch_text
from prospector.miners.base import is_blacklisted

SIMPLIFY_NEW_GRAD_URL = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"

FAST_ATS_DOMAINS = [
    "ashbyhq.com",
    "greenhouse.io",
    "lever.co",
    "workable.com",
    "bamboohr.com"
]

def mine_simplify(query=None, remote_only=False, fast_ats_only=True, max_results=50):
    """
    Minera vagas ativas de New Grad / Junior / Entry-Level do repositório SimplifyJobs/New-Grad-Positions.
    Filtra automaticamente cargos ativos em ATS de etapa única (Ashby, Greenhouse, Lever).
    """
    print(f"{Color.CYAN}🔍 Minerando vagas New Grad / Associate do SimplifyJobs (GitHub dev)...{Color.RESET}")
    content = fetch_text(SIMPLIFY_NEW_GRAD_URL)
    if not content:
        print(f"{Color.RED}❌ Não foi possível carregar o README de SimplifyJobs.{Color.RESET}")
        return []

    # Ignora as seções de vagas inativas (<details><summary>🗃️ Inactive roles...</details>)
    active_content = re.sub(r"<details>.*?</details>", "", content, flags=re.DOTALL)
    trs = re.findall(r"<tr>(.*?)</tr>", active_content, re.DOTALL)

    leads = []
    prev_company = ""

    for r in trs:
        tds = re.findall(r"<td.*?>(.*?)</td>", r, re.DOTALL)
        if len(tds) < 4:
            continue

        comp_raw = re.sub(r"<[^>]+>", "", tds[0]).strip()
        role_text = re.sub(r"<[^>]+>", "", tds[1]).strip()
        loc_text = re.sub(r"<br\s*/?>", " / ", tds[2])
        loc_text = re.sub(r"<[^>]+>", "", loc_text).strip()

        # Extrai links de aplicação
        links = re.findall(r'href=[\"\']([^\"\']+)[\"\']', tds[3])
        app_url = ""
        for l in links:
            if "simplify.jobs/p/" not in l:
                app_url = l
                break
        if not app_url and links:
            app_url = links[0]

        age = re.sub(r"<[^>]+>", "", tds[4]).strip() if len(tds) > 4 else ""

        # Trata empresa herdada (quando tem ↳)
        comp_clean = unescape(comp_raw).replace("🔥", "").strip()
        if comp_clean == "↳" or not comp_clean:
            company = prev_company
        else:
            company = comp_clean
            prev_company = comp_clean

        title = unescape(role_text)
        location = unescape(loc_text)

        # Filtro de Fast ATS
        is_fast_ats = any(domain in app_url.lower() for domain in FAST_ATS_DOMAINS)
        if fast_ats_only and not is_fast_ats:
            continue

        # Filtro de Anti-Patterns (Workday, Taleo, Gupy, etc.)
        if is_blacklisted(app_url) and not is_fast_ats:
            continue

        # Filtro de Localização Remota (se requisitado)
        is_remote = any(k in location.lower() for k in ["remote", "anywhere", "latam", "brazil", "brasil"])
        if remote_only and not is_remote:
            continue

        # Filtro de Busca (Query)
        if query:
            q_lower = query.lower()
            text_search = f"{company} {title} {location}".lower()
            if q_lower not in text_search:
                continue

        fast_links = [app_url] if is_fast_ats else []
        
        leads.append({
            "source": f"Simplify NewGrad ({age})" if age else "Simplify NewGrad",
            "title": title,
            "company": company,
            "url": app_url,
            "location": location,
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "labels": ["New-Grad", "Simplify", location],
            "emails": [],
            "fast_links": fast_links,
            "raw_body": f"Vaga New Grad / Entry Level na {company}: {title}.\nLocalização: {location}\nIdade do anúncio: {age}\nLink direto ATS: {app_url}"
        })

        if len(leads) >= max_results:
            break

    print(f"{Color.GREEN}✅ {len(leads)} vagas qualificadas encontradas no SimplifyJobs!{Color.RESET}")
    return leads
