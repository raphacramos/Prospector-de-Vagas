"""Taxonomia de skills, extracao de JD, renderizador de PDF e calibracao honesta do CV."""
import json
import os
import stat
import sys
import tempfile
import unittest

from prospector.adapters.jd_fetcher import JobDescriptionFetcher
from prospector.adapters.pdf_chrome import ChromePdfRenderer, PdfRendererUnavailable, find_chrome
from prospector.adapters.storage import SqliteLeadRepository
from prospector.domain.lead import Lead, Region
from prospector.domain.skills import extract_canonical_skills, requirements_from_text
from prospector.profile import EXAMPLE_PATH, load_profile
from prospector.services.tailoring import TailoringError, TailoringService, inject_keywords

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


BASE_HTML = """<html><body><h1>Raphael</h1><div class="subtitle">Old headline</div>
<p>Python, PostgreSQL, Linux, telemetry pipelines.</p>
<p>Skills: Docker, Git, SQL</p></body></html>"""


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

    def test_requisitos_manuais(self):
        self.assertEqual(requirements_from_text("FastAPI, Kafka, postgres"), {"FastAPI", "Kafka", "PostgreSQL"})


class StubHttp:
    def __init__(self, json_by_url=None, text_by_url=None):
        self.json_by_url = json_by_url or {}
        self.text_by_url = text_by_url or {}

    def get_json(self, url, headers=None):
        return self.json_by_url.get(url)

    def get_text(self, url, headers=None):
        return self.text_by_url.get(url)


class JobDescriptionFetcherTest(unittest.TestCase):
    def test_greenhouse(self):
        http = StubHttp({"https://boards-api.greenhouse.io/v1/boards/acme/jobs/9": {
            "title": "Backend Engineer", "content": "&lt;p&gt;We use &lt;b&gt;Python&lt;/b&gt; and Kafka&lt;/p&gt;"}})
        self.assertEqual(JobDescriptionFetcher(http).fetch("https://job-boards.greenhouse.io/acme/jobs/9?gh_src=x"),
                         ("Backend Engineer", "We use Python and Kafka"))

    def test_lever(self):
        http = StubHttp({"https://api.lever.co/v0/postings/acme/abc": {
            "text": "SWE", "descriptionPlain": "Build APIs.",
            "lists": [{"text": "Requirements", "content": "<li>Go</li><li>Redis</li>"}]}})
        title, text = JobDescriptionFetcher(http).fetch("https://jobs.lever.co/acme/abc")
        self.assertEqual(title, "SWE")
        self.assertIn("Requirements Go Redis", text)

    def test_json_ld_e_html_generico(self):
        page = ('<html><script type="application/ld+json">{"@type": "JobPosting", "title": "Data Eng",'
                ' "description": "<p>Airflow and SQL</p>"}</script></html>')
        http = StubHttp(text_by_url={"https://jobs.ashbyhq.com/x/1": page,
                                     "https://site/job": "<html><style>.a{}</style><p>Rust role</p></html>"})
        self.assertEqual(JobDescriptionFetcher(http).fetch("https://jobs.ashbyhq.com/x/1"),
                         ("Data Eng", "Airflow and SQL"))
        self.assertEqual(JobDescriptionFetcher(http).fetch("https://site/job"), ("", "Rust role"))
        self.assertEqual(JobDescriptionFetcher(http).fetch("https://fora/do/ar"), ("", ""))


def make_fake_chrome(folder, write_pdf=True):
    """Executavel que imita o Chrome: escreve o arquivo passado em --print-to-pdf."""
    path = os.path.join(folder, "fake-chrome")
    body = "pass" if not write_pdf else (
        "out = [a.split('=', 1)[1] for a in sys.argv if a.startswith('--print-to-pdf=')][0]\n"
        "with open(out, 'wb') as f:\n"
        "    f.write(b'%PDF-1.4 fake')")
    with open(path, "w") as f:
        f.write(f"#!{sys.executable}\nimport sys\n{body}\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


class PdfRendererTest(unittest.TestCase):
    def test_render_com_executavel_falso(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = os.path.join(tmp, "cv.html")
            write(html, "<p>oi</p>")
            pdf = os.path.join(tmp, "cv.pdf")
            self.assertTrue(ChromePdfRenderer(make_fake_chrome(tmp)).render(html, pdf, timeout=10))
            self.assertFalse(ChromePdfRenderer(make_fake_chrome(tmp, write_pdf=False)).render(html, pdf, timeout=5))

    def test_chrome_configurado_inexistente(self):
        with self.assertRaises(PdfRendererUnavailable):
            find_chrome("/nao/existe/chrome")


class InjectKeywordsTest(unittest.TestCase):
    def test_insere_so_o_que_falta(self):
        html, added = inject_keywords(BASE_HTML, ["FastAPI", "PostgreSQL"], "Docker, Git,")
        self.assertEqual(added, ["FastAPI"])
        self.assertIn("Skills: FastAPI, Docker, Git, SQL", html)

    def test_sem_ancora(self):
        self.assertEqual(inject_keywords(BASE_HTML, ["FastAPI"], "Kubernetes,"), (BASE_HTML, []))


class TailoringServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        html_path = os.path.join(self.tmp.name, "cv_en.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(BASE_HTML)
        with open(EXAMPLE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        data["curriculos"]["html_en"] = html_path
        data["curriculos"]["html_pt"] = os.path.join(self.tmp.name, "nao_existe.html")
        data["skills"] = ["Python", "PostgreSQL", "Linux & Internals", "Docker & Containers",
                          "Data Pipelines & Telemetry"]
        data["palavras_opcionais_cv"] = []
        self.data = data
        self.repo = SqliteLeadRepository(os.path.join(self.tmp.name, "p.db"))
        self.out = os.path.join(self.tmp.name, "out")
        self.http = StubHttp({"https://boards-api.greenhouse.io/v1/boards/acme/jobs/1": {
            "title": "Backend Engineer",
            "content": "Python, PostgreSQL, Kafka and FastAPI. Docker is a plus."}})

    def service(self, **profile_overrides):
        self.data.update(profile_overrides)
        path = os.path.join(self.tmp.name, "profile.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f)
        renderer = ChromePdfRenderer(make_fake_chrome(self.tmp.name))
        return TailoringService(load_profile(path), self.repo, JobDescriptionFetcher(self.http), renderer, self.out)

    def test_lacunas_nao_entram_no_cv(self):
        r = self.service().run(company="Acme", url="https://job-boards.greenhouse.io/acme/jobs/1",
                               requirements_text="Kafka")
        self.assertEqual(r.role, "Backend Engineer")
        self.assertEqual(r.missing, ["FastAPI", "Kafka"])
        self.assertEqual(r.matched, ["Docker & Containers", "PostgreSQL", "Python"])
        self.assertEqual(r.coverage, 60.0)
        self.assertIsNotNone(r.similarity)
        self.assertEqual(r.injected, [])
        html = read(r.html_path)
        self.assertNotIn("FastAPI", html)
        self.assertNotIn("Kafka", html)
        self.assertIn('<div class="subtitle">Software Engineer | Backend & Data Systems | Python, Linux, '
                      'Docker & Containers, PostgreSQL</div>', html)
        self.assertTrue(r.pdf_ok and os.path.exists(r.pdf_path))
        self.assertTrue(r.pdf_path.endswith("Curriculo_Raphael_Ramos_Acme.pdf"))

    def test_palavra_opcional_declarada_entra_quando_a_vaga_pede(self):
        r = self.service(palavras_opcionais_cv=["FastAPI", "Terraform"]).run(
            company="Acme", url="https://job-boards.greenhouse.io/acme/jobs/1")
        self.assertEqual(r.injected, ["FastAPI"])
        self.assertNotIn("FastAPI", r.missing)
        self.assertIn("FastAPI, Docker, Git,", read(r.html_path))

    def test_sem_requisitos_nao_inventa_score(self):
        r = self.service().run(company="Acme", render_pdf=False)
        self.assertIsNone(r.coverage)
        self.assertIsNone(r.similarity)
        self.assertTrue(any("nenhum requisito" in w for w in r.warnings))
        self.assertEqual(r.pdf_path, "")

    def test_lead_define_empresa_e_idioma(self):
        lead_id = self.repo.add(Lead(company="Beta", title="SWE", source="GitHub", url="https://sem-jd",
                                     region=Region.BR))
        with self.assertRaisesRegex(TailoringError, "currículo base não encontrado"):
            self.service().run(lead_id=lead_id)  # lead BR -> CV em pt, que nao existe neste teste
        r = self.service().run(lead_id=lead_id, lang="en", render_pdf=False)
        self.assertEqual((r.company, r.role, r.language), ("Beta", "SWE", "en"))
        self.assertTrue(any("não consegui extrair" in w for w in r.warnings))

    def test_lead_inexistente(self):
        with self.assertRaisesRegex(TailoringError, "não encontrado"):
            self.service().run(lead_id=999)


if __name__ == "__main__":
    unittest.main()
