# Revisão de arquitetura e plano para a v3

Data: 2026-09-16 · Base analisada: commit `686f230` (v2.0.0) · Método: agente `architect` do ECC (`.claude/agents/architect.md`): estado atual → requisitos → proposta → trade-offs.

## 1. Estado atual em uma frase

Um CLI em Python puro (stdlib), dividido em `core` (config, SQLite, HTTP), `miners` (GitHub, HN, Greenhouse, Simplify) e `engine` (mensagens, CV tailoring, envio). A divisão em pastas está boa, mas as camadas ainda se conhecem demais: `engine` chama o banco direto, `miners` imprimem no terminal, e o "lead" circula como dict na mineração e como tupla de 8 posições depois de salvo.

## 2. O que eu mantenho (concordo)

| Decisão | Por quê |
|---|---|
| Só stdlib, sem `pip` | Clona e roda. Para um CLI pessoal isso vale muito. Manter para o runtime; aceitar dependências só em dev (testes/lint), se quiser. |
| SQLite local como funil | Simples, sem servidor, e dá para consultar na mão. Escala de sobra para o volume de uma pessoa. |
| Um minerador por fonte, todos devolvendo o mesmo formato | É o ponto de extensão certo. Só falta formalizar o contrato (ver 4.2). |
| APIs públicas de ATS (Greenhouse `boards-api`, Lever `postings`, JSON-LD do Ashby) em vez de scraping de HTML | Mais estável e mais barato. |
| Filtro anti-Gupy/Workday e prioridade para ATS de etapa única | É a tese do produto e está bem aplicada. |
| Dedup por `url UNIQUE` + `INSERT OR IGNORE` | Rodar `mine` várias vezes sem duplicar. |
| Funil com status + alerta D+5 | Tem o modelo mental certo. |
| Subcomandos `argparse` | Adequado. Não precisa de Click/Typer. |

## 3. O que eu mudaria (discordo), com evidência

### 3.1 Bugs confirmados

1. **Idioma/CV errado para vagas do Simplify.** A regra "é internacional?" está copiada 5 vezes com critérios diferentes. Para um lead com origem `Simplify NewGrad (2d)`, o `show` usa inglês, mas `send`, `gmail` e `draft` usam **template em português + PDF em português** para vagas nos EUA. (Testado em `cli.py:68`, `mailer.py:24`, `mailer.py:65`, `mailer.py:80`, `cli.py:124`.)
2. **`send` pode enviar e-mail sem o currículo.** `mailer.py:39` só anexa `if os.path.exists(pdf_path)`, sem aviso. Nesta cópia do projeto não existe nenhum `.html`/`.pdf` de currículo na raiz, então hoje o envio sairia sem anexo e o `tailor` quebraria com `FileNotFoundError`.
3. **Regex de skills com falhas.** `\bc\+\+\b` nunca casa com "C++ " (o `\b` depois de `+` exige um caractere de palavra), e `\bgo\b` casa com "you will go above…". O resultado é gap e score errados.
4. **Filtro do GitHub quase não filtra.** `"eng"` em `is_python_backend` casa com "english", "engenharia", "length"… E a empresa padrão é o dono do repositório (`backend-br`), não a empresa da vaga.
5. **`--query` é ignorado** no Greenhouse (`mine_greenhouse` recebe `query` e não usa) e nem é passado ao GitHub.
6. **O funil fica errado.** `gmail` e `draft` marcam `mensagem_enviada` só por abrir o navegador ou o rascunho, mesmo que você não envie. Isso distorce o D+5.
7. **Os templates não cumprem "< 400 caracteres"**: têm 476, 464 e 447 caracteres.

### 3.2 Problemas de desenho

- **Não é Clean Architecture ainda**, é uma organização em pacotes. `engine/mailer.py` importa `core/db.update_status`; `engine/tailor.py` importa `core/db.get_lead`; os mineradores chamam `print`. Sugiro tirar o termo do README ou chegar lá de fato (seção 4).
- **O lead não tem tipo.** `lid, comp, title, src, url, contact, raw_body, status = lead` se repete em 5 lugares. Se você adicionar uma coluna, tudo quebra em silêncio.
- **Perda de dados na persistência.** Os mineradores calculam `labels`, `location` e `created_at`, mas nada disso é salvo. E-mails e links de ATS são concatenados em `contact_info`, e depois o mailer usa regex para separar de novo.
- **A coluna `followup_due_at` existe, mas nunca é usada.** `update_status` sobrescreve `contacted_at` em qualquer mudança, inclusive `descartada`. Não existe histórico de status, então não dá para medir conversão por fonte.
- **Dados pessoais e caminhos fixos no código:** e-mail, LinkedIn e textos dos templates, além do caminho do Chrome no macOS e do `open`. Isso deveria ficar num arquivo de perfil.
- **Saídas geradas na raiz do repo** (`curriculo_tailored_*.html`, `Curriculo_*.pdf`, `draft_lead_*.eml`). Só `*.eml` está no `.gitignore`.
- **`ssl._create_unverified_context()`** desliga a verificação TLS em todo fetch, e o fallback para `curl` engole erros. Em macOS, o certo é rodar o `Install Certificates.command` do Python em vez de desligar a verificação.
- **Não há nenhum teste.** Os parsers (HN, Simplify, JSON-LD) são exatamente o tipo de código que quebra quando a fonte muda.

### 3.3 Ponto de honestidade no CV Tailoring

- O "ATS Match Score" não mede o seu currículo: `core_profile_skills` injeta 20 skills fixas em `resume_skills`, o score vira **95.0 fixo** quando a JD não tem skills reconhecidas, e a similaridade vira **35 fixo** sem JD.
- Com `--skills "FastAPI, Redis, Kafka"`, essas skills entram automaticamente no seu perfil **e são inseridas no PDF** (`tailor.py:198-246`). Isso pode colocar no currículo algo que você não sustenta numa entrevista técnica.
- **Proposta:** declarar suas skills reais num `profile`, nunca injetar skill fora dele e renomear o número para "cobertura de keywords", que é o que ele mede.

## 4. Arquitetura proposta (v3)

Pragmática, sem virar framework. As regras dependem só de `domain`, e o resto depende delas.

```text
prospector/
├── domain/            # sem I/O
│   ├── lead.py        # @dataclass Lead, enum LeadStatus, enum Region(BR, INTL)
│   └── skills.py      # taxonomia + matching (regex corrigidas)
├── ports.py           # Protocols: Miner, LeadRepository, Sender, PdfRenderer, HttpClient
├── services/          # casos de uso (orquestram ports)
│   ├── mining.py      # MineLeads: roda miners, normaliza, deduplica, salva
│   ├── outreach.py    # PrepareMessage (template + CV por Region), SendOutreach
│   ├── tailoring.py   # TailorCV (score honesto, só skills do profile)
│   └── funnel.py      # followups, transições de status, métricas
├── adapters/
│   ├── miners/        # github, hacker_news, greenhouse, simplify (+ lever, ashby)
│   ├── storage/sqlite.py   # repositório + migrações por schema_version
│   ├── senders/       # smtp, gmail_web, eml_draft
│   ├── http.py        # urllib com TLS verificado, retry e timeout
│   └── pdf_chrome.py  # caminho do Chrome configurável
├── profile.py         # carrega profile.toml (tomllib, stdlib 3.11+)
└── cli.py             # só parse de argumentos + apresentação
data/                  # (gitignored) prospector.db, curriculos base, saídas geradas
profile.example.toml   # nome, e-mail, links, skills reais, templates, caminhos
tests/                 # unittest + fixtures JSON/HTML salvas de cada fonte
```

Decisões-chave:

- **`Region` é decidida uma vez, na mineração, e salva no lead.** Idioma do template e PDF saem dela. Isso resolve o bug 3.1.1 na raiz.
- **Novo schema:** colunas `emails`, `ats_links` e `labels` (JSON), `location`, `region`, `posted_at`, mais a tabela `lead_events(lead_id, status, at, note)` para histórico e métricas. Migração automática a partir do schema v2.
- **Status só muda com ação confirmada.** `gmail`/`draft` → `rascunho_aberto`; `send` com sucesso → `mensagem_enviada`; um novo comando `mark-sent` serve para envios manuais.
- **`send` falha se o PDF não existir** (ou exige `--sem-anexo` explícito).
- **Mineradores não imprimem.** Devolvem `list[Lead]`, e o CLI apresenta. O registro é um dict `{nome: Miner}`, então adicionar uma fonte não mexe no CLI.

### Trade-offs

| Decisão | Prós | Contras | Alternativa considerada |
|---|---|---|---|
| Ports com `typing.Protocol` | Testável com fakes, sem dependências | Mais arquivos | Manter funções soltas (mais simples, sem testes) |
| Continuar só com stdlib | Zero setup | Parsers HTML na mão | `httpx` + `selectolax`: mais robusto, mas perde o "clona e roda" |
| `profile.toml` | Separa código de dados pessoais; o repo pode ser público sem expor nada | Exige Python 3.11+ para `tomllib` | JSON (funciona em 3.8, porém menos legível) |
| SQLite + `lead_events` | Métricas de conversão por fonte | Migração necessária | Só a coluna `status` (sem histórico) |

## 5. Roadmap sugerido

| Fase | Entrega | Risco |
|---|---|---|
| **0: correções rápidas** (sem mudar a estrutura) ✅ feita | Função única `region_of(lead)`; `send` aborta sem PDF; regex C++/Go; filtro GitHub; `--query` no Greenhouse; saídas em `data/out/`; gmail/draft sem marcar como enviado | Baixo |
| **1: modelo de domínio** | `Lead` dataclass, `LeadStatus`, `Region`; repositório SQLite com migração v2→v3 | Médio (mexe no banco; fazer backup do `.db`) |
| **2: mineradores com contrato** | `Miner` Protocol, registro, sem `print`, testes com fixtures | Baixo |
| **3: outreach** | `Sender` ports, `profile.toml`, templates fora do código, status honesto | Baixo |
| **4: tailoring honesto** | Skills do profile, "cobertura de keywords", sem injeção fora do profile, Chrome configurável | Baixo |
| **5: opcional** | Métricas do funil (`prospector stats`), mineradores Lever/Ashby diretos, `--dry-run` no `send` | — |

Comandos do ECC úteis por fase: `/plan` (detalhar uma fase), `/python-review` (revisão após cada fase), agente `tdd-guide` (fases 1 e 2) e `code-architect` (validar a estrutura da fase 1).
