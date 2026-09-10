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
        "subject": "Aplicação Engenharia Backend - Raphael Ramos",
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
        "subject": "Software Engineer Application - Raphael Ramos",
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
        "subject": "Candidatura: {vaga} - Raphael Ramos",
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

# --- COMANDOS CLI ---

def cmd_mine(args):
    init_db()
    all_leads = []
    if args.source in ["all", "github"]:
        all_leads.extend(mine_github(junior_only=not args.all_levels))
    if args.source in ["all", "hn"]:
        all_leads.extend(mine_hacker_news(query=args.query))

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
    is_intl = "hacker news" in src.lower() or "international" in src.lower()
    model = "2" if is_intl else "1"
    subj, body = get_message_content(model, nome="Team", empresa=comp, vaga=title)
    print(f"\n{Color.BOLD}=== LEAD #{lid}: {comp} ==={Color.RESET}")
    print(f"Cargo: {title} | Status: {status}")
    print(f"Contato: {contact or 'Sem e-mail explícito'}")
    print(f"URL: {url}")
    print(f"\n{Color.CYAN}Assunto:{Color.RESET} {subj}")
    print(f"{Color.DIM}{'-'*65}{Color.RESET}\n{body}\n{Color.DIM}{'-'*65}{Color.RESET}")
    print(f"Dica: Para abrir no Gmail Web, use: {Color.BOLD}python3 prospector.py gmail {lid}{Color.RESET}")
    print(f"Dica: Para gerar rascunho com PDF anexado: {Color.BOLD}python3 prospector.py draft {lid}{Color.RESET}\n")

def cmd_gmail(args):
    """Abre o Gmail Web diretamente no navegador com campos preenchidos."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, company, title, source, contact_info FROM leads WHERE id = ?", (args.id,))
    row = cur.fetchone()
    if not row:
        print("Lead não encontrado.")
        return
    lid, comp, title, src, contact = row
    
    # Extrai primeiro e-mail se houver
    emails = re.findall(EMAIL_REGEX, contact or "")
    to_addr = emails[0] if emails else ""
    is_intl = "hacker news" in src.lower()
    model = "2" if is_intl else "1"
    subj, body = get_message_content(model, nome="Team", empresa=comp, vaga=title)

    gmail_url = (
        "https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={urllib.parse.quote(to_addr)}"
        f"&su={urllib.parse.quote(subj)}"
        f"&body={urllib.parse.quote(body)}"
    )

    print(f"\n{Color.GREEN}🚀 Abrindo Gmail Web no seu navegador com e-mail preenchido...{Color.RESET}")
    print(f"Destinatário: {to_addr or 'Preencher manualmente'}")
    print(f"Anexo recomendado: {PDF_EN if is_intl else PDF_PT}\n")

    subprocess.run(["open", gmail_url])

    # Pergunta se deseja marcar como enviado
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("UPDATE leads SET status = 'mensagem_enviada', contacted_at = ? WHERE id = ?", (now_str, lid))
    conn.commit()
    conn.close()
    print(f"{Color.GREEN}✅ Lead #{lid} atualizado no funil para 'mensagem_enviada'! (Follow-up D+5 ativado){Color.RESET}\n")

def cmd_draft(args):
    """Gera um arquivo .eml com o PDF anexado e abre no aplicativo de e-mail do sistema."""
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
    is_intl = "hacker news" in src.lower()
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

    print(f"\n{Color.GREEN}📄 Rascunho gerado com PDF já anexado em: {eml_file}{Color.RESET}")
    print(f"Abrindo seu aplicativo de e-mail...\n")
    subprocess.run(["open", eml_file])

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("UPDATE leads SET status = 'mensagem_enviada', contacted_at = ? WHERE id = ?", (now_str, lid))
    conn.commit()
    conn.close()
    print(f"{Color.GREEN}✅ Lead #{lid} atualizado para 'mensagem_enviada'!{Color.RESET}\n")

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
        print(f"\n{Color.GREEN}🎉 Nenhum follow-up pendente! Todos os contatos estão dentro de 5 dias úteis.{Color.RESET}\n")
        return

    print(f"\n{Color.RED}{Color.BOLD}⚠️ ALERTA DE FOLLOW-UP (D+5): {len(rows)} contato(s) aguardando recontato!{Color.RESET}\n")
    for r in rows:
        lid, comp, title, src, c_date = r
        is_intl = "hacker news" in src.lower()
        print(f"📌 [ID {lid}] {comp} - {title} (Contatado em: {c_date})")
        if is_intl:
            print("Hi [Name], just following up to see if my background in high-throughput backend pipelines fits your needs at {comp}. Best regards!")
        else:
            print("Olá [Nome], tudo bem? Passando apenas para saber se conseguiu avaliar meu perfil técnico na {comp}. Um abraço!")
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
    p_mine = subparsers.add_parser("mine", help="Minerar vagas")
    p_mine.add_argument("--source", choices=["all", "github", "hn"], default="all")
    p_mine.add_argument("--query", default="Python")
    p_mine.add_argument("--all-levels", action="store_true")

    # list
    subparsers.add_parser("list", help="Listar leads no funil")

    # show
    p_show = subparsers.add_parser("show", help="Ver detalhes e mensagem de um lead")
    p_show.add_argument("id", type=int)

    # gmail
    p_gmail = subparsers.add_parser("gmail", help="Abrir Gmail Web com e-mail preenchido em 1 clique")
    p_gmail.add_argument("id", type=int)

    # draft
    p_draft = subparsers.add_parser("draft", help="Gerar rascunho .eml com PDF já anexado")
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
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
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
