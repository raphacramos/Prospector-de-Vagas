import os
import re
import smtplib
import subprocess
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from prospector.core import config
from prospector.core.config import Color
from prospector.core.db import update_status
from prospector.core.region import is_international
from prospector.engine.copywriter import get_message_content
from prospector.miners.base import EMAIL_REGEX

DRAFT_STATUS = "rascunho_aberto"


def prepare_message(lead):
    """Escolhe destinatario, template e PDF a partir da regiao do lead (regra unica)."""
    lid, comp, title, src, url, contact, raw_body, status = lead
    emails = re.findall(EMAIL_REGEX, contact or "")
    to_addr = emails[0] if emails else ""
    is_intl = is_international(src)
    model = "2" if is_intl else "1"
    subj, body = get_message_content(model, nome="Team", empresa=comp, vaga=title)
    pdf_path = config.PDF_EN if is_intl else config.PDF_PT
    return to_addr, subj, body, pdf_path


def _print_draft_hint(lid):
    print(f"{Color.YELLOW}📝 Lead #{lid} marcado como '{DRAFT_STATUS}'. Depois de enviar de fato, rode:{Color.RESET}")
    print(f"   python3 prospector.py update {lid} mensagem_enviada\n")


def send_smtp(lead, user, password, allow_no_attachment=False):
    """Envia o e-mail via SMTP do Gmail com o PDF correspondente anexado."""
    lid, comp = lead[0], lead[1]
    to_addr, subj, body, pdf_path = prepare_message(lead)
    if not to_addr:
        print(f"{Color.RED}❌ Lead #{lid} não possui e-mail direto cadastrado.{Color.RESET}")
        return False

    has_pdf = os.path.exists(pdf_path)
    if not has_pdf and not allow_no_attachment:
        print(f"{Color.RED}❌ Currículo não encontrado: {pdf_path}{Color.RESET}")
        print(f"   Coloque o PDF em data/ (ou na raiz) ou use --sem-anexo para enviar mesmo assim. Nada foi enviado.")
        return False

    print(f"\n{Color.CYAN}📨 Preparando envio para:{Color.RESET} {to_addr}")
    print(f"🏢 Empresa: {comp} | Assunto: {subj}")
    print(f"📎 Anexo: {os.path.basename(pdf_path) if has_pdf else 'NENHUM (--sem-anexo)'}")

    msg = MIMEMultipart()
    msg["From"] = f"Raphael Ramos <{user}>"
    msg["To"] = to_addr
    msg["Subject"] = subj
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if has_pdf:
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

        update_status(lid, "mensagem_enviada")
        print(f"\n{Color.GREEN}{Color.BOLD}✅ E-mail enviado com sucesso para {to_addr}!{Color.RESET}")
        print(f"{Color.GREEN}Funil atualizado: Lead #{lid} marcado como 'mensagem_enviada' (Follow-up D+5 ativado).{Color.RESET}\n")
        return True
    except Exception as e:
        print(f"\n{Color.RED}❌ Falha no envio SMTP: {e}{Color.RESET}\n")
        return False

def open_gmail_web(lead):
    """Abre o Gmail Web no navegador com campos preenchidos (o anexo é manual)."""
    lid = lead[0]
    to_addr, subj, body, pdf_path = prepare_message(lead)

    gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={urllib.parse.quote(to_addr)}&su={urllib.parse.quote(subj)}&body={urllib.parse.quote(body)}"
    print(f"{Color.GREEN}🚀 Abrindo Gmail Web com e-mail preenchido...{Color.RESET}")
    print(f"📎 Anexe manualmente: {pdf_path}" + ("" if os.path.exists(pdf_path) else f" {Color.RED}(arquivo não encontrado){Color.RESET}"))
    subprocess.run(["open", gmail_url])
    update_status(lid, DRAFT_STATUS)
    _print_draft_hint(lid)

def create_eml_draft(lead):
    """Gera um arquivo .eml com o PDF anexado e abre no aplicativo padrão."""
    lid = lead[0]
    to_addr, subj, body, pdf_path = prepare_message(lead)

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
    else:
        print(f"{Color.YELLOW}⚠️ Currículo não encontrado ({pdf_path}); rascunho gerado sem anexo.{Color.RESET}")

    eml_file = os.path.join(config.ensure_output_dir(), f"draft_lead_{lid}.eml")
    with open(eml_file, "w", encoding="utf-8") as f:
        f.write(msg.as_string())

    print(f"{Color.GREEN}📄 Rascunho gerado em: {eml_file}{Color.RESET}")
    subprocess.run(["open", eml_file])
    update_status(lid, DRAFT_STATUS)
    _print_draft_hint(lid)
