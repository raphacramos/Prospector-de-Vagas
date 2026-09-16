"""Repositorio SQLite: schema v3, historico, follow-up e migracao do banco v2."""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta

from prospector.adapters.storage import SqliteLeadRepository
from prospector.domain.lead import Lead, LeadStatus, Region

V2_SCHEMA = """
CREATE TABLE leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL, title TEXT NOT NULL, source TEXT NOT NULL,
    url TEXT UNIQUE, contact_info TEXT, raw_body TEXT,
    status TEXT DEFAULT 'minerado', notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    contacted_at TIMESTAMP, followup_due_at TIMESTAMP
)"""


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "prospector.db")
        self.backups = os.path.join(self.tmp.name, "backups")
        self.clock = Clock(datetime(2026, 9, 1, 10, 0, 0))

    def repo(self):
        return SqliteLeadRepository(self.db, backup_dir=self.backups, clock=self.clock)


class NewDatabaseTest(RepoTestCase):
    def test_add_get_roundtrip_e_dedup(self):
        repo = self.repo()
        self.assertIsNone(repo.last_backup_path)  # banco novo nao gera backup
        lead = Lead(company="Acme", title="Backend", source="Greenhouse (Acme)", url="https://a",
                    region=Region.INTL, emails=["a@acme.com"], ats_links=["https://a"],
                    labels=["Remote"], location="Remote", posted_at="2026-08-30")
        lead_id = repo.add(lead)
        self.assertIsNone(repo.add(lead))
        got = repo.get(lead_id)
        self.assertEqual((got.region, got.emails, got.ats_links, got.labels, got.location, got.posted_at),
                         (Region.INTL, ["a@acme.com"], ["https://a"], ["Remote"], "Remote", "2026-08-30"))
        self.assertEqual(got.status, LeadStatus.MINERADO)
        self.assertEqual([e["status"] for e in repo.events(lead_id)], ["minerado"])

    def test_urls_vazias_nao_colidem(self):
        repo = self.repo()
        a = repo.add(Lead(company="A", title="t", source="s", url=""))
        b = repo.add(Lead(company="B", title="t", source="s", url=""))
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)

    def test_followup_so_para_status_de_contato(self):
        repo = self.repo()
        lead_id = repo.add(Lead(company="A", title="t", source="s", url="https://x"))
        repo.set_status(lead_id, LeadStatus.RASCUNHO_ABERTO)
        self.assertIsNone(repo.get(lead_id).followup_due_at)

        repo.set_status(lead_id, LeadStatus.MENSAGEM_ENVIADA, note="smtp")
        self.assertEqual(repo.get(lead_id).followup_due_at, "2026-09-06 10:00:00")
        self.assertEqual(repo.pending_followups(), [])

        self.clock.now += timedelta(days=5)
        self.assertEqual([l.id for l in repo.pending_followups()], [lead_id])

        repo.set_status(lead_id, LeadStatus.RESPOSTA)
        self.assertEqual(repo.pending_followups(), [])
        got = repo.get(lead_id)
        self.assertEqual(got.contacted_at, "2026-09-01 10:00:00")  # resposta nao sobrescreve o contato
        self.assertEqual([e["status"] for e in repo.events(lead_id)],
                         ["minerado", "rascunho_aberto", "mensagem_enviada", "resposta"])

    def test_set_status_lead_inexistente(self):
        self.assertFalse(self.repo().set_status(999, LeadStatus.RESPOSTA))

    def test_list_filtra_status(self):
        repo = self.repo()
        a = repo.add(Lead(company="A", title="t", source="s", url="https://a"))
        repo.add(Lead(company="B", title="t", source="s", url="https://b"))
        repo.set_status(a, LeadStatus.DESCARTADA)
        self.assertEqual([l.company for l in repo.list_recent(status="descartada")], ["A"])
        self.assertEqual([l.company for l in repo.list_recent()], ["B", "A"])


class MigrationV2Test(RepoTestCase):
    def setUp(self):
        super().setUp()
        conn = sqlite3.connect(self.db)
        conn.execute(V2_SCHEMA)
        rows = [
            ("Acme", "Backend Jr", "GitHub (backend-br/vagas)", "https://gh/1",
             "rh@acme.com.br, https://jobs.lever.co/acme/123", "minerado", "2026-08-01 09:00:00", None),
            ("Beta", "SWE", "Simplify NewGrad (3d)", "https://jobs.ashbyhq.com/beta/1",
             "https://jobs.ashbyhq.com/beta/1", "mensagem_enviada", "2026-08-02 09:00:00", "2026-08-20 12:00:00"),
            ("Gama", "Data", "Hacker News (Ask HN...)", "https://hn/3",
             "jobs@gama.io", "status_estranho", "2026-08-03 09:00:00", None),
        ]
        conn.executemany(
            "INSERT INTO leads (company, title, source, url, contact_info, status, created_at, contacted_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        conn.close()

    def test_migra_com_backup_e_dados_estruturados(self):
        repo = self.repo()
        self.assertTrue(repo.last_backup_path and os.path.exists(repo.last_backup_path))
        backup = sqlite3.connect(repo.last_backup_path)
        self.assertEqual(backup.execute("SELECT count(*) FROM leads").fetchone()[0], 3)
        self.assertEqual(backup.execute("PRAGMA user_version").fetchone()[0], 0)
        backup.close()

        acme, beta, gama = repo.get(1), repo.get(2), repo.get(3)
        self.assertEqual((acme.region, acme.emails, acme.ats_links),
                         (Region.BR, ["rh@acme.com.br"], ["https://jobs.lever.co/acme/123"]))
        self.assertEqual(beta.region, Region.INTL)  # Simplify: antes recebia portugues
        self.assertEqual(beta.followup_due_at, "2026-08-25 12:00:00")
        self.assertEqual(gama.status, LeadStatus.MINERADO)  # status invalido normalizado
        self.assertEqual([e["status"] for e in repo.events(2)], ["minerado", "mensagem_enviada"])

        self.clock.now = datetime(2026, 9, 1)
        self.assertEqual([l.company for l in repo.pending_followups()], ["Beta"])

    def test_migracao_idempotente(self):
        self.repo()
        again = self.repo()
        self.assertIsNone(again.last_backup_path)
        self.assertEqual(len(again.events(2)), 2)
        self.assertEqual(len(os.listdir(self.backups)), 1)


if __name__ == "__main__":
    unittest.main()
