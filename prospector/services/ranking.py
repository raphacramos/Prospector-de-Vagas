"""Pontuacao rapida (sem IA) para ordenar a fila de candidaturas."""
from prospector.domain.skills import extract_canonical_skills


def match_score(lead, proven_skills):
    """0-100: quanto das competencias citadas na vaga o candidato comprova. None se a vaga nao cita nenhuma."""
    asked = extract_canonical_skills(f"{lead.title}\n{lead.raw_body}")
    if not asked:
        return None
    return round(100.0 * len(asked & set(proven_skills)) / len(asked))


def queue_key(lead, score):
    """Ordena: vagas com ATS de etapa unica ou e-mail primeiro, depois maior aderencia, depois mais novas."""
    has_channel = bool(lead.ats_links or lead.emails)
    return (not has_channel, -(score if score is not None else 40), -(lead.id or 0))
