"""Painel: seguranca (host e token), consultas, tarefas e arquivos."""
import copy
import http.client
import json
import os
import tempfile
import threading
import time
import unittest

from prospector.adapters.storage import SqliteLeadRepository
from prospector.container import Container
from prospector.domain.lead import Lead, Region
from prospector.domain.resume import MasterResume, assign_ids
from prospector.profile import EXAMPLE_PATH, load_profile
from prospector.services.application import ApplicationService
from prospector.services.apply_flow import ApplyFlow
from prospector.services.resume_store import ResumeStore
from prospector.web.server import serve
from tests.fakes_llm import MASTER, TAILORED, FakeLlm
from tests.test_application import StubJd, StubPdf


class PanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = cls.tmp.name
        repo = SqliteLeadRepository(os.path.join(tmp, "p.db"))
        c = Container(repo=repo, use_browser=False)
        profile = load_profile(EXAMPLE_PATH)
        store = ResumeStore(os.path.join(tmp, "resume.json"))
        store.save(MasterResume.from_dict(assign_ids(copy.deepcopy(MASTER))))
        llm = FakeLlm({"registrar_adaptacao": TAILORED})
        apps = ApplicationService(repo, profile, store, llm, StubJd({}), StubPdf(), os.path.join(tmp, "apps"))
        opened = []
        c.__dict__.update(profile=profile, resume_store=store, llm=llm, applications=apps,
                          miners={}, apply_flow=ApplyFlow(apps, profile, store, opener=opened.append))
        cls.opened = opened
        cls.ids = [
            repo.add(Lead(company="SemCanal", title="Python dev", source="s", url="https://x/1")),
            repo.add(Lead(company="Acme", title="Acme - Backend", source="Greenhouse (Acme)",
                          url="https://job-boards.greenhouse.io/acme/jobs/1", region=Region.INTL,
                          ats_links=["https://job-boards.greenhouse.io/acme/jobs/1"],
                          raw_body="Python, PostgreSQL and Docker")),
        ]
        cls.app, cls.httpd = serve(c, port=0, token="segredo")
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, token="segredo", host="127.0.0.1"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": f"{host}:{self.port}", "Content-Type": "application/json"}
        if token:
            headers["X-Prospector-Token"] = token
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        ctype = resp.getheader("Content-Type", "")
        return resp.status, (json.loads(raw) if "json" in ctype else raw)

    def wait(self, job):
        for _ in range(100):
            _, j = self.call("GET", f"/api/jobs/{job['id']}")
            if j["state"] != "running":
                return j
            time.sleep(0.05)
        self.fail("tarefa não terminou")

    def test_seguranca(self):
        self.assertEqual(self.call("GET", "/api/state", token=None)[0], 401)
        self.assertEqual(self.call("GET", "/api/state", token="errado")[0], 401)
        self.assertEqual(self.call("GET", "/api/state", host="evil.example.com")[0], 403)
        status, html = self.call("GET", "/?token=segredo", token=None)
        self.assertEqual(status, 200)
        self.assertIn(b'const TOKEN = "segredo"', html)
        self.assertNotIn(b"__TOKEN__", html)

    def test_estado_e_fila(self):
        status, state = self.call("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(state["resume_loaded"])
        self.assertFalse(state["autofill"])
        _, queue = self.call("GET", "/api/queue")
        self.assertEqual(queue[0]["company"], "Acme")  # tem link de ATS, vem primeiro
        self.assertEqual(queue[0]["score"], 100)
        _, filtered = self.call("GET", "/api/queue?q=semcanal")
        self.assertEqual([l["company"] for l in filtered], ["SemCanal"])
        self.assertEqual(self.call("GET", "/api/leads/999")[0], 404)

    def test_preparar_arquivos_aplicar_e_status(self):
        acme = self.ids[1]
        status, job = self.call("POST", f"/api/leads/{acme}/prepare", {"language": "en"})
        self.assertEqual(status, 202)
        done = self.wait(job)
        self.assertEqual(done["state"], "done", done)
        _, lead = self.call("GET", f"/api/leads/{acme}")
        self.assertEqual(lead["status"], "candidatura_preparada")
        self.assertEqual(lead["package"]["language"], "en")

        status, body = self.call("GET", f"/files/{acme}/cv.pdf")
        self.assertEqual((status, body), (200, b"%PDF fake"))
        self.assertEqual(self.call("GET", f"/files/{acme}/meta.json")[0], 404)
        self.assertEqual(self.call("GET", f"/files/{acme}/..%2Fp.db")[0], 404)

        status, pkg = self.call("POST", f"/api/leads/{acme}/cover-letter", {"text": "Carta nova"})
        self.assertEqual((status, pkg["cover_letter"]), (200, "Carta nova"))

        _, job = self.call("POST", f"/api/leads/{acme}/apply")
        done = self.wait(job)
        self.assertEqual(done["result"]["mode"], "manual")
        self.assertEqual(self.opened[-1], "https://job-boards.greenhouse.io/acme/jobs/1")

        status, lead = self.call("POST", f"/api/leads/{acme}/status", {"status": "candidatura_enviada"})
        self.assertEqual((status, lead["status"]), (200, "candidatura_enviada"))
        self.assertEqual(self.call("POST", f"/api/leads/{acme}/status", {"status": "inventado"})[0], 400)
        _, stats = self.call("GET", "/api/stats")
        self.assertEqual(stats["total"]["contacted"], 1)

    def test_erros_de_tarefa(self):
        _, job = self.call("POST", "/api/leads/999/prepare", {})
        done = self.wait(job)
        self.assertEqual(done["state"], "error")
        self.assertIn("não encontrado", done["error"])
        _, job = self.call("POST", f"/api/leads/{self.ids[0]}/apply")
        self.assertIn("prepare", self.wait(job)["error"])
        self.assertEqual(self.call("POST", "/api/nada", {})[0], 404)


if __name__ == "__main__":
    unittest.main()
