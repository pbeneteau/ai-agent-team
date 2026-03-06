# AI Agent Team Orchestrator

Orchestrateur d'équipe d'agents IA pour startups. Un agent Associé top-level (**Alex**) orchestre des équipes spécialisées via un chat conversationnel. Les agents ont chacun leur workspace isolé, apprennent leur domaine, et s'auto-enrichissent pendant les tâches.

## Stack

- **Backend** : Python / FastAPI + WebSocket
- **LLM** : Anthropic Claude (Sonnet pour les spécialistes, Opus pour Alex et les leads)
- **Orchestration** : CrewAI v1
- **Mémoire** : ChromaDB (vecteurs RAG) + fichiers Markdown (skills par agent)
- **Frontend** : Next.js + Tailwind + shadcn/ui + react-flow
- **Infra locale** : Redis

## Démarrage rapide

### Prérequis

- Python 3.12+
- Node.js 20+
- Redis (`brew install redis`)
- Une clé API Anthropic

### Configuration

```bash
cp backend/.env.example backend/.env
# Éditez backend/.env et ajoutez vos clés (voir Variables d'environnement)
```

### Lancement

```bash
chmod +x start.sh
./start.sh
```

Ou manuellement :

```bash
# Terminal 1 — Redis
redis-server

# Terminal 2 — Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 3 — Frontend
cd frontend
npm install
npm run dev
```

## URLs

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

## Architecture

```
ai-agent-team/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app
│   │   ├── config.py                # Settings (Pydantic)
│   │   ├── api/routes/
│   │   │   ├── chat.py              # WebSocket chat + team-builder WS
│   │   │   ├── agents.py            # CRUD agents + workspace + knowledge + research
│   │   │   ├── teams.py             # CRUD équipes + organigramme
│   │   │   ├── tasks.py             # Suivi des tâches
│   │   │   ├── documents.py         # Upload documents + brief-agents
│   │   │   └── usage.py             # Suivi consommation tokens/coût
│   │   ├── core/
│   │   │   ├── agent_factory.py     # Création dynamique d'agents + workspaces
│   │   │   ├── team_builder.py      # Session conversationnelle de création d'équipe
│   │   │   ├── learning.py          # Phase d'apprentissage, rebriefing, recherche web
│   │   │   ├── orchestrator.py      # Exécution CrewAI avec self-augmentation
│   │   │   ├── workspace.py         # Gestion workspaces isolés par agent
│   │   │   ├── document_store.py    # Upload, parsing, RAG ChromaDB
│   │   │   └── usage_tracker.py     # Suivi tokens Anthropic
│   │   ├── agents/
│   │   │   ├── associate.py         # Alex — chat, RAG documents, actions JSON
│   │   │   ├── base_agent.py        # Builder CrewAI agent
│   │   │   └── specialists/         # Templates de rôles (dev, marketing, legal…)
│   │   ├── memory/                  # ChromaDB wrapper + skills store + project context
│   │   └── tools/                   # Outils CrewAI (web search, skill_note, git, shell…)
│   └── data/
│       ├── workspaces/{agent_id}/   # Workspace isolé par agent
│       │   ├── skills/              # core_skills.md, project_context.md, notes…
│       │   ├── downloads/           # Fichiers/URLs partagés avec l'agent
│       │   ├── repos/               # Repos git clonés
│       │   ├── output/              # Livrables des tâches
│       │   └── tmp/                 # Espace temporaire
│       ├── documents/               # Documents uploadés par l'utilisateur
│       ├── chromadb/                # Embeddings vecteurs
│       ├── agents.json              # Définitions agents persistées
│       └── teams.json               # Définitions équipes persistées
└── frontend/
    ├── app/
    │   ├── page.tsx                 # Dashboard
    │   ├── chat/                    # Chat avec Alex (mode création d'équipe inclus)
    │   ├── team/                    # Équipe — organigramme + workspace par agent
    │   └── tasks/                   # Suivi des tâches
    └── components/
        ├── chat/ChatPanel.tsx       # Chat, documents @mention, plan mode
        ├── agents/WorkspacePanel.tsx # Skills, Knowledge (upload/URL/recherche web)
        └── organigramme/OrgChart.tsx # Arbre interactif cliquable
```

## Flux principaux

### 1. Construction d'équipe

La création d'équipe se fait **entièrement dans le chat avec Alex** — pas de page dédiée.

1. L'utilisateur décrit son projet et ses besoins à Alex
2. Alex conçoit la structure d'équipe (rôles, spécialisations, niveaux de modèle)
3. Alex génère l'action `create_team_direct` → l'équipe est créée immédiatement
4. Chaque agent passe par une **phase d'apprentissage** automatique :
   - Claude génère `core_skills.md` (expertise métier) et `project_context.md` (contexte projet)
   - Chaque fichier est écrit dans le workspace isolé de l'agent
5. L'organigramme s'affiche dans **Mon Équipe**

### 2. Enrichissement du knowledge des agents

Trois façons d'enrichir le contexte d'un agent :

**a) Document/URL global** (panel Documents dans le chat)
- Uploader un PDF, DOCX, TXT… → indexé en ChromaDB pour le RAG d'Alex
- Cliquer 📖 → met à jour le `project_context.md` de **tous** les agents

**b) Partage ciblé par agent** (onglet Knowledge dans le workspace d'un agent)
- Upload fichier ou coller une URL → sauvegardé dans `workspace/downloads/`
- Génère une mise à jour ciblée du `project_context.md` de cet agent uniquement

**c) Recherche web autonome** (onglet Knowledge → Recherche web)
- Saisir un sujet → l'agent effectue 3–5 recherches Google (via Serper)
- Synthèse sauvegardée dans `workspace/skills/research_*.md`
- Nécessite `SERPER_API_KEY`

### 3. Exécution de tâche avec self-augmentation

1. L'utilisateur soumet une tâche à Alex (chat ou `/tasks`)
2. Alex délègue à la bonne équipe via l'action `create_task`
3. CrewAI orchestre les agents avec leurs skills comme backstory
4. **Si** l'agent fait une recherche externe et trouve quelque chose de nouveau → `skill_note` ajoute une note datée sans écraser les skills existants
5. Au-delà de 5 000 chars, consolidation automatique via Claude (déduplication)
6. Les résultats remontent en temps réel via WebSocket

### 4. Plan mode et formulaires dynamiques

Quand Alex (ou le team builder) a besoin d'infos structurées, il peut retourner un bloc `gather_info` :

```json
{"action": "gather_info", "title": "...", "fields": [...]}
```

Le frontend affiche un **formulaire dynamique** inline (texte, textarea, sélecteur). Les réponses sont renvoyées à Alex comme message structuré.

## Variables d'environnement

| Variable | Description | Requis |
|---|---|---|
| `ANTHROPIC_API_KEY` | Clé API Anthropic | ✅ |
| `REDIS_URL` | URL Redis | `redis://localhost:6379` |
| `CLAUDE_MODEL_SONNET` | Modèle spécialistes | `claude-sonnet-4-5` |
| `CLAUDE_MODEL_OPUS` | Modèle Alex + leads | `claude-opus-4-5` |
| `CHROMA_PERSIST_DIR` | Dossier ChromaDB | `./data/chromadb` |
| `SERPER_API_KEY` | Recherche Google pour agents (serper.dev — gratuit 2500/mois) | Optionnel |
| `GITHUB_TOKEN` | GitHub API search (clone SSH fonctionne sans) | Optionnel |

## Vérification rapide

```bash
# Backend up ?
curl http://localhost:8000/health

# Agents et équipes
curl http://localhost:8000/api/agents/
curl http://localhost:8000/api/teams/

# Web search active ?
curl http://localhost:8000/api/agents/capabilities

# Upload d'un document
curl -F "file=@README.md" http://localhost:8000/api/documents/

# Brief tous les agents avec un doc
curl -X POST http://localhost:8000/api/documents/{doc_id}/brief-agents
```
