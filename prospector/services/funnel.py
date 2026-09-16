"""Metricas do funil por fonte, a partir do historico de status."""
import re
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class SourceStats:
    source: str
    leads: int = 0
    contacted: int = 0
    replied: int = 0
    discarded: int = 0

    @property
    def reply_rate(self):
        return round(100.0 * self.replied / self.contacted, 1) if self.contacted else None


def source_family(source):
    """'Simplify NewGrad (2d)' -> 'Simplify NewGrad'; 'GitHub (backend-br/vagas)' fica igual."""
    source = source or "?"
    if source.startswith("GitHub"):
        return source
    return re.sub(r"\s*\(.*\)\s*$", "", source) or source


def funnel_stats(rows):
    """rows: dicts com source, status, contacted, replied (ver SqliteLeadRepository.funnel_rows)."""
    by_source = OrderedDict()
    total = SourceStats("TOTAL")
    for r in sorted(rows, key=lambda r: source_family(r["source"])):
        key = source_family(r["source"])
        st = by_source.setdefault(key, SourceStats(key))
        for s in (st, total):
            s.leads += 1
            s.contacted += bool(r["contacted"])
            s.replied += bool(r["replied"])
            s.discarded += r["status"] == "descartada"
    return list(by_source.values()), total
