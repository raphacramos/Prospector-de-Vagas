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

## ⚡ Candidaturas rápidas (estilo AIApply)

O fluxo para aplicar em várias vagas com o currículo adaptado a cada uma:

1. **Buscar** vagas (`mine` ou o botão *Buscar vagas*).
2. **Priorizar:** a fila mostra primeiro as vagas com link de ATS ou e-mail e maior aderência ao seu CV.
3. **Preparar:** a IA lê a vaga e monta, a partir do seu CV-mestre, um currículo adaptado (resumo, ordem e texto dos bullets, skills), uma carta curta e o PDF. Dá para preparar várias vagas de uma vez.
4. **Aplicar:** o Chrome abre o formulário do Greenhouse, Lever ou Ashby já preenchido, com CV e carta anexados. Perguntas abertas são respondidas pela IA quando ela tem base para isso. O que precisa de você fica destacado em laranja.
5. **Enviar:** você revisa e clica em enviar no site. O Prospector nunca envia sozinho.
6. **Marcar enviada:** o follow-up e as métricas passam a contar a vaga.

**O que a IA não faz:** inventar. Empresas, cargos, datas e formação vêm sempre do CV-mestre (a IA só traduz cargos e cursos quando o CV sai em outro idioma). Experiências, bullets e skills que não existem no mestre são removidos, e tecnologias citadas sem comprovação aparecem como aviso. O que a vaga pede e você não tem vira **lacuna** no painel.

### Configuração (uma vez)

```bash
# 1. Chave da API da Anthropic (console.anthropic.com), no arquivo .env da raiz
echo 'ANTHROPIC_API_KEY=sua-chave' >> .env

# 2. Perfil com seus dados, respostas padrão e idioma
mkdir -p data && cp profile.example.json data/profile.json   # edite "candidato" e "ia"

# 3. CV-mestre a partir do seu currículo (PDF, DOCX, TXT ou MD)
python3 prospector.py importar-cv ~/Downloads/meu-curriculo.pdf   # revise data/resume.json

# 4. Opcional: preenchimento automático dos formulários (usa o Chrome instalado)
pip3 install -r requirements-opcional.txt

# 5. Painel
python3 prospector.py painel
```

O painel abre em `http://127.0.0.1:8765` com um token da sessão e só aceita conexões deste computador. Atalhos: <kbd>j</kbd>/<kbd>k</kbd> navegam, <kbd>p</kbd> prepara, <kbd>a</kbd> aplica, <kbd>e</kbd> marca como enviada, <kbd>d</kbd> descarta e <kbd>/</kbd> busca.

Os mesmos passos existem no terminal:

```bash
python3 prospector.py preparar 12 15 18            # uma ou várias vagas
python3 prospector.py aplicar 12                   # abre o formulário preenchido e pergunta se você enviou
```

**Custo:** com o modelo padrão (`claude-sonnet-5`, US$ 2 por milhão de tokens de entrada e US$ 10 por milhão de saída na tabela da Anthropic), cada vaga preparada usa em geral 5 a 9 mil tokens de entrada e 1,5 a 2,5 mil de saída, cerca de US$ 0,03 a 0,05. O painel mostra os tokens de cada candidatura. Para trocar o modelo, altere `ia.modelo` no perfil.

**Arquivos gerados** em `data/applications/<id>-<empresa>/`: `cv.html`, o PDF, `carta.txt`, `vaga.txt`, `tailored.json` (o que a IA escolheu) e `meta.json`.

**Chrome do Prospector:** o preenchimento usa um perfil próprio em `data/browser-profile`. Se um ATS pedir login, entre uma vez nessa janela e o login fica salvo.

---

## 🏗️ Arquitetura (v3)

As regras de negócio ficam em `domain/` e `services/` e não conhecem terminal, SQLite ou HTTP. Tudo que faz I/O fica em `adapters/`, atrás dos contratos de `ports.py`. A revisão que levou a essa estrutura está em [`docs/arquitetura/001-revisao-e-plano-v3.md`](docs/arquitetura/001-revisao-e-plano-v3.md).

```text
Prospector-de-Vagas/
├── prospector.py                 # Ponto de entrada (python3 prospector.py ...)
├── profile.example.json          # Perfil de exemplo: dados pessoais, templates, skills, fontes, IA
├── requirements-opcional.txt     # Playwright (preenchimento automático, opcional)
├── prospector/
│   ├── cli.py                    # argparse + apresentação no terminal
│   ├── container.py              # Monta as peças para o CLI e o painel
│   ├── ports.py                  # Contratos: Miner, HttpClient, LeadRepository, LlmClient
│   ├── profile.py                # Carrega o perfil (data/profile.json ou o exemplo)
│   ├── domain/
│   │   ├── lead.py               # Lead, LeadStatus, Region (define idioma de mensagem e CV)
│   │   ├── resume.py             # CV-mestre, CV adaptado e checagem de fidelidade
│   │   └── skills.py             # Taxonomia de competências e similaridade
│   ├── services/
│   │   ├── mining.py             # Roda as fontes, isola falhas, deduplica e salva
│   │   ├── outreach.py           # Monta a mensagem certa e registra no funil
│   │   ├── tailoring.py          # Compara CV x vaga sem IA (comando tailor)
│   │   ├── application.py        # Pacote de candidatura com IA (CV, carta, PDF, respostas)
│   │   ├── apply_flow.py         # Abre o formulário preenchido
│   │   ├── resume_import.py      # PDF/DOCX -> CV-mestre
│   │   ├── ranking.py            # Ordem da fila
│   │   └── funnel.py             # Métricas por fonte
│   ├── adapters/
│   │   ├── llm_anthropic.py      # API do Claude (JSON estruturado via tool use)
│   │   ├── autofill/             # Leitura e preenchimento de formulários (Playwright opcional)
│   │   ├── miners/               # github, hacker_news, greenhouse, lever, ashby, simplify
│   │   ├── storage/sqlite.py     # Repositório + migração automática de schema
│   │   ├── senders.py            # SMTP, Gmail Web e rascunho .eml
│   │   ├── http.py               # urllib com TLS verificado
│   │   ├── jd_fetcher.py         # Descrição da vaga (Greenhouse, Lever, Ashby, JSON-LD)
│   │   ├── resume_files.py       # Leitura de PDF/DOCX para importar o CV
│   │   ├── resume_render.py      # CV adaptado em HTML A4
│   │   └── pdf_chrome.py         # HTML -> PDF com Chrome/Chromium headless
│   ├── web/                      # Painel local (server.py + static/index.html)
│   └── core/                     # config (caminhos, .env, cores) e fábrica do repositório
├── tests/                        # unittest + respostas gravadas, IA falsa e formulários de teste
├── docs/arquitetura/             # Decisões e roadmap
└── data/                         # (fora do git) banco, perfil, CV-mestre, candidaturas, backups
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
| `ANTHROPIC_API_KEY` | Chave da API do Claude (preparar candidaturas e importar o CV) |
| `PROSPECTOR_MODEL` | Trocar o modelo da IA sem editar o perfil |

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

Os testes usam respostas gravadas das fontes (`tests/fixtures/`), uma IA falsa e um SMTP falso. Nenhum teste acessa a internet, gasta créditos da IA, envia e-mail ou toca no seu `prospector.db`. Os testes de preenchimento com navegador só rodam quando o Playwright e um Chromium estão instalados (`python3 -m playwright install chromium`).

## 🤖 Apoio de IA

A pasta `.claude/` contém os agentes, regras e comandos do [ECC](https://github.com/affaan-m/ECC) (por exemplo, `architect`, `planner` e `python-reviewer`), usados no planejamento da v3.

---

## 📄 Licença

Distribuído sob a licença MIT. Desenvolvido para uso pessoal e profissional em engenharia de software.
