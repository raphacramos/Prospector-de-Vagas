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
│   │   └── greenhouse.py       # Consumo das APIs públicas do Greenhouse para startups
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
# Mineração completa (GitHub + Hacker News + Greenhouse)
python3 prospector.py mine

# Minerar apenas GitHub (Mercado Brasileiro)
python3 prospector.py mine --source github

# Minerar apenas Hacker News (Thread ativa do mês)
python3 prospector.py mine --source hn

# Minerar apenas APIs públicas do Greenhouse
python3 prospector.py mine --source greenhouse
```

---

### 2. Motor de Customização de Currículo (CV Tailoring)

Gera uma versão do currículo calibrada com as competências exatas da vaga:

```bash
# Customização por palavras-chave
python3 prospector.py tailor --empresa "Linear" --vaga "Backend Engineer" --skills "FastAPI, PostgreSQL, Concurrency"

# Customização a partir de um arquivo de Job Description
python3 prospector.py tailor --empresa "Cloudflare" --jd vaga_cloudflare.txt
```

---

### 3. Disparo Automatizado e Rápido

```bash
# ⚡ Disparo 100% automatizado via SMTP com anexo automático do PDF
python3 prospector.py send <ID>

# 🌐 Abertura do Gmail Web com assunto, mensagem e destinatário preenchidos
python3 prospector.py gmail <ID>

# 📄 Geração de rascunho .eml com PDF anexado
python3 prospector.py draft <ID>
```

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

## 📄 Licença

Distribuído sob a licença MIT. Desenvolvido para uso pessoal e profissional em engenharia de software.
