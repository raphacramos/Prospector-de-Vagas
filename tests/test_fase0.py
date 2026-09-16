"""Testes de regressao da fase 0 (docs/arquitetura/001-revisao-e-plano-v3.md).

Rodar da raiz do projeto:  python3 -m unittest discover -s tests -v
Nenhum teste acessa a rede, envia e-mail ou toca no prospector.db.
"""
import os
import tempfile
import unittest
from unittest import mock

from prospector.core import config
from prospector.domain.lead import Lead, Region, region_from_source
from prospector.engine import mailer
from prospector.engine.tailor import extract_canonical_skills


def make_lead(source, email="tech@empresa.com"):
    return Lead(id=7, company="Acme", title="Backend Engineer", source=source, url="https://x",
                region=region_from_source(source), emails=[email] if email else [])


def is_international(source):
    return region_from_source(source) is Region.INTL


class RegionTest(unittest.TestCase):
    def test_fontes_internacionais(self):
        for src in ["Simplify NewGrad (2d)", "Hacker News (Ask HN...)", "Greenhouse (Gitlab)"]:
            self.assertTrue(is_international(src), src)

    def test_fontes_nacionais(self):
        self.assertFalse(is_international("GitHub (backend-br/vagas)"))
        self.assertFalse(is_international(None))

    def test_simplify_usa_template_e_pdf_em_ingles(self):
        _, subj, body, pdf = mailer.prepare_message(make_lead("Simplify NewGrad (2d)"))
        self.assertIn("Software Engineer Application", subj)
        self.assertTrue(body.startswith("Hi "))
        self.assertEqual(pdf, config.PDF_EN)

    def test_github_usa_portugues(self):
        _, subj, body, pdf = mailer.prepare_message(make_lead("GitHub (backend-br/vagas)"))
        self.assertTrue(body.startswith("Olá "))
        self.assertEqual(pdf, config.PDF_PT)


class SkillsRegexTest(unittest.TestCase):
    def test_cpp(self):
        self.assertIn("C/C++", extract_canonical_skills("Strong C++ skills."))
        self.assertIn("C/C++", extract_canonical_skills("Experience in C/C++ required"))

    def test_go_nao_confunde_com_verbo(self):
        self.assertNotIn("Go", extract_canonical_skills("You will go above and beyond."))
        self.assertNotIn("Go", extract_canonical_skills("Go beyond the basics."))

    def test_go_linguagem(self):
        self.assertIn("Go", extract_canonical_skills("Backend in Go and Rust"))
        self.assertIn("Go", extract_canonical_skills("experience with golang"))

    def test_big_o(self):
        self.assertIn("Algorithms & Data Structures", extract_canonical_skills("reason about O(n) costs"))


class OutreachTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        missing = os.path.join(self.tmp.name, "nao_existe.pdf")
        for name, value in [("PDF_EN", missing), ("PDF_PT", missing),
                            ("OUTPUT_DIR", os.path.join(self.tmp.name, "out"))]:
            p = mock.patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.repo = mock.Mock()
        self.update_status = self.repo.set_status
        self.addCleanup(mock.patch.stopall)
        mock.patch("builtins.print").start()

    def test_send_aborta_sem_pdf(self):
        with mock.patch.object(mailer.smtplib, "SMTP") as smtp:
            ok = mailer.send_smtp(make_lead("GitHub (backend-br/vagas)"), self.repo, "eu@x.com", "senha")
        self.assertFalse(ok)
        smtp.assert_not_called()
        self.update_status.assert_not_called()

    def test_send_sem_anexo_explicito_envia(self):
        with mock.patch.object(mailer.smtplib, "SMTP") as smtp:
            ok = mailer.send_smtp(make_lead("GitHub (backend-br/vagas)"), self.repo, "eu@x.com", "senha",
                                  allow_no_attachment=True)
        self.assertTrue(ok)
        smtp.return_value.sendmail.assert_called_once()
        self.assertEqual(self.update_status.call_args[0][:2], (7, "mensagem_enviada"))

    def test_draft_nao_marca_como_enviado_e_salva_em_data_out(self):
        with mock.patch.object(mailer.subprocess, "run"):
            mailer.create_eml_draft(make_lead("Simplify NewGrad (2d)"), self.repo)
        self.assertEqual(self.update_status.call_args[0][:2], (7, "rascunho_aberto"))
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "out", "draft_lead_7.eml")))

    def test_gmail_nao_marca_como_enviado(self):
        with mock.patch.object(mailer.subprocess, "run"):
            mailer.open_gmail_web(make_lead("GitHub (backend-br/vagas)"), self.repo)
        self.assertEqual(self.update_status.call_args[0][:2], (7, "rascunho_aberto"))


if __name__ == "__main__":
    unittest.main()
