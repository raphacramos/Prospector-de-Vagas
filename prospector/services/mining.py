"""Caso de uso: minerar fontes, aplicar filtros comuns, deduplicar e salvar."""
from dataclasses import dataclass, field
from typing import Dict, List

from prospector.adapters.miners.filters import is_remote
from prospector.ports import SourceUnavailable


@dataclass
class SourceResult:
    name: str
    label: str
    found: int = 0
    error: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class MiningReport:
    leads: list = field(default_factory=list)
    sources: Dict[str, SourceResult] = field(default_factory=dict)
    inserted: int = 0
    duplicates: int = 0


class MiningService:
    def __init__(self, miners, repo):
        self.miners = miners
        self.repo = repo

    def run(self, names, options, on_source_start=None):
        report = MiningReport()
        seen = set()
        for name in names:
            miner = self.miners[name]
            result = SourceResult(name=name, label=miner.label)
            report.sources[name] = result
            if on_source_start:
                on_source_start(miner)
            try:
                leads = miner.mine(options)
            except SourceUnavailable as e:
                result.error = str(e)
                continue
            result.warnings = list(getattr(miner, "warnings", []))
            for lead in leads:
                if options.remote_only and not is_remote(lead.location):
                    continue
                key = lead.url or (lead.company, lead.title)
                if key in seen:
                    continue
                seen.add(key)
                report.leads.append(lead)
                result.found += 1
        report.inserted, report.duplicates = self.repo.add_many(report.leads)
        return report
