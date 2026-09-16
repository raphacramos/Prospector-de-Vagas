"""Caso de uso: comparar curriculo e vaga e gerar uma versao calibrada, sem inventar competencias."""
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from prospector.adapters.miners.filters import clean_html
from prospector.adapters.pdf_chrome import PdfRendererUnavailable
from prospector.domain.skills import (
    cosine_similarity, extract_canonical_skills, requirements_from_text, skill_in,
)
from prospector.services.outreach import render_template

SUBTITLE_RE = re.compile(r'<div class="subtitle">.*?</div>', re.DOTALL)
# Skills genericas demais para destacar no titulo do CV
NOT_HIGHLIGHTED = {"Python", "Linux & Internals", "Git & CI/CD"}


class TailoringError(Exception):
    pass


@dataclass
class TailoringReport:
    company: str
    role: str
    url: str
    language: str
    jd_available: bool
    requirements: List[str]
    matched: List[str]
    missing: List[str]
    coverage: Optional[float]
    similarity: Optional[float]
    injected: List[str] = field(default_factory=list)
    headline: str = ""
    html_path: str = ""
    pdf_path: str = ""
    pdf_ok: bool = False
    subject: str = ""
    message: str = ""
    warnings: List[str] = field(default_factory=list)


def analyze(candidate_skills, resume_text, requirements, jd_text):
    matched = sorted(r for r in requirements if skill_in(r, candidate_skills))
    missing = sorted(r for r in requirements if not skill_in(r, candidate_skills))
    coverage = round(100.0 * len(matched) / len(requirements), 1) if requirements else None
    similarity = round(cosine_similarity(resume_text, jd_text), 1) if jd_text else None
    return matched, missing, coverage, similarity


def inject_keywords(html, keywords, anchor):
    """Insere antes da ancora as palavras que ainda nao aparecem no HTML. Retorna (html, inseridas)."""
    if not keywords or not anchor or anchor not in html:
        return html, []
    text = clean_html(html).lower()
    new = [k for k in keywords if not re.search(r"(?<!\w)" + re.escape(k.lower()) + r"(?!\w)", text)]
    if not new:
        return html, []
    return html.replace(anchor, ", ".join(new) + ", " + anchor, 1), new


class TailoringService:
    def __init__(self, profile, repo, jd_fetcher, pdf_renderer, output_dir):
        self.profile = profile
        self.repo = repo
        self.jd_fetcher = jd_fetcher
        self.pdf_renderer = pdf_renderer
        self.output_dir = output_dir

    def run(self, company=None, role=None, lead_id=None, url=None, requirements_text="", jd_text="",
            lang=None, render_pdf=True):
        warnings = []
        region_lang = None
        if lead_id:
            lead = self.repo.get(lead_id)
            if not lead:
                raise TailoringError(f"lead #{lead_id} não encontrado")
            company = company or lead.company
            role = role or lead.title
            url = url or lead.url
            region_lang = "en" if lead.is_international else "pt"
        company = company or "Empresa"
        role = role or "Software Engineer"
        lang = lang or region_lang or "en"

        if not jd_text and url:
            fetched_title, jd_text = self.jd_fetcher.fetch(url)
            if not jd_text:
                warnings.append("não consegui extrair a descrição da vaga pela URL; análise só com --skills")
            elif fetched_title and not lead_id and role == "Software Engineer":
                role = fetched_title

        html_path = self.profile.cv_path(f"html_{lang}")
        if not os.path.exists(html_path):
            raise TailoringError(f"currículo base não encontrado: {html_path}. "
                                 "Coloque o HTML em data/ (ou na raiz do projeto).")
        with open(html_path, encoding="utf-8") as f:
            base_html = f.read()
        resume_text = clean_html(base_html)

        declared = set(self.profile.skills) | set(self.profile.palavras_opcionais_cv)
        candidate = extract_canonical_skills(resume_text) | declared
        requirements = extract_canonical_skills(jd_text) | requirements_from_text(requirements_text)
        matched, missing, coverage, similarity = analyze(candidate, resume_text, requirements, jd_text)
        if not requirements:
            warnings.append("nenhum requisito reconhecido; informe a URL, --jd ou --skills para comparar")

        # So entram no CV palavras declaradas em 'palavras_opcionais_cv' que a vaga pede.
        wanted = [k for k in self.profile.palavras_opcionais_cv
                  if skill_in(k, requirements) or re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", jd_text, re.I)]
        tailored, injected = inject_keywords(base_html, wanted, self.profile.ancora_insercao_cv)
        if wanted and not injected and self.profile.ancora_insercao_cv not in base_html:
            warnings.append(f"âncora '{self.profile.ancora_insercao_cv}' não encontrada no CV; nada inserido")

        highlights = [s for s in matched if s not in NOT_HIGHLIGHTED][:2]
        headline = self.profile.headline_cv.format(
            destaques=", ".join(highlights) if highlights else self.profile.destaques_padrao)
        if SUBTITLE_RE.search(tailored):
            tailored = SUBTITLE_RE.sub(lambda _: f'<div class="subtitle">{headline}</div>', tailored, count=1)
        else:
            warnings.append('CV sem <div class="subtitle">; título não alterado')

        os.makedirs(self.output_dir, exist_ok=True)
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", company).strip("_") or "Empresa"
        out_html = os.path.join(self.output_dir, f"curriculo_tailored_{slug}.html")
        with open(out_html, "w", encoding="utf-8") as f:
            f.write(tailored)
        out_pdf = os.path.join(self.output_dir, f"{self.profile.curriculos.get('prefixo_pdf_calibrado', 'Curriculo')}_{slug}.pdf")

        pdf_ok = False
        if render_pdf:
            try:
                pdf_ok = self.pdf_renderer.render(out_html, out_pdf)
            except PdfRendererUnavailable as e:
                warnings.append(str(e))
            if not pdf_ok:
                warnings.append(f"PDF não gerado; abra {out_html} no navegador e imprima como PDF")

        subject, message = render_template(self.profile, "intl" if lang == "en" else "br", company, role)
        return TailoringReport(
            company=company, role=role, url=url or "", language=lang, jd_available=bool(jd_text),
            requirements=sorted(requirements), matched=matched, missing=missing, coverage=coverage,
            similarity=similarity, injected=injected, headline=headline, html_path=out_html,
            pdf_path=out_pdf if pdf_ok else "", pdf_ok=pdf_ok, subject=subject, message=message,
            warnings=warnings,
        )
