# 🎯 Prospector de Vagas

> **CLI de Mineração Técnica & Funil de Prospecção Ágil para Engenharia de Software**  
> Arquitetura modular orientada a dados para automatização da rotina estratégica de prospecção ativa, mineração algorítmica de vagas ocultas e contato direto com lideranças técnicas (CTOs, Tech Leads e Engineering Managers).

---

## 💡 Por que este projeto existe?

O ecossistema contemporâneo de recrutamento impõe barreiras assimétricas para profissionais de tecnologia. Sistemas ATS convencionais (como **Gupy**, **Workday** e **Taleo**) desviam o foco do mérito técnico para triagens automatizadas opacas, onde as taxas de conversão final para entrevistas frequentemente ficam abaixo de **2%**.

O **Prospector de Vagas** reverte essa dinâmica através de:
1. **Foco em canais de baixa fricção operacional:** Mineração direta no **GitHub Issues** (`backend-br`, `datascience-br`), no fórum mensal do **Hacker News** (*Ask HN: Who is hiring?*) e nas APIs públicas do **Greenhouse**, **Lever** e **Ashby**, além do **SimplifyJobs**.
2. **Filtro Anti-Gupy / Anti-Workday:** Descarte automatizado de links para portais burocráticos de triagem lenta.
3. **Extração de Contatos Diretos:** Identificação imediata de e-mails de engenharia e links de ATS ágeis (Ashby, Greenhouse, Lever, Workable).
4. **Motor de Mensagens Curtas:** Templates de abordagem técnica configuráveis no perfil, com aviso quando passam do limite de caracteres definido.
5. **Funil & Gestão de Follow-up (D+5):** Registro local em SQLite com histórico de status, alertas de recontato e taxa de resposta por fonte.
6. **CV Tailoring:** Comparação currículo x vaga e geração de currículo calibrado para cada empresa, sem incluir competências que você não declarou.

---

## 🏗️ Arquitetura (v3)

As regras de negócio ficam em `domain/` e `services/` e não conhecem terminal, SQLite ou HTTP. Tudo que faz I/O fica em `adapters/`, atrás dos contratos de `ports.py`. A revisão que levou a essa estrutura está em [`docs/arquitetura/001-revisao-e-plano-v3.md`](docs/arquitetura/001-revisao-e-plano-v3.md).

```text
Prospector-de-Vagas/
├── prospector.py                 # Ponto de entrada (python3 prospector.py ...)
├── profile.example.json          # Perfil de exemplo: dados pessoais, templates, skills, fontes
├── prospector/
│   ├── cli.py                    # argparse + apresentação no terminal
│   ├── ports.py                  # Contratos: Miner, HttpClient, LeadRepository, MiningOptions
│   ├── profile.py                # Carrega o perfil (data/profile.json ou o exemplo)
│   ├── domain/
│   │   ├── lead.py               # Lead, LeadStatus, Region (define idioma de mensagem e CV)
│   │   └── skills.py             # Taxonomia de competências e similaridade
│   ├── services/
│   │   ├── mining.py             # Roda as fontes, isola falhas, deduplica e salva
│   │   ├── outreach.py           # Monta a mensagem certa e registra no funil
│   │   ├── tailoring.py          # Compara CV x vaga e gera o CV calibrado
│   │   └── funnel.py             # Métricas por fonte
│   ├── adapters/
│   │   ├── miners/               # github, hacker_news, greenhouse, lever, ashby, simplify
│   │   ├── storage/sqlite.py     # Repositório + migração automática de schema
│   │   ├── senders.py            # SMTP, Gmail Web e rascunho .eml
│   │   ├── http.py               # urllib com TLS verificado
│   │   ├── jd_fetcher.py         # Descrição da vaga (Greenhouse, Lever, Ashby, JSON-LD)
│   │   └── pdf_chrome.py         # HTML -> PDF com Chrome/Chromium headless
│   └── core/                     # config (caminhos, .env, cores) e fábrica do repositório
├── tests/                        # unittest + respostas gravadas das fontes (sem rede)
├── docs/arquitetura/             # Decisões e roadmap
└── data/                         # (fora do git) banco, perfil, currículos, saídas e backups
```

---

## ⚙️ Configuração

Requer **Python 3.8+** e usa **apenas a biblioteca padrão**, sem `pip install`.

1. **Perfil:** copie o exemplo e edite seus dados. Sem `data/profile.json`, o Prospector usa `profile.example.json`.
   ```bash
   mkdir -p data && cp profile.example.json data/profile.json
   ```
   No perfil ficam nome, e-mail, links, templates (`br`, `intl`, `recrutador`), textos de follow-up, arquivos de currículo, **skills que você realmente tem**, o título do CV e as listas de empresas por fonte (`fontes.github`, `greenhouse`, `lever`, `ashby`).
2. **Currículos:** coloque em `data/` os arquivos indicados em `curriculos` do perfil (`curriculo_en.html`, `curriculo_pt_destaque.html` e os PDFs). A raiz do projeto continua aceita como local antigo.
3. **Envio por SMTP:** crie um `.env` na raiz com `EMAIL_USER` e `EMAIL_PASS` (senha de app do Gmail).

Variáveis de ambiente opcionais:

| Variável | Para quê |
|---|---|
| `PROSPECTOR_DB` | Usar outro arquivo de banco (padrão: `data/prospector.db`, ou `prospector.db` na raiz se já existir) |
| `PROSPECTOR_PROFILE` | Usar outro arquivo de perfil |
| `GITHUB_TOKEN` | Aumentar o limite da API do GitHub (60 req/h sem token) |
| `CHROME_PATH` | Caminho do Chrome/Chromium, se não for detectado |
| `PROSPECTOR_DEBUG=1` | Mostrar erros de rede no terminal |

**Atualizando da v2:** na primeira execução, o banco antigo é migrado para o schema v3 automaticamente. Antes disso, uma cópia é salva em `data/backups/`.

---

## 🚀 Guia de Uso

### 1. Mineração

```bash
python3 prospector.py mine                          # todas as fontes
python3 prospector.py mine --source lever           # github | hn | greenhouse | lever | ashby | simplify
python3 prospector.py mine --query backend          # filtra por termo (título/descrição, conforme a fonte)
python3 prospector.py mine --remote-only            # só vagas remotas/LATAM/globais, em todas as fontes
python3 prospector.py mine --source github --all-levels   # inclui vagas acima de júnior
python3 prospector.py mine --source simplify --all-ats    # aceita sites próprios (Workday segue bloqueado)
python3 prospector.py mine --limit 20               # máximo por fonte (no Greenhouse/Lever/Ashby, por empresa)
```

Uma fonte fora do ar não interrompe as outras, e o resumo mostra quantas vagas vieram de cada uma. Vagas repetidas (mesma URL, sem parâmetros de rastreamento) não são salvas de novo. No GitHub, issues com o template sem preencher são ignoradas.

### 2. Calibração de currículo

```bash
python3 prospector.py tailor --lead 452                   # usa empresa, cargo, URL e idioma do lead
python3 prospector.py tailor --url https://job-boards.greenhouse.io/gitlab/jobs/123
python3 prospector.py tailor --empresa "Linear" --skills "FastAPI, PostgreSQL, Redis"
python3 prospector.py tailor --empresa "Cloudflare" --jd vaga_cloudflare.txt --lang pt --sem-pdf
```

O relatório mostra a **cobertura de requisitos** (quantos requisitos da vaga aparecem no seu CV ou nas `skills` do perfil) e a **similaridade textual**. Sem requisitos para comparar, o resultado é `n/d`.

Requisitos que você não tem aparecem como **lacunas** e **não são adicionados ao CV**. Uma palavra só é inserida no currículo quando está em `palavras_opcionais_cv` no perfil **e** a vaga pede. O HTML e o PDF calibrados vão para `data/out/`.

### 3. Abordagem

```bash
python3 prospector.py show <ID>                     # detalhes, histórico, mensagem e avisos
python3 prospector.py send <ID>                     # SMTP com o PDF no idioma do template
python3 prospector.py send <ID> --dry-run           # só mostra; não envia nem muda o funil
python3 prospector.py send <ID> --sem-anexo         # envia mesmo sem o PDF
python3 prospector.py gmail <ID>                    # abre o Gmail Web preenchido (anexo manual)
python3 prospector.py draft <ID> --modelo recrutador --nome Ana   # .eml em data/out/
```

Por padrão, o template é escolhido pela região do lead: `br` para o GitHub brasileiro e `intl` para HN, Greenhouse, Lever, Ashby e Simplify. O PDF anexado segue o idioma do template.

O `send` marca o lead como `mensagem_enviada` e agenda o follow-up. `gmail` e `draft` marcam `rascunho_aberto`; depois de enviar de fato, rode `update <ID> mensagem_enviada`.

O `show` avisa quando a mensagem passa de `max_caracteres_mensagem`, quando a empresa não foi identificada e quando o currículo não existe.

### 4. Funil e follow-ups

```bash
python3 prospector.py list [--status mensagem_enviada] [--limit 50]
python3 prospector.py update <ID> resposta --nota "call marcada 20/09"
python3 prospector.py followups                     # contatos com D+5 vencido
python3 prospector.py stats                         # leads, contatados, respostas e taxa por fonte
```

Toda mudança de status fica registrada no histórico (`lead_events`), e o `stats` usa esse histórico: um lead descartado depois de responder continua contando como resposta.

---

## 🧪 Testes

```bash
python3 -m unittest discover -s tests -v
```

Os testes usam respostas gravadas das fontes (`tests/fixtures/`) e um SMTP falso. Nenhum teste acessa a rede, envia e-mail ou toca no seu `prospector.db`.

## 🤖 Apoio de IA

A pasta `.claude/` contém os agentes, regras e comandos do [ECC](https://github.com/affaan-m/ECC) (por exemplo, `architect`, `planner` e `python-reviewer`), usados no planejamento da v3.

---

## 📄 Licença

Distribuído sob a licença MIT. Desenvolvido para uso pessoal e profissional em engenharia de software.
