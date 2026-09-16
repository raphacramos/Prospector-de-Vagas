# 🎯 Prospector de Vagas

> **CLI de Mineração Técnica & Funil de Prospecção Ágil para Engenharia de Software**  
> Arquitetura modular orientada a dados para automatização da rotina estratégica de prospecção ativa, mineração algorítmica de vagas ocultas e contato direto com lideranças técnicas (CTOs, Tech Leads e Engineering Managers).

---

## 💡 Por que este projeto existe?

O ecossistema contemporâneo de recrutamento impõe barreiras assimétricas para profissionais de tecnologia. Sistemas ATS convencionais (como **Gupy**, **Workday** e **Taleo**) desviam o foco do mérito técnico para triagens automatizadas opacas, onde as taxas de conversão final para entrevistas frequentemente ficam abaixo de **2%**.

O **Prospector de Vagas** reverte essa dinâmica através de:
1. **Foco em canais de baixa fricção operacional:** Mineração direta no **GitHub Issues** (`backend-br`, `datascience-br`), no fórum mensal do **Hacker News** (*Ask HN: Who is hiring?*) e nas APIs públicas do **Greenhouse**.
2. **Filtro Anti-Gupy / Anti-Workday:** Descarte automatizado de links para portais burocráticos de triagem lenta.
3. **Extração de Contatos Diretos:** Identificação imediata de e-mails de engenharia e links de ATS ágeis (Ashby, Greenhouse, Lever, Workable).
4. **Motor de Mensagens de Alto Impacto (< 400 caracteres):** Geração automática de abordagens técnicas cirúrgicas personalizadas para o perfil de **Software Engineer (Backend & Data Platforms)**.
5. **Funil & Gestão de Follow-up (D+5):** Registro local em SQLite com alertas de recontato (onde ocorrem de 40% a 55% das respostas positivas).
6. **CV Tailoring Engine:** Customização dinâmica de palavras-chave e geração de currículo sob medida para cada empresa.

---

## 🏗️ Arquitetura Modular

O projeto foi refatorado seguindo princípios de **Clean Architecture** e separação formal de responsabilidades, garantindo desacoplamento, facilidade de teste e manutenibilidade:

```text
Prospector-de-Vagas/
├── prospector.py               # Ponto de entrada executável da CLI
├── prospector/
│   ├── __init__.py             # Metadados e versão do pacote
│   ├── __main__.py             # Permite execução como módulo: python3 -m prospector
│   ├── cli.py                  # Parser e roteamento dos comandos CLI (argparse)
│   ├── core/
│   │   ├── config.py           # Constantes de caminhos, cores ANSI e carregamento de .env
│   │   ├── db.py               # Camada de persistência SQLite (prospector.db) e funil
│   │   └── utils.py            # Utilitários de requisição HTTP, sanitização e compilação
│   ├── miners/
│   │   ├── base.py             # Expressões regulares, filtros anti-Gupy e extratores
│   │   ├── github.py           # Scraper da API do GitHub (backend-br, datascience-br)
│   │   ├── hacker_news.py      # Parser Algolia da thread mensal Ask HN: Who is hiring
│   │   ├── greenhouse.py       # Consumo das APIs públicas do Greenhouse para startups
│   │   └── simplify.py         # Parser algorítmico do SimplifyJobs (New Grad & Fast ATS)
│   └── engine/
│       ├── copywriter.py       # Motor de mensagens de abordagem (< 400 chars) em PT/EN
│       ├── tailor.py           # Motor de customização dinâmica de currículo (CV Tailoring)
│       └── mailer.py           # Disparador SMTP via Gmail, rascunhos .eml e Gmail Web
```

---

## 🚀 Guia de Uso

O projeto utiliza **apenas a biblioteca padrão do Python (3.8+)**, sem dependências externas (`pip`).

### 1. Mineração de Oportunidades

```bash
# Mineração completa (GitHub + Hacker News + Greenhouse + SimplifyJobs)
python3 prospector.py mine

# Minerar SimplifyJobs (Vagas ativas New Grad / Associate em Fast-ATS: Ashby, Greenhouse, Lever)
python3 prospector.py mine --source simplify

# Minerar SimplifyJobs apenas vagas com trabalho Remoto / Global / LATAM
python3 prospector.py mine --source simplify --remote-only

# Minerar apenas GitHub (Mercado Brasileiro)
python3 prospector.py mine --source github

# Minerar apenas Hacker News (Thread ativa do mês)
python3 prospector.py mine --source hn

# Minerar apenas APIs públicas do Greenhouse
python3 prospector.py mine --source greenhouse
```

---

### 2. Motor de Calibração de Currículo (CV Tailoring & ATS Scoring)

Inspirado no algoritmo do **Resume-Matcher**, o motor analisa a descrição da vaga (Job Description), calcula o **Score de Aderência ATS**, identifica **Keywords Faltantes (Keyword Gap)** e compila automaticamente uma versão em PDF (1 página A4) via Google Chrome headless:

```bash
# 🚀 Calibração automática direto do ID da vaga (extrai JD oficial de Ashby, Greenhouse e Lever)
python3 prospector.py tailor --lead 452

# Calibração via URL direta da vaga
python3 prospector.py tailor --url https://boards.greenhouse.io/spacex/jobs/8696097002

# Customização cirúrgica por competências
python3 prospector.py tailor --empresa "Linear" --vaga "Backend Engineer" --skills "FastAPI, PostgreSQL, Concurrency, Redis"

# Customização a partir de um arquivo local de Job Description
python3 prospector.py tailor --empresa "Cloudflare" --jd vaga_cloudflare.txt
```

---

### 3. Disparo Automatizado e Rápido

```bash
# ⚡ Disparo 100% automatizado via SMTP com anexo automático do PDF
#    (aborta se o PDF não existir; use --sem-anexo para enviar mesmo assim)
python3 prospector.py send <ID>

# 🌐 Abertura do Gmail Web com assunto, mensagem e destinatário preenchidos
python3 prospector.py gmail <ID>

# 📄 Geração de rascunho .eml com PDF anexado (salvo em data/out/)
python3 prospector.py draft <ID>
```

`gmail` e `draft` marcam o lead como `rascunho_aberto`. Depois de enviar de fato, rode `python3 prospector.py update <ID> mensagem_enviada` para iniciar a contagem do follow-up D+5.

Idioma da mensagem e do currículo: vagas de Hacker News, Greenhouse e SimplifyJobs usam inglês; vagas do GitHub (mercado brasileiro) usam português. A regra fica em `prospector/core/region.py`.

---

### 4. Gestão do Funil e Follow-ups (D+5)

```bash
# Listar oportunidades no funil
python3 prospector.py list

# Inspecionar detalhes de uma vaga e mensagem sugerida
python3 prospector.py show <ID>

# Checar alertas de follow-up (D+5)
python3 prospector.py followups

# Atualizar status de um lead
python3 prospector.py update <ID> resposta
```

---

## 📁 Arquivos pessoais (`data/`)

A pasta `data/` é ignorada pelo git. Coloque nela os currículos base (`curriculo_en.html`, `curriculo_pt_destaque.html`, `Curriculo_Raphael_Ramos_EN.pdf`, `Curriculo_Raphael_Ramos_PT_Destaque.pdf`). A raiz do projeto continua sendo aceita como local antigo. Os currículos calibrados e os rascunhos `.eml` são gerados em `data/out/`.

## 🧪 Testes

```bash
python3 -m unittest discover -s tests -v
```

Os testes não acessam a rede, não enviam e-mails e não tocam no `prospector.db`.

## 🏛️ Arquitetura e roadmap

Veja [`docs/arquitetura/001-revisao-e-plano-v3.md`](docs/arquitetura/001-revisao-e-plano-v3.md). A pasta `.claude/` contém os agentes, regras e comandos do [ECC](https://github.com/affaan-m/ECC) usados no planejamento.

## 📄 Licença

Distribuído sob a licença MIT. Desenvolvido para uso pessoal e profissional em engenharia de software.
