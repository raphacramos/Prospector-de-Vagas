"""CV-mestre, checagem de fidelidade, renderizacao e cliente da IA."""
import copy
import io
import json
import os
import tempfile
import unittest
import urllib.error
import zipfile

from prospector.adapters.llm_anthropic import AnthropicClient, validate_schema
from prospector.adapters.resume_files import ResumeFileError, content_blocks, docx_text
from prospector.adapters.resume_render import render_html
from prospector.domain.resume import (
    MasterResume, ResumeError, TailoredResume, assign_ids, enforce_faithfulness, resolve, untailored,
)
from prospector.ports import LlmError
from prospector.profile import EXAMPLE_PATH, load_profile
from prospector.services.prompts import IMPORT_SCHEMA
from prospector.services.resume_import import ResumeImportService
from prospector.services.resume_store import ResumeStore
from tests.fakes_llm import MASTER, TAILORED, FakeLlm


def master():
    return MasterResume.from_dict(assign_ids(copy.deepcopy(MASTER)))


class MasterResumeTest(unittest.TestCase):
    def test_ids_estaveis(self):
        m = master()
        self.assertEqual([e.id for e in m.experiences], ["exp1", "exp2"])
        self.assertEqual(m.experiences[0].bullets[2].id, "exp1.b3")
        self.assertEqual(m.projects[0].bullets[0].id, "proj1.b1")
        self.assertEqual(m.education[0].id, "edu1")
        self.assertEqual(MasterResume.from_dict(m.to_dict()).to_dict(), m.to_dict())

    def test_ids_repetidos(self):
        data = assign_ids(copy.deepcopy(MASTER))
        data["experiences"][1]["id"] = "exp1"
        with self.assertRaisesRegex(ResumeError, "repetido"):
            MasterResume.from_dict(data)

    def test_sem_nome(self):
        data = copy.deepcopy(MASTER)
        data["contact"]["name"] = " "
        with self.assertRaisesRegex(ResumeError, "sem nome"):
            MasterResume.from_dict(assign_ids(data))

    def test_competencias_comprovadas(self):
        self.assertTrue({"Python", "Linux & Internals", "Docker & Containers"} <= master().known_skills())


class FaithfulnessTest(unittest.TestCase):
    def tailored(self, **changes):
        data = copy.deepcopy(TAILORED)
        data.update(changes)
        return TailoredResume.from_dict({**data, "language": "en"})

    def test_saida_valida_passa_sem_avisos(self):
        t = enforce_faithfulness(master(), self.tailored())
        self.assertEqual(t.warnings, [])
        self.assertEqual(len(t.experiences[0].bullets), 2)

    def test_remove_invencoes(self):
        t = self.tailored(
            experiences=[
                {"id": "exp9", "bullets": [{"id": "exp9.b1", "text": "Led a team at Google"}]},
                {"id": "exp2", "bullets": [{"id": "exp1.b1", "text": "bullet de outra experiência"},
                                           {"id": "exp2.b1", "text": ""}]},
            ],
            skills=["Python", "Kubernetes", "python"],
            summary="Expert in Kafka and Python.",
        )
        enforce_faithfulness(master(), t)
        self.assertEqual([i.id for i in t.experiences], ["exp2"])
        self.assertEqual([b.id for b in t.experiences[0].bullets], ["exp2.b1"])
        self.assertEqual(t.experiences[0].bullets[0].text, "Ensinei estruturas de dados e algoritmos")
        self.assertEqual(t.skills, ["Python", "python"])
        joined = " ".join(t.warnings)
        self.assertIn("exp9", joined)
        self.assertIn("Kubernetes", joined)
        self.assertIn("kafka", joined.lower())

    def test_render(self):
        m = master()
        m.contact.name = "Raphael <Ramos>"
        html = render_html(resolve(m, enforce_faithfulness(m, self.tailored())))
        self.assertIn("Raphael &lt;Ramos&gt;", html)
        self.assertIn("Built Python telemetry pipelines with HDF5", html)
        self.assertIn("<h2>Experience</h2>", html)
        self.assertNotIn("Otimizei algoritmos", html)  # bullet nao escolhido fica fora
        self.assertIn("Projeto BINGO", html)

    def test_untailored_em_portugues(self):
        html = render_html(resolve(master(), untailored(master())))
        self.assertIn("<h2>Experiência</h2>", html)
        self.assertIn("Otimizei algoritmos", html)


def fake_response(body, status=200):
    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    if status != 200:
        return urllib.error.HTTPError("https://api", status, "err", {"retry-after": "0"},
                                      io.BytesIO(json.dumps({"error": {"message": "boom"}}).encode()))
    return Resp(json.dumps(body).encode())


class AnthropicClientTest(unittest.TestCase):
    SCHEMA = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}

    def client(self, responses):
        seen = []

        def opener(req, timeout):
            seen.append(json.loads(req.data))
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        c = AnthropicClient(api_key="k", model="m", opener=opener, sleep=lambda s: None)
        return c, seen

    def ok(self, value, stop="tool_use"):
        return fake_response({"stop_reason": stop, "usage": {"input_tokens": 10, "output_tokens": 5},
                              "content": [{"type": "text", "text": "..."},
                                          {"type": "tool_use", "name": "t", "input": value}]})

    def test_sucesso_e_corpo(self):
        c, seen = self.client([self.ok({"x": 3})])
        self.assertEqual(c.generate_json("sys", [{"type": "text", "text": "oi"}], self.SCHEMA, "t"), {"x": 3})
        body = seen[0]
        self.assertEqual(body["tool_choice"], {"type": "tool", "name": "t"})
        self.assertEqual(body["model"], "m")
        self.assertEqual(c.usage, {"input_tokens": 10, "output_tokens": 5})

    def test_retry_em_429(self):
        c, _ = self.client([fake_response(None, 429), fake_response(None, 529), self.ok({"x": 1})])
        self.assertEqual(c.generate_json("s", [], self.SCHEMA, "t"), {"x": 1})

    def test_erros(self):
        c, _ = self.client([fake_response(None, 401)])
        with self.assertRaisesRegex(LlmError, "401"):
            c.generate_json("s", [], self.SCHEMA, "t")
        c, _ = self.client([fake_response(None, 400)])
        with self.assertRaisesRegex(LlmError, "boom"):
            c.generate_json("s", [], self.SCHEMA, "t")
        c, _ = self.client([self.ok({"x": 1}, stop="max_tokens")])
        with self.assertRaisesRegex(LlmError, "cortada"):
            c.generate_json("s", [], self.SCHEMA, "t")
        c, _ = self.client([self.ok({"x": "três"})])
        with self.assertRaisesRegex(LlmError, "inválida"):
            c.generate_json("s", [], self.SCHEMA, "t")
        with self.assertRaisesRegex(LlmError, "ANTHROPIC_API_KEY"):
            AnthropicClient(api_key="").generate_json("s", [], self.SCHEMA, "t")

    def test_validate_schema(self):
        validate_schema({"language": "pt", "contact": {"name": "x"}, "experiences": [], "skills": []}, IMPORT_SCHEMA)
        with self.assertRaises(LlmError):
            validate_schema({"language": "es", "contact": {"name": "x"}, "experiences": [], "skills": []}, IMPORT_SCHEMA)
        with self.assertRaises(LlmError):
            validate_schema(True, {"type": "integer"})


def make_docx(path, paragraphs):
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(
        f'<w:p>{"<w:pPr><w:numPr/></w:pPr>" if bullet else ""}<w:r><w:t>{text}</w:t></w:r></w:p>'
        for text, bullet in paragraphs)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_docx_e_formatos(self):
        path = os.path.join(self.tmp.name, "cv.docx")
        make_docx(path, [("Raphael Ramos", False), ("Python e Linux", True)])
        self.assertEqual(docx_text(path), "Raphael Ramos\n• Python e Linux")
        pdf = os.path.join(self.tmp.name, "cv.pdf")
        with open(pdf, "wb") as f:
            f.write(b"%PDF-1.4 x")
        self.assertEqual(content_blocks(pdf)[0]["type"], "document")
        for bad in ("cv.doc", "cv.odt", "nao_existe.pdf"):
            p = os.path.join(self.tmp.name, bad)
            if bad != "nao_existe.pdf":
                open(p, "w").close()
            with self.assertRaises(ResumeFileError):
                content_blocks(p)

    def test_importa_salva_e_guarda_versao_anterior(self):
        src = os.path.join(self.tmp.name, "cv.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("meu cv")
        data = copy.deepcopy(MASTER)
        data["contact"]["email"] = ""
        llm = FakeLlm({"registrar_curriculo": data})
        store = ResumeStore(os.path.join(self.tmp.name, "data", "resume.json"))
        service = ResumeImportService(llm, store, load_profile(EXAMPLE_PATH))
        resume, backup = service.run(src)
        self.assertIsNone(backup)
        self.assertEqual(resume.contact.email, "raphaelramosc@gmail.com")  # completado pelo perfil
        self.assertEqual(llm.calls[0]["content"][0]["text"], "meu cv")
        self.assertEqual(store.load().experiences[0].bullets[0].id, "exp1.b1")
        _, backup = service.run(src)
        self.assertTrue(backup and os.path.exists(backup))

    def test_store_sem_arquivo(self):
        with self.assertRaisesRegex(ResumeError, "importar-cv"):
            ResumeStore(os.path.join(self.tmp.name, "x.json")).load()


if __name__ == "__main__":
    unittest.main()
