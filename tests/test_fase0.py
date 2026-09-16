"""Testes de regressao da fase 0 (docs/arquitetura/001-revisao-e-plano-v3.md).

Rodar da raiz do projeto:  python3 -m unittest discover -s tests -v
Nenhum teste acessa a rede, envia e-mail ou toca no prospector.db.
"""
import os
import tempfile
import unittest
from unittest import mock

from prospector.core import config
from prospector.core.region import is_international
from prospector.engine import mailer
from prospector.engine.tailor import extract_canonical_skills
from prospector.miners import greenhouse
from prospector.miners.github import is_backend_role


def make_lead(source, contact="tech@empresa.com"):
    # (id, company, title, source, url, contact_info, raw_body, status)
    return (7, "Acme", "Backend Engineer", source, "https://x", contact, "", "minerado")


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


class GithubFilterTest(unittest.TestCase):
    def test_english_nao_e_backend(self):
        self.assertFalse(is_backend_role("Vendedor com english fluente"))

    def test_backend(self):
        self.assertTrue(is_backend_role("[Remoto] Desenvolvedor Back-end Júnior"))
        self.assertTrue(is_backend_role("Engenheira de Dados Jr - Python"))


class GreenhouseQueryTest(unittest.TestCase):
    JOBS = {"jobs": [
        {"title": "Backend Engineer, Python", "absolute_url": "https://a", "updated_at": "2026-09-01"},
        {"title": "Platform Engineer (Go)", "absolute_url": "https://b", "updated_at": "2026-09-01"},
    ]}

    def run_miner(self, query):
        with mock.patch.object(greenhouse, "fetch_json", return_value=self.JOBS), \
             mock.patch("builtins.print"):
            return greenhouse.mine_greenhouse(query=query, companies=["acme"])

    def test_sem_query_traz_tudo(self):
        self.assertEqual(len(self.run_miner(None)), 2)

    def test_query_filtra(self):
        self.assertEqual([l["url"] for l in self.run_miner("python")], ["https://a"])


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
        self.update_status = mock.patch.object(mailer, "update_status").start()
        self.addCleanup(mock.patch.stopall)
        mock.patch("builtins.print").start()

    def test_send_aborta_sem_pdf(self):
        with mock.patch.object(mailer.smtplib, "SMTP") as smtp:
            ok = mailer.send_smtp(make_lead("GitHub (backend-br/vagas)"), "eu@x.com", "senha")
        self.assertFalse(ok)
        smtp.assert_not_called()
        self.update_status.assert_not_called()

    def test_send_sem_anexo_explicito_envia(self):
        with mock.patch.object(mailer.smtplib, "SMTP") as smtp:
            ok = mailer.send_smtp(make_lead("GitHub (backend-br/vagas)"), "eu@x.com", "senha",
                                  allow_no_attachment=True)
        self.assertTrue(ok)
        smtp.return_value.sendmail.assert_called_once()
        self.update_status.assert_called_once_with(7, "mensagem_enviada")

    def test_draft_nao_marca_como_enviado_e_salva_em_data_out(self):
        with mock.patch.object(mailer.subprocess, "run"):
            mailer.create_eml_draft(make_lead("Simplify NewGrad (2d)"))
        self.update_status.assert_called_once_with(7, "rascunho_aberto")
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "out", "draft_lead_7.eml")))

    def test_gmail_nao_marca_como_enviado(self):
        with mock.patch.object(mailer.subprocess, "run"):
            mailer.open_gmail_web(make_lead("GitHub (backend-br/vagas)"))
        self.update_status.assert_called_once_with(7, "rascunho_aberto")


if __name__ == "__main__":
    unittest.main()
