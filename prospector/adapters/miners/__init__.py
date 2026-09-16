"""Registro dos mineradores. Para adicionar uma fonte: crie a classe e inclua em build_miners."""
from prospector.adapters.miners.github import GithubMiner
from prospector.adapters.miners.greenhouse import GreenhouseMiner
from prospector.adapters.miners.hacker_news import HackerNewsMiner
from prospector.adapters.miners.simplify import SimplifyMiner


def build_miners(http, sources=None):
    """Retorna {nome: miner} na ordem de execucao. `sources` vem do profile (listas de empresas/repos)."""
    sources = sources or {}
    miners = [
        GithubMiner(http, repos=sources.get("github")),
        HackerNewsMiner(http),
        GreenhouseMiner(http, companies=sources.get("greenhouse")),
        SimplifyMiner(http),
    ]
    return {m.name: m for m in miners}
