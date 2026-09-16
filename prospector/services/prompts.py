"""Prompts e schemas usados com a IA. Ficam juntos para facilitar ajustes."""

_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": _STR}

IMPORT_SCHEMA = {
    "type": "object",
    "required": ["language", "contact", "experiences", "skills"],
    "properties": {
        "language": {"type": "string", "enum": ["pt", "en"]},
        "contact": {"type": "object", "required": ["name"], "properties": {
            "name": _STR, "email": _STR, "phone": _STR, "location": _STR, "links": _STR_LIST}},
        "headline": _STR,
        "summary": _STR,
        "experiences": {"type": "array", "items": {"type": "object", "required": ["company", "role", "bullets"],
                        "properties": {"company": _STR, "role": _STR, "start": _STR, "end": _STR,
                                       "location": _STR, "bullets": _STR_LIST}}},
        "projects": {"type": "array", "items": {"type": "object", "required": ["name"],
                     "properties": {"name": _STR, "description": _STR, "link": _STR, "bullets": _STR_LIST}}},
        "education": {"type": "array", "items": {"type": "object", "required": ["institution", "degree"],
                      "properties": {"institution": _STR, "degree": _STR, "start": _STR, "end": _STR,
                                     "details": _STR}}},
        "skills": _STR_LIST,
        "languages": _STR_LIST,
        "certifications": _STR_LIST,
    },
}

IMPORT_SYSTEM = """Você extrai currículos para um formato estruturado.
Regras:
- Copie apenas o que está no documento. Não invente, não complete e não melhore nada.
- Mantenha o idioma original do documento e informe-o em `language` ("pt" ou "en").
- Cada responsabilidade ou conquista vira um item de `bullets`, com o texto original.
- Datas como aparecem (ex.: "03/2022", "2021", "Atual", "Present").
- `skills`: tecnologias, ferramentas e competências citadas no documento, sem duplicatas.
- `links`: LinkedIn, GitHub, site, como aparecem.
- Se algo não existir no documento, omita o campo ou use lista vazia."""

_TAILORED_ITEM = {"type": "object", "required": ["id", "bullets"], "properties": {
    "id": _STR,
    "bullets": {"type": "array", "items": {"type": "object", "required": ["id", "text"],
                "properties": {"id": _STR, "text": _STR}}},
}}

TAILOR_SCHEMA = {
    "type": "object",
    "required": ["headline", "summary", "experiences", "projects", "skills", "cover_letter",
                 "keywords_used", "missing_requirements"],
    "properties": {
        "headline": _STR,
        "summary": _STR,
        "experiences": {"type": "array", "items": _TAILORED_ITEM},
        "projects": {"type": "array", "items": _TAILORED_ITEM},
        "skills": _STR_LIST,
        "keywords_used": _STR_LIST,
        "missing_requirements": _STR_LIST,
        "cover_letter": _STR,
        "fit_summary": _STR,
    },
}

TAILOR_SYSTEM = """Você adapta um currículo verdadeiro para uma vaga específica.

Você recebe o CV-mestre em JSON (a única fonte de fatos) e a descrição da vaga.

Regras invioláveis:
1. Não invente nada: nenhuma tecnologia, métrica, responsabilidade, empresa ou resultado que não esteja no CV-mestre. Se a vaga pede algo que o candidato não tem, liste em `missing_requirements` e não mencione no currículo nem na carta.
2. Use apenas ids que existem no CV-mestre. Cada bullet de saída tem o `id` do bullet de origem e um `text` reescrito a partir dele; você pode reescrever, encurtar e usar os termos da vaga quando forem sinônimos exatos do que o bullet já diz.
3. Não repita o mesmo bullet de origem.
4. Escreva tudo no idioma pedido (traduza fielmente se o mestre estiver em outro idioma).

Objetivo:
- `experiences`: todas as experiências relevantes, na ordem mais recente primeiro, com os bullets mais aderentes à vaga primeiro (no máximo {max_bullets} por experiência).
- `projects`: só os projetos que ajudam nesta vaga (pode ser lista vazia).
- `headline`: título profissional curto alinhado ao cargo, sem prometer senioridade que o CV não mostra.
- `summary`: 2 a 3 frases com o que o candidato tem de mais relevante para esta vaga.
- `skills`: até 16 itens do CV-mestre, os mais relevantes primeiro, escritos como no mestre.
- `keywords_used`: termos da vaga que o currículo adaptado cobre de fato.
- `cover_letter`: carta curta (até 170 palavras), sem clichês, citando a empresa e 2 evidências concretas do CV. Sem cabeçalho de endereço. Assine com o nome do candidato.
- `fit_summary`: uma frase honesta sobre a aderência (para o candidato, não para a empresa).
- O currículo deve caber em uma página A4."""

ANSWERS_SCHEMA = {
    "type": "object",
    "required": ["answers"],
    "properties": {"answers": {"type": "array", "items": {
        "type": "object", "required": ["question", "answer", "confident"],
        "properties": {"question": _STR, "answer": _STR, "confident": {"type": "boolean"}},
    }}},
}

ANSWERS_SYSTEM = """Você responde perguntas abertas de formulários de candidatura em nome do candidato.
Use apenas fatos do CV-mestre, das respostas padrão do candidato e da vaga. Se a pergunta pedir um
fato que não está disponível (salário, data de início, autorização de trabalho, dados pessoais),
responda com string vazia e `confident: false`. Nunca invente. Respostas curtas e diretas
(até 120 palavras), no idioma da pergunta."""
