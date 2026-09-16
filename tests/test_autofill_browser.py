"""Preenchimento real num Chromium headless contra formularios de teste (sem internet).

Roda so quando o Playwright para Python e um Chromium estao disponiveis; caso contrario e
ignorado. Para rodar no seu Mac: `pip3 install playwright && python3 -m playwright install chromium`.
"""
import functools
import glob
import http.server
import os
import tempfile
import threading
import unittest

from prospector.adapters.autofill.browser import (
    AutofillWorker, BrowserSession, fill_page, playwright_available,
)

FORMS = os.path.join(os.path.dirname(__file__), "fixtures", "forms")


def find_chromium():
    env = os.environ.get("PROSPECTOR_TEST_CHROME")
    if env:
        return env
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    return hits[0] if hits else ""


@unittest.skipUnless(playwright_available(), "Playwright não instalado")
class BrowserAutofillTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        handler = functools.partial(Quiet, directory=FORMS)
        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.session = BrowserSession(os.path.join(cls.tmp.name, "profile"), chrome_path=find_chromium(), headless=True)
        try:
            cls.ctx = cls.session.context()
        except Exception as e:  # sem navegador disponivel
            cls.httpd.shutdown()
            raise unittest.SkipTest(f"Chromium indisponível: {e}")
        cls.cv = os.path.join(cls.tmp.name, "Curriculo_Raphael_Ramos_Acme.pdf")
        with open(cls.cv, "wb") as f:
            f.write(b"%PDF-1.4 teste")
        cls.letter = os.path.join(cls.tmp.name, "carta.txt")
        with open(cls.letter, "w") as f:
            f.write("Carta")
        cls.values = {"first_name": "Raphael", "last_name": "Ramos", "full_name": "Raphael Ramos",
                      "email": "raphael@example.com", "phone": "+55 83 90000-0000",
                      "linkedin": "https://linkedin.com/in/r", "github": "https://github.com/raphacramos",
                      "website": "https://github.com/raphacramos", "location": "Campina Grande",
                      "company": "Projeto BINGO", "resume": cls.cv, "cover_letter": "Carta completa."}

    @classmethod
    def tearDownClass(cls):
        cls.session.close()
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def open(self, name):
        page = self.ctx.new_page()
        self.addCleanup(page.close)
        page.goto(f"{self.base}/{name}")
        return page

    def test_greenhouse(self):
        page = self.open("greenhouse.html")
        asked = []

        def answer(questions):
            asked.extend(questions)
            return {q: "Because of the data platform." for q in questions if q.startswith("Why")}

        rep = fill_page(page, 1, page.url, self.values, self.letter, answer)
        self.assertEqual(page.input_value("#first_name"), "Raphael")
        self.assertEqual(page.input_value("#last_name"), "Ramos")
        self.assertEqual(page.input_value("#email"), "raphael@example.com")
        self.assertEqual(page.input_value("#question_1"), "https://linkedin.com/in/r")
        self.assertEqual(page.input_value("#question_2"), "Because of the data platform.")
        self.assertEqual(page.input_value("#question_3"), "")
        self.assertEqual(page.eval_on_selector("#resume", "e => e.files[0].name"), "Curriculo_Raphael_Ramos_Acme.pdf")
        self.assertEqual(page.eval_on_selector("#cover_letter", "e => e.files[0].name"), "carta.txt")
        self.assertEqual(sorted(asked), ["What is your salary expectation?*", "Why do you want to work at Acme?*"])
        self.assertIn("What is your salary expectation?*", rep.manual)
        self.assertIn("Are you legally authorized to work in the US?*", rep.manual)
        self.assertEqual(rep.answered, ["Why do you want to work at Acme?*"])
        self.assertFalse(page.evaluate("window.submitted"))
        self.assertIn("precisam de você", page.inner_text("#prospector-bar"))
        self.assertEqual(rep.errors, [])

    def test_lever(self):
        page = self.open("lever.html")
        rep = fill_page(page, 2, page.url, self.values, self.letter,
                        lambda qs: {q: "The data work." for q in qs if "interests" in q})
        self.assertEqual(page.input_value("input[name=name]"), "Raphael Ramos")
        self.assertEqual(page.input_value("input[name=org]"), "Projeto BINGO")
        self.assertEqual(page.input_value("input[name='urls[GitHub]']"), "https://github.com/raphacramos")
        self.assertEqual(page.input_value("textarea[name='cards[a][field0]']"), "The data work.")
        self.assertEqual(page.eval_on_selector("input[name=resume]", "e => e.files.length"), 1)
        self.assertIn("Do you require visa sponsorship?✱", rep.manual)
        self.assertEqual(page.input_value("textarea[name=comments]"), "")  # sem resposta confiavel: fica vazio

    def test_lever_radio_marcado_pelas_respostas_padrao(self):
        page = self.open("lever.html")
        rep = fill_page(page, 2, page.url, self.values, self.letter, lambda qs: {},
                        answers={"visa sponsorship": "No"})
        self.assertTrue(page.is_checked('input[name="cards[a][field1]"][value="No"]'))
        self.assertFalse(page.is_checked('input[name="cards[a][field1]"][value="Yes"]'))
        self.assertIn("Do you require visa sponsorship?✱", rep.filled)
        self.assertNotIn("Do you require visa sponsorship?✱", rep.manual)

    def test_ashby_renderizado_depois(self):
        page = self.open("ashby.html")
        rep = fill_page(page, 3, page.url, self.values, self.letter, lambda qs: {})
        self.assertEqual(page.input_value("#_systemfield_name"), "Raphael Ramos")
        self.assertEqual(page.evaluate("window.reactValue"), "Raphael Ramos")
        self.assertEqual(page.eval_on_selector("#_systemfield_resume", "e => e.files.length"), 1)
        self.assertEqual(page.input_value("#f1"), "https://linkedin.com/in/r")
        self.assertEqual(page.input_value("#f2"), "")          # combobox fica para voce
        self.assertEqual(page.input_value("#f4"), "já preenchido")
        self.assertEqual(rep.uploaded, ["Curriculo_Raphael_Ramos_Acme.pdf"])


class WorkerTest(unittest.TestCase):
    """O worker usa o Playwright numa thread propria, como no painel."""

    def test_fila_em_thread(self):
        if not playwright_available():
            self.skipTest("Playwright não instalado")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        session = BrowserSession(os.path.join(tmp.name, "profile"), chrome_path=find_chromium(), headless=True)
        worker = AutofillWorker(session)
        url = "file://" + os.path.join(FORMS, "lever.html")
        fut = worker.submit(9, url, {"full_name": "Raphael Ramos", "email": "r@x.com"}, "", lambda qs: {})
        try:
            rep = fut.result(timeout=90)
        except Exception as e:
            self.skipTest(f"Chromium indisponível: {e}")
        finally:
            worker.stop(wait=True)
        self.assertEqual(rep.lead_id, 9)
        self.assertIn("Full name✱", rep.filled)
        self.assertTrue(rep.url.endswith("lever.html"))  # arquivo local nao ganha /apply
        self.assertIsNone(session._context)


if __name__ == "__main__":
    unittest.main()
