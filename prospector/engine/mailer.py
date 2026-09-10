import os
import re
import smtplib
import subprocess
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from prospector.core.config import Color, PDF_EN, PDF_PT, BASE_DIR
from prospector.core.db import update_status
from prospector.engine.copywriter import get_message_content
from prospector.miners.base import EMAIL_REGEX

def send_smtp(lead, user, password):
    """Envia o e-mail via SMTP do Gmail com o PDF correspondente anexado."""
    lid, comp, title, src, url, contact, raw_body, status = lead
    emails = re.findall(EMAIL_REGEX, contact or "")
    if not emails:
        print(f"{Color.RED}❌ Lead #{lid} não possui e-mail direto cadastrado.{Color.RESET}")
        return False
    to_addr = emails[0]

    is_intl = "hacker news" in src.lower() or "greenhouse" in src.lower() or "international" in src.lower()
    model = "2" if is_intl else "1"
    subj, body = get_message_content(model, nome="Team", empresa=comp, vaga=title)
    pdf_path = PDF_EN if is_intl else PDF_PT

    print(f"\n{Color.CYAN}📨 Preparando envio para:{Color.RESET} {to_addr}")
    print(f"🏢 Empresa: {comp} | Assunto: {subj}")
    print(f"📎 Anexo: {os.path.basename(pdf_path)}")

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

        update_status(lid, "mensagem_enviada")
        print(f"\n{Color.GREEN}{Color.BOLD}✅ E-mail enviado com sucesso para {to_addr}!{Color.RESET}")
        print(f"{Color.GREEN}Funil atualizado: Lead #{lid} marcado como 'mensagem_enviada' (Follow-up D+5 ativado).{Color.RESET}\n")
        return True
    except Exception as e:
        print(f"\n{Color.RED}❌ Falha no envio SMTP: {e}{Color.RESET}\n")
        return False

def open_gmail_web(lead):
    """Abre o Gmail Web no navegador com campos preenchidos."""
    lid, comp, title, src, url, contact, raw_body, status = lead
    emails = re.findall(EMAIL_REGEX, contact or "")
    to_addr = emails[0] if emails else ""
    is_intl = "hacker news" in src.lower() or "greenhouse" in src.lower()
    model = "2" if is_intl else "1"
    subj, body = get_message_content(model, nome="Team", empresa=comp, vaga=title)

    gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={urllib.parse.quote(to_addr)}&su={urllib.parse.quote(subj)}&body={urllib.parse.quote(body)}"
    print(f"{Color.GREEN}🚀 Abrindo Gmail Web com e-mail preenchido...{Color.RESET}")
    subprocess.run(["open", gmail_url])
    update_status(lid, "mensagem_enviada")
    print(f"{Color.GREEN}✅ Lead #{lid} atualizado para 'mensagem_enviada'!{Color.RESET}\n")

def create_eml_draft(lead):
    """Gera um arquivo .eml com o PDF anexado e abre no aplicativo padrão."""
    lid, comp, title, src, url, contact, raw_body, status = lead
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
    update_status(lid, "mensagem_enviada")
    print(f"{Color.GREEN}✅ Lead #{lid} atualizado para 'mensagem_enviada'!{Color.RESET}\n")
