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
import subprocess
import smtplib
import tempfile
from datetime import datetime, timedelta
import urllib.request
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "prospector.db")
PDF_EN = os.path.join(BASE_DIR, "Curriculo_Raphael_Ramos_EN.pdf")
PDF_PT = os.path.join(BASE_DIR, "Curriculo_Raphael_Ramos_PT_Destaque.pdf")
HTML_EN = os.path.join(BASE_DIR, "curriculo_en.html")
HTML_PT = os.path.join(BASE_DIR, "curriculo_pt_destaque.html")
ENV_PATH = os.path.join(BASE_DIR, ".env")

class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    DIM = "\033[2m"

def load_env():
    """Carrega variáveis do arquivo .env se existir."""
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().replace('"', '').replace("'", ''))

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
            status TEXT DEFAULT 'minerado',
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
    r"https?://job-boards\.greenhouse\.io/[a-zA-Z0-9_\-]+/jobs/[0-9]+",
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

def mine_github(repos=None, max_per_repo=50, junior_only=True):
    if repos is None:
        repos = ["backend-br/vagas", "datascience-br/vagas", "react-brasil/vagas"]
    results = []
    print(f"{Color.CYAN}🔍 Minerando GitHub Issues em {', '.join(repos)}...{Color.RESET}")

    for repo in repos:
        url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page={max_per_repo}"
        data = fetch_json(url)
        if not data or not isinstance(data, list):
            continue

        for issue in data:
            if "pull_request" in issue:
                continue
            title = clean_html(issue.get("title", ""))
            body = issue.get("body", "") or ""
            labels = [l.get("name", "") for l in issue.get("labels", [])]
            labels_str = " ".join(labels)
            full_text = f"{title} {body} {labels_str}"

            is_junior = any(k in full_text.lower() for k in ["júnior", "junior", "estágio", "estagio", "entry level", "trainee", "associate", "pleno"])
            is_python_backend = any(k in full_text.lower() for k in ["python", "backend", "dados", "data", "eng", "node", "postgresql"])

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

            # Filtro por relevância técnica
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

# --- MOTOR DE MENSAGENS (< 400 CARACTERES) ---

TEMPLATES = {
    "1": {
        "name": "Modelo 1: Tech Lead / EM (Nacional - Backend & BINGO)",
        "subject": "Aplicação Engenharia Backend - {empresa} - Raphael Ramos",
        "template": (
            "Olá {nome},\n\n"
            "Acompanho a evolução técnica da {empresa} e vi a movimentação no time de engenharia.\n"
            "Sou graduado em Computação pela UFCG, com atuação em pipelines de alta vazão e telemetria em tempo real no radiotelescópio BINGO.\n"
            "Domino Python, PostgreSQL e arquitetura limpa focada em resiliência e concorrência.\n\n"
            "Teria 5 min para um breve alinhamento técnico sobre os desafios atuais do time?\n\n"
            "Abraço,\n"
            "Raphael Ramos\n"
            "linkedin.com/in/raphael-c-1a7430108 • github.com/raphacramos"
        )
    },
    "2": {
        "name": "Modelo 2: CTO / Engineering Lead (Internacional Remoto - English)",
        "subject": "Software Engineer Application - {empresa} - Raphael Ramos",
        "template": (
            "Hi {nome},\n\n"
            "I follow {empresa}'s work and your focus on scaling backend services.\n"
            "Graduating in CS from UFCG, I engineered high-throughput telemetry pipelines with Python, HDF5, and SDR on the BINGO Telescope.\n"
            "My background emphasizes Linux internals, algorithm optimization, and Clean Architecture.\n\n"
            "Open to a brief 5-min chat on how my profile fits your engineering needs?\n\n"
            "Best regards,\n"
            "Raphael Ramos\n"
            "linkedin.com/in/raphael-c-1a7430108 • github.com/raphacramos"
        )
    },
    "3": {
        "name": "Modelo 3: Recrutador Técnico / Talent Acquisition",
        "subject": "Candidatura: {vaga} - {empresa} - Raphael Ramos",
        "template": (
            "Olá {nome},\n\n"
            "Notei a oportunidade de {vaga} na {empresa}.\n"
            "Minha formação na UFCG abrange computação científica, sistemas operacionais e backend com Python, Docker e bancos relacionais.\n"
            "Tenho inglês fluente e experiência como monitor de Algoritmos Avançados (LEDA) e Redes.\n\n"
            "Posso compartilhar meu currículo para avaliação direta junto à liderança técnica?\n\n"
            "Atenciosamente,\n"
            "Raphael Ramos\n"
            "linkedin.com/in/raphael-c-1a7430108 • github.com/raphacramos"
        )
    }
}

def get_message_content(model_key, nome="Hiring Team", empresa="Company", vaga="Software Engineer"):
    config = TEMPLATES.get(str(model_key), TEMPLATES["2"])
    subject = config["subject"].format(nome=nome, empresa=empresa, vaga=vaga)
    body = config["template"].format(nome=nome, empresa=empresa, vaga=vaga)
    return subject, body

# --- CV TAILORING ENGINE (OPÇÃO 3) ---

def tailor_cv(empresa, vaga="Software Engineer", skills=None, jd_text="", lang="en"):
    """Gera versão sob medida do currículo alinhada com as palavras-chave da vaga."""
    print(f"\n{Color.CYAN}🎯 Iniciando CV Tailoring Engine para: {Color.BOLD}{empresa}{Color.RESET}")
    clean_empresa = re.sub(r"[^a-zA-Z0-9]", "_", empresa)
    
    # 1. Analisa competências a destacar
    target_skills = []
    if skills:
        target_skills = [s.strip() for s in skills.split(",") if s.strip()]
    if jd_text:
        # Detecta palavras-chave da vaga
        potential_kw = [
            "FastAPI", "Django", "Flask", "PostgreSQL", "Redis", "Docker", "Kubernetes",
            "Distributed Systems", "Concurrency", "High Throughput", "Telemetry",
            "Machine Learning", "Data Pipelines", "HDF5", "Kafka", "RabbitMQ", "Microservices",
            "Clean Architecture", "Linux", "AsyncIO", "REST APIs", "C++", "Go"
        ]
        for kw in potential_kw:
            if re.search(r"\b" + re.escape(kw) + r"\b", jd_text, re.IGNORECASE):
                if kw not in target_skills:
                    target_skills.append(kw)

    print(f"Palavras-chave destacadas para alinhamento: {Color.GREEN}{', '.join(target_skills) if target_skills else 'Python, Backend, Distributed Systems'}{Color.RESET}")

    # 2. Carrega base HTML
    base_html_path = HTML_EN if lang == "en" else HTML_PT
    with open(base_html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 3. Customiza Headline
    highlight_tag = target_skills[0] if target_skills else "Distributed Telemetry"
    new_headline = f"Software Engineer | Backend & Data Systems | Python, Linux, {highlight_tag}"
    html_content = re.sub(
        r'<div class="subtitle">.*?</div>',
        f'<div class="subtitle">{new_headline}</div>',
        html_content
    )

    # 4. Salva HTML Customizado
    output_html_name = f"curriculo_tailored_{clean_empresa}.html"
    output_html_path = os.path.join(BASE_DIR, output_html_name)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"📄 Arquivo HTML customizado gerado: {Color.BOLD}{output_html_name}{Color.RESET}")

    # 5. Compila PDF sob medida
    output_pdf_name = f"Curriculo_Raphael_Ramos_{clean_empresa}.pdf"
    output_pdf_path = os.path.join(BASE_DIR, output_pdf_name)

    print(f"⚙️ Compilando PDF sob medida via Chrome headless...")
    user_dir = tempfile.mkdtemp()
    cmd = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--user-data-dir={user_dir}",
        f"--print-to-pdf={output_pdf_path}",
        f"file://{output_html_path}"
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        subprocess.run(["rm", "-rf", user_dir])
        if os.path.exists(output_pdf_path) and os.path.getsize(output_pdf_path) > 0:
            print(f"{Color.GREEN}{Color.BOLD}✅ PDF sob medida gerado com sucesso: {output_pdf_name}!{Color.RESET}")
        else:
            print(f"{Color.YELLOW}⚠️ HTML pronto. Para gerar o PDF, abra {output_html_name} e imprima como PDF.{Color.RESET}")
    except Exception as e:
        subprocess.run(["rm", "-rf", user_dir])
        print(f"{Color.YELLOW}⚠️ HTML gerado com sucesso. (PDF pode ser impresso direto de {output_html_name}){Color.RESET}")

    # 6. Gera mensagem sugerida para a empresa
    model = "2" if lang == "en" else "1"
    subj, msg = get_message_content(model, nome="Team", empresa=empresa, vaga=vaga)
    print(f"\n{Color.BOLD}--- Mensagem de Abordagem Sob Medida para {empresa} ---{Color.RESET}")
    print(f"Assunto: {subj}\n")
    print(msg)
    print("-" * 65 + "\n")

# --- COMANDOS CLI ---

def cmd_mine(args):
    init_db()
    all_leads = []
    if args.source in ["all", "github"]:
        all_leads.extend(mine_github(junior_only=not args.all_levels))
    if args.source in ["all", "hn"]:
        all_leads.extend(mine_hacker_news(query=args.query))
    if args.source in ["all", "greenhouse"]:
        all_leads.extend(mine_greenhouse(query=args.query))

    print(f"\n{Color.BOLD}✨ Total minerado: {len(all_leads)} vagas qualificadas.{Color.RESET}\n")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for idx, lead in enumerate(all_leads, 1):
        cur.execute("""
            INSERT OR IGNORE INTO leads (company, title, source, url, contact_info, raw_body, status)
            VALUES (?, ?, ?, ?, ?, ?, 'minerado')
        """, (lead["company"], lead["title"], lead["source"], lead["url"], ", ".join(lead["emails"] + lead["fast_links"]), lead["raw_body"]))
        print(f"[{idx}] {lead['title']} | {lead['company']}")
        if lead["emails"]:
            print(f"    📬 E-mail direto: {', '.join(lead['emails'])}")
        elif lead["fast_links"]:
            print(f"    ⚡ ATS Rápido: {lead['fast_links'][0]}")
    conn.commit()
    conn.close()

def cmd_list(args):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, company, title, source, status, contact_info FROM leads ORDER BY id DESC LIMIT 35")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print("Nenhuma vaga no funil.")
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
        print("Lead não encontrado.")
        return
    lid, comp, title, src, url, contact, raw_body, status = row
    is_intl = "hacker news" in src.lower() or "international" in src.lower() or "greenhouse" in src.lower()
    model = "2" if is_intl else "1"
    subj, body = get_message_content(model, nome="Team", empresa=comp, vaga=title)
    print(f"\n{Color.BOLD}=== LEAD #{lid}: {comp} ==={Color.RESET}")
    print(f"Cargo: {title} | Status: {status}")
    print(f"Contato: {contact or 'Sem e-mail explícito'}")
    print(f"URL: {url}")
    print(f"\n{Color.CYAN}Assunto:{Color.RESET} {subj}")
    print(f"{Color.DIM}{'-'*65}{Color.RESET}\n{body}\n{Color.DIM}{'-'*65}{Color.RESET}")
    if contact and "@" in contact:
        print(f"⚡ Disparar agora via SMTP: {Color.BOLD}python3 prospector.py send {lid}{Color.RESET}")
        print(f"🌐 Abrir no Gmail Web: {Color.BOLD}python3 prospector.py gmail {lid}{Color.RESET}\n")
    else:
        print(f"🔗 Candidatura direta no ATS: {Color.GREEN}{url}{Color.RESET}\n")

def cmd_send(args):
    """Envia o e-mail via SMTP com o PDF anexado."""
    load_env()
    user = os.environ.get("EMAIL_USER", "raphaelramosc@gmail.com")
    password = os.environ.get("EMAIL_PASS")

    if not password:
        print(f"{Color.RED}❌ Erro: Senha de App não configurada.{Color.RESET}")
        return

    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, company, title, source, contact_info FROM leads WHERE id = ?", (args.id,))
    row = cur.fetchone()
    if not row:
        print(f"{Color.RED}Lead #{args.id} não encontrado.{Color.RESET}")
        return
    lid, comp, title, src, contact = row

    emails = re.findall(EMAIL_REGEX, contact or "")
    if not emails:
        print(f"{Color.RED}❌ Lead #{lid} não possui e-mail cadastrado.{Color.RESET}")
        return
    to_addr = emails[0]

    is_intl = "hacker news" in src.lower() or "greenhouse" in src.lower() or "international" in src.lower()
    model = "2" if is_intl else "1"
    subj, body = get_message_content(model, nome="Team", empresa=comp, vaga=title)
    pdf_path = PDF_EN if is_intl else PDF_PT

    print(f"\n{Color.CYAN}📨 Enviando para:{Color.RESET} {to_addr}")
    print(f"🏢 Empresa: {comp} | Assunto: {subj}")

    msg = MIMEMultipart()
    msg["From"] = f"Raphael Ramos <{user}>"
    msg["To"] = to_addr
    msg["Subject"] = subj
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(pdf_path))
            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(pdf_path)}"'
            msg.attach(part)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(user, password.replace(" ", ""))
        server.sendmail(user, [to_addr], msg.as_string())
        server.quit()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE leads SET status = 'mensagem_enviada', contacted_at = ? WHERE id = ?", (now_str, lid))
        conn.commit()
        print(f"{Color.GREEN}{Color.BOLD}✅ E-mail enviado com sucesso para {to_addr}!{Color.RESET}\n")
    except Exception as e:
        print(f"{Color.RED}❌ Falha no envio: {e}{Color.RESET}\n")
    finally:
        conn.close()

def cmd_gmail(args):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, company, title, source, contact_info FROM leads WHERE id = ?", (args.id,))
    row = cur.fetchone()
    if not row:
        print("Lead não encontrado.")
        return
    lid, comp, title, src, contact = row
    emails = re.findall(EMAIL_REGEX, contact or "")
    to_addr = emails[0] if emails else ""
    is_intl = "hacker news" in src.lower() or "greenhouse" in src.lower()
    model = "2" if is_intl else "1"
    subj, body = get_message_content(model, nome="Team", empresa=comp, vaga=title)

    gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={urllib.parse.quote(to_addr)}&su={urllib.parse.quote(subj)}&body={urllib.parse.quote(body)}"
    print(f"{Color.GREEN}🚀 Abrindo Gmail Web...{Color.RESET}")
    subprocess.run(["open", gmail_url])

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("UPDATE leads SET status = 'mensagem_enviada', contacted_at = ? WHERE id = ?", (now_str, lid))
    conn.commit()
    conn.close()

def cmd_draft(args):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, company, title, source, contact_info FROM leads WHERE id = ?", (args.id,))
    row = cur.fetchone()
    if not row:
        print("Lead não encontrado.")
        return
    lid, comp, title, src, contact = row
    emails = re.findall(EMAIL_REGEX, contact or "")
    to_addr = emails[0] if emails else ""
    is_intl = "hacker news" in src.lower() or "greenhouse" in src.lower()
    model = "2" if is_intl else "1"
    subj, body = get_message_content(model, nome="Team", empresa=comp, vaga=title)
    pdf_path = PDF_EN if is_intl else PDF_PT

    msg = MIMEMultipart()
    msg["From"] = "Raphael Ramos <raphaelramosc@gmail.com>"
    msg["To"] = to_addr
    msg["Subject"] = subj
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(pdf_path))
            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(pdf_path)}"'
            msg.attach(part)

    eml_file = os.path.join(BASE_DIR, f"draft_lead_{lid}.eml")
    with open(eml_file, "w", encoding="utf-8") as f:
        f.write(msg.as_string())

    print(f"{Color.GREEN}📄 Rascunho gerado em: {eml_file}{Color.RESET}")
    subprocess.run(["open", eml_file])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("UPDATE leads SET status = 'mensagem_enviada', contacted_at = ? WHERE id = ?", (now_str, lid))
    conn.commit()
    conn.close()

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
        print(f"\n{Color.GREEN}🎉 Nenhum follow-up pendente para hoje!{Color.RESET}\n")
        return

    print(f"\n{Color.RED}{Color.BOLD}⚠️ ALERTA DE FOLLOW-UP (D+5): {len(rows)} contato(s) aguardando recontato!{Color.RESET}\n")
    for r in rows:
        lid, comp, title, src, c_date = r
        is_intl = "hacker news" in src.lower() or "greenhouse" in src.lower()
        print(f"📌 [ID {lid}] {comp} - {title} (Contatado em: {c_date})")
        if is_intl:
            print(f"Hi Team, just following up to see if my background in high-throughput backend pipelines fits your needs at {comp}. Best regards!")
        else:
            print(f"Olá, tudo bem? Passando apenas para saber se conseguiram avaliar meu perfil técnico na {comp}. Um abraço!")
        print("-" * 65)

def cmd_status_update(args):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("UPDATE leads SET status = ?, contacted_at = ? WHERE id = ?", (args.status, now_str, args.id))
    conn.commit()
    conn.close()
    print(f"{Color.GREEN}✅ Lead #{args.id} atualizado para status '{args.status}'!{Color.RESET}")

def main():
    parser = argparse.ArgumentParser(description="Prospector CLI - Mineração Técnica & Funil de Prospecção Ágil")
    subparsers = parser.add_subparsers(dest="command")

    # mine
    p_mine = subparsers.add_parser("mine", help="Minerar vagas (GitHub, Hacker News, Greenhouse)")
    p_mine.add_argument("--source", choices=["all", "github", "hn", "greenhouse"], default="all")
    p_mine.add_argument("--query", default="Python")
    p_mine.add_argument("--all-levels", action="store_true")

    # tailor
    p_tailor = subparsers.add_parser("tailor", help="Gerar versão sob medida do currículo (CV Tailoring Engine)")
    p_tailor.add_argument("--empresa", required=True, help="Nome da empresa")
    p_tailor.add_argument("--vaga", default="Software Engineer", help="Título do cargo")
    p_tailor.add_argument("--skills", help="Competências separadas por vírgula (ex: FastAPI, Docker, Redis)")
    p_tailor.add_argument("--jd", help="Texto ou arquivo de Job Description")
    p_tailor.add_argument("--lang", choices=["en", "pt"], default="en", help="Idioma do currículo")

    # list
    subparsers.add_parser("list", help="Listar leads no funil")

    # show
    p_show = subparsers.add_parser("show", help="Ver detalhes e mensagem de um lead")
    p_show.add_argument("id", type=int)

    # send
    p_send = subparsers.add_parser("send", help="Enviar e-mail diretamente via SMTP com PDF anexado")
    p_send.add_argument("id", type=int)

    # gmail
    p_gmail = subparsers.add_parser("gmail", help="Abrir Gmail Web com e-mail preenchido")
    p_gmail.add_argument("id", type=int)

    # draft
    p_draft = subparsers.add_parser("draft", help="Gerar rascunho .eml com PDF")
    p_draft.add_argument("id", type=int)

    # followups
    subparsers.add_parser("followups", help="Ver alertas de follow-up (D+5)")

    # update
    p_update = subparsers.add_parser("update", help="Atualizar status de um lead no funil")
    p_update.add_argument("id", type=int)
    p_update.add_argument("status", choices=["minerado", "conexao_enviada", "mensagem_enviada", "aguardando_followup", "resposta", "entrevista", "descartada"])

    args = parser.parse_args()

    if args.command == "mine":
        cmd_mine(args)
    elif args.command == "tailor":
        jd_text = args.jd or ""
        if args.jd and os.path.exists(args.jd):
            with open(args.jd, "r", encoding="utf-8") as f:
                jd_text = f.read()
        tailor_cv(empresa=args.empresa, vaga=args.vaga, skills=args.skills, jd_text=jd_text, lang=args.lang)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "send":
        cmd_send(args)
    elif args.command == "gmail":
        cmd_gmail(args)
    elif args.command == "draft":
        cmd_draft(args)
    elif args.command == "followups":
        cmd_followups(args)
    elif args.command == "update":
        cmd_status_update(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
