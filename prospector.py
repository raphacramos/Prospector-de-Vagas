#!/usr/bin/env python3
"""
Prospector CLI - Sistema de Mineração Técnica & Funil de Prospecção Ágil
Desenvolvido para Raphael Ramos com base na estratégia de Engenharia de Software.
"""

import sys
import os
import json
import re
import sqlite3
import argparse
import ssl
import html
from datetime import datetime, timedelta
import urllib.request
import urllib.parse

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prospector.db")

class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    DIM = "\033[2m"

def clean_html(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def fetch_json(url, headers=None, timeout=10):
    if headers is None:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        try:
            import subprocess
            cmd = ["curl", "-s", "-H", f"User-Agent: {headers.get('User-Agent', '')}", url]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout)
        except Exception:
            pass
        return None

# --- BANCO DE DADOS LOCAL (FUNIL DE CANDIDATURAS) ---

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            source TEXT NOT NULL,
            url TEXT UNIQUE,
            contact_info TEXT,
            raw_body TEXT,
            status TEXT DEFAULT 'minerado', -- minerado, conexao_enviada, mensagem_enviada, aguardando_followup, resposta, entrevista, descartada
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            contacted_at TIMESTAMP,
            followup_due_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# --- FILTRAGEM ANTI-GUPY E EXTRAÇÃO DE CONTATOS ---

ANTI_PATTERNS = [
    r"gupy\.io",
    r"kenoby\.com",
    r"workday\.com",
    r"myworkdayjobs\.com",
    r"taleo\.net",
    r"banco de talentos",
    r"cadastro de reserva"
]

FAST_ATS_PATTERNS = [
    r"https?://jobs\.ashbyhq\.com/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+",
    r"https?://boards\.greenhouse\.io/[a-zA-Z0-9_\-]+/jobs/[0-9]+",
    r"https?://jobs\.lever\.co/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+",
    r"https?://apply\.workable\.com/[a-zA-Z0-9_\-]+/j/[a-zA-Z0-9_\-]+"
]

EMAIL_REGEX = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

def is_blacklisted(text):
    text_lower = text.lower()
    for pattern in ANTI_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def extract_contacts(text):
    emails = list(set(re.findall(EMAIL_REGEX, text)))
    filtered_emails = [e for e in emails if not e.endswith((".png", ".jpg", "github.com", "users.noreply.github.com"))]
    
    fast_links = []
    for pat in FAST_ATS_PATTERNS:
        fast_links.extend(re.findall(pat, text))
    
    return filtered_emails, list(set(fast_links))

# --- SCRAPERS ---

def mine_github(repos=None, max_per_repo=30, junior_only=True):
    if repos is None:
        repos = ["backend-br/vagas", "datascience-br/vagas"]
    
    results = []
    print(f"{Color.CYAN}🔍 Minerando GitHub Issues em {', '.join(repos)}...{Color.RESET}")

    for repo in repos:
        url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page={max_per_repo}"
        data = fetch_json(url)
        if not data or not isinstance(data, list):
            print(f"{Color.YELLOW}⚠️ Não foi possível obter issues de {repo}.{Color.RESET}")
            continue

        for issue in data:
            if "pull_request" in issue:
                continue
            
            title = clean_html(issue.get("title", ""))
            body = issue.get("body", "") or ""
            labels = [l.get("name", "") for l in issue.get("labels", [])]
            labels_str = " ".join(labels)
            full_text = f"{title} {body} {labels_str}"

            is_junior = any(k in full_text.lower() for k in ["júnior", "junior", "estágio", "estagio", "entry level", "trainee", "associate"])
            is_python_backend = any(k in full_text.lower() for k in ["python", "backend", "dados", "data", "eng"])

            if junior_only and not is_junior:
                continue

            if not is_python_backend:
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

def mine_hacker_news(query="Python", hits=20):
    print(f"{Color.CYAN}🔍 Buscando na edição mais recente do 'Ask HN: Who is hiring?'...{Color.RESET}")
    search_url = "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&query=Who%20is%20hiring&hitsPerPage=1"
    story_data = fetch_json(search_url)
    
    if not story_data or not story_data.get("hits"):
        print(f"{Color.YELLOW}⚠️ Não foi possível obter thread do Hacker News.{Color.RESET}")
        return []
    
    story = story_data["hits"][0]
    story_id = story["objectID"]
    story_title = clean_html(story["title"])
    print(f"{Color.BOLD}📖 Thread ativa:{Color.RESET} {story_title} (ID: {story_id})")

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

        results.append({
            "source": f"Hacker News ({story_title[:22]}...)",
            "title": f"{company} - {role}",
            "company": company,
            "url": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            "created_at": hit.get("created_at", "")[:10],
            "labels": ["Remote", "International", "HN"],
            "emails": emails,
            "fast_links": fast_links,
            "raw_body": clean_text
        })

    return results

# --- MODELOS DE MENSAGEM (< 400 CARACTERES) ---

TEMPLATES = {
    "1": {
        "name": "Modelo 1: Tech Lead / EM (Nacional - Backend & BINGO)",
        "audience": "Gestores de Engenharia no Brasil (LinkedIn DM pós-conexão)",
        "template": (
            "Olá {nome}, acompanho a evolução técnica da {empresa} e vi a movimentação no time de engenharia.\n"
            "Sou graduado em Computação pela UFCG, com atuação em pipelines de alta vazão e telemetria em tempo real no radiotelescópio BINGO.\n"
            "Domino Python, PostgreSQL e arquitetura limpa focada em resiliência e concorrência.\n"
            "Teria 5 min para um breve alinhamento técnico sobre os desafios atuais do time?"
        )
    },
    "2": {
        "name": "Modelo 2: CTO / Engineering Lead (Internacional Remoto - English)",
        "audience": "CTOs & Founders globais (Hacker News / LinkedIn Remote)",
        "template": (
            "Hi {nome}, I follow {empresa}'s work and your focus on scaling backend services.\n"
            "Graduating in CS from UFCG, I engineered high-throughput telemetry pipelines with Python, HDF5, and SDR on the BINGO Telescope.\n"
            "My background emphasizes Linux internals, algorithm optimization, and Clean Architecture.\n"
            "Open to a brief 5-min chat on how my profile fits your engineering needs?"
        )
    },
    "3": {
        "name": "Modelo 3: Recrutador Técnico / Talent Acquisition",
        "audience": "Tech Recruiters em posições anunciadas",
        "template": (
            "Olá {nome}, notei a oportunidade de {vaga} na {empresa}.\n"
            "Minha formação na UFCG abrange computação científica, sistemas operacionais e backend com Python, Docker e bancos relacionais.\n"
            "Tenho inglês fluente e experiência como monitor de Algoritmos Avançados (LEDA) e Redes.\n"
            "Posso compartilhar meu currículo para avaliação direta junto à liderança técnica?"
        )
    },
    "followup_pt": {
        "name": "Follow-up Cordial (D+5 Nacional - 1 Linha)",
        "audience": "Recontato 5 dias úteis após o primeiro contato sem resposta",
        "template": (
            "Olá {nome}, tudo bem? Passando apenas para saber se conseguiu avaliar meu perfil técnico para as demandas de backend/dados na {empresa}. Um abraço!"
        )
    },
    "followup_en": {
        "name": "Follow-up Cordial (D+5 Global - 1 Line)",
        "audience": "Recontact 5 business days after initial outreach",
        "template": (
            "Hi {nome}, just following up to see if my background in high-throughput backend pipelines aligns with what you're building at {empresa}. Best regards!"
        )
    }
}

def generate_message(model_key, nome="[Nome]", empresa="[Empresa]", vaga="Software Engineer"):
    nome = (nome or "").strip() or "[Nome]"
    empresa = (empresa or "").strip() or "[Empresa]"
    vaga = (vaga or "").strip() or "Software Engineer"

    config = TEMPLATES.get(str(model_key))
    if not config:
        return "Modelo inválido."

    msg = config["template"].format(nome=nome, empresa=empresa, vaga=vaga)
    length = len(msg)
    char_indicator = f"{Color.GREEN}{length} chars (Ótimo: <400){Color.RESET}" if length <= 400 else f"{Color.RED}{length} chars (Alerta: >400){Color.RESET}"

    output = []
    output.append(f"{Color.BOLD}{config['name']}{Color.RESET}")
    output.append(f"{Color.DIM}Público: {config['audience']} | Tamanho: {char_indicator}{Color.RESET}")
    output.append("-" * 65)
    output.append(msg)
    output.append("-" * 65)
    return "\n".join(output)

# --- GERADOR DE DORKS / BUSCAS BOOLEANAS ---

def print_dorks():
    print(f"\n{Color.BOLD}🎯 BUSCAS BOOLEANAS E X-RAY PRONTAS PARA CLICAR:{Color.RESET}\n")
    
    dorks = [
        {
            "canal": "Google X-Ray (ATS Ágeis: Ashby + Greenhouse + Lever)",
            "query": '(site:jobs.ashbyhq.com OR site:boards.greenhouse.io OR site:jobs.lever.co) ("Junior" OR "Associate") ("Backend" OR "Software Engineer") "Python" ("Remote" OR "LATAM" OR "Brazil") -intitle:"applied"',
            "url_base": "https://www.google.com/search?q="
        },
        {
            "canal": "LinkedIn Publicações (Feed Orgânico - Gestores Contratando no Brasil)",
            "query": '("contratando" OR "vaga aberta" OR "abrimos vaga") AND ("backend" OR "dados" OR "data engineer") AND ("júnior" OR "junior" OR "entry level") AND ("Python" OR "SQL") AND ("DM" OR "mensagem" OR "currículo por e-mail" OR "email") -gupy -kenoby -workday',
            "url_base": "https://www.linkedin.com/search/results/content/?keywords="
        },
        {
            "canal": "LinkedIn Publicações (Feed Internacional - Remoto Global / LATAM)",
            "query": '("hiring" OR "join our team") AND ("junior" OR "associate" OR "entry level") AND ("backend" OR "software engineer") AND ("Python") AND ("remote" OR "LATAM" OR "anywhere") AND ("send CV" OR "DM me" OR "email") -workday -taleo',
            "url_base": "https://www.linkedin.com/search/results/content/?keywords="
        },
        {
            "canal": "LinkedIn Vagas (Filtro Candidatura Simplificada)",
            "query": '("Software Engineer" OR "Backend Developer") AND ("Junior" OR "Júnior" OR "Associate") AND ("Python" OR "PostgreSQL") NOT (Gupy OR Workday OR Kenoby OR "banco de talentos")',
            "url_base": "https://www.linkedin.com/jobs/search/?keywords="
        }
    ]

    for d in dorks:
        encoded = urllib.parse.quote(d["query"])
        full_url = d["url_base"] + encoded
        print(f"{Color.CYAN}{Color.BOLD}📌 {d['canal']}:{Color.RESET}")
        print(f"  {Color.DIM}Sintaxe:{Color.RESET} {d['query']}")
        print(f"  {Color.GREEN}🔗 Link:{Color.RESET} {full_url}\n")

# --- COMANDOS CLI ---

def cmd_mine(args):
    init_db()
    all_leads = []
    
    if args.source in ["all", "github"]:
        github_leads = mine_github(junior_only=not args.all_levels)
        all_leads.extend(github_leads)

    if args.source in ["all", "hn"]:
        hn_leads = mine_hacker_news(query=args.query)
        all_leads.extend(hn_leads)

    print(f"\n{Color.BOLD}✨ Total de oportunidades mineradas e qualificadas: {len(all_leads)}{Color.RESET}\n")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for idx, lead in enumerate(all_leads, 1):
        cur.execute("""
            INSERT OR IGNORE INTO leads (company, title, source, url, contact_info, raw_body, status)
            VALUES (?, ?, ?, ?, ?, ?, 'minerado')
        """, (
            lead["company"],
            lead["title"],
            lead["source"],
            lead["url"],
            ", ".join(lead["emails"] + lead["fast_links"]),
            lead["raw_body"]
        ))

        print(f"{Color.BOLD}[#{idx}] {lead['title']}{Color.RESET}")
        print(f"  🏢 {Color.CYAN}Empresa:{Color.RESET} {lead['company']}")
        print(f"  🌐 {Color.MAGENTA}Origem:{Color.RESET} {lead['source']} ({lead['created_at']})")
        print(f"  🔗 {Color.GREEN}Link da Vaga:{Color.RESET} {lead['url']}")
        
        if lead["emails"]:
            print(f"  📬 {Color.YELLOW}{Color.BOLD}E-mail direto:{Color.RESET} {', '.join(lead['emails'])}")
        if lead["fast_links"]:
            print(f"  ⚡ {Color.CYAN}{Color.BOLD}ATS Rápido (Ashby/Greenhouse/Lever):{Color.RESET} {', '.join(lead['fast_links'])}")
        
        is_intl = "hacker news" in lead["source"].lower() or "international" in [l.lower() for l in lead.get("labels", [])]
        chosen_model = "2" if is_intl else "1"
        print(f"  💬 {Color.DIM}Modelo sugerido: {chosen_model} (Use: python3 prospector.py msg {chosen_model} --empresa \"{lead['company']}\"){Color.RESET}")
        print("-" * 75)

    conn.commit()
    conn.close()
    print(f"{Color.GREEN}✅ Vagas salvas em 'prospector.db'. Use 'python3 prospector.py list' para gerenciar o funil.{Color.RESET}\n")

def cmd_list(args):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, company, title, source, status, contact_info FROM leads ORDER BY id DESC LIMIT 35")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"{Color.YELLOW}Nenhuma vaga no funil ainda. Execute 'python3 prospector.py mine' para minerar.{Color.RESET}")
        return

    print(f"\n{Color.BOLD}{'ID':<4} {'EMPRESA':<22} {'STATUS':<20} {'ORIGEM':<22} {'CONTATO':<30}{Color.RESET}")
    print("=" * 98)
    for r in rows:
        lid, comp, title, src, status, contact = r
        status_color = Color.GREEN if status in ["resposta", "entrevista"] else (Color.YELLOW if "enviada" in status else Color.RESET)
        print(f"{lid:<4} {comp[:20]:<22} {status_color}{status:<20}{Color.RESET} {src[:20]:<22} {(contact or '')[:28]:<30}")
    print("\n")

def cmd_show(args):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, company, title, source, url, contact_info, raw_body, status FROM leads WHERE id = ?", (args.id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        print(f"{Color.RED}Lead com ID {args.id} não encontrado.{Color.RESET}")
        return

    lid, comp, title, src, url, contact, raw_body, status = row
    print(f"\n{Color.BOLD}================== DETALHES DO LEAD #{lid} =================={Color.RESET}")
    print(f"🏢 {Color.CYAN}Empresa:{Color.RESET} {comp}")
    print(f"📌 {Color.BOLD}Título:{Color.RESET} {title}")
    print(f"🌐 {Color.MAGENTA}Origem:{Color.RESET} {src}")
    print(f"📊 {Color.YELLOW}Status:{Color.RESET} {status}")
    print(f"🔗 {Color.GREEN}URL:{Color.RESET} {url}")
    print(f"📬 {Color.YELLOW}Contato:{Color.RESET} {contact or 'Nenhum e-mail explícito'}")
    if raw_body:
        print(f"\n{Color.DIM}--- Trecho da Descrição ---{Color.RESET}")
        print(raw_body[:400] + "..." if len(raw_body) > 400 else raw_body)
    
    is_intl = "hacker news" in src.lower() or "international" in src.lower()
    model = "2" if is_intl else "1"
    print(f"\n{Color.BOLD}--- Mensagem Sugerida (Modelo {model}) ---{Color.RESET}")
    print(generate_message(model, nome="[Nome]", empresa=comp, vaga=title))
    print("\n")

def cmd_followups(args):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    five_days_ago = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        SELECT id, company, title, source, contacted_at 
        FROM leads 
        WHERE status IN ('conexao_enviada', 'mensagem_enviada', 'aguardando_followup')
        AND contacted_at <= ?
    """, (five_days_ago,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"\n{Color.GREEN}🎉 Nenhum follow-up pendente! Todos os contatos estão dentro da janela de 5 dias úteis.{Color.RESET}\n")
        return

    print(f"\n{Color.RED}{Color.BOLD}⚠️ ALERTA DE FOLLOW-UP (D+5): {len(rows)} contato(s) sem resposta há mais de 5 dias!{Color.RESET}\n")
    for r in rows:
        lid, comp, title, src, c_date = r
        is_intl = "hacker news" in src.lower()
        model = "followup_en" if is_intl else "followup_pt"
        print(f"📌 {Color.BOLD}[ID {lid}] {comp} - {title}{Color.RESET} (Contatado em: {c_date})")
        print(generate_message(model, nome="[Nome]", empresa=comp))
        print("-" * 65)

def cmd_msg(args):
    print("\n" + generate_message(args.model, nome=args.nome, empresa=args.empresa, vaga=args.vaga) + "\n")

def cmd_status_update(args):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        UPDATE leads 
        SET status = ?, contacted_at = ? 
        WHERE id = ?
    """, (args.status, now_str, args.id))
    conn.commit()
    conn.close()
    print(f"{Color.GREEN}✅ Lead #{args.id} atualizado para status '{args.status}'!{Color.RESET}")

def main():
    parser = argparse.ArgumentParser(description="Prospector CLI - Mineração Técnica & Funil de Prospecção Ágil")
    subparsers = parser.add_subparsers(dest="command")

    p_mine = subparsers.add_parser("mine", help="Minerar vagas no GitHub e Hacker News")
    p_mine.add_argument("--source", choices=["all", "github", "hn"], default="all", help="Fonte de mineração")
    p_mine.add_argument("--query", default="Python", help="Linguagem/Tecnologia (padrão: Python)")
    p_mine.add_argument("--all-levels", action="store_true", help="Incluir todos os níveis (não apenas júnior/entry)")

    p_msg = subparsers.add_parser("msg", help="Gerar mensagem de abordagem < 400 chars")
    p_msg.add_argument("model", choices=["1", "2", "3", "followup_pt", "followup_en"], help="Número do modelo")
    p_msg.add_argument("--nome", default="[Nome]", help="Nome do destinatário (Tech Lead / Recrutador)")
    p_msg.add_argument("--empresa", default="[Empresa]", help="Nome da empresa")
    p_msg.add_argument("--vaga", default="Software Engineer", help="Nome da vaga")

    subparsers.add_parser("list", help="Listar leads no funil")

    p_show = subparsers.add_parser("show", help="Ver detalhes e mensagem de um lead")
    p_show.add_argument("id", type=int, help="ID do lead")

    subparsers.add_parser("followups", help="Ver alertas de follow-up (D+5)")

    p_update = subparsers.add_parser("update", help="Atualizar status de um lead no funil")
    p_update.add_argument("id", type=int, help="ID do lead")
    p_update.add_argument("status", choices=["minerado", "conexao_enviada", "mensagem_enviada", "aguardando_followup", "resposta", "entrevista", "descartada"])

    subparsers.add_parser("dorks", help="Exibir buscas booleanas e Google X-Ray prontas")

    args = parser.parse_args()

    if args.command == "mine":
        cmd_mine(args)
    elif args.command == "msg":
        cmd_msg(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "followups":
        cmd_followups(args)
    elif args.command == "update":
        cmd_status_update(args)
    elif args.command == "dorks":
        print_dorks()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
