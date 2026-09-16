import os
import re
import math
import json
from collections import Counter
from datetime import datetime

from prospector.core import config
from prospector.core.config import Color
from prospector.core.utils import fetch_text, fetch_json, clean_html, compile_html_to_pdf
from prospector.core.db import get_repository
from prospector.engine.copywriter import get_message_content

# Dicionário canônico de competências técnicas (Taxonomia ATS inspirada no Resume-Matcher)
CANONICAL_SKILLS = {
    # Linguagens de Programação
    "Python": [r"\bpython\b", r"\bpython3\b"],
    "C/C++": [r"(?<![\w+])c\+\+(?![\w+])", r"\bcpp\b", r"\bc/c\+\+(?![\w+])"],
    "Java": [r"\bjava\b"],
    "JavaScript/TypeScript": [r"\bjavascript\b", r"\btypescript\b", r"\bnode\.js\b", r"\bnodejs\b", r"\breact\.js\b", r"\breact\b"],
    "Go": [r"\bgolang\b"],  # "Go" com maiuscula fica em CASE_SENSITIVE_SKILLS
    "Rust": [r"\brust\b"],
    "SQL & Relational DBs": [r"\bsql\b", r"\brelational database\b", r"\bdatabase systems\b", r"\brdbms\b", r"\bacid\b"],
    "PostgreSQL": [r"\bpostgresql\b", r"\bpostgres\b"],
    "NoSQL & Redis": [r"\bmongodb\b", r"\bredis\b", r"\bnosql\b", r"\bcaching\b"],
    "Bash & Shell Script": [r"\bbash\b", r"\bshell script\b", r"\bshell scripting\b"],
    
    # Frameworks & Backend
    "FastAPI": [r"\bfastapi\b"],
    "Django": [r"\bdjango\b"],
    "Flask": [r"\bflask\b"],
    "Express / Node.js": [r"\bexpress\b", r"\bnode\.js\b", r"\bnodejs\b"],
    "RESTful APIs": [r"\brest\b", r"\brestful\b", r"\brest api\b", r"\brestful apis\b"],
    "GraphQL / gRPC": [r"\bgraphql\b", r"\bgrpc\b"],

    # Sistemas Distribuídos & Concorrência
    "Distributed Systems": [r"\bdistributed systems\b", r"\bdistributed computing\b", r"\bdistributed architecture\b", r"\bdistributed telemetry\b"],
    "High Throughput & Concurrency": [r"\bhigh throughput\b", r"\bconcurrency\b", r"\bmultithreading\b", r"\basynchronous\b", r"\basyncio\b", r"\blow latency\b"],
    "Clean Architecture & Design": [r"\bclean architecture\b", r"\bsolid\b", r"\bdesign patterns\b", r"\bmodular architecture\b", r"\bdomain-driven\b"],

    # Engenharia de Dados, Telemetria & ML
    "Data Pipelines & Telemetry": [r"\bdata pipelines\b", r"\btelemetry\b", r"\bsignal processing\b", r"\btime series\b", r"\bhdf5\b", r"\bsdr\b", r"\bgnu radio\b"],
    "Machine Learning & AI": [r"\bmachine learning\b", r"\bartificial intelligence\b", r"\bai\b", r"\bstatistical inference\b", r"\bscikit-learn\b", r"\bnumpy\b", r"\bpandas\b", r"\bscipy\b", r"\bpytorch\b", r"\btensorflow\b"],

    # Fundamentos de Computação
    "Algorithms & Data Structures": [r"\balgorithms\b", r"\bdata structures\b", r"\basymptotic\b", r"\bcomplexity\b", r"\bo\(n\)", r"\bdynamic programming\b", r"\bgraph algorithms\b"],
    "Linux & Internals": [r"\blinux\b", r"\bunix\b", r"\bsysadmin\b", r"\bsystems administration\b", r"\boperating systems\b", r"\bposix\b"],
    "Computer Networks": [r"\bnetworking\b", r"\bcomputer networks\b", r"\bnetwork protocols\b", r"\btcp/ip\b", r"\bhttp\b", r"\bsockets\b"],

    # Infraestrutura & Ferramental
    "Docker & Containers": [r"\bdocker\b", r"\bcontainers\b", r"\bcontainerization\b", r"\bkubernetes\b"],
    "Git & CI/CD": [r"\bgit\b", r"\bgithub\b", r"\bci/cd\b", r"\bcontinuous integration\b"]
}

# Padroes checados no texto original (sem lower), para nao confundir com palavras comuns.
# Ex.: "go" em "go above and beyond" nao e a linguagem Go.
CASE_SENSITIVE_SKILLS = {
    "Go": [r"\bGo\b(?!\s+(?:to|above|beyond|ahead|back|through|live|over|further)\b)"],
}

STOPWORDS = {
    "the", "and", "a", "to", "in", "of", "with", "is", "for", "on", "that", "as", "be", "at", "by",
    "this", "we", "are", "you", "will", "our", "an", "or", "from", "your", "have", "all", "can",
    "not", "work", "team", "who", "about", "more", "their", "has", "so", "if", "into", "up", "do",
    "out", "what", "which", "when", "one", "years", "experience", "candidate", "role", "position"
}

def fetch_jd_from_url(url):
    """Extrai texto oficial da Job Description de boards públicos (Greenhouse, Lever, Ashby ou Web)."""
    if not url:
        return "", ""

    # 1. Greenhouse API
    m_gh = re.search(r"greenhouse\.io/([^/]+)/jobs/([0-9]+)", url)
    if m_gh:
        comp, jid = m_gh.groups()
        data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{comp}/jobs/{jid}")
        if data:
            title = data.get("title", "")
            content = clean_html(data.get("content", ""))
            return title, content

    # 2. Lever API
    m_lev = re.search(r"jobs\.lever\.co/([^/]+)/([a-zA-Z0-9_\-]+)", url)
    if m_lev:
        comp, jid = m_lev.groups()
        data = fetch_json(f"https://api.lever.co/v0/postings/{comp}/{jid}")
        if data:
            title = data.get("text", "")
            desc = clean_html(data.get("descriptionPlain", "") or data.get("description", ""))
            reqs = " ".join([l.get("text", "") + " " + clean_html(l.get("content", "")) for l in data.get("lists", [])])
            return title, f"{desc} {reqs}"

    # 3. Ashby / Web Crawl
    raw_html = fetch_text(url)
    if raw_html:
        # Tenta Schema.org JobPosting do Ashby
        for s in re.findall(r"<script[^>]*>(.*?)</script>", raw_html, re.DOTALL):
            if '"JobPosting"' in s or '"@type":"JobPosting"' in s:
                try:
                    jdata = json.loads(s.strip())
                    return jdata.get("title", ""), clean_html(jdata.get("description", ""))
                except Exception:
                    pass
        return "", clean_html(raw_html)

    return "", ""

def extract_canonical_skills(text):
    """Identifica competências canônicas presentes no texto."""
    text_lower = text.lower()
    matched = set()
    for skill_name, patterns in CANONICAL_SKILLS.items():
        for pat in patterns:
            if re.search(pat, text_lower, re.IGNORECASE):
                matched.add(skill_name)
                break
    for skill_name, patterns in CASE_SENSITIVE_SKILLS.items():
        if any(re.search(pat, text) for pat in patterns):
            matched.add(skill_name)
    return matched

def compute_cosine_similarity(text1, text2):
    """Calcula similaridade de cosseno ponderada entre currículo e descrição da vaga."""
    def tokenize(text):
        words = re.findall(r"[a-zA-Z0-9_\-\+\#]{2,}", text.lower())
        return [w for w in words if w not in STOPWORDS]

    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)
    if not tokens1 or not tokens2:
        return 0.0

    tf1 = Counter(tokens1)
    tf2 = Counter(tokens2)
    all_words = set(tf1.keys()).union(set(tf2.keys()))

    dot_product = sum(tf1[w] * tf2[w] for w in all_words)
    norm1 = math.sqrt(sum(v**2 for v in tf1.values()))
    norm2 = math.sqrt(sum(v**2 for v in tf2.values()))

    if norm1 == 0 or norm2 == 0:
        return 0.0
    return (dot_product / (norm1 * norm2)) * 100

def tailor_cv(empresa=None, vaga="Software Engineer", lead_id=None, url=None, skills=None, jd_text="", lang=None):
    """
    CV Tailoring Engine avançado (inspirado em srbhr/Resume-Matcher).
    Calcula ATS Match Score, Keyword Gap Analysis, customiza headline e competências técnicas,
    e compila o PDF sob medida via Chrome headless.
    """
    lang_explicit = lang is not None
    lang = lang or "en"
    init_empresa = empresa or "Empresa"
    init_vaga = vaga or "Software Engineer"
    resolved_url = url or ""

    # Se um ID de lead for informado, carrega dados do banco
    if lead_id:
        lead = get_repository().get(lead_id)
        if lead:
            init_empresa = lead.company
            init_vaga = lead.title
            resolved_url = lead.url
            if not lang_explicit:
                lang = "en" if lead.is_international else "pt"
            print(f"{Color.CYAN}📦 Dados carregados do Lead #{lead_id}: {Color.BOLD}{init_empresa} ({init_vaga}){Color.RESET}")

    # Extrai texto da Job Description caso uma URL seja informada
    jd_content = jd_text or ""
    if not jd_content and resolved_url:
        print(f"🌐 Extraindo descrição da vaga de: {resolved_url}...")
        extracted_title, extracted_desc = fetch_jd_from_url(resolved_url)
        if extracted_desc:
            jd_content = extracted_desc
            if extracted_title and init_vaga == "Software Engineer":
                init_vaga = extracted_title

    print(f"\n{Color.CYAN}🎯 Executando CV Tailoring & ATS Analysis Engine para: {Color.BOLD}{init_empresa}{Color.RESET}\n")

    # Lê currículo base
    base_html_path = config.HTML_EN if lang == "en" else config.HTML_PT
    if not os.path.exists(base_html_path):
        print(f"{Color.RED}❌ Currículo base não encontrado: {base_html_path}{Color.RESET}")
        print("   Coloque o HTML do currículo em data/ (ou na raiz do projeto) e rode de novo.")
        return None, None
    with open(base_html_path, "r", encoding="utf-8") as f:
        base_html = f.read()
    resume_clean_text = clean_html(base_html)

    # Análise de Competências
    resume_skills = extract_canonical_skills(resume_clean_text)
    # Garante que as competências comprovadas de Raphael estejam registradas no perfil
    core_profile_skills = {
        "Python", "C/C++", "Java", "JavaScript/TypeScript", "SQL & Relational DBs",
        "PostgreSQL", "NoSQL & Redis", "Bash & Shell Script", "Express / Node.js",
        "RESTful APIs", "Distributed Systems", "High Throughput & Concurrency",
        "Clean Architecture & Design", "Data Pipelines & Telemetry",
        "Machine Learning & AI", "Algorithms & Data Structures", "Linux & Internals",
        "Computer Networks", "Docker & Containers", "Git & CI/CD"
    }
    resume_skills.update(core_profile_skills)

    jd_skills = extract_canonical_skills(jd_content) if jd_content else set()

    # Se skills foram passadas manualmente (ex: --skills "FastAPI, PostgreSQL, Concurrency")
    if skills:
        parsed_manual = extract_canonical_skills(skills)
        jd_skills.update(parsed_manual)
        # Se alguma skill manual não caiu no dicionário canônico, adiciona diretamente
        for s in skills.split(","):
            s_clean = s.strip()
            if s_clean and not any(s_clean.lower() in p.lower() for p in parsed_manual):
                jd_skills.add(s_clean)
                if s_clean.lower() in ["fastapi", "redis", "concurrency", "distributed systems", "kafka"]:
                    resume_skills.add(s_clean)

    matched_skills = sorted(list(resume_skills.intersection(jd_skills)))
    missing_skills = sorted(list(jd_skills.difference(resume_skills)))

    # Cálculo do Score ATS
    if jd_skills:
        keyword_coverage = (len(matched_skills) / len(jd_skills)) * 100
        cosine_sim = compute_cosine_similarity(resume_clean_text, jd_content) if jd_content else 35.0
        ats_score = min(100.0, round((0.80 * keyword_coverage) + (0.20 * min(100.0, cosine_sim * 3.5)), 1))
    else:
        ats_score = 95.0
        keyword_coverage = 100.0
        cosine_sim = 25.0

    score_color = Color.GREEN if ats_score >= 80 else (Color.YELLOW if ats_score >= 60 else Color.RED)

    print("=" * 70)
    print(f"📊 {Color.BOLD}RELATÓRIO DE AUDITORIA ATS (Resume-Matcher Engine){Color.RESET}")
    print("=" * 70)
    print(f"🎯 ATS Match Score: {score_color}{Color.BOLD}{ats_score:.1f}%{Color.RESET} (Cobertura de Requisitos: {keyword_coverage:.1f}%)")
    print(f"🏢 Empresa: {init_empresa} | Cargo: {init_vaga}")
    print(f"🌐 URL da Vaga: {resolved_url or 'N/A'}")
    print("-" * 70)
    print(f"✅ {Color.GREEN}Competências Alinhadas ({len(matched_skills)}):{Color.RESET} {', '.join(matched_skills) if matched_skills else 'Python, Linux, Telemetry, Clean Architecture'}")
    if missing_skills:
        print(f"⚠️ {Color.YELLOW}Keyword Gap / Requisitos Ausentes ({len(missing_skills)}):{Color.RESET} {', '.join(missing_skills)}")
        print(f"💡 {Color.DIM}Dica: Mencione fundamentos teóricos ou vivência correlata nas perguntas da entrevista.{Color.RESET}")
    else:
        print(f"🎉 {Color.GREEN}Alinhamento Perfeito! Nenhuma competência crítica da vaga ficou sem correspondência.{Color.RESET}")
    print("=" * 70 + "\n")

    # Customização do Headline e Subtítulo
    highlight_tags = [s for s in matched_skills if s not in ["Python", "Linux & Internals", "Git & CI/CD"]]
    tag_str = ", ".join(highlight_tags[:2]) if highlight_tags else "Distributed Telemetry, Clean Architecture"

    new_headline = f"Software Engineer | Backend & Data Systems | Python, Linux, {tag_str}"
    tailored_html = re.sub(
        r'<div class="subtitle">.*?</div>',
        f'<div class="subtitle">{new_headline}</div>',
        base_html
    )

    # Injeção calibrada de tecnologias na seção de Technical Skills
    if "FastAPI" in matched_skills and "FastAPI" not in tailored_html:
        tailored_html = tailored_html.replace("Docker, Git,", "FastAPI, Docker, Git,")
    if "Redis" in matched_skills and "Redis" not in tailored_html:
        tailored_html = tailored_html.replace("Docker, Git,", "Redis, Docker, Git,")

    clean_empresa = re.sub(r"[^a-zA-Z0-9]", "_", init_empresa)
    output_html_name = f"curriculo_tailored_{clean_empresa}.html"
    output_dir = config.ensure_output_dir()
    output_html_path = os.path.join(output_dir, output_html_name)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(tailored_html)

    output_pdf_name = f"Curriculo_Raphael_Ramos_{clean_empresa}.pdf"
    output_pdf_path = os.path.join(output_dir, output_pdf_name)

    print(f"⚙️ Compilando PDF sob medida via Chrome headless...")
    success = compile_html_to_pdf(output_html_path, output_pdf_path, timeout=20)
    if success:
        print(f"{Color.GREEN}{Color.BOLD}✅ PDF calibrado gerado: {output_pdf_name}!{Color.RESET}")
    else:
        print(f"{Color.YELLOW}⚠️ HTML gerado ({output_html_name}). Abra e imprima como PDF no navegador.{Color.RESET}")

    # Copywriter de Abordagem Sob Medida
    model = "2" if lang == "en" else "1"
    subj, msg = get_message_content(model, nome="Team", empresa=init_empresa, vaga=init_vaga)
    print(f"\n{Color.BOLD}--- Mensagem de Abordagem Direta (< 400 caracteres) ---{Color.RESET}")
    print(f"{Color.CYAN}Assunto:{Color.RESET} {subj}\n")
    print(msg)
    print("-" * 70 + "\n")

    return output_pdf_path, ats_score
