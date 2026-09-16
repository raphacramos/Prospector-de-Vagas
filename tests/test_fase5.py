"""Fase 5: mineradores Lever/Ashby, JD do Ashby e metricas do funil."""
import os
import tempfile
import unittest
from datetime import datetime

from prospector.adapters.jd_fetcher import JobDescriptionFetcher
from prospector.adapters.miners.ashby import AshbyMiner
from prospector.adapters.miners.lever import LeverMiner
from prospector.adapters.storage import SqliteLeadRepository
from prospector.domain.lead import Lead, LeadStatus, Region
from prospector.ports import MiningOptions, SourceUnavailable
from prospector.services.funnel import funnel_stats, source_family
from tests.fakes import FakeHttp


class LeverMinerTest(unittest.TestCase):
    def test_filtra_e_mapeia(self):
        miner = LeverMiner(FakeHttp({"postings/acme": "lever_postings.json"}), companies=["acme"])
        leads = miner.mine(MiningOptions())
        self.assertEqual([l.url for l in leads], ["https://jobs.lever.co/acme/a1", "https://jobs.lever.co/acme/a3?lever-origin=applied"])
        first = leads[0]
        self.assertEqual((first.company, first.region, first.location, first.posted_at),
                         ("Acme", Region.INTL, "São Paulo (Remote)", "2026-09-08"))
        self.assertIn("Kafka", first.raw_body)

    def test_query_por_time(self):
        miner = LeverMiner(FakeHttp({"postings/acme": "lever_postings.json"}), companies=["acme"])
        self.assertEqual(len(miner.mine(MiningOptions(query="infra"))), 1)

    def test_empresa_inexistente_vira_aviso(self):
        miner = LeverMiner(FakeHttp({"postings/acme": "lever_postings.json", "postings/x": None}),
                           companies=["x", "acme"])
        self.assertEqual(len(miner.mine(MiningOptions())), 2)
        self.assertEqual(miner.warnings, ["empresa 'x' não encontrada no Lever"])

    def test_falha_de_rede_aborta_rapido(self):
        http = FakeHttp({"postings/": FakeHttp.NETWORK})
        with self.assertRaisesRegex(SourceUnavailable, "sem acesso"):
            LeverMiner(http, companies=["a", "b", "c"]).mine(MiningOptions())
        self.assertEqual(len(http.calls), 1)


class AshbyMinerTest(unittest.TestCase):
    def test_so_engenharia_listada(self):
        leads = AshbyMiner(FakeHttp({"job-board/acme": "ashby_board.json"}), orgs=["acme"]).mine(MiningOptions())
        self.assertEqual(len(leads), 1)
        self.assertEqual((leads[0].location, leads[0].posted_at), ("Remote (EMEA)", "2026-08-12"))
        self.assertEqual(leads[0].source, "Ashby (Acme)")

    def test_falha_de_rede_aborta_rapido(self):
        http = FakeHttp({"job-board/": FakeHttp.NETWORK})
        with self.assertRaises(SourceUnavailable):
            AshbyMiner(http, orgs=["a", "b"]).mine(MiningOptions())
        self.assertEqual(len(http.calls), 1)

    def test_jd_do_ashby_pela_api(self):
        http = FakeHttp({"job-board/acme": "ashby_board.json"})
        title, text = JobDescriptionFetcher(http).fetch(
            "https://jobs.ashbyhq.com/acme/0be1b52c-2401-4ae2-b7fc-5d018c1ff96f/application")
        self.assertEqual((title, text), ("Software Engineer - Backend", "Python, ClickHouse and Kafka."))


class FunnelStatsTest(unittest.TestCase):
    def test_source_family(self):
        self.assertEqual(source_family("Simplify NewGrad (2d)"), "Simplify NewGrad")
        self.assertEqual(source_family("Greenhouse (Gitlab)"), "Greenhouse")
        self.assertEqual(source_family("GitHub (backend-br/vagas)"), "GitHub (backend-br/vagas)")

    def test_taxa_de_resposta_pelo_historico(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = SqliteLeadRepository(os.path.join(tmp, "p.db"), clock=lambda: datetime(2026, 9, 1))
            ids = [repo.add(Lead(company=f"C{i}", title="t", source=src, url=f"https://{i}"))
                   for i, src in enumerate(["Simplify NewGrad (1d)", "Simplify NewGrad (9d)",
                                            "Greenhouse (A)", "Greenhouse (B)"])]
            repo.set_status(ids[0], LeadStatus.MENSAGEM_ENVIADA)
            repo.set_status(ids[0], LeadStatus.RESPOSTA)
            repo.set_status(ids[0], LeadStatus.DESCARTADA)  # descartada depois: continua contando a resposta
            repo.set_status(ids[1], LeadStatus.MENSAGEM_ENVIADA)
            repo.set_status(ids[2], LeadStatus.RASCUNHO_ABERTO)  # rascunho nao conta como contato
            per_source, total = funnel_stats(repo.funnel_rows())
        by = {s.source: s for s in per_source}
        simplify = by["Simplify NewGrad"]
        self.assertEqual((simplify.leads, simplify.contacted, simplify.replied, simplify.discarded), (2, 2, 1, 1))
        self.assertEqual(simplify.reply_rate, 50.0)
        self.assertEqual((by["Greenhouse"].contacted, by["Greenhouse"].reply_rate), (0, None))
        self.assertEqual((total.leads, total.contacted, total.replied), (4, 2, 1))


if __name__ == "__main__":
    unittest.main()


class EngineeringTitleTest(unittest.TestCase):
    def test_titulos_reais(self):
        from prospector.adapters.miners.filters import is_engineering_title
        aceitos = ["Backend Engineer, Mimir, Personalization", "Associate Software Engineer",
                   "Forward Deployed Infrastructure Engineer, New Grad - US Government",
                   "Senior C++/iOS Engineer - User Platform", "Python Developer", "SRE II"]
        recusados = ["Director of Engineering - Content Platform (Catalog)", "Engineering Manager - Data Platform",
                     "Global Associate Director, Experiential & Content Production",
                     "Product Manager - Data Platform", "Sales Engineer", "Data Analyst", "Product Designer"]
        for t in aceitos:
            self.assertTrue(is_engineering_title(t), t)
        for t in recusados:
            self.assertFalse(is_engineering_title(t), t)
