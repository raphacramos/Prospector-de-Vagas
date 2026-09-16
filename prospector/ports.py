"""Contratos (ports) entre servicos e adapters. Implementacoes ficam em prospector/adapters."""
from dataclasses import dataclass
from typing import List, Optional

try:  # Python 3.8+
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object


class SourceUnavailable(Exception):
    """Fonte de vagas fora do ar, bloqueada ou com formato inesperado."""


@dataclass
class MiningOptions:
    query: Optional[str] = None
    all_levels: bool = False   # GitHub: incluir vagas acima de junior
    remote_only: bool = False  # todas as fontes: so vagas remotas/LATAM/globais
    all_ats: bool = False      # Simplify: nao exigir ATS de etapa unica
    limit: int = 50            # maximo por fonte


class Miner(Protocol):
    name: str   # chave usada no --source
    label: str  # nome exibido

    def mine(self, options: MiningOptions) -> list:
        """Devolve list[Lead]. Levanta SourceUnavailable se a fonte falhar por completo."""


class HttpClient(Protocol):
    def get_text(self, url: str, headers: Optional[dict] = None) -> Optional[str]: ...
    def get_json(self, url: str, headers: Optional[dict] = None): ...


class LeadRepository(Protocol):
    def add(self, lead) -> Optional[int]: ...
    def add_many(self, leads: List) -> tuple: ...
    def get(self, lead_id: int): ...
    def list_recent(self, limit: int = 35, status: Optional[str] = None) -> List: ...
    def set_status(self, lead_id: int, status, note: str = "") -> bool: ...
    def pending_followups(self) -> List: ...
    def events(self, lead_id: int) -> List[dict]: ...


class LlmError(Exception):
    """Falha ao chamar o modelo (chave ausente, limite, resposta invalida)."""


class LlmClient(Protocol):
    def generate_json(self, system: str, content: list, schema: dict, tool_name: str,
                      max_tokens: int = 4096) -> dict:
        """Envia `content` (blocos de texto/documento) e devolve o JSON validado pelo `schema`."""
