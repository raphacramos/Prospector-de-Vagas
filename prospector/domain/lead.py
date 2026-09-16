"""Entidade Lead e enums do funil. Sem I/O."""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Region(str, Enum):
    """Define idioma da mensagem e do curriculo."""
    BR = "br"
    INTL = "intl"


class LeadStatus(str, Enum):
    MINERADO = "minerado"
    RASCUNHO_ABERTO = "rascunho_aberto"
    CONEXAO_ENVIADA = "conexao_enviada"
    MENSAGEM_ENVIADA = "mensagem_enviada"
    AGUARDANDO_FOLLOWUP = "aguardando_followup"
    RESPOSTA = "resposta"
    ENTREVISTA = "entrevista"
    DESCARTADA = "descartada"

    @classmethod
    def values(cls):
        return [s.value for s in cls]


# Status em que ja houve contato e esperamos resposta (contam para o follow-up).
AWAITING_REPLY = frozenset({
    LeadStatus.CONEXAO_ENVIADA,
    LeadStatus.MENSAGEM_ENVIADA,
    LeadStatus.AGUARDANDO_FOLLOWUP,
})

# Status que representam retorno positivo da empresa.
POSITIVE = frozenset({LeadStatus.RESPOSTA, LeadStatus.ENTREVISTA})

FOLLOWUP_DAYS = 5

_INTERNATIONAL_SOURCE_MARKERS = ("hacker news", "greenhouse", "simplify", "international", "lever", "ashby")


def region_from_source(source):
    """Deduz a regiao pela origem. Usado para leads antigos (schema v2); miners novos definem a regiao."""
    src = (source or "").lower()
    return Region.INTL if any(m in src for m in _INTERNATIONAL_SOURCE_MARKERS) else Region.BR


@dataclass
class Lead:
    company: str
    title: str
    source: str
    url: str
    region: Region = Region.BR
    emails: List[str] = field(default_factory=list)
    ats_links: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    location: str = ""
    posted_at: str = ""  # YYYY-MM-DD, quando a fonte informa
    raw_body: str = ""
    status: LeadStatus = LeadStatus.MINERADO
    notes: str = ""
    id: Optional[int] = None
    created_at: Optional[str] = None
    contacted_at: Optional[str] = None
    followup_due_at: Optional[str] = None

    def __post_init__(self):
        self.region = Region(self.region)
        self.status = LeadStatus(self.status)

    @property
    def is_international(self):
        return self.region is Region.INTL

    @property
    def primary_email(self):
        return self.emails[0] if self.emails else ""

    @property
    def contact_summary(self):
        return ", ".join(self.emails + self.ats_links)
