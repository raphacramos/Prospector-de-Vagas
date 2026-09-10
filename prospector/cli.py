import os
import sys
import argparse

from prospector.core.config import Color, load_env
from prospector.core.db import (
    init_db, insert_lead, get_lead, list_leads, 
    update_status, get_pending_followups
)
from prospector.miners.github import mine_github
from prospector.miners.hacker_news import mine_hacker_news
from prospector.miners.greenhouse import mine_greenhouse
from prospector.engine.copywriter import get_message_content
from prospector.engine.tailor import tailor_cv
from prospector.engine.mailer import send_smtp, open_gmail_web, create_eml_draft

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
    for idx, lead in enumerate(all_leads, 1):
        insert_lead(
            lead["company"], lead["title"], lead["source"], 
            lead["url"], ", ".join(lead["emails"] + lead["fast_links"]), 
            lead["raw_body"]
        )
        print(f"[{idx}] {lead['title']} | {lead['company']}")
        if lead["emails"]:
            print(f"    📬 E-mail direto: {', '.join(lead['emails'])}")
        elif lead["fast_links"]:
            print(f"    ⚡ ATS Rápido: {lead['fast_links'][0]}")

def cmd_list(args):
    init_db()
    rows = list_leads(limit=35)
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
    lead = get_lead(args.id)
    if not lead:
        print(f"{Color.RED}Lead #{args.id} não encontrado.{Color.RESET}")
        return
    lid, comp, title, src, url, contact, raw_body, status = lead
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
        print(f"⚡ Disparar via SMTP: {Color.BOLD}python3 prospector.py send {lid}{Color.RESET}")
        print(f"🌐 Abrir no Gmail Web: {Color.BOLD}python3 prospector.py gmail {lid}{Color.RESET}\n")
    else:
        print(f"🔗 Candidatura direta no ATS: {Color.GREEN}{url}{Color.RESET}\n")

def cmd_send(args):
    load_env()
    user = os.environ.get("EMAIL_USER", "raphaelramosc@gmail.com")
    password = os.environ.get("EMAIL_PASS")
    if not password:
        print(f"{Color.RED}❌ Erro: Senha de App não encontrada no arquivo .env nem em EMAIL_PASS.{Color.RESET}")
        return
    init_db()
    lead = get_lead(args.id)
    if not lead:
        print(f"{Color.RED}Lead #{args.id} não encontrado.{Color.RESET}")
        return
    send_smtp(lead, user, password)

def cmd_gmail(args):
    init_db()
    lead = get_lead(args.id)
    if not lead:
        print(f"{Color.RED}Lead #{args.id} não encontrado.{Color.RESET}")
        return
    open_gmail_web(lead)

def cmd_draft(args):
    init_db()
    lead = get_lead(args.id)
    if not lead:
        print(f"{Color.RED}Lead #{args.id} não encontrado.{Color.RESET}")
        return
    create_eml_draft(lead)

def cmd_followups(args):
    init_db()
    rows = get_pending_followups(days=5)
    if not rows:
        print(f"\n{Color.GREEN}🎉 Nenhum follow-up pendente para hoje! Todos os contatos estão dentro de 5 dias úteis.{Color.RESET}\n")
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
    update_status(args.id, args.status)
    print(f"{Color.GREEN}✅ Lead #{args.id} atualizado para status '{args.status}'!{Color.RESET}")

def main():
    parser = argparse.ArgumentParser(description="Prospector CLI - Sistema de Mineração Técnica & Funil Ágil")
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
    p_send = subparsers.add_parser("send", help="Enviar e-mail via SMTP com PDF anexado")
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
