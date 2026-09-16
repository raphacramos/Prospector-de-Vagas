"""Regra unica de regiao do lead (nacional x internacional).

Antes essa decisao estava copiada em 5 lugares com criterios diferentes, e vagas
do SimplifyJobs recebiam template e curriculo em portugues no send/gmail/draft.
"""

INTERNATIONAL_SOURCE_MARKERS = ("hacker news", "greenhouse", "simplify", "international")


def is_international(source):
    """True se o lead veio de uma fonte internacional (mensagem e CV em ingles)."""
    src = (source or "").lower()
    return any(marker in src for marker in INTERNATIONAL_SOURCE_MARKERS)
