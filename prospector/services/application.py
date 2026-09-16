"""Caso de uso: montar o pacote de candidatura de uma vaga (CV adaptado, carta, PDF)."""
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from prospector.adapters.llm_anthropic import text_block
from prospector.adapters.pdf_chrome import PdfRendererUnavailable
from prospector.adapters.resume_render import render_html
from prospector.domain.lead import LeadStatus
from prospector.domain.resume import TailoredResume, enforce_faithfulness, resolve, unproven_terms
from prospector.services.prompts import (
    ANSWERS_SCHEMA, ANSWERS_SYSTEM, TAILOR_SCHEMA, TAILOR_SYSTEM,
)

MIN_JD_CHARS = 200


class ApplicationError(Exception):
    pass


@dataclass
class ApplicationPackage:
    lead_id: int
    folder: str
    language: str
    company: str
    role: str
    apply_url: str
    created_at: str
    cv_html: str
    cv_pdf: str = ""
    cover_letter: str = ""
    headline: str = ""
    fit_summary: str = ""
    keywords_used: List[str] = field(default_factory=list)
    missing_requirements: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    jd_source: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)

    def to_dict(self):
        return dict(self.__dict__)


def slugify(text):
    return re.sub(r"[^a-zA-Z0-9]+", "_", text or "").strip("_")[:40] or "Empresa"


def _extract_company_role(lead):
    """Titulos dos mineradores costumam vir como 'Empresa - Cargo'."""
    prefix = f"{lead.company} - "
    role = lead.title[len(prefix):] if lead.title.startswith(prefix) else lead.title
    return lead.company, role


class ApplicationService:
    def __init__(self, repo, profile, resume_store, llm, jd_fetcher, pdf_renderer, base_dir,
                 clock=datetime.now):
        self.repo = repo
        self.profile = profile
        self.resume_store = resume_store
        self.llm = llm
        self.jd_fetcher = jd_fetcher
        self.pdf_renderer = pdf_renderer
        self.base_dir = base_dir
        self._now = clock

    # ----------------------------------------------------------------- pastas
    def folder_for(self, lead):
        return os.path.join(self.base_dir, f"{lead.id}-{slugify(lead.company)}")

    def apply_url(self, lead):
        return lead.ats_links[0] if lead.ats_links else lead.url

    def load(self, lead_id) -> Optional[ApplicationPackage]:
        lead = self.repo.get(lead_id)
        if not lead:
            return None
        meta = os.path.join(self.folder_for(lead), "meta.json")
        if not os.path.exists(meta):
            return None
        with open(meta, encoding="utf-8") as f:
            return ApplicationPackage(**json.load(f))

    # ---------------------------------------------------------------- preparo
    def job_description(self, lead):
        """Texto da vaga. GitHub e HN ja trazem o anuncio inteiro no texto minerado."""
        mined = (lead.raw_body or "").strip()
        if lead.source.startswith(("GitHub", "Hacker News")) and mined:
            return mined[:30000], "minerado"
        text, source = "", ""
        for url in dict.fromkeys([lead.url] + list(lead.ats_links)):
            if not url:
                continue
            try:
                _, fetched = self.jd_fetcher.fetch(url)
            except Exception:  # fonte fora do ar nao impede usar o texto minerado
                fetched = ""
            if len(fetched or "") > len(text):
                text, source = fetched, "url"
            if len(text) >= MIN_JD_CHARS:
                break
        if len(text) < len(mined):
            text, source = mined, "minerado"
        return text.strip()[:30000], source

    def prepare(self, lead_id, language=None, render_pdf=True):
        lead = self.repo.get(lead_id)
        if not lead:
            raise ApplicationError(f"lead #{lead_id} não encontrado")
        master = self.resume_store.load()
        company, role = _extract_company_role(lead)
        language = language or ("en" if lead.is_international else "pt")
        jd, jd_source = self.job_description(lead)
        warnings = []
        if len(jd) < MIN_JD_CHARS:
            warnings.append("descrição da vaga curta ou indisponível; a adaptação usou só o título")

        prompt = (
            f"<idioma_de_saida>{language}</idioma_de_saida>\n"
            f"<empresa>{company}</empresa>\n<cargo>{role}</cargo>\n"
            f"<vaga>\n{jd or '(sem descrição)'}\n</vaga>\n"
            f"<cv_mestre>\n{json.dumps(master.to_dict(), ensure_ascii=False)}\n</cv_mestre>"
        )
        system = TAILOR_SYSTEM.replace("{max_bullets}", str(self.profile.max_bullets))
        before = dict(getattr(self.llm, "usage", {}) or {})
        data = self.llm.generate_json(system, [text_block(prompt)], TAILOR_SCHEMA, "registrar_adaptacao",
                                      max_tokens=6000)
        after = dict(getattr(self.llm, "usage", {}) or {})
        usage = {k: after.get(k, 0) - before.get(k, 0) for k in after}

        tailored = TailoredResume.from_dict({**data, "language": language, "warnings": []})
        for item in tailored.experiences:
            item.bullets = item.bullets[: self.profile.max_bullets]
        enforce_faithfulness(master, tailored)
        cover = (data.get("cover_letter") or "").strip()
        for term in unproven_terms(master, cover):
            tailored.warnings.append(f"a carta cita '{term}', que não aparece no CV-mestre; revise")
        warnings += tailored.warnings

        folder = self.folder_for(lead)
        os.makedirs(folder, exist_ok=True)
        html_path = os.path.join(folder, "cv.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(render_html(resolve(master, tailored)))
        with open(os.path.join(folder, "tailored.json"), "w", encoding="utf-8") as f:
            json.dump(tailored.to_dict(), f, ensure_ascii=False, indent=2)
        with open(os.path.join(folder, "carta.txt"), "w", encoding="utf-8") as f:
            f.write(cover + "\n")
        with open(os.path.join(folder, "vaga.txt"), "w", encoding="utf-8") as f:
            f.write(jd + "\n")

        pdf_path = ""
        if render_pdf:
            pdf_name = f"{self.profile.curriculos.get('prefixo_pdf_calibrado', 'Curriculo')}_{slugify(company)}.pdf"
            target = os.path.join(folder, pdf_name)
            try:
                if self.pdf_renderer.render(html_path, target):
                    pdf_path = target
                else:
                    warnings.append("o Chrome não gerou o PDF; abra cv.html e imprima como PDF")
            except PdfRendererUnavailable as e:
                warnings.append(str(e))

        pkg = ApplicationPackage(
            lead_id=lead.id, folder=folder, language=language, company=company, role=role,
            apply_url=self.apply_url(lead), created_at=self._now().strftime("%Y-%m-%d %H:%M:%S"),
            cv_html=html_path, cv_pdf=pdf_path, cover_letter=cover, headline=tailored.headline,
            fit_summary=data.get("fit_summary", ""), keywords_used=tailored.keywords_used,
            missing_requirements=list(data.get("missing_requirements", [])), warnings=warnings,
            jd_source=jd_source, model=getattr(self.llm, "model", ""), usage=usage,
        )
        with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(pkg.to_dict(), f, ensure_ascii=False, indent=2)
        if lead.status in (LeadStatus.MINERADO, LeadStatus.RASCUNHO_ABERTO, LeadStatus.CANDIDATURA_PREPARADA):
            self.repo.set_status(lead.id, LeadStatus.CANDIDATURA_PREPARADA, note=f"pacote {language}")
        return pkg

    def update_cover_letter(self, lead_id, text):
        pkg = self.load(lead_id)
        if not pkg:
            raise ApplicationError(f"lead #{lead_id} ainda não tem candidatura preparada")
        pkg.cover_letter = text.strip()
        with open(os.path.join(pkg.folder, "carta.txt"), "w", encoding="utf-8") as f:
            f.write(pkg.cover_letter + "\n")
        with open(os.path.join(pkg.folder, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(pkg.to_dict(), f, ensure_ascii=False, indent=2)
        return pkg

    def discard(self, lead_id):
        lead = self.repo.get(lead_id)
        if lead and os.path.isdir(self.folder_for(lead)):
            shutil.rmtree(self.folder_for(lead))

    def mark_submitted(self, lead_id, note="enviada pelo portal"):
        if not self.repo.set_status(lead_id, LeadStatus.CANDIDATURA_ENVIADA, note=note):
            raise ApplicationError(f"lead #{lead_id} não encontrado")

    # --------------------------------------------------------------- respostas
    def answer_questions(self, lead_id, questions):
        """Responde perguntas abertas do formulario. Retorna {pergunta: resposta} so com as confiaveis."""
        questions = [q.strip() for q in questions if q and q.strip()]
        if not questions:
            return {}
        lead = self.repo.get(lead_id)
        master = self.resume_store.load()
        pkg = self.load(lead_id)
        prompt = (
            f"<empresa>{lead.company}</empresa>\n<cargo>{lead.title}</cargo>\n"
            f"<carta>{pkg.cover_letter if pkg else ''}</carta>\n"
            f"<respostas_padrao>{json.dumps(self.profile.standard_answers, ensure_ascii=False)}</respostas_padrao>\n"
            f"<cv_mestre>{json.dumps(master.to_dict(), ensure_ascii=False)}</cv_mestre>\n"
            "<perguntas>\n" + "\n".join(f"- {q}" for q in questions) + "\n</perguntas>"
        )
        data = self.llm.generate_json(ANSWERS_SYSTEM, [text_block(prompt)], ANSWERS_SCHEMA,
                                      "registrar_respostas", max_tokens=3000)
        return {a["question"]: a["answer"] for a in data["answers"]
                if a.get("confident") and a.get("answer", "").strip()}
