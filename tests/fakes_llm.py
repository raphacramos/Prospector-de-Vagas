"""IA falsa: devolve respostas prontas e guarda as chamadas."""
import copy


class FakeLlm:
    model = "fake-model"

    def __init__(self, responses):
        self.responses = responses   # tool_name -> dict ou callable(system, content) -> dict
        self.calls = []
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.configured = True

    def generate_json(self, system, content, schema, tool_name, max_tokens=4096):
        self.calls.append({"system": system, "content": content, "tool": tool_name})
        self.usage["input_tokens"] += 100
        self.usage["output_tokens"] += 50
        resp = self.responses[tool_name]
        return copy.deepcopy(resp(system, content) if callable(resp) else resp)


MASTER = {
    "language": "pt",
    "contact": {"name": "Raphael Ramos", "email": "raphael@example.com", "phone": "+55 83 90000-0000",
                "location": "Campina Grande, PB", "links": ["github.com/raphacramos"]},
    "headline": "Engenheiro de Software",
    "summary": "Backend e dados com Python.",
    "experiences": [
        {"company": "Projeto BINGO", "role": "Pesquisador", "start": "2021", "end": "Atual",
         "bullets": ["Construí pipelines de telemetria em Python e HDF5",
                     "Automatizei rotinas em Linux com Bash",
                     "Otimizei algoritmos de processamento de sinais"]},
        {"company": "UFCG", "role": "Monitor de LEDA", "start": "2019", "end": "2020",
         "bullets": ["Ensinei estruturas de dados e algoritmos"]},
    ],
    "projects": [{"name": "Prospector", "description": "CLI de vagas", "bullets": ["CLI em Python com SQLite"]}],
    "education": [{"institution": "UFCG", "degree": "Ciência da Computação", "start": "2017", "end": "2023"}],
    "skills": ["Python", "PostgreSQL", "Linux", "Docker", "Git", "HDF5"],
    "languages": ["Português (nativo)", "Inglês (fluente)"],
}

TAILORED = {
    "headline": "Backend Engineer",
    "summary": "Backend engineer with Python and data pipelines.",
    "experiences": [
        {"id": "exp1", "bullets": [
            {"id": "exp1.b1", "text": "Built Python telemetry pipelines with HDF5"},
            {"id": "exp1.b2", "text": "Automated Linux routines with Bash"},
        ]},
        {"id": "exp2", "bullets": [{"id": "exp2.b1", "text": "Taught data structures and algorithms"}]},
    ],
    "projects": [],
    "skills": ["Python", "PostgreSQL", "Docker", "Linux"],
    "keywords_used": ["Python", "PostgreSQL"],
    "missing_requirements": ["Kafka"],
    "cover_letter": "Hi team, I built Python telemetry pipelines... Raphael Ramos",
    "fit_summary": "Boa aderência em Python; falta Kafka.",
    "role_titles": [{"id": "exp1", "text": "Researcher"}, {"id": "exp2", "text": "Data Structures TA"}],
    "education_titles": [{"id": "edu1", "text": "B.Sc. in Computer Science"}],
    "languages": ["Portuguese (native)", "English (fluent)"],
}
