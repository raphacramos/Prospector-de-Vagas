"""Perfil, templates, senders e registro no funil (sem rede, sem SMTP real)."""
import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from prospector.adapters.senders import EmlDraftSender, GmailWebSender, SendError, SmtpSender
from prospector.adapters.storage import SqliteLeadRepository
from prospector.domain.lead import Lead, LeadStatus, Region
from prospector.profile import EXAMPLE_PATH, ProfileError, load_profile
from prospector.services.outreach import OutreachError, OutreachService, render_template


def write_profile(tmpdir, pdf_en=None, pdf_pt=None, **overrides):
    with open(EXAMPLE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data["curriculos"]["pdf_en"] = pdf_en or os.path.join(tmpdir, "nao_existe_en.pdf")
    data["curriculos"]["pdf_pt"] = pdf_pt or os.path.join(tmpdir, "nao_existe_pt.pdf")
    data.update(overrides)
    path = os.path.join(tmpdir, "profile.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout):
        self.sent = []
        FakeSMTP.instances.append(self)

    def starttls(self):
        pass

    def login(self, user, password):
        self.login_args = (user, password)

    def sendmail(self, from_addr, to_addrs, body):
        self.sent.append((from_addr, to_addrs, body))

    def quit(self):
        pass


class ProfileTest(unittest.TestCase):
    def test_exemplo_versionado_carrega(self):
        p = load_profile(EXAMPLE_PATH)
        self.assertEqual(set(p.templates), {"br", "intl", "recrutador"})
        self.assertEqual(p.template("intl").idioma, "en")

    def test_erros_claros(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "p.json")
            with open(bad, "w") as f:
                f.write("{ nao e json")
            with self.assertRaisesRegex(ProfileError, "JSON inválido"):
                load_profile(bad)
            with open(bad, "w") as f:
                json.dump({"nome": "x", "email": "y", "templates": {"br": {"idioma": "pt", "assunto": "", "corpo": ""}},
                           "followups": {}, "curriculos": {}}, f)
            with self.assertRaisesRegex(ProfileError, "'intl'"):
                load_profile(bad)

    def test_render_campos(self):
        p = load_profile(EXAMPLE_PATH)
        subj, body = render_template(p, "recrutador", "Acme", "Backend Jr", nome="Ana")
        self.assertIn("Backend Jr - Acme - Raphael Ramos", subj)
        self.assertTrue(body.startswith("Olá Ana,"))
        self.assertIn("github.com/raphacramos", body)

    def test_campo_desconhecido(self):
        p = load_profile(EXAMPLE_PATH)
        p.templates["br"].corpo = "Oi {cargo}"
        with self.assertRaisesRegex(OutreachError, "cargo"):
            render_template(p, "br", "Acme", "Dev")


class OutreachServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pdf_en = os.path.join(self.tmp.name, "cv_en.pdf")
        with open(self.pdf_en, "wb") as f:
            f.write(b"%PDF-1.4 fake")
        self.profile = load_profile(write_profile(self.tmp.name, pdf_en=self.pdf_en))
        self.repo = SqliteLeadRepository(os.path.join(self.tmp.name, "p.db"),
                                         clock=lambda: datetime(2026, 9, 1, 12))
        self.service = OutreachService(self.repo, self.profile)
        self.intl = self._add("Simplify NewGrad (2d)", Region.INTL, "https://a", ["jobs@beta.io"])
        self.br = self._add("GitHub (backend-br/vagas)", Region.BR, "https://b", ["rh@acme.com.br"])
        self.no_email = self._add("Greenhouse (X)", Region.INTL, "https://c", [])
        FakeSMTP.instances = []

    def _add(self, source, region, url, emails):
        lead_id = self.repo.add(Lead(company="Beta", title="SWE", source=source, url=url,
                                     region=region, emails=emails))
        return self.repo.get(lead_id)

    def smtp(self):
        return SmtpSender("eu@gmail.com", "abcd efgh", smtp_factory=FakeSMTP)

    def test_intl_envia_em_ingles_com_pdf_en(self):
        msg, result = self.service.send(self.intl, self.smtp())
        self.assertTrue(result.delivered)
        self.assertEqual((msg.language, msg.attachment, msg.to), ("en", self.pdf_en, "jobs@beta.io"))
        _, to, body = FakeSMTP.instances[0].sent[0]
        self.assertEqual(to, ["jobs@beta.io"])
        self.assertIn('filename="cv_en.pdf"', body)
        self.assertEqual(FakeSMTP.instances[0].login_args, ("eu@gmail.com", "abcdefgh"))
        lead = self.repo.get(self.intl.id)
        self.assertEqual(lead.status, LeadStatus.MENSAGEM_ENVIADA)
        self.assertIsNotNone(lead.followup_due_at)
        self.assertIn("[intl]", self.repo.events(lead.id)[-1]["note"])

    def test_br_sem_pdf_nao_envia(self):
        with self.assertRaisesRegex(OutreachError, "currículo não encontrado"):
            self.service.send(self.br, self.smtp())
        self.assertEqual(FakeSMTP.instances, [])
        self.assertEqual(self.repo.get(self.br.id).status, LeadStatus.MINERADO)

    def test_sem_anexo_explicito(self):
        msg, result = self.service.send(self.br, self.smtp(), allow_no_attachment=True)
        self.assertTrue(result.delivered)
        self.assertIsNone(msg.attachment)

    def test_modelo_forcado_muda_idioma_e_anexo(self):
        msg = self.service.build_message(self.br, template_key="intl")
        self.assertEqual((msg.language, msg.attachment), ("en", self.pdf_en))

    def test_sem_email(self):
        with self.assertRaisesRegex(OutreachError, "não tem e-mail"):
            self.service.send(self.no_email, self.smtp())

    def test_dry_run_mostra_mesmo_sem_pdf(self):
        msg, result = self.service.send(self.br, self.smtp(), dry_run=True)
        self.assertIn("dry-run", result.detail)
        self.assertTrue(msg.body.startswith("Olá "))

    def test_dry_run_nao_muda_nada(self):
        _, result = self.service.send(self.intl, self.smtp(), dry_run=True)
        self.assertFalse(result.delivered)
        self.assertEqual(FakeSMTP.instances, [])
        self.assertEqual(self.repo.get(self.intl.id).status, LeadStatus.MINERADO)

    def test_falha_smtp_nao_muda_funil(self):
        class Broken(FakeSMTP):
            def login(self, user, password):
                import smtplib
                raise smtplib.SMTPAuthenticationError(535, b"bad")
        with self.assertRaises(SendError):
            self.service.send(self.intl, SmtpSender("eu", "x", smtp_factory=Broken))
        self.assertEqual(self.repo.get(self.intl.id).status, LeadStatus.MINERADO)

    def test_gmail_marca_rascunho(self):
        opened = []
        msg, result = self.service.send(self.no_email, GmailWebSender(opener=opened.append))
        self.assertFalse(result.delivered)
        self.assertTrue(opened[0].startswith("https://mail.google.com/mail/?view=cm"))
        self.assertIn("su=Software%20Engineer%20Application", opened[0])
        self.assertEqual(self.repo.get(self.no_email.id).status, LeadStatus.RASCUNHO_ABERTO)
        self.assertIsNone(self.repo.get(self.no_email.id).followup_due_at)

    def test_draft_eml(self):
        out = os.path.join(self.tmp.name, "out")
        sender = EmlDraftSender(out, opener=lambda p: None)
        self.service.send(self.intl, sender)
        with open(sender.last_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("To: jobs@beta.io", content)
        self.assertIn("Raphael Ramos <raphaelramosc@gmail.com>", content)
        self.assertEqual(self.repo.get(self.intl.id).status, LeadStatus.RASCUNHO_ABERTO)

    def test_avisos(self):
        lead = self.br
        lead.labels.append("empresa-nao-identificada")
        warnings = self.service.warnings(lead, self.service.build_message(lead))
        self.assertTrue(any("caracteres" in w for w in warnings))
        self.assertTrue(any("empresa não identificada" in w for w in warnings))
        self.assertTrue(any("currículo não encontrado" in w for w in warnings))

    def test_followup_por_idioma(self):
        self.assertIn("following up", self.service.followup_text(self.intl))
        self.assertIn("Passando apenas", self.service.followup_text(self.br))


if __name__ == "__main__":
    unittest.main()
