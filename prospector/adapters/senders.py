"""Formas de entregar uma mensagem: SMTP (envia de fato), Gmail Web e rascunho .eml (so preparam)."""
import os
import smtplib
import subprocess
import sys
import urllib.parse
import webbrowser
from dataclasses import dataclass
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional


@dataclass
class OutreachMessage:
    lead_id: int
    to: str
    subject: str
    body: str
    attachment: Optional[str]
    language: str
    template_key: str
    from_name: str = ""
    from_addr: str = ""


@dataclass
class SendResult:
    delivered: bool  # True so quando o e-mail saiu de fato
    detail: str


class SendError(Exception):
    pass


def build_mime(msg):
    mime = MIMEMultipart()
    mime["From"] = formataddr((msg.from_name, msg.from_addr)) if msg.from_addr else msg.from_name
    mime["To"] = msg.to
    mime["Subject"] = msg.subject
    mime.attach(MIMEText(msg.body, "plain", "utf-8"))
    if msg.attachment:
        name = os.path.basename(msg.attachment)
        with open(msg.attachment, "rb") as f:
            part = MIMEApplication(f.read(), Name=name)
        part["Content-Disposition"] = f'attachment; filename="{name}"'
        mime.attach(part)
    return mime


def open_with_system(path):
    """Abre arquivo no app padrao (macOS/Linux/Windows). Retorna False se nao conseguir."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        elif os.name == "nt":
            os.startfile(path)  # noqa: attr-defined (so existe no Windows)
        else:
            subprocess.run(["xdg-open", path], check=False)
        return True
    except OSError:
        return False


class SmtpSender:
    name = "smtp"
    delivers = True
    requires_email = True

    def __init__(self, user, password, host="smtp.gmail.com", port=587, smtp_factory=smtplib.SMTP):
        self.user = user
        self.password = (password or "").replace(" ", "")
        self.host, self.port = host, port
        self.smtp_factory = smtp_factory

    def send(self, msg):
        mime = build_mime(msg)
        try:
            server = self.smtp_factory(self.host, self.port, timeout=15)
            try:
                server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.user, [msg.to], mime.as_string())
            finally:
                server.quit()
        except (smtplib.SMTPException, OSError) as e:
            raise SendError(f"falha no envio SMTP: {e}")
        return SendResult(True, f"smtp para {msg.to}")


class GmailWebSender:
    name = "gmail"
    delivers = False
    requires_email = False

    def __init__(self, opener=webbrowser.open):
        self.opener = opener

    @staticmethod
    def compose_url(msg):
        q = urllib.parse.urlencode({"view": "cm", "fs": "1", "to": msg.to, "su": msg.subject, "body": msg.body},
                                   quote_via=urllib.parse.quote)
        return f"https://mail.google.com/mail/?{q}"

    def send(self, msg):
        url = self.compose_url(msg)
        self.opener(url)
        return SendResult(False, "gmail web")


class EmlDraftSender:
    name = "draft"
    delivers = False
    requires_email = False

    def __init__(self, output_dir, opener=open_with_system):
        self.output_dir = output_dir
        self.opener = opener
        self.last_path = None

    def send(self, msg):
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, f"draft_lead_{msg.lead_id}.eml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_mime(msg).as_string())
        self.last_path = path
        self.opener(path)
        return SendResult(False, f"rascunho {os.path.basename(path)}")
