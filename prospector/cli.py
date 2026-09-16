import argparse
import os

from prospector.adapters.http import default_client
from prospector.adapters.jd_fetcher import JobDescriptionFetcher
from prospector.adapters.miners import build_miners
from prospector.adapters.pdf_chrome import ChromePdfRenderer
from prospector.adapters.senders import EmlDraftSender, GmailWebSender, SendError, SmtpSender
from prospector.core import config
from prospector.core.config import Color, load_env
from prospector.core.db import get_repository
from prospector.domain.lead import LeadStatus
from prospector.ports import MiningOptions
from prospector.profile import ProfileError, load_profile
from prospector.services.funnel import funnel_stats
from prospector.services.mining import MiningService
from prospector.services.outreach import OutreachError, OutreachService
from prospector.services.tailoring import TailoringError, TailoringService


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
    miners = build_miners(default_client(), sources=load_profile().fontes)
    names = list(miners) if args.source == "all" else [args.source]
    options = MiningOptions(query=args.query, all_levels=args.all_levels, remote_only=args.remote_only,
                            all_ats=args.all_ats, limit=args.limit)
    report = MiningService(miners, repo).run(
        names, options,
        on_source_start=lambda m: print(f"{Color.CYAN}🔍 Minerando {m.label}...{Color.RESET}"),
    )

    for res in report.sources.values():
        if res.error:
            print(f"{Color.RED}❌ {res.label} indisponível: {res.error}{Color.RESET}")
        else:
            print(f"{Color.GREEN}✅ {res.label}: {res.found} vagas{Color.RESET}")
        for w in res.warnings:
            print(f"{Color.YELLOW}   ⚠️ {w}{Color.RESET}")

    print(f"\n{Color.BOLD}✨ Total minerado: {len(report.leads)} vagas qualificadas "
          f"({report.inserted} novas, {report.duplicates} já estavam no funil).{Color.RESET}\n")
    for idx, lead in enumerate(report.leads, 1):
        print(f"[{idx}] {lead.title} | {lead.company}" + (f" | {lead.location}" if lead.location else ""))
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


def _print_message(msg, warnings):
    print(f"\n{Color.CYAN}Para:{Color.RESET} {msg.to or '(sem e-mail)'}   "
          f"{Color.CYAN}Modelo:{Color.RESET} {msg.template_key} ({msg.language})")
    print(f"{Color.CYAN}Assunto:{Color.RESET} {msg.subject}")
    print(f"{Color.CYAN}Anexo:{Color.RESET} {msg.attachment or 'nenhum'}")
    print(f"{Color.DIM}{'-' * 65}{Color.RESET}\n{msg.body}\n{Color.DIM}{'-' * 65}{Color.RESET}")
    for w in warnings:
        print(f"{Color.YELLOW}⚠️ {w}{Color.RESET}")


def cmd_show(args, repo):
    lead = _load_lead(repo, args.id)
    if not lead:
        return
    service = OutreachService(repo, load_profile())
    msg = service.build_message(lead, args.modelo, args.nome)
    print(f"\n{Color.BOLD}=== LEAD #{lead.id}: {lead.company} ==={Color.RESET}")
    print(f"Cargo: {lead.title} | Status: {lead.status.value} | Região: {lead.region.value}")
    if lead.location:
        print(f"Local: {lead.location}")
    if lead.posted_at:
        print(f"Publicada em: {lead.posted_at}")
    print(f"Contato: {lead.contact_summary or 'Sem e-mail explícito'}")
    print(f"URL: {lead.url}")
    _print_message(msg, service.warnings(lead, msg))
    events = repo.events(lead.id)
    if events:
        print(f"{Color.DIM}Histórico: " + " → ".join(f"{e['status']} ({e['at'][:10]})" for e in events) + Color.RESET)
    if lead.emails:
        print(f"⚡ Disparar via SMTP: {Color.BOLD}python3 prospector.py send {lead.id}{Color.RESET}")
        print(f"🌐 Abrir no Gmail Web: {Color.BOLD}python3 prospector.py gmail {lead.id}{Color.RESET}\n")
    else:
        print(f"🔗 Candidatura direta no ATS: {Color.GREEN}{lead.url}{Color.RESET}\n")


def _make_sender(args, profile):
    if args.command == "send":
        load_env()
        password = os.environ.get("EMAIL_PASS")
        if not password and not args.dry_run:
            raise OutreachError("senha de app não encontrada no .env nem em EMAIL_PASS")
        return SmtpSender(os.environ.get("EMAIL_USER", profile.email), password or "")
    if args.command == "gmail":
        return GmailWebSender()
    return EmlDraftSender(config.OUTPUT_DIR)


def cmd_outreach(args, repo):
    lead = _load_lead(repo, args.id)
    if not lead:
        return
    profile = load_profile()
    service = OutreachService(repo, profile)
    try:
        sender = _make_sender(args, profile)
        preview = service.build_message(lead, args.modelo, args.nome)
        warnings = service.warnings(lead, preview)
        msg, result = service.send(lead, sender, template_key=args.modelo, nome=args.nome,
                                   allow_no_attachment=getattr(args, "sem_anexo", False), dry_run=args.dry_run)
    except (OutreachError, SendError) as e:
        print(f"{Color.RED}❌ {e}{Color.RESET}")
        return
    _print_message(msg, warnings)
    if args.dry_run:
        print(f"{Color.CYAN}🔎 {result.detail}{Color.RESET}\n")
    elif result.delivered:
        print(f"{Color.GREEN}{Color.BOLD}✅ E-mail enviado para {msg.to}! Lead #{lead.id} → mensagem_enviada "
              f"(follow-up em 5 dias).{Color.RESET}\n")
    else:
        where = f" em {sender.last_path}" if getattr(sender, "last_path", None) else ""
        print(f"{Color.GREEN}📝 {result.detail} aberto{where}.{Color.RESET}")
        if not msg.attachment:
            print(f"{Color.YELLOW}📎 Sem anexo: anexe o currículo manualmente.{Color.RESET}")
        elif args.command == "gmail":
            print(f"📎 Anexe manualmente: {msg.attachment}")
        print(f"{Color.YELLOW}Lead #{lead.id} marcado como 'rascunho_aberto'. Depois de enviar de fato, rode:{Color.RESET}")
        print(f"   python3 prospector.py update {lead.id} mensagem_enviada\n")


def cmd_followups(args, repo):
    leads = repo.pending_followups()
    if not leads:
        print(f"\n{Color.GREEN}🎉 Nenhum follow-up pendente para hoje!{Color.RESET}\n")
        return
    service = OutreachService(repo, load_profile())
    print(f"\n{Color.RED}{Color.BOLD}⚠️ ALERTA DE FOLLOW-UP (D+5): {len(leads)} contato(s) aguardando recontato!{Color.RESET}\n")
    for l in leads:
        print(f"📌 [ID {l.id}] {l.company} - {l.title} (Contatado em: {l.contacted_at})")
        print(service.followup_text(l))
        print("-" * 65)


def cmd_status_update(args, repo):
    if repo.set_status(args.id, args.status, note=args.nota or ""):
        print(f"{Color.GREEN}✅ Lead #{args.id} atualizado para status '{args.status}'!{Color.RESET}")
    else:
        print(f"{Color.RED}Lead #{args.id} não encontrado.{Color.RESET}")


def _pct(value):
    return "n/d" if value is None else f"{value:.1f}%"


def cmd_tailor(args, repo):
    jd_text = args.jd or ""
    if args.jd and os.path.exists(args.jd):
        with open(args.jd, "r", encoding="utf-8") as f:
            jd_text = f.read()
    profile = load_profile()
    http = default_client()
    service = TailoringService(profile, repo, JobDescriptionFetcher(http),
                               ChromePdfRenderer(profile.chrome_path), config.OUTPUT_DIR)
    print(f"{Color.CYAN}🎯 Calibrando currículo...{Color.RESET}")
    try:
        r = service.run(company=args.empresa, role=args.vaga, lead_id=args.lead, url=args.url,
                        requirements_text=args.skills or "", jd_text=jd_text, lang=args.lang,
                        render_pdf=not args.sem_pdf)
    except TailoringError as e:
        print(f"{Color.RED}❌ {e}{Color.RESET}")
        return

    color = Color.RESET if r.coverage is None else (
        Color.GREEN if r.coverage >= 80 else Color.YELLOW if r.coverage >= 60 else Color.RED)
    print("=" * 70)
    print(f"📊 {Color.BOLD}ADERÊNCIA CURRÍCULO x VAGA{Color.RESET}")
    print("=" * 70)
    print(f"🏢 {r.company} | {r.role} | CV em {r.language}")
    print(f"🌐 {r.url or 'sem URL'} | descrição da vaga: {'sim' if r.jd_available else 'não'}")
    print(f"🎯 Cobertura de requisitos: {color}{Color.BOLD}{_pct(r.coverage)}{Color.RESET} "
          f"({len(r.matched)} de {len(r.requirements)})   Similaridade textual: {_pct(r.similarity)}")
    print("-" * 70)
    if r.matched:
        print(f"✅ {Color.GREEN}Você tem:{Color.RESET} {', '.join(r.matched)}")
    if r.missing:
        print(f"⚠️ {Color.YELLOW}Lacunas:{Color.RESET} {', '.join(r.missing)}")
        print(f"   {Color.DIM}Não foram adicionadas ao CV. Se você domina alguma, inclua em 'skills' ou "
              f"'palavras_opcionais_cv' do perfil.{Color.RESET}")
    if r.injected:
        print(f"➕ Inseridas no CV (declaradas no perfil): {', '.join(r.injected)}")
    print(f"🏷️ Título: {r.headline}")
    print("=" * 70)
    for w in r.warnings:
        print(f"{Color.YELLOW}⚠️ {w}{Color.RESET}")
    print(f"📄 HTML: {r.html_path}")
    if r.pdf_ok:
        print(f"{Color.GREEN}{Color.BOLD}✅ PDF: {r.pdf_path}{Color.RESET}")
    print(f"\n{Color.BOLD}--- Mensagem de abordagem ---{Color.RESET}\n{Color.CYAN}Assunto:{Color.RESET} {r.subject}\n")
    print(r.message)
    print("-" * 70)


def cmd_stats(args, repo):
    per_source, total = funnel_stats(repo.funnel_rows())
    if not total.leads:
        print("Nenhuma vaga no funil.")
        return
    print(f"\n{Color.BOLD}{'FONTE':<30} {'LEADS':>6} {'CONTAT.':>8} {'RESP.':>6} {'TAXA':>7} {'DESC.':>6}{Color.RESET}")
    print("=" * 68)
    for st in per_source + [total]:
        rate = "-" if st.reply_rate is None else f"{st.reply_rate:.0f}%"
        bold = Color.BOLD if st is total else ""
        print(f"{bold}{st.source[:30]:<30} {st.leads:>6} {st.contacted:>8} {st.replied:>6} {rate:>7} "
              f"{st.discarded:>6}{Color.RESET}")
    print(f"\n{Color.DIM}TAXA = respostas ou entrevistas / leads contatados (por histórico).{Color.RESET}\n")


def build_parser():
    parser = argparse.ArgumentParser(description="Prospector CLI - Sistema de Mineração Técnica & Funil Ágil")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("mine", help="Minerar vagas (GitHub, Hacker News, Greenhouse, Lever, Ashby, SimplifyJobs)")
    p.add_argument("--source", choices=["all"] + list(build_miners(http=None)), default="all")
    p.add_argument("--query", default=None, help="Termo de busca/filtro (ex: Python, Backend, Remote)")
    p.add_argument("--all-levels", action="store_true", help="Incluir níveis acima de Júnior/Entry-Level no GitHub")
    p.add_argument("--remote-only", action="store_true",
                   help="Manter só vagas remotas/LATAM/globais (vale para todas as fontes)")
    p.add_argument("--all-ats", action="store_true", help="Desativar filtro restritivo de ATS rápido")
    p.add_argument("--limit", type=int, default=50, help="Máximo de vagas por fonte; no Greenhouse, por empresa (padrão: 50)")
    p.set_defaults(func=cmd_mine)

    p = sub.add_parser("tailor", help="Comparar currículo x vaga e gerar CV calibrado (sem inventar skills)")
    p.add_argument("--lead", type=int, help="ID do lead no funil para calibrar automaticamente")
    p.add_argument("--empresa", help="Nome da empresa")
    p.add_argument("--vaga", default="Software Engineer", help="Título do cargo")
    p.add_argument("--url", help="URL direta da vaga para extração automática da JD")
    p.add_argument("--skills", help="Requisitos da vaga separados por vírgula (ex: FastAPI, Docker, Redis)")
    p.add_argument("--jd", help="Texto ou caminho do arquivo de Job Description")
    p.add_argument("--lang", choices=["en", "pt"], default=None,
                   help="Idioma do currículo (padrão: região do lead, ou en)")
    p.add_argument("--sem-pdf", action="store_true", help="Gerar só o HTML calibrado")
    p.set_defaults(func=cmd_tailor)

    p = sub.add_parser("list", help="Listar leads no funil")
    p.add_argument("--limit", type=int, default=35)
    p.add_argument("--status", choices=LeadStatus.values())
    p.set_defaults(func=cmd_list)

    templates = list(load_profile().templates)
    for name, helptext, func in [
        ("show", "Ver detalhes, histórico e mensagem de um lead", cmd_show),
        ("send", "Enviar e-mail via SMTP com PDF anexado", cmd_outreach),
        ("gmail", "Abrir Gmail Web com e-mail preenchido (anexo manual)", cmd_outreach),
        ("draft", "Gerar rascunho .eml com PDF em data/out/", cmd_outreach),
    ]:
        p = sub.add_parser(name, help=helptext)
        p.add_argument("id", type=int)
        p.add_argument("--modelo", choices=templates, help="Template do perfil (padrão: pela região do lead)")
        p.add_argument("--nome", help="Nome na saudação (padrão: saudacao_padrao do template)")
        p.set_defaults(func=func)
        if name != "show":
            p.add_argument("--dry-run", action="store_true", help="Só mostrar a mensagem; não envia nem muda o funil")
        if name == "send":
            p.add_argument("--sem-anexo", action="store_true", help="Enviar mesmo sem o PDF do currículo")

    p = sub.add_parser("followups", help="Ver alertas de follow-up (D+5)")
    p.set_defaults(func=cmd_followups)

    p = sub.add_parser("stats", help="Métricas do funil por fonte (taxa de resposta)")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("update", help="Atualizar status de um lead no funil")
    p.add_argument("id", type=int)
    p.add_argument("status", choices=LeadStatus.values())
    p.add_argument("--nota", help="Observação registrada no histórico")
    p.set_defaults(func=cmd_status_update)
    return parser


def main(argv=None):
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        if not getattr(args, "func", None):
            parser.print_help()
            return
        args.func(args, _open_repo_verbose())
    except ProfileError as e:
        print(f"{Color.RED}❌ Perfil inválido: {e}{Color.RESET}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
