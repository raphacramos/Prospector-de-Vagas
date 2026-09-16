"""CV-mestre (tudo o que e verdade sobre o candidato) e CV adaptado para uma vaga. Sem I/O.

A IA nunca escreve empresas, cargos ou datas: eles vem sempre do CV-mestre. Ela so escolhe
quais itens entram, em que ordem, e reescreve o texto de bullets que existem no mestre.
"""
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from prospector.domain.skills import extract_canonical_skills, mentioned_terms


class ResumeError(Exception):
    pass


@dataclass
class Bullet:
    id: str
    text: str


@dataclass
class Experience:
    id: str
    company: str
    role: str
    start: str = ""
    end: str = ""
    location: str = ""
    bullets: List[Bullet] = field(default_factory=list)


@dataclass
class Project:
    id: str
    name: str
    description: str = ""
    link: str = ""
    bullets: List[Bullet] = field(default_factory=list)


@dataclass
class Education:
    id: str
    institution: str
    degree: str
    start: str = ""
    end: str = ""
    details: str = ""


@dataclass
class Contact:
    name: str
    email: str = ""
    phone: str = ""
    location: str = ""
    links: List[str] = field(default_factory=list)


@dataclass
class MasterResume:
    contact: Contact
    headline: str = ""
    summary: str = ""
    experiences: List[Experience] = field(default_factory=list)
    projects: List[Project] = field(default_factory=list)
    education: List[Education] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    language: str = "pt"  # idioma em que o mestre foi escrito

    # ------------------------------------------------------------- serializacao
    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        try:
            contact = Contact(**data["contact"])
            exps = [Experience(**{**e, "bullets": [Bullet(**b) for b in e.get("bullets", [])]})
                    for e in data.get("experiences", [])]
            projs = [Project(**{**p, "bullets": [Bullet(**b) for b in p.get("bullets", [])]})
                     for p in data.get("projects", [])]
            edu = [Education(**e) for e in data.get("education", [])]
        except (KeyError, TypeError) as e:
            raise ResumeError(f"CV-mestre com formato inválido: {e}")
        resume = cls(
            contact=contact, headline=data.get("headline", ""), summary=data.get("summary", ""),
            experiences=exps, projects=projs, education=edu,
            skills=list(data.get("skills", [])), languages=list(data.get("languages", [])),
            certifications=list(data.get("certifications", [])), language=data.get("language", "pt"),
        )
        resume.validate()
        return resume

    def validate(self):
        if not self.contact.name.strip():
            raise ResumeError("CV-mestre sem nome")
        seen = set()
        for item_id in self._all_ids():
            if not item_id:
                raise ResumeError("item do CV-mestre sem id")
            if item_id in seen:
                raise ResumeError(f"id repetido no CV-mestre: {item_id}")
            seen.add(item_id)

    def _all_ids(self):
        for e in self.experiences:
            yield e.id
            for b in e.bullets:
                yield b.id
        for p in self.projects:
            yield p.id
            for b in p.bullets:
                yield b.id
        for e in self.education:
            yield e.id

    # ------------------------------------------------------------------ consulta
    def bullet_index(self):
        """{bullet_id: (item_id, texto)} de experiencias e projetos."""
        idx = {}
        for item in list(self.experiences) + list(self.projects):
            for b in item.bullets:
                idx[b.id] = (item.id, b.text)
        return idx

    def all_text(self):
        parts = [self.headline, self.summary, " ".join(self.skills), " ".join(self.certifications)]
        for e in self.experiences:
            parts += [e.role, e.company] + [b.text for b in e.bullets]
        for p in self.projects:
            parts += [p.name, p.description] + [b.text for b in p.bullets]
        for e in self.education:
            parts += [e.degree, e.institution, e.details]
        return "\n".join(x for x in parts if x)

    def known_skills(self):
        """Competencias canonicas comprovadas pelo texto do mestre."""
        return extract_canonical_skills(self.all_text())


def assign_ids(data):
    """Garante ids estaveis (exp1, exp1.b1, proj1...) num dict vindo da IA ou do usuario."""
    for prefix, key in (("exp", "experiences"), ("proj", "projects")):
        for i, item in enumerate(data.get(key, []), 1):
            item["id"] = item.get("id") or f"{prefix}{i}"
            bullets = []
            for j, b in enumerate(item.get("bullets", []), 1):
                if isinstance(b, str):
                    b = {"text": b}
                b["id"] = b.get("id") or f"{item['id']}.b{j}"
                bullets.append(b)
            item["bullets"] = bullets
    for i, item in enumerate(data.get("education", []), 1):
        item["id"] = item.get("id") or f"edu{i}"
    return data


# ---------------------------------------------------------------- CV adaptado
@dataclass
class TailoredItem:
    id: str                        # id da experiencia/projeto no mestre
    bullets: List[Bullet]          # id do bullet de origem + texto reescrito


@dataclass
class TailoredResume:
    language: str
    headline: str
    summary: str
    experiences: List[TailoredItem]
    projects: List[TailoredItem]
    skills: List[str]
    keywords_used: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        def items(key):
            return [TailoredItem(id=i["id"], bullets=[Bullet(**b) for b in i.get("bullets", [])])
                    for i in data.get(key, [])]
        return cls(language=data.get("language", "en"), headline=data.get("headline", ""),
                   summary=data.get("summary", ""), experiences=items("experiences"),
                   projects=items("projects"), skills=list(data.get("skills", [])),
                   keywords_used=list(data.get("keywords_used", [])),
                   warnings=list(data.get("warnings", [])))


_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*[A-Za-z0-9+#]")


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def enforce_faithfulness(master, tailored):
    """Remove o que nao existe no mestre e registra avisos. Retorna o proprio `tailored`.

    Regras:
    - experiencias/projetos e bullets precisam existir no mestre (pelo id);
    - skills listadas precisam estar em `master.skills` ou no texto do mestre;
    - competencias canonicas citadas no texto novo precisam estar comprovadas no mestre.
    """
    warnings = list(tailored.warnings)
    bullets = master.bullet_index()
    exp_ids = {e.id for e in master.experiences}
    proj_ids = {p.id for p in master.projects}

    def clean_items(items, valid_ids, label):
        out = []
        for item in items:
            if item.id not in valid_ids:
                warnings.append(f"{label} '{item.id}' não existe no CV-mestre; removido")
                continue
            kept = []
            for b in item.bullets:
                origin = bullets.get(b.id)
                if not origin or origin[0] != item.id:
                    warnings.append(f"bullet '{b.id}' não pertence a '{item.id}'; removido")
                    continue
                if not b.text.strip():
                    b.text = origin[1]
                kept.append(b)
            out.append(TailoredItem(id=item.id, bullets=kept))
        return out

    tailored.experiences = clean_items(tailored.experiences, exp_ids, "experiência")
    tailored.projects = clean_items(tailored.projects, proj_ids, "projeto")

    master_text = _norm(master.all_text())
    master_skill_names = {_norm(s) for s in master.skills}
    kept_skills = []
    for s in tailored.skills:
        if _norm(s) in master_skill_names or (_norm(s) and _norm(s) in master_text):
            if s not in kept_skills:
                kept_skills.append(s)
        else:
            warnings.append(f"skill '{s}' não está no CV-mestre; removida")
    tailored.skills = kept_skills

    new_text = " ".join([tailored.headline, tailored.summary] +
                        [b.text for i in tailored.experiences + tailored.projects for b in i.bullets])
    for term in unproven_terms(master, new_text):
        warnings.append(f"o texto adaptado cita '{term}', que não aparece no CV-mestre; revise")

    tailored.warnings = warnings
    return tailored


def unproven_terms(master, text):
    """Competencias/tecnologias citadas em `text` que o CV-mestre nao comprova."""
    master_text = master.all_text()
    out = sorted(extract_canonical_skills(text) - master.known_skills())
    out += sorted(mentioned_terms(text) - mentioned_terms(master_text))
    return out


def resolve(master, tailored):
    """Junta o adaptado com os dados fixos do mestre para renderizar."""
    exp_by_id = {e.id: e for e in master.experiences}
    proj_by_id = {p.id: p for p in master.projects}
    return {
        "contact": master.contact,
        "headline": tailored.headline or master.headline,
        "summary": tailored.summary or master.summary,
        "experiences": [(exp_by_id[i.id], i.bullets) for i in tailored.experiences if i.id in exp_by_id],
        "projects": [(proj_by_id[i.id], i.bullets) for i in tailored.projects if i.id in proj_by_id],
        "education": master.education,
        "skills": tailored.skills or master.skills,
        "languages": master.languages,
        "certifications": master.certifications,
        "language": tailored.language,
    }


def untailored(master, language=None):
    """CV adaptado 'neutro' (tudo do mestre, na ordem original)."""
    return TailoredResume(
        language=language or master.language, headline=master.headline, summary=master.summary,
        experiences=[TailoredItem(e.id, list(e.bullets)) for e in master.experiences],
        projects=[TailoredItem(p.id, list(p.bullets)) for p in master.projects],
        skills=list(master.skills),
    )
