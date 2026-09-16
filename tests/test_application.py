"""Pacote de candidatura, respostas de formulario, preenchimento (plano) e fluxo de aplicar."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from prospector.adapters.autofill.fields import (
    FormField, application_url, classify, detect_ats, plan_fields, profile_values,
)
from prospector.adapters.storage import SqliteLeadRepository
from prospector.domain.lead import Lead, LeadStatus, Region
from prospector.domain.resume import MasterResume, assign_ids
from prospector.profile import EXAMPLE_PATH, load_profile
from prospector.services.application import ApplicationError, ApplicationService
from prospector.services.apply_flow import ApplyFlow
from prospector.services.funnel import funnel_stats
from prospector.services.ranking import match_score, queue_key
from prospector.services.resume_store import ResumeStore
from tests.fakes_llm import MASTER, TAILORED, FakeLlm

def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


LONG_JD = "We need a Backend Engineer with Python, PostgreSQL and Kafka. " * 10


class StubJd:
    def __init__(self, texts):
        self.texts = texts
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return "Backend Engineer", self.texts.get(url, "")


class StubPdf:
    def __init__(self, ok=True):
        self.ok = ok

    def render(self, html, pdf, timeout=30):
        if self.ok:
            with open(pdf, "wb") as f:
                f.write(b"%PDF fake")
        return self.ok


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 16, 10, 0)

    def __call__(self):
        return self.now


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.repo = SqliteLeadRepository(os.path.join(self.tmp.name, "p.db"), clock=self.clock)
        self.profile = load_profile(EXAMPLE_PATH)
        self.store = ResumeStore(os.path.join(self.tmp.name, "resume.json"))
        self.store.save(MasterResume.from_dict(assign_ids(copy.deepcopy(MASTER))))
        self.intl_id = self.repo.add(Lead(
            company="Acme", title="Acme - Backend Engineer", source="Greenhouse (Acme)",
            url="https://job-boards.greenhouse.io/acme/jobs/1", region=Region.INTL,
            ats_links=["https://job-boards.greenhouse.io/acme/jobs/1"], raw_body="Position at Acme"))
        self.gh_id = self.repo.add(Lead(
            company="Beta", title="[Remoto] Dev Python Jr - Beta", source="GitHub (backend-br/vagas)",
            url="https://github.com/backend-br/vagas/issues/1", region=Region.BR,
            emails=["rh@beta.com"], raw_body="Vaga para Python júnior com Django e PostgreSQL. " * 8))
        self.jd = StubJd({"https://job-boards.greenhouse.io/acme/jobs/1": LONG_JD})
        self.llm = FakeLlm({"registrar_adaptacao": TAILORED,
                            "registrar_respostas": {"answers": [
                                {"question": "Why Acme?", "answer": "Because of pipelines.", "confident": True},
                                {"question": "Salary expectation?", "answer": "", "confident": False},
                                {"question": "Start date?", "answer": "Next week", "confident": False}]}})
        self.base = os.path.join(self.tmp.name, "applications")

    def service(self, pdf_ok=True):
        return ApplicationService(self.repo, self.profile, self.store, self.llm, self.jd,
                                  StubPdf(pdf_ok), self.base, clock=self.clock)


class PrepareTest(Base):
    def test_pacote_completo(self):
        pkg = self.service().prepare(self.intl_id)
        self.assertEqual((pkg.language, pkg.company, pkg.role), ("en", "Acme", "Backend Engineer"))
        self.assertEqual(pkg.jd_source, "url")
        self.assertTrue(pkg.cv_pdf.endswith("Curriculo_Raphael_Ramos_Acme.pdf"))
        for name in ("cv.html", "carta.txt", "vaga.txt", "tailored.json", "meta.json"):
            self.assertTrue(os.path.exists(os.path.join(pkg.folder, name)), name)
        self.assertEqual(pkg.missing_requirements, ["Kafka"])
        self.assertEqual(pkg.usage, {"input_tokens": 100, "output_tokens": 50})
        prompt = self.llm.calls[0]["content"][0]["text"]
        self.assertIn("<idioma_de_saida>en</idioma_de_saida>", prompt)
        self.assertIn("Kafka", prompt)
        self.assertIn('"exp1.b1"', prompt)
        self.assertNotIn("{max_bullets}", self.llm.calls[0]["system"])
        self.assertEqual(self.repo.get(self.intl_id).status, LeadStatus.CANDIDATURA_PREPARADA)
        loaded = self.service().load(self.intl_id)
        self.assertEqual(loaded.to_dict(), pkg.to_dict())

    def test_github_usa_texto_minerado_e_portugues(self):
        pkg = self.service().prepare(self.gh_id)
        self.assertEqual((pkg.language, pkg.jd_source), ("pt", "minerado"))
        self.assertEqual(self.jd.calls, [])

    def test_invencao_vira_aviso_e_e_removida(self):
        bad = copy.deepcopy(TAILORED)
        bad["skills"] = ["Python", "Kafka"]
        bad["cover_letter"] = "I have 5 years with Kubernetes."
        self.llm.responses["registrar_adaptacao"] = bad
        pkg = self.service().prepare(self.intl_id)
        tailored = read_json(os.path.join(pkg.folder, "tailored.json"))
        self.assertEqual(tailored["skills"], ["Python"])
        self.assertTrue(any("Kafka" in w for w in pkg.warnings))
        self.assertTrue(any("carta" in w and "kubernetes" in w for w in pkg.warnings))

    def test_limita_bullets_e_sem_pdf(self):
        self.profile.ia["max_bullets_por_experiencia"] = 1
        pkg = self.service(pdf_ok=False).prepare(self.intl_id)
        tailored = read_json(os.path.join(pkg.folder, "tailored.json"))
        self.assertEqual(len(tailored["experiences"][0]["bullets"]), 1)
        self.assertEqual(pkg.cv_pdf, "")
        self.assertEqual(pkg.cover_letter_pdf, "")
        self.assertTrue(any("PDF" in w for w in pkg.warnings))
        self.assertIn(" 1 ", self.llm.calls[0]["system"])

    def test_carta_esvaziada_remove_pdf_antigo(self):
        svc = self.service()
        pkg = svc.prepare(self.intl_id)
        self.assertTrue(os.path.exists(pkg.cover_letter_pdf))
        pkg = svc.update_cover_letter(self.intl_id, "   ")
        self.assertEqual(pkg.cover_letter_pdf, "")
        self.assertFalse(os.path.exists(os.path.join(pkg.folder, "carta.pdf")))
        self.assertFalse(os.path.exists(os.path.join(pkg.folder, "carta.html")))

    def test_carta_em_pdf(self):
        pkg = self.service().prepare(self.intl_id)
        self.assertTrue(pkg.cover_letter_pdf.endswith("carta.pdf"))
        self.assertTrue(os.path.exists(os.path.join(pkg.folder, "carta.html")))
        self.assertTrue(os.path.exists(pkg.cover_letter_pdf))

    def test_jd_curta_avisa(self):
        self.jd.texts = {}
        pkg = self.service().prepare(self.intl_id)
        self.assertEqual(pkg.jd_source, "minerado")
        self.assertTrue(any("curta" in w for w in pkg.warnings))

    def test_erros(self):
        with self.assertRaises(ApplicationError):
            self.service().prepare(999)
        with self.assertRaises(ApplicationError):
            self.service().update_cover_letter(self.intl_id, "x")

    def test_carta_editada(self):
        svc = self.service()
        svc.prepare(self.intl_id)
        pkg = svc.update_cover_letter(self.intl_id, "  Nova carta ")
        self.assertEqual(svc.load(self.intl_id).cover_letter, "Nova carta")
        self.assertTrue(pkg.cover_letter_pdf.endswith("carta.pdf"))

    def test_respostas_so_confiaveis(self):
        svc = self.service()
        svc.prepare(self.intl_id)
        answers = svc.answer_questions(self.intl_id, ["Why Acme?", "Salary expectation?", "Start date?", " "])
        self.assertEqual(answers, {"Why Acme?": "Because of pipelines."})
        self.assertIn("respostas_padrao", self.llm.calls[-1]["content"][0]["text"])
        self.assertEqual(svc.answer_questions(self.intl_id, []), {})

    def test_enviada_conta_no_funil_e_no_followup(self):
        svc = self.service()
        svc.prepare(self.intl_id)
        svc.mark_submitted(self.intl_id)
        _, total = funnel_stats(self.repo.funnel_rows())
        self.assertEqual(total.contacted, 1)
        self.clock.now += timedelta(days=6)
        self.assertEqual([l.id for l in self.repo.pending_followups()], [self.intl_id])
        # preparar de novo nao rebaixa o status
        svc.prepare(self.intl_id)
        self.assertEqual(self.repo.get(self.intl_id).status, LeadStatus.CANDIDATURA_ENVIADA)


class RankingTest(Base):
    def test_score_e_ordem(self):
        proven = {"Python", "SQL & Relational DBs", "PostgreSQL"}
        gh = self.repo.get(self.gh_id)
        self.assertEqual(match_score(gh, proven), 67)  # Python, PostgreSQL; falta Django
        acme = self.repo.get(self.intl_id)
        self.assertIsNone(match_score(acme, proven))
        sem_canal = Lead(company="X", title="Python", source="s", url="u", id=99)
        ordered = sorted([(sem_canal, 100), (acme, None), (gh, 67)], key=lambda p: queue_key(*p))
        self.assertEqual([l.company for l, _ in ordered], ["Beta", "Acme", "X"])


def field(pid, label, tag="input", type="text", required=False, **kw):
    return FormField(pid=pid, tag=tag, type=type, label=label, required=required, **kw)


class FieldPlanTest(unittest.TestCase):
    VALUES = {"first_name": "Raphael", "last_name": "Ramos", "full_name": "Raphael Ramos",
              "email": "r@x.com", "phone": "+55", "linkedin": "https://linkedin.com/in/r",
              "github": "https://github.com/r", "website": "https://github.com/r", "location": "Campina Grande",
              "company": "BINGO", "resume": "/tmp/cv.pdf", "cover_letter": "Carta"}

    def test_greenhouse(self):
        fields = [
            field("p0", "First Name*", required=True), field("p1", "Last Name*", required=True),
            field("p2", "Email*", type="email", required=True), field("p3", "Phone", type="tel"),
            field("p4", "Resume/CV*", type="file", required=True), field("p5", "Cover Letter", type="file"),
            field("p6", "LinkedIn Profile"), field("p7", "Why do you want to work at Acme?*", tag="textarea", required=True),
            field("p8", "Are you legally authorized to work in the US?*", tag="select", type="select-one", required=True),
            field("p9", "Website"), field("p10", "Preferred pronouns"),
            field("p11", "Email", type="email", has_value=True),
        ]
        plan = plan_fields(fields, self.VALUES, "/tmp/carta.txt")
        self.assertEqual(plan.fills, {"p0": "Raphael", "p1": "Ramos", "p2": "r@x.com", "p3": "+55",
                                      "p6": "https://linkedin.com/in/r", "p9": "https://github.com/r"})
        self.assertEqual(plan.files, {"p4": "/tmp/cv.pdf", "p5": "/tmp/carta.txt"})
        self.assertEqual(plan.questions, {"p7": "Why do you want to work at Acme?*"})
        self.assertEqual([f.pid for f in plan.manual], ["p8"])

    def test_lever_e_nomes(self):
        fields = [field("a", "Full name✱", name="name"), field("b", "Current company", name="org"),
                  field("c", "Additional information", tag="textarea", name="comments"),
                  field("d", "GitHub URL", name="urls[GitHub]"), field("e", "Resume/CV", type="file", name="resume")]
        plan = plan_fields(fields, self.VALUES)
        self.assertEqual(plan.fills["a"], "Raphael Ramos")
        self.assertEqual(plan.fills["b"], "BINGO")
        self.assertEqual(plan.fills["d"], "https://github.com/r")
        self.assertEqual(plan.questions, {"c": "Additional information"})
        # Nome + Sobrenome em portugues
        pt = plan_fields([field("n", "Nome"), field("s", "Sobrenome")], self.VALUES)
        self.assertEqual(pt.fills, {"n": "Raphael", "s": "Ramos"})
        self.assertEqual(plan_fields([field("n", "Nome")], self.VALUES).fills, {"n": "Raphael Ramos"})

    def test_carta_em_textarea_e_sem_valor(self):
        plan = plan_fields([field("c", "Cover letter", tag="textarea", required=True)], self.VALUES)
        self.assertEqual(plan.fills, {"c": "Carta"})
        plan = plan_fields([field("c", "Cover letter", type="file", required=True)], self.VALUES, "")
        self.assertEqual([f.pid for f in plan.manual], ["c"])
        self.assertIsNone(classify(field("r", "Resume link (optional)", type="url")))

    def test_perguntas_nao_viram_dado_fixo(self):
        fields = [field("a", "Are you subject to agreements with your current employer?*", tag="select", required=True),
                  field("b", "Have you ever worked at your current company before?"),
                  field("c", "What's the name you'd prefer us to use?"),
                  field("d", "Country of Residence"),
                  field("e", "Current company")]
        plan = plan_fields(fields, {**self.VALUES, "country": "Brazil"})
        self.assertEqual(plan.fills, {"c": "Raphael", "d": "Brazil", "e": "BINGO"})
        self.assertEqual(plan.questions, {"b": "Have you ever worked at your current company before?"})
        self.assertEqual([f.pid for f in plan.manual], ["a"])

    def test_select_e_radio_preenchidos_pelas_respostas_padrao(self):
        fields = [
            field("s", "Are you legally authorized to work in the US?*", tag="select", type="select-one",
                  required=True, options=["", "Yes", "No"]),
            field("r", "Do you require visa sponsorship?", type="radio", options=["Yes", "No"]),
        ]
        answers = {"authorized to work": "Yes", "visa sponsorship": "No"}
        plan = plan_fields(fields, self.VALUES, answers=answers)
        self.assertEqual(plan.choices, {"s": "Yes"})
        self.assertEqual(plan.radio_picks, {"r": 1})
        self.assertEqual(plan.manual, [])

    def test_select_sem_resposta_correspondente_fica_manual(self):
        fields = [field("s", "Are you legally authorized to work in the US?*", tag="select", type="select-one",
                        required=True, options=["", "Yes", "No"])]
        plan = plan_fields(fields, self.VALUES, answers={"outra pergunta": "Yes"})
        self.assertEqual(plan.choices, {})
        self.assertEqual([f.pid for f in plan.manual], ["s"])

    def test_resposta_sem_opcao_correspondente_fica_manual(self):
        fields = [field("s", "How did you hear about us?", tag="select", required=True,
                        options=["LinkedIn", "Referral"])]
        plan = plan_fields(fields, self.VALUES, answers={"como soube da vaga": "Company careers page"})
        self.assertEqual(plan.choices, {})
        self.assertEqual([f.pid for f in plan.manual], ["s"])

    def test_resposta_curta_nao_casa_por_substring_solta(self):
        # "No" nao pode "vazar" pra dentro de "now"/"not": marcar a opcao errada numa
        # pergunta sensivel (patrocinio de visto) e pior do que deixar manual.
        from prospector.adapters.autofill.fields import match_option
        self.assertIsNone(match_option("No", ["I require sponsorship now", "I do not require sponsorship"]))
        self.assertEqual(match_option("No", ["Yes", "No"]), (1, "No"))
        self.assertEqual(match_option("Company careers page", ["LinkedIn", "Company careers page"]), (1, "Company careers page"))

    def test_select_nao_obrigatorio_sem_resposta_e_ignorado(self):
        fields = [field("s", "Pronouns", tag="select", options=["He", "She", "They"])]
        plan = plan_fields(fields, self.VALUES, answers={})
        self.assertEqual(plan.choices, {})
        self.assertEqual(plan.manual, [])

    def test_urls(self):
        self.assertEqual(application_url("https://jobs.lever.co/acme/abc"), "https://jobs.lever.co/acme/abc/apply")
        self.assertEqual(application_url("https://jobs.lever.co/acme/abc/apply"), "https://jobs.lever.co/acme/abc/apply")
        self.assertEqual(application_url("https://jobs.ashbyhq.com/x/1"), "https://jobs.ashbyhq.com/x/1/application")
        self.assertEqual(application_url("https://job-boards.greenhouse.io/a/jobs/1"), "https://job-boards.greenhouse.io/a/jobs/1")
        self.assertEqual(detect_ats("https://apply.workable.com/x/j/1"), "workable")


class FakeWorker:
    def __init__(self):
        self.jobs = []

    def submit(self, lead_id, url, values, cover_path, answer_fn, answers=None):
        self.jobs.append((lead_id, url, values, cover_path, answer_fn, answers))
        return "future"


class ApplyFlowTest(Base):
    def test_com_e_sem_navegador(self):
        app = self.service()
        with self.assertRaisesRegex(ApplicationError, "prepare"):
            ApplyFlow(app, self.profile, self.store).start(self.intl_id)
        app.prepare(self.intl_id)
        worker = FakeWorker()
        mode, fut = ApplyFlow(app, self.profile, self.store, worker=worker).start(self.intl_id)
        self.assertEqual((mode, fut), ("autofill", "future"))
        lead_id, url, values, cover, answer_fn, answers = worker.jobs[0]
        self.assertEqual(answers, self.profile.standard_answers)
        self.assertEqual(values["first_name"], "Raphael")
        self.assertEqual(values["phone"], "+55 83 90000-0000")  # do CV-mestre, perfil sem telefone
        self.assertTrue(values["resume"].endswith(".pdf"))
        self.assertTrue(cover.endswith("carta.pdf"))  # PDF preferido ao .txt quando disponivel
        self.assertEqual(answer_fn(["Why Acme?"]), {"Why Acme?": "Because of pipelines."})

        opened = []
        mode, payload = ApplyFlow(app, self.profile, self.store, opener=opened.append).start(self.intl_id)
        self.assertEqual(mode, "manual")
        self.assertEqual(opened, ["https://job-boards.greenhouse.io/acme/jobs/1"])
        self.assertEqual(profile_values(self.profile, None, None)["resume"], "")


if __name__ == "__main__":
    unittest.main()
