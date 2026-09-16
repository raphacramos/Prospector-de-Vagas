"""Perfil do candidato: dados pessoais, templates, curriculos e skills (fora do codigo).

Ordem de busca: $PROSPECTOR_PROFILE, data/profile.json, profile.example.json (versionado).
"""
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List

from prospector.core import config

EXAMPLE_PATH = os.path.join(config.ROOT_DIR, "profile.example.json")
LOCAL_PATH = os.path.join(config.DATA_DIR, "profile.json")


class ProfileError(Exception):
    pass


@dataclass
class Template:
    key: str
    descricao: str
    idioma: str
    assunto: str
    corpo: str
    saudacao_padrao: str = "Team"


@dataclass
class Profile:
    nome: str
    email: str
    links: List[str]
    templates: Dict[str, Template]
    followups: Dict[str, str]
    curriculos: Dict[str, str]
    skills: List[str] = field(default_factory=list)
    palavras_opcionais_cv: List[str] = field(default_factory=list)
    ancora_insercao_cv: str = ""
    headline_cv: str = "Software Engineer | {destaques}"
    destaques_padrao: str = "Backend"
    max_caracteres_mensagem: int = 400
    chrome_path: str = ""
    fontes: Dict[str, List[str]] = field(default_factory=dict)
    candidato: Dict[str, object] = field(default_factory=dict)
    ia: Dict[str, object] = field(default_factory=dict)
    path: str = ""

    @property
    def first_name(self):
        return self.nome.split()[0] if self.nome.strip() else ""

    @property
    def last_name(self):
        parts = self.nome.split()
        return " ".join(parts[1:]) if len(parts) > 1 else ""

    @property
    def model(self):
        return str(self.ia.get("modelo") or "")

    @property
    def max_bullets(self):
        return int(self.ia.get("max_bullets_por_experiencia") or 4)

    @property
    def master_resume_path(self):
        name = str(self.ia.get("curriculo_mestre") or "resume.json")
        return name if os.path.isabs(name) else os.path.join(config.DATA_DIR, name)

    @property
    def standard_answers(self):
        return dict(self.candidato.get("respostas_padrao") or {})

    @property
    def assinatura(self):
        return "\n".join([self.nome, " • ".join(self.links)]) if self.links else self.nome

    def cv_path(self, kind):
        """kind: html_en, html_pt, pdf_en, pdf_pt. Procura em data/ e depois na raiz."""
        name = self.curriculos.get(kind)
        if not name:
            raise ProfileError(f"'curriculos.{kind}' não definido em {self.path}")
        return name if os.path.isabs(name) else config.resolve_asset(name)

    def template(self, key):
        if key not in self.templates:
            raise ProfileError(f"template '{key}' não existe (disponíveis: {', '.join(self.templates)})")
        return self.templates[key]


def _require(data, key, path):
    if key not in data:
        raise ProfileError(f"campo obrigatório '{key}' ausente em {path}")
    return data[key]


def load_profile(path=None):
    path = path or os.environ.get("PROSPECTOR_PROFILE") or (
        LOCAL_PATH if os.path.exists(LOCAL_PATH) else EXAMPLE_PATH)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ProfileError(f"perfil não encontrado: {path}")
    except ValueError as e:
        raise ProfileError(f"JSON inválido em {path}: {e}")

    templates = {}
    for key, t in _require(data, "templates", path).items():
        for field_name in ("idioma", "assunto", "corpo"):
            _require(t, field_name, f"{path} (templates.{key})")
        if t["idioma"] not in ("pt", "en"):
            raise ProfileError(f"templates.{key}.idioma deve ser 'pt' ou 'en'")
        templates[key] = Template(key=key, descricao=t.get("descricao", key), idioma=t["idioma"],
                                  assunto=t["assunto"], corpo=t["corpo"],
                                  saudacao_padrao=t.get("saudacao_padrao", "Team"))
    for required in ("br", "intl"):
        if required not in templates:
            raise ProfileError(f"template '{required}' é obrigatório em {path}")

    return Profile(
        nome=_require(data, "nome", path), email=_require(data, "email", path),
        links=list(data.get("links", [])), templates=templates,
        followups=dict(_require(data, "followups", path)), curriculos=dict(_require(data, "curriculos", path)),
        skills=list(data.get("skills", [])), palavras_opcionais_cv=list(data.get("palavras_opcionais_cv", [])),
        ancora_insercao_cv=data.get("ancora_insercao_cv", ""),
        headline_cv=data.get("headline_cv", "Software Engineer | {destaques}"),
        destaques_padrao=data.get("destaques_padrao", "Backend"),
        max_caracteres_mensagem=int(data.get("max_caracteres_mensagem", 400)),
        chrome_path=data.get("chrome_path", ""), fontes=dict(data.get("fontes", {})),
        candidato=dict(data.get("candidato", {})), ia=dict(data.get("ia", {})), path=path,
    )
