import argparse
import os

from prospector.core.config import Color, load_env
from prospector.core.db import get_repository
from prospector.domain.lead import Lead, LeadStatus, region_from_source
from prospector.engine.copywriter import get_message_content
from prospector.engine.mailer import create_eml_draft, open_gmail_web, send_smtp
from prospector.engine.tailor import tailor_cv
from prospector.miners.github import mine_github
from prospector.miners.greenhouse import mine_greenhouse
from prospector.miners.hacker_news import mine_hacker_news
from prospector.miners.simplify import mine_simplify


def lead_from_miner_dict(d):
    """Converte o dict dos mineradores (formato v2) em Lead."""
    return Lead(
        company=d["company"], title=d["title"], source=d["source"], url=d.get("url", ""),
        region=region_from_source(d["source"]), emails=list(d.get("emails", [])),
        ats_links=[l for l in d.get("fast_links", []) if l], labels=[l for l in d.get("labels", []) if l],
        location=d.get("location", ""), posted_at=d.get("created_at", ""), raw_body=d.get("raw_body", ""),
    )


def _open_repo_verbose():
    repo = get_repository()
    if repo.last_backup_path:
        print(f"{Color.YELLOW}🗄️ Banco migrado para o schema v3. Backup do banco antigo: {repo.last_backup_path}{Color.RESET}")
    return repo


def _load_lead(repo, lead_id):
    lead = repo.get(lead_id)
    if not lead:
        print(f"{Color.RED}Lead #{lead_id} não encontrado.{Color.RESET}")
    return lead


def cmd_mine(args, repo):
    raw = []
    if args.source in ["all", "github"]:
        raw.extend(mine_github(junior_only=not args.all_levels, query=args.query))
    if args.source in ["all", "hn"]:
        raw.extend(mine_hacker_news(query=args.query or "Python"))
    if args.source in ["all", "greenhouse"]:
        raw.extend(mine_greenhouse(query=args.query))
    if args.source in ["all", "simplify"]:
        raw.extend(mine_simplify(query=args.query, remote_only=args.remote_only, fast_ats_only=not args.all_ats))

    leads = [lead_from_miner_dict(d) for d in raw]
    inserted, duplicates = repo.add_many(leads)
    print(f"\n{Color.BOLD}✨ Total minerado: {len(leads)} vagas qualificadas "
          f"({inserted} novas, {duplicates} já estavam no funil).{Color.RESET}\n")
    for idx, lead in enumerate(leads, 1):
        print(f"[{idx}] {lead.title} | {lead.company}")
        if lead.emails:
            print(f"    📬 E-mail direto: {', '.join(lead.emails)}")
        elif lead.ats_links:
            print(f"    ⚡ ATS Rápido: {lead.ats_links[0]}")


def cmd_list(args, repo):
    leads = repo.list_recent(limit=args.limit, status=args.status)
    if not leads:
        print("Nenhuma vaga no funil.")
        return
    print(f"\n{Color.BOLD}{'ID':<4} {'EMPRESA':<22} {'STATUS':<20} {'REG':<5} {'ORIGEM':<22} {'CONTATO':<30}{Color.RESET}")
    print("=" * 104)
    for l in leads:
        s = l.status.value
        color = Color.GREEN if s in ["resposta", "entrevista"] else (Color.YELLOW if "enviada" in s else Color.RESET)
        print(f"{l.id:<4} {l.company[:20]:<22} {color}{s:<20}{Color.RESET} {l.region.value:<5} "
              f"{l.source[:20]:<22} {l.contact_summary[:28]:<30}")
    print()


def cmd_show(args, repo):
    lead = _load_lead(repo, args.id)
    if not lead:
        return
    subj, body = get_message_content("2" if lead.is_international else "1", nome="Team",
                                     empresa=lead.company, vaga=lead.title)
    print(f"\n{Color.BOLD}=== LEAD #{lead.id}: {lead.company} ==={Color.RESET}")
    print(f"Cargo: {lead.title} | Status: {lead.status.value} | Região: {lead.region.value}")
    if lead.location:
        print(f"Local: {lead.location}")
    print(f"Contato: {lead.contact_summary or 'Sem e-mail explícito'}")
    print(f"URL: {lead.url}")
    print(f"\n{Color.CYAN}Assunto:{Color.RESET} {subj}")
    print(f"{Color.DIM}{'-' * 65}{Color.RESET}\n{body}\n{Color.DIM}{'-' * 65}{Color.RESET}")
    events = repo.events(lead.id)
    if events:
        print(f"{Color.DIM}Histórico: " + " → ".join(f"{e['status']} ({e['at'][:10]})" for e in events) + Color.RESET)
    if lead.emails:
        print(f"⚡ Disparar via SMTP: {Color.BOLD}python3 prospector.py send {lead.id}{Color.RESET}")
        print(f"🌐 Abrir no Gmail Web: {Color.BOLD}python3 prospector.py gmail {lead.id}{Color.RESET}\n")
    else:
        print(f"🔗 Candidatura direta no ATS: {Color.GREEN}{lead.url}{Color.RESET}\n")


def cmd_send(args, repo):
    load_env()
    user = os.environ.get("EMAIL_USER", "raphaelramosc@gmail.com")
    password = os.environ.get("EMAIL_PASS")
    if not password:
        print(f"{Color.RED}❌ Erro: Senha de App não encontrada no arquivo .env nem em EMAIL_PASS.{Color.RESET}")
        return
    lead = _load_lead(repo, args.id)
    if lead:
        send_smtp(lead, repo, user, password, allow_no_attachment=args.sem_anexo)


def cmd_gmail(args, repo):
    lead = _load_lead(repo, args.id)
    if lead:
        open_gmail_web(lead, repo)


def cmd_draft(args, repo):
    lead = _load_lead(repo, args.id)
    if lead:
        create_eml_draft(lead, repo)


def cmd_followups(args, repo):
    leads = repo.pending_followups()
    if not leads:
        print(f"\n{Color.GREEN}🎉 Nenhum follow-up pendente para hoje!{Color.RESET}\n")
        return
    print(f"\n{Color.RED}{Color.BOLD}⚠️ ALERTA DE FOLLOW-UP (D+5): {len(leads)} contato(s) aguardando recontato!{Color.RESET}\n")
    for l in leads:
        print(f"📌 [ID {l.id}] {l.company} - {l.title} (Contatado em: {l.contacted_at})")
        if l.is_international:
            print(f"Hi Team, just following up to see if my background in high-throughput backend pipelines fits your needs at {l.company}. Best regards!")
        else:
            print(f"Olá, tudo bem? Passando apenas para saber se conseguiram avaliar meu perfil técnico na {l.company}. Um abraço!")
        print("-" * 65)


def cmd_status_update(args, repo):
    if repo.set_status(args.id, args.status, note=args.nota or ""):
        print(f"{Color.GREEN}✅ Lead #{args.id} atualizado para status '{args.status}'!{Color.RESET}")
    else:
        print(f"{Color.RED}Lead #{args.id} não encontrado.{Color.RESET}")


def cmd_tailor(args, repo):
    jd_text = args.jd or ""
    if args.jd and os.path.exists(args.jd):
        with open(args.jd, "r", encoding="utf-8") as f:
            jd_text = f.read()
    tailor_cv(empresa=args.empresa, vaga=args.vaga, lead_id=args.lead, url=args.url,
              skills=args.skills, jd_text=jd_text, lang=args.lang)


def build_parser():
    parser = argparse.ArgumentParser(description="Prospector CLI - Sistema de Mineração Técnica & Funil Ágil")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("mine", help="Minerar vagas (GitHub, Hacker News, Greenhouse, SimplifyJobs)")
    p.add_argument("--source", choices=["all", "github", "hn", "greenhouse", "simplify"], default="all")
    p.add_argument("--query", default=None, help="Termo de busca/filtro (ex: Python, Backend, Remote)")
    p.add_argument("--all-levels", action="store_true", help="Incluir níveis acima de Júnior/Entry-Level no GitHub")
    p.add_argument("--remote-only", action="store_true", help="Filtrar apenas vagas remotas/LATAM/globais")
    p.add_argument("--all-ats", action="store_true", help="Desativar filtro restritivo de ATS rápido")
    p.set_defaults(func=cmd_mine)

    p = sub.add_parser("tailor", help="Calibrar currículo com cobertura de keywords (Resume-Matcher)")
    p.add_argument("--lead", type=int, help="ID do lead no funil para calibrar automaticamente")
    p.add_argument("--empresa", help="Nome da empresa")
    p.add_argument("--vaga", default="Software Engineer", help="Título do cargo")
    p.add_argument("--url", help="URL direta da vaga para extração automática da JD")
    p.add_argument("--skills", help="Requisitos da vaga separados por vírgula (ex: FastAPI, Docker, Redis)")
    p.add_argument("--jd", help="Texto ou caminho do arquivo de Job Description")
    p.add_argument("--lang", choices=["en", "pt"], default=None,
                   help="Idioma do currículo (padrão: região do lead, ou en)")
    p.set_defaults(func=cmd_tailor)

    p = sub.add_parser("list", help="Listar leads no funil")
    p.add_argument("--limit", type=int, default=35)
    p.add_argument("--status", choices=LeadStatus.values())
    p.set_defaults(func=cmd_list)

    for name, helptext, func in [
        ("show", "Ver detalhes, histórico e mensagem de um lead", cmd_show),
        ("send", "Enviar e-mail via SMTP com PDF anexado", cmd_send),
        ("gmail", "Abrir Gmail Web com e-mail preenchido", cmd_gmail),
        ("draft", "Gerar rascunho .eml com PDF", cmd_draft),
    ]:
        p = sub.add_parser(name, help=helptext)
        p.add_argument("id", type=int)
        p.set_defaults(func=func)
        if name == "send":
            p.add_argument("--sem-anexo", action="store_true", help="Enviar mesmo sem o PDF do currículo")

    p = sub.add_parser("followups", help="Ver alertas de follow-up (D+5)")
    p.set_defaults(func=cmd_followups)

    p = sub.add_parser("update", help="Atualizar status de um lead no funil")
    p.add_argument("id", type=int)
    p.add_argument("status", choices=LeadStatus.values())
    p.add_argument("--nota", help="Observação registrada no histórico")
    p.set_defaults(func=cmd_status_update)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return
    args.func(args, _open_repo_verbose())


if __name__ == "__main__":
    main()
