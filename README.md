# 🎯 Prospector de Vagas

> **CLI de Mineração Técnica & Funil de Prospecção Ágil para Engenharia de Software**  
> Automatização da rotina estratégica de prospecção ativa, mineração algorítmica de vagas ocultas e contato direto com lideranças técnicas (CTOs, Tech Leads e Engineering Managers).

---

## 💡 Por que este projeto existe?

O ecossistema contemporâneo de recrutamento impõe barreiras assimétricas para profissionais de tecnologia. Sistemas ATS convencionais (como **Gupy**, **Workday** e **Taleo**) desviam o foco do mérito técnico para triagens automatizadas opacas, onde as taxas de conversão final para entrevistas frequentemente ficam abaixo de **2%**.

O **Prospector de Vagas** reverte essa dinâmica através de:
1. **Foco em canais de baixa fricção operacional:** Mineração direta no **GitHub Issues** (`backend-br`, `datascience-br`) e no fórum mensal do **Hacker News** (*Ask HN: Who is hiring?*).
2. **Filtro Anti-Gupy / Anti-Workday:** Descarte automatizado de links para portais burocráticos de triagem lenta.
3. **Extração de Contatos Diretos:** Identificação imediata de e-mails de engenharia e links de ATS ágeis (Ashby, Greenhouse, Lever, Workable).
4. **Motor de Mensagens de Alto Impacto (< 400 caracteres):** Geração automática de abordagens técnicas cirúrgicas personalizadas para o perfil de **Software Engineer (Backend & Data Platforms)**.
5. **Funil & Gestão de Follow-up (D+5):** Registro local em SQLite com alertas de recontato (onde ocorrem de 40% a 55% das respostas positivas).

---

## ⚙️ Arquitetura e Funcionalidades

```
                             ┌─────────────────────────────────────────────────────────┐
                             │                     PROSPECTOR CLI                      │
                             └───────────────────────────┬─────────────────────────────┘
                                                         │
             ┌───────────────────────────────────────────┼───────────────────────────────────────────┐
             ▼                                           ▼                                           ▼
  [1. MINERAÇÃO AUTOMATIZADA]                   [2. MOTOR DE COPYWRITING]                  [3. FUNIL & CRM LOCAL]
 • GitHub Issues (backend-br)                  • Scripts de Abordagem em <400 chars       • Banco local SQLite (prospector.db)
 • Hacker News (Ask HN: Who is Hiring?)        • Modelo 1: Tech Lead / EM (Nacional)      • Gestão de status de candidaturas
 • Filtro Anti-Gupy / Anti-Workday             • Modelo 2: CTO / Eng Lead (Global - EN)   • Alertas de Follow-up após 5 dias (D+5)
 • Extração de e-mails e ATS rápidos           • Modelo 3: Recrutador Técnico             • Dorks X-Ray para Google & LinkedIn
```

---

## 🚀 Guia de Uso

O script foi desenvolvido em **Python puro (3.8+)**, sem necessidade de instalar dependências externas (`pip`).

### 1. Minerar Vagas Abertas

Varre os repositórios do GitHub e o tópico ativo do mês no Hacker News:

```bash
# Mineração completa (GitHub + Hacker News)
python3 prospector.py mine

# Minerar apenas GitHub Issues
python3 prospector.py mine --source github

# Minerar apenas Hacker News (thread do mês atual)
python3 prospector.py mine --source hn

# Minerar incluindo todos os níveis de senioridade
python3 prospector.py mine --all-levels
```

As vagas mineradas são salvas automaticamente no banco de dados local `prospector.db`.

---

### 2. Inspecionar Detalhes e Gerar Mensagem de Abordagem

Para visualizar uma vaga específica do funil e obter a mensagem pronta para envio:

```bash
python3 prospector.py show <ID>
```

Exemplo para uma vaga internacional minerada:
```bash
python3 prospector.py show 22
```

Saída:
```text
================== DETALHES DO LEAD #22 ==================
🏢 Empresa: Biobase
📌 Título: Biobase - Technical Product Engineer (Early Career)
🌐 Origem: Hacker News (Ask HN: Who is hiring?)
📊 Status: minerado
🔗 URL: https://news.ycombinator.com/item?id=49528044
📬 Contato: jobs@biobase.ai

--- Mensagem Sugerida (Modelo 2) ---
Hi Sarah, I follow Biobase's work and your focus on scaling backend services.
Graduating in CS from UFCG, I engineered high-throughput telemetry pipelines with Python, HDF5, and SDR on the BINGO Telescope.
My background emphasizes Linux internals, algorithm optimization, and Clean Architecture.
Open to a brief 5-min chat on how my profile fits your engineering needs?
(370 chars - Ótimo: <400)
```

---

### 3. Gerador Avulso de Mensagens de Prospecção

Se você encontrou um gestor ou recrutador avulso no LinkedIn, gere a mensagem instantaneamente:

```bash
# Modelo 1: Tech Lead / Engineering Manager (Brasil - Português)
python3 prospector.py msg 1 --empresa "Nubank" --nome "Carlos"

# Modelo 2: CTO / Engineering Lead (Internacional Remoto - Inglês)
python3 prospector.py msg 2 --empresa "MixRank" --nome "Alex"

# Modelo 3: Recrutador Técnico / Talent Acquisition
python3 prospector.py msg 3 --empresa "PicPay" --nome "Mariana" --vaga "Software Engineer (Backend)"

# Follow-up Cordial (D+5)
python3 prospector.py msg followup_pt --empresa "Nubank" --nome "Carlos"
python3 prospector.py msg followup_en --empresa "MixRank" --nome "Alex"
```

---

### 4. Gerenciar o Funil de Candidaturas

```bash
# Listar todas as oportunidades e seus status
python3 prospector.py list

# Atualizar o status de um lead após o envio da mensagem
python3 prospector.py update <ID> mensagem_enviada

# Status disponíveis:
# minerado | conexao_enviada | mensagem_enviada | aguardando_followup | resposta | entrevista | descartada
```

---

### 5. Monitorar Alertas de Follow-up (D+5)

Segundo métricas de prospecção direta, a ausência de um recontato após 5 dias úteis descarta mais de metade do potencial de resposta:

```bash
python3 prospector.py followups
```
*Se houver contatos feitos há mais de 5 dias úteis sem retorno, o comando lista o lead e o texto exato de follow-up pronto para copiar e colar.*

---

### 6. Buscas Booleanas e Google X-Ray em 1 Clique

Gera URLs parametrizadas com operadores lógicos avançados para abrir diretamente no navegador:

```bash
python3 prospector.py dorks
```

Inclui consultas formatadas para:
* **Google X-Ray em ATS Ágeis:** `(site:jobs.ashbyhq.com OR site:boards.greenhouse.io OR site:jobs.lever.co)`
* **LinkedIn Feed (Orgânico - Brasil):** Busca posts de gestores que pedem CV/DM sem passar por portais lentos.
* **LinkedIn Feed (Internacional):** Vagas remotas em Python na América Latina/Global.

---

## 🛠️ Tecnologias Utilizadas

* **Python 3.8+** (Standard Library: `urllib`, `sqlite3`, `re`, `argparse`, `json`, `html`, `ssl`)
* **SQLite 3** (Armazenamento local e gestão do funil)
* **GitHub REST API** & **Hacker News Algolia Search API**

---

## 📄 Licença

Distribuído sob a licença MIT. Desenvolvido para uso pessoal e profissional em engenharia de software.
