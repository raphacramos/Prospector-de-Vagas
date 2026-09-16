import os
import smtplib
import subprocess
import urllib.parse
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from prospector.core import config
from prospector.core.config import Color
from prospector.domain.lead import LeadStatus
from prospector.engine.copywriter import get_message_content


def prepare_message(lead):
    """Escolhe destinatario, template e PDF a partir da regiao do lead."""
    model = "2" if lead.is_international else "1"
    subj, body = get_message_content(model, nome="Team", empresa=lead.company, vaga=lead.title)
    pdf_path = config.PDF_EN if lead.is_international else config.PDF_PT
    return lead.primary_email, subj, body, pdf_path


def _build_mime(from_addr, to_addr, subj, body, pdf_path):
    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subj
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(pdf_path))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(pdf_path)}"'
        msg.attach(part)
    return msg


def _print_draft_hint(lead_id):
    print(f"{Color.YELLOW}📝 Lead #{lead_id} marcado como '{LeadStatus.RASCUNHO_ABERTO.value}'. Depois de enviar de fato, rode:{Color.RESET}")
    print(f"   python3 prospector.py update {lead_id} mensagem_enviada\n")


def send_smtp(lead, repo, user, password, allow_no_attachment=False):
    """Envia o e-mail via SMTP do Gmail com o PDF correspondente anexado."""
    to_addr, subj, body, pdf_path = prepare_message(lead)
    if not to_addr:
        print(f"{Color.RED}❌ Lead #{lead.id} não possui e-mail direto cadastrado.{Color.RESET}")
        return False

    has_pdf = os.path.exists(pdf_path)
    if not has_pdf and not allow_no_attachment:
        print(f"{Color.RED}❌ Currículo não encontrado: {pdf_path}{Color.RESET}")
        print("   Coloque o PDF em data/ (ou na raiz) ou use --sem-anexo para enviar mesmo assim. Nada foi enviado.")
        return False

    print(f"\n{Color.CYAN}📨 Preparando envio para:{Color.RESET} {to_addr}")
    print(f"🏢 Empresa: {lead.company} | Assunto: {subj}")
    print(f"📎 Anexo: {os.path.basename(pdf_path) if has_pdf else 'NENHUM (--sem-anexo)'}")
    msg = _build_mime(f"Raphael Ramos <{user}>", to_addr, subj, body, pdf_path if has_pdf else None)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(user, password.replace(" ", ""))
        server.sendmail(user, [to_addr], msg.as_string())
        server.quit()
    except Exception as e:
        print(f"\n{Color.RED}❌ Falha no envio SMTP: {e}{Color.RESET}\n")
        return False

    repo.set_status(lead.id, LeadStatus.MENSAGEM_ENVIADA, note=f"smtp para {to_addr}")
    print(f"\n{Color.GREEN}{Color.BOLD}✅ E-mail enviado com sucesso para {to_addr}!{Color.RESET}")
    print(f"{Color.GREEN}Funil atualizado: Lead #{lead.id} marcado como 'mensagem_enviada' (Follow-up D+5 ativado).{Color.RESET}\n")
    return True


def open_gmail_web(lead, repo):
    """Abre o Gmail Web no navegador com campos preenchidos (o anexo é manual)."""
    to_addr, subj, body, pdf_path = prepare_message(lead)
    gmail_url = (
        "https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={urllib.parse.quote(to_addr)}&su={urllib.parse.quote(subj)}&body={urllib.parse.quote(body)}"
    )
    print(f"{Color.GREEN}🚀 Abrindo Gmail Web com e-mail preenchido...{Color.RESET}")
    missing = "" if os.path.exists(pdf_path) else f" {Color.RED}(arquivo não encontrado){Color.RESET}"
    print(f"📎 Anexe manualmente: {pdf_path}{missing}")
    subprocess.run(["open", gmail_url])
    repo.set_status(lead.id, LeadStatus.RASCUNHO_ABERTO, note="gmail web")
    _print_draft_hint(lead.id)


def create_eml_draft(lead, repo):
    """Gera um arquivo .eml com o PDF anexado e abre no aplicativo padrão."""
    to_addr, subj, body, pdf_path = prepare_message(lead)
    if not os.path.exists(pdf_path):
        print(f"{Color.YELLOW}⚠️ Currículo não encontrado ({pdf_path}); rascunho gerado sem anexo.{Color.RESET}")
    msg = _build_mime("Raphael Ramos <raphaelramosc@gmail.com>", to_addr, subj, body, pdf_path)

    eml_file = os.path.join(config.ensure_output_dir(), f"draft_lead_{lead.id}.eml")
    with open(eml_file, "w", encoding="utf-8") as f:
        f.write(msg.as_string())

    print(f"{Color.GREEN}📄 Rascunho gerado em: {eml_file}{Color.RESET}")
    subprocess.run(["open", eml_file])
    repo.set_status(lead.id, LeadStatus.RASCUNHO_ABERTO, note="rascunho .eml")
    _print_draft_hint(lead.id)
