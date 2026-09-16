"""Mineradores com respostas gravadas (sem rede)."""
import unittest
from datetime import date

from prospector.adapters.miners import build_miners
from prospector.adapters.miners.filters import clean_url, date_from_age, extract_contacts, is_remote
from prospector.adapters.miners.github import GithubMiner, is_backend_role, parse_title
from prospector.adapters.miners.greenhouse import GreenhouseMiner
from prospector.adapters.miners.hacker_news import HackerNewsMiner, parse_header
from prospector.adapters.miners.simplify import SimplifyMiner
from prospector.domain.lead import Region
from prospector.ports import MiningOptions, SourceUnavailable
from prospector.services.mining import MiningService
from tests.fakes import FakeHttp


class FiltersTest(unittest.TestCase):
    def test_clean_url_remove_rastreamento(self):
        self.assertEqual(clean_url("https://x.io/jobs/1?utm_source=a&ref=Simplify&id=7&gh_src=z"),
                         "https://x.io/jobs/1?id=7")

    def test_extract_contacts(self):
        emails, links = extract_contacts(
            "mail a@b.com, a@b.com. logo@img.png https:&#x2F;&#x2F;jobs.lever.co&#x2F;acme&#x2F;1")
        self.assertEqual(emails, ["a@b.com"])
        self.assertEqual(links, ["https://jobs.lever.co/acme/1"])

    def test_date_from_age(self):
        today = date(2026, 9, 16)
        self.assertEqual(date_from_age("2d", today), "2026-09-14")
        self.assertEqual(date_from_age("1mo", today), "2026-08-17")
        self.assertEqual(date_from_age("??", today), "")

    def test_is_remote(self):
        self.assertTrue(is_remote("Remote, LATAM"))
        self.assertTrue(is_remote("Remoto"))
        self.assertFalse(is_remote("San Francisco, CA"))
        self.assertFalse(is_remote(""))


class GithubMinerTest(unittest.TestCase):
    def setUp(self):
        self.http = FakeHttp({"api.github.com": "github_issues.json"})
        self.miner = GithubMiner(self.http, repos=["backend-br/vagas"])

    def test_filtra_template_vendedor_gupy_senior_e_pr(self):
        leads = self.miner.mine(MiningOptions())
        self.assertEqual([l.url for l in leads], ["https://github.com/backend-br/vagas/issues/1"])
        lead = leads[0]
        self.assertEqual((lead.company, lead.location, lead.region), ("Acme Tecnologia", "Remoto", Region.BR))
        self.assertEqual(lead.emails, ["vagas@acme.com.br"])
        self.assertEqual(lead.ats_links, ["https://jobs.lever.co/acme/abc-123"])
        self.assertEqual(lead.posted_at, "2026-09-10")

    def test_all_levels_inclui_senior(self):
        leads = self.miner.mine(MiningOptions(all_levels=True))
        self.assertIn("DataCo", [l.company for l in leads])

    def test_query(self):
        self.assertEqual(self.miner.mine(MiningOptions(all_levels=True, query="pipelines"))[0].company, "DataCo")

    def test_fonte_fora_do_ar(self):
        miner = GithubMiner(FakeHttp({"api.github.com": None}), repos=["a/b"])
        with self.assertRaises(SourceUnavailable):
            miner.mine(MiningOptions())

    def test_parse_title(self):
        self.assertEqual(parse_title("[Híbrido - SP] Back-end developer Cobol TED - Evertec"),
                         ("Back-end developer Cobol TED - Evertec", "Híbrido - SP", "Evertec"))
        self.assertEqual(parse_title("[Hiring] Senior Engineer")[2], "")

    def test_is_backend_role(self):
        self.assertFalse(is_backend_role("Vendedor com english fluente"))
        self.assertTrue(is_backend_role("Engenheira de Dados Jr - Python"))


class HackerNewsMinerTest(unittest.TestCase):
    def test_so_comentarios_de_primeiro_nivel(self):
        http = FakeHttp({"search_by_date": "hn_story.json", "search?tags=comment": "hn_comments.json"})
        leads = HackerNewsMiner(http).mine(MiningOptions())
        self.assertEqual(len(leads), 2)
        first = leads[0]
        self.assertEqual(first.company, "VersaFeed.com")
        self.assertEqual(first.location, "REMOTE (USA ONLY)")
        self.assertEqual(first.emails, ["jobs@versafeed.example.org"])
        self.assertEqual(first.ats_links, ["https://jobs.ashbyhq.com/versafeed/42"])
        self.assertIn("YC Startup", leads[1].labels)
        self.assertIn("story_900", http.calls[1])
        self.assertIn("Python%20Remote", http.calls[1])

    def test_parse_header_sem_pipe(self):
        self.assertEqual(parse_header("We are hiring<p>x")[0], "Startup HN")

    def test_sem_thread(self):
        with self.assertRaises(SourceUnavailable):
            HackerNewsMiner(FakeHttp({"search_by_date": None})).mine(MiningOptions())


class GreenhouseMinerTest(unittest.TestCase):
    def miner(self, routes=None):
        return GreenhouseMiner(FakeHttp(routes or {"boards/acme": "greenhouse_jobs.json"}), companies=["acme"])

    def test_filtra_titulos_e_limpa_url(self):
        leads = self.miner().mine(MiningOptions())
        self.assertEqual([l.url for l in leads],
                         ["https://job-boards.greenhouse.io/acme/jobs/1", "https://job-boards.greenhouse.io/acme/jobs/2"])
        self.assertEqual(leads[0].location, "Remote, LATAM")
        self.assertEqual(leads[0].posted_at, "2026-09-14")

    def test_query(self):
        self.assertEqual(len(self.miner().mine(MiningOptions(query="python"))), 1)

    def test_board_inexistente_vira_aviso(self):
        miner = GreenhouseMiner(FakeHttp({"boards/acme": "greenhouse_jobs.json", "boards/morta": None}),
                                companies=["acme", "morta"])
        self.assertEqual(len(miner.mine(MiningOptions())), 2)
        self.assertEqual(miner.warnings, ["board 'morta' indisponível"])

    def test_todos_indisponiveis(self):
        with self.assertRaises(SourceUnavailable):
            self.miner({"boards/acme": None}).mine(MiningOptions())


class SimplifyMinerTest(unittest.TestCase):
    def setUp(self):
        self.miner = SimplifyMiner(FakeHttp({"SimplifyJobs": "simplify_readme.md"}))

    def test_fast_ats_empresa_herdada_e_inativas(self):
        leads = self.miner.mine(MiningOptions())
        self.assertEqual([(l.company, l.url) for l in leads], [
            ("SingleStore", "https://job-boards.greenhouse.io/singlestore/jobs/8205427"),
            ("SingleStore", "https://jobs.lever.co/singlestore/xyz"),
        ])
        self.assertTrue(all(l.region is Region.INTL for l in leads))
        self.assertTrue(leads[0].posted_at)

    def test_all_ats_inclui_sites_proprios_mas_nunca_workday(self):
        leads = self.miner.mine(MiningOptions(all_ats=True))
        self.assertEqual([l.company for l in leads], ["SingleStore", "SingleStore", "Bigcorp"])
        self.assertEqual(leads[-1].location, "NYC / Boston")
        self.assertEqual(leads[-1].ats_links, [])


class FakeRepo:
    def __init__(self):
        self.saved = []

    def add_many(self, leads):
        self.saved.extend(leads)
        return len(leads), 0


class MiningServiceTest(unittest.TestCase):
    def setUp(self):
        http = FakeHttp({
            "api.github.com": None,
            "boards/acme": "greenhouse_jobs.json",
            "SimplifyJobs": "simplify_readme.md",
        })
        self.miners = build_miners(http, sources={"github": ["a/b"], "greenhouse": ["acme"]})
        self.repo = FakeRepo()

    def test_fonte_com_erro_nao_derruba_as_outras(self):
        report = MiningService(self.miners, self.repo).run(["github", "greenhouse"], MiningOptions())
        self.assertTrue(report.sources["github"].error)
        self.assertEqual(report.sources["greenhouse"].found, 2)
        self.assertEqual(len(self.repo.saved), 2)

    def test_remote_only_vale_para_todas_as_fontes(self):
        report = MiningService(self.miners, self.repo).run(
            ["greenhouse", "simplify"], MiningOptions(remote_only=True))
        self.assertEqual(sorted(l.location for l in report.leads), ["Remote in USA", "Remote, LATAM"])

    def test_registro_tem_as_fontes_da_cli(self):
        self.assertEqual(list(build_miners(None)), ["github", "hn", "greenhouse", "lever", "ashby", "simplify"])


if __name__ == "__main__":
    unittest.main()
