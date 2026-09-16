"""Taxonomia de competencias e metricas de aderencia curriculo x vaga. Sem I/O."""
import math
import re
from collections import Counter

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

# Sinonimos em portugues: um CV-mestre em pt comprova o que o CV adaptado diz em ingles.
PT_PATTERNS = {
    "SQL & Relational DBs": [r"\bbancos? de dados relaciona(l|is)\b"],
    "Distributed Systems": [r"\bsistemas distribu[ií]dos\b"],
    "High Throughput & Concurrency": [r"\bconcorr[eê]ncia\b", r"\balta vaz[aã]o\b", r"\bparalelismo\b", r"\bbaixa lat[eê]ncia\b"],
    "Clean Architecture & Design": [r"\barquitetura limpa\b", r"\bpadr[oõ]es de projeto\b"],
    "Data Pipelines & Telemetry": [r"\bpipelines? de dados\b", r"\btelemetria\b", r"\bprocessamento de sinais\b", r"\bs[eé]ries temporais\b"],
    "Machine Learning & AI": [r"\baprendizado de m[aá]quina\b", r"\bintelig[eê]ncia artificial\b"],
    "Algorithms & Data Structures": [r"\balgoritmos?\b", r"\bestruturas? de dados\b"],
    "Linux & Internals": [r"\bsistemas operacionais\b"],
    "Computer Networks": [r"\bredes de computadores\b", r"\bprotocolos de rede\b"],
    "Docker & Containers": [r"\bcont[eê]ineres\b"],
    "Git & CI/CD": [r"\bintegra[cç][aã]o cont[ií]nua\b"],
}
for _name, _pats in PT_PATTERNS.items():
    CANONICAL_SKILLS[_name] = CANONICAL_SKILLS[_name] + _pats

# Tecnologias fora da taxonomia, usadas para detectar termos inventados no texto adaptado.
TECH_TERMS = [
    "kafka", "rabbitmq", "kubernetes", "k8s", "terraform", "ansible", "aws", "gcp", "azure", "lambda",
    "s3", "ec2", "bigquery", "snowflake", "databricks", "spark", "pyspark", "hadoop", "airflow", "dbt",
    "flink", "elasticsearch", "opensearch", "clickhouse", "cassandra", "dynamodb", "mysql", "sqlite",
    "graphql", "grpc", "kotlin", "scala", "ruby", "rails", "php", "laravel", "swift", "elixir", "haskell",
    "typescript", "javascript", "react", "vue", "angular", "next.js", "node.js", "django", "flask",
    "fastapi", "spring", "celery", "pandas", "numpy", "pytorch", "tensorflow", "scikit-learn", "llm",
    "langchain", "openai", "prometheus", "grafana", "datadog", "jenkins", "github actions", "gitlab ci",
    "circleci", "helm", "istio", "nginx", "redis", "mongodb", "postgresql", "docker", "linux", "go",
    "golang", "rust", "java", "c++", "c#", ".net", "tableau", "power bi", "looker", "sap", "salesforce",
]


def mentioned_terms(text, terms=TECH_TERMS):
    low = (text or "").lower()
    found = set()
    for t in terms:
        if t == "go":
            if re.search(r"\bGo\b(?!\s+(?:to|above|beyond|ahead|back|through))", text or "") or "golang" in low:
                found.add(t)
            continue
        if re.search(r"(?<![\w+#.])" + re.escape(t) + r"(?![\w+#])", low):
            found.add(t)
    return found


STOPWORDS = {
    "the", "and", "a", "to", "in", "of", "with", "is", "for", "on", "that", "as", "be", "at", "by",
    "this", "we", "are", "you", "will", "our", "an", "or", "from", "your", "have", "all", "can",
    "not", "work", "team", "who", "about", "more", "their", "has", "so", "if", "into", "up", "do",
    "out", "what", "which", "when", "one", "years", "experience", "candidate", "role", "position"
}


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

def cosine_similarity(text1, text2):
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


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def requirements_from_text(items):
    """'FastAPI, Kafka' -> {'FastAPI', 'Kafka'} usando nomes canonicos quando reconhecidos."""
    found = set()
    for item in (items or "").split(","):
        item = item.strip()
        if not item:
            continue
        canonical = extract_canonical_skills(item)
        exact = [name for name in CANONICAL_SKILLS if _norm(name) == _norm(item)]
        found.update(exact or canonical or {item})
    return found


def skill_in(skill, collection):
    """Comparacao sem diferenciar maiusculas."""
    key = _norm(skill)
    return any(_norm(s) == key for s in collection)
