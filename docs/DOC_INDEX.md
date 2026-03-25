# DOC_INDEX — Index de référence du backend

> Ce document est le socle de toute la documentation produit. Il inventorie exhaustivement les entités, endpoints, événements, enums et contraintes du système. Les 6 documents de documentation détaillés (DATA_MODELS, API_REFERENCE, WEBSOCKET_PROTOCOL, USER_FLOWS, ERRORS_AND_LIMITS, FRONTEND_GUIDELINES) s'appuieront sur cet index.

---

## 1. Executive Summary

**AI Agent Team** est un orchestrateur d'équipes d'agents IA. Il permet à un utilisateur (product manager, fondateur, chef de projet) de :

- **Constituer des équipes** d'agents spécialisés (développeurs, marketeurs, analystes, designers) via un chat conversationnel ou des templates prédéfinis.
- **Décrire le contexte projet** (brief) pour que chaque agent adapte son comportement et ses connaissances au domaine métier.
- **Créer et exécuter des tâches** décomposées automatiquement en sous-tâches (nœuds) assignées aux agents, avec exécution parallèle en vagues et gestion des dépendances.
- **Enrichir les connaissances** des agents via des documents, des recherches web autonomes, et un système d'apprentissage continu (skills, réflexions, work learnings).
- **Connecter des outils externes** : serveurs MCP (Model Context Protocol) et fournisseurs Git (GitHub, GitLab) pour que les agents interagissent avec l'écosystème technique.
- **Suivre les coûts** (tokens, USD) par modèle et par jour.

L'interface frontend communique avec le backend via une API REST et des WebSockets pour le streaming temps réel.

---

## 2. Architecture haut niveau

```
┌─────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (Next.js)                         │
│                                                                     │
│   Chat UI ◄──── WS /api/chat/ws ────► Associate (Alex)             │
│   Task Planning ◄── WS /api/task-planning/ws ──► Task Planner      │
│   REST calls ◄──── HTTP /api/* ────► API Routes                     │
└────────────┬──────────────────────────────────────┬─────────────────┘
             │                                      │
             ▼                                      ▼
┌────────────────────────┐          ┌──────────────────────────────┐
│     API Layer          │          │     WebSocket Manager         │
│                        │          │                              │
│  agents, tasks, teams  │          │  ConnectionManager           │
│  chat, documents       │          │  broadcast() / send()        │
│  projects, labels      │          │                              │
│  mcp, git-providers    │          └──────────┬───────────────────┘
│  usage, task-comments  │                     │
│  task-relations        │                     │
└────────┬───────────────┘                     │
         │                                     │
         ▼                                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                        CORE SERVICES                              │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐   │
│  │ Orchestrator  │  │ AgentFactory │  │ UniversalPlanSession  │   │
│  │              │  │              │  │                       │   │
│  │ Plan → Waves │  │ Create/CRUD  │  │ Discovery → Confirm   │   │
│  │ Execute DAG  │  │ Templates    │  │ → Execute             │   │
│  └──────┬───────┘  └──────────────┘  └───────────────────────┘   │
│         │                                                         │
│  ┌──────▼───────┐  ┌──────────────┐  ┌───────────────────────┐   │
│  │ Anthropic     │  │ Learning     │  │ Knowledge Audit       │   │
│  │ AgentRunner   │  │              │  │                       │   │
│  │              │  │ Briefing     │  │ Readiness scoring     │   │
│  │ Tool loop    │  │ Reflection   │  │ Recommendations       │   │
│  │ Streaming    │  │ Work Learn.  │  │ Gap analysis          │   │
│  └──────────────┘  └──────────────┘  └───────────────────────┘   │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐   │
│  │ Workspace    │  │ Document     │  │ Stores (JSON-backed)  │   │
│  │ Manager      │  │ Store        │  │                       │   │
│  │              │  │              │  │ Projects, Labels      │   │
│  │ Skills, I/O  │  │ Upload, RAG  │  │ Comments, Relations   │   │
│  │ Repos, Tmp   │  │ ChromaDB     │  │ Plan Reviews, Usage   │   │
│  └──────────────┘  └──────────────┘  └───────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
┌─────────────────┐    ┌────────────────────┐
│  External Tools  │    │  Persistence       │
│                 │    │                    │
│  MCP Servers    │    │  data/*.json       │
│  Git Providers  │    │  data/workspaces/  │
│  Web Search     │    │  data/documents/   │
│  GitHub API     │    │  ChromaDB          │
└─────────────────┘    └────────────────────┘
```

---

## 3. Glossaire complet

| Terme | Définition |
|-------|-----------|
| **Agent** | Entité IA autonome avec un rôle, une spécialisation, des outils et un workspace isolé. Peut exécuter des tâches, apprendre, et interagir avec des services externes. |
| **Associate (Alex)** | Agent singleton qui sert d'interface conversationnelle principale. Interprète les demandes utilisateur et orchestre les plans (création de tâches ou d'équipes). |
| **Team** | Regroupement d'agents sous un domaine commun (technology, marketing, etc.), avec optionnellement un lead agent. |
| **Team Lead** | Agent ayant le rôle `team_lead` dans une équipe. Compile les résultats des spécialistes lors d'exécutions multi-nœuds. |
| **Specialist** | Agent avec le rôle `specialist`, exécutant des sous-tâches spécifiques dans un plan de dépendances. |
| **Task** | Unité de travail assignée à une équipe/un agent. Suit un cycle de vie (triage → backlog → queued → executing → done). |
| **Node (TaskExecutionNode)** | Sous-tâche atomique dans le plan d'exécution d'une tâche. Assigné à un seul agent, peut dépendre d'autres nœuds. |
| **Execution Plan** | Graphe orienté acyclique (DAG) de nœuds décrivant la décomposition et l'ordre d'exécution d'une tâche. |
| **Execution Wave** | Groupe de nœuds pouvant s'exécuter en parallèle (même rang topologique dans le DAG). |
| **Execution Mode** | Stratégie d'exécution : `auto` (le système décide), `standalone` (un seul nœud), `dependency_graph` (DAG explicite). |
| **Plan (UniversalPlan)** | Proposition structurée (création de tâche ou d'équipe) générée par l'Associate, soumise à confirmation utilisateur avant exécution. |
| **Plan Review** | Snapshot persisté d'un plan en cours de revue, permettant de reprendre une session interrompue. |
| **Workspace** | Répertoire isolé par agent (`data/workspaces/{agent_id}/`) contenant skills, repos clonés, fichiers de sortie et temporaires. |
| **Skill** | Document Markdown stocké dans le workspace d'un agent, représentant une connaissance acquise (brief projet, learnings, recherche, compétences consolidées). |
| **Core Skills** | Skills fondamentaux d'un agent, consolidés automatiquement lorsqu'ils dépassent un seuil de taille. |
| **Work Learnings** | Insights extraits automatiquement après l'exécution d'un nœud de tâche : bonnes pratiques, écueils, sources utilisées. |
| **Learning Phase** | Phase d'apprentissage initial d'un agent : briefing projet + génération de skills de base. |
| **Briefing / Rebriefing** | Injection du contexte projet dans les skills d'un agent. Le rebriefing met à jour les skills quand le brief change. |
| **Reflection** | Phase périodique où un agent consolide ses apprentissages et met à jour son profil de progression. |
| **Knowledge Readiness** | Score évaluant si un agent a suffisamment de connaissances pour travailler efficacement. Trois niveaux : sufficient, partial, insufficient. |
| **Knowledge Recommendation** | Action suggérée pour combler un manque de connaissance (fournir un document, lancer une recherche web, etc.). |
| **Deliverable** | Fichier produit par un agent dans `output/` de son workspace, consultable/téléchargeable via l'API. |
| **Project Brief (Project Context)** | Description structurée du projet : nom, description, domaine, objectif court terme, stack technique, audience cible, modèle économique, notes. |
| **Completeness Score** | Score 0-100 mesurant le remplissage du brief projet, pondéré par champ. |
| **Brief Fingerprint** | Hash SHA-256 du brief, utilisé pour détecter les changements et déclencher le rebriefing. |
| **Document** | Fichier uploadé par l'utilisateur (PDF, DOCX, TXT, MD, CSV, JSON, YAML), indexé dans ChromaDB pour la recherche sémantique. |
| **MCP Connection** | Connexion à un serveur MCP (Model Context Protocol) exposant des outils appelables par les agents. |
| **MCP Tool Binding** | Association entre un agent et un outil MCP spécifique, avec mode d'approbation (auto, confirm, blocked). |
| **Git Provider Connection** | Connexion à un fournisseur Git (GitHub/GitLab) avec token d'authentification. |
| **Git Binding** | Association entre un agent et un dépôt Git, avec permissions (lecture, push, ouverture de PR). |
| **Organigramme** | Vue hiérarchique arborescente de tous les agents et équipes. |
| **Label** | Étiquette colorée pour catégoriser les tâches (similaire aux labels GitHub/Linear). |
| **Project** | Conteneur organisationnel pour regrouper des tâches avec un identifiant séquentiel (PRJ-1, PRJ-2...). |
| **Task Relation** | Lien entre deux tâches : `blocks`, `related`, ou `duplicate`. |
| **Task Comment** | Message attaché à une tâche, pouvant provenir d'un humain, d'un agent, ou du système. |
| **Iteration** | Cycle d'exécution d'une tâche. Une tâche peut être itérée (feedback → ré-exécution) plusieurs fois. |
| **Sufficiency Check** | Évaluation par IA de la clarté et complétude d'une description de tâche avant exécution. |
| **Cost Estimation** | Estimation pré-exécution du coût en tokens et USD d'une tâche, basée sur le plan d'exécution. |
| **Usage Tracker** | Suivi cumulé des tokens consommés et coûts par modèle et par jour. |
| **Model Tier** | Niveau de modèle utilisé par un agent : `sonnet` (rapide/économique) ou `opus` (puissant/coûteux). |
| **Progression Level** | Niveau de maturité d'un agent : `apprenti`, `opérationnel`, `expert`. |
| **Structured JSON** | Mécanisme robuste d'extraction/génération de JSON structuré depuis les réponses LLM, avec réparation automatique. |

---

## 4. Inventaire des entités

### Entités principales

| Entité | Fichier source | Champs principaux | Relations |
|--------|---------------|-------------------|-----------|
| `AgentConfig` | `models/agent.py` | id, name, role, title, specialization, goal, backstory, team_id, parent_id, status, occupancy_status, occupancy_reason, current_task_id, current_node_id, busy_since, tools, model_tier, max_iter, max_tokens | → TeamConfig (team_id), → AgentGitBinding[], → AgentMcpToolBinding[] |
| `AgentResponse` | `models/agent.py` | id, name, role, title, specialization, goal, backstory, status, occupancy_status, occupancy_reason, current_task_id, current_node_id, team_id, parent_id, tools, model_tier, max_iter | → AgentGitBindingResolved[], → AgentMcpToolBindingResolved[] |
| `TeamConfig` | `models/team.py` | id, name, description, domain, lead_agent_id, scope_note, agent_ids | → AgentConfig[] (agent_ids) |
| `TeamResponse` | `models/team.py` | id, name, description, domain, lead_agent_id, scope_note, agents | → AgentResponse[] |
| `TaskResponse` | `models/task.py` | id, title, description, status, priority, assigned_team_id, assigned_agent_id, execution_mode, execution_plan, result, error, progress_log, deliverables, sources, assumptions, warnings, identifier, project_id, labels, creator_type, current_iteration, estimated/actual costs | → TaskExecutionPlan, → TaskProgressEntry[], → TaskDeliverable[] |
| `TaskExecutionPlan` | `models/task.py` | status, mode, compiler_agent_id, planning_notes, nodes | → TaskExecutionNode[] |
| `TaskExecutionNode` | `models/task.py` | id, title, description, node_type, status, assigned_agent_id, depends_on, result, error, quality_score, quality_flags, sources, assumptions, warnings | — |
| `ProjectResponse` | `models/project.py` | id, identifier, name, description, status, color, icon, lead_agent_id, default_team_id, labels, target_date, sort_order, total_estimated/actual_cost_usd | — |
| `LabelResponse` | `models/label.py` | id, name, color, group, description, created_at | — |
| `TaskRelationResponse` | `models/task_relation.py` | id, type, source_task_id, target_task_id, created_at | → TaskResponse (source), → TaskResponse (target) |
| `TaskCommentResponse` | `models/task_comment.py` | id, task_id, author_type, author_id, author_name, body, comment_type, node_id, iteration, resolved, created_at | → TaskResponse (task_id) |
| `TaskIterationResponse` | `models/task_iteration.py` | id, task_id, iteration_number, trigger, feedback, started_at, completed_at, input_tokens, output_tokens, cost_usd, result_summary | → TaskResponse (task_id) |

### Entités de connexion externe

| Entité | Fichier source | Champs principaux | Relations |
|--------|---------------|-------------------|-----------|
| `McpConnectionConfig` | `models/mcp.py` | id, name, transport, endpoint_url, enabled, auth_header_name, auth_token, notes, tool_allowlist, discovered_tools, status, total_calls, total_failures | → McpToolDescriptor[] |
| `McpConnectionResponse` | `models/mcp.py` | id, name, transport, endpoint_url, enabled, has_auth_token, notes, discovered_tools, status | → McpToolDescriptor[] |
| `McpToolDescriptor` | `models/mcp.py` | name, description, input_schema, read_only, capability_class | — |
| `AgentMcpToolBinding` | `models/mcp.py` | connection_id, tool_name, enabled, alias, approval_mode | → McpConnectionConfig |
| `GitProviderConnectionConfig` | `models/git_providers.py` | id, provider, name, base_url, auth_mode, auth_token, enabled, discovered_repos, status, total_repo_actions, clone/push/pr_actions | → GitRemoteRepo[] |
| `GitProviderConnectionResponse` | `models/git_providers.py` | id, provider, name, base_url, has_auth_token, enabled, discovered_repos, status | → GitRemoteRepo[] |
| `GitRemoteRepo` | `models/git_providers.py` | full_name, owner, name, web_url, clone_url, default_branch | — |
| `AgentGitBinding` | `models/git_providers.py` | connection_id, repo_full_name, enabled, can_push, can_open_pr, branch_prefix | → GitProviderConnectionConfig |

### Entités de planification

| Entité | Fichier source | Champs principaux | Relations |
|--------|---------------|-------------------|-----------|
| `PlanSessionState` | `models/plan.py` | session_id, kind, state, form, draft, last_error | → PlanForm, → PlanDraft |
| `TaskPlanDraft` | `models/plan.py` | id, session_id, kind, state, revision, title, task_title, task_description, priority, execution_mode, assigned_team_id, assigned_agent_id, context_document_ids, validation_issues | → PlanValidationIssue[] |
| `TeamPlanDraft` | `models/plan.py` | id, session_id, kind, state, revision, title, project, teams | → TeamPlanProjectDraft, → TeamPlanTeamDraft[] |
| `TeamPlanTeamDraft` | `models/plan.py` | name, description, domain, agents | → TeamPlanAgentDraft[] |
| `TeamPlanAgentDraft` | `models/plan.py` | name, title, specialization, goal, backstory, is_lead, model_tier | — |
| `PlanReviewSnapshot` | `models/plan.py` | id, session_id, workflow, kind, state, draft, updated_at, error, session | → PlanDraft, → PlanSessionState |
| `PlanForm` | `models/plan.py` | title, description, fields | → PlanField[] |
| `PlanField` | `models/plan.py` | id, label, type, placeholder, options, required | — |

### Entités de connaissance

| Entité | Fichier source | Champs principaux | Relations |
|--------|---------------|-------------------|-----------|
| `AgentKnowledgeReadiness` | `models/knowledge.py` | agent_id, agent_name, readiness_level, readiness_score, summary, missing_knowledge_summary, recommendations, generation_source, context_fingerprint | → KnowledgeRecommendation[] |
| `GlobalKnowledgeReadiness` | `models/knowledge.py` | generated_at, fingerprint, total/insufficient/partial/sufficient_agents, agents, shared_gaps | → AgentKnowledgeReadiness[], → GlobalKnowledgeGap[] |
| `KnowledgeRecommendation` | `models/knowledge.py` | id, agent_id, title, summary, reason, priority, knowledge_type, action_type, can_be_found_on_web, recommended_source, suggested_topic, status, evidence | → KnowledgeRecommendationEvidence[] |
| `AgentLearningProfile` | `models/agent.py` | agent_id, completed_task_nodes, avg_quality_score, last_5_learnings, readiness_score, progression_level, last_reflection_at, episode_count | — |

### Entités de brief projet

| Entité | Fichier source | Champs principaux | Relations |
|--------|---------------|-------------------|-----------|
| `ProjectBriefSnapshot` | `models/brief.py` | revision, status, updated_at, published_at, brief_fingerprint, completeness_score, name, description, domain, short_term_goal, tech_stack, target_audience, business_model, notes | — |
| `ProjectBriefStateResponse` | `models/brief.py` | draft, published, active, has_unpublished_changes | → ProjectBriefSnapshot (×3) |

### Entités de recommandation d'équipe

| Entité | Fichier source | Champs principaux | Relations |
|--------|---------------|-------------------|-----------|
| `TeamRecommendation` | `models/team_recommendations.py` | id, name, description, domain, reason, urgency, score, agents | → RecommendedAgentSpec[] |
| `TeamChangeRecommendation` | `models/team_recommendations.py` | id, team_id, team_name, change_type, urgency, score, reason, suggested_agent, scope_update | → RecommendedAgentSpec |
| `RecommendationResponse` | `models/team_recommendations.py` | new_teams, team_changes, generation_source, generation_channel | → TeamRecommendation[], → TeamChangeRecommendation[] |

### Entités de chat

| Entité | Fichier source | Champs principaux | Relations |
|--------|---------------|-------------------|-----------|
| `WSMessage` | `models/chat.py` | type, data, timestamp | — |
| `ChatMessageIn` | `models/chat.py` | content, session_id | — |
| `ChatMessageOut` | `models/chat.py` | role, content, timestamp, metadata | — |

### Actions de l'Associate

| Entité | Fichier source | Champs principaux | Relations |
|--------|---------------|-------------------|-----------|
| `StartTeamBuilderAction` | `models/chat_actions.py` | action="start_team_builder" | — |
| `GatherInfoAction` | `models/chat_actions.py` | action="gather_info", title, description, fields | → PlanField[] |
| `TaskPlanProposalAction` | `models/chat_actions.py` | action="plan_task", title, description, priority, execution_mode, team_id, agent_id, context_document_ids | — |
| `TeamPlanProposalAction` | `models/chat_actions.py` | action="plan_team", title, project, teams | → TeamPlanProjectDraft, → TeamPlanTeamDraft[] |
| `TriggerLearningAction` | `models/chat_actions.py` | action="trigger_learning", agent_ids, team_ids, reason | — |

---

## 5. Inventaire des endpoints

### Agents — `/api/agents`

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/` | Lister tous les agents |
| GET | `/capabilities` | Obtenir les capacités optionnelles disponibles (web search, github, model override, mcp, git) |
| GET | `/workspaces/all` | Lister tous les workspaces agents avec usage disque |
| GET | `/knowledge-readiness` | Résumé global de préparation des connaissances |
| GET | `/readiness/global` | Résumé global de préparation (alias) |
| GET | `/{agent_id}` | Détail d'un agent |
| GET | `/{agent_id}/git-bindings` | Lister les bindings Git d'un agent |
| PUT | `/{agent_id}/git-bindings` | Mettre à jour les bindings Git d'un agent |
| GET | `/{agent_id}/mcp-tools` | Lister les bindings MCP d'un agent |
| PUT | `/{agent_id}/mcp-tools` | Mettre à jour les bindings MCP d'un agent |
| GET | `/{agent_id}/knowledge-recommendations` | Recommandations de connaissances pour un agent |
| POST | `/{agent_id}/knowledge-recommendations/{rec_id}/dismiss` | Rejeter une recommandation |
| POST | `/{agent_id}/knowledge-recommendations/{rec_id}/apply` | Appliquer une recommandation auto-exécutable |
| GET | `/{agent_id}/workspace` | Contenu du workspace d'un agent |
| GET | `/{agent_id}/workspace/browse` | Naviguer dans un sous-répertoire du workspace |
| GET | `/{agent_id}/workspace/read` | Lire un fichier texte du workspace |
| PATCH | `/{agent_id}/model` | Changer le tier de modèle d'un agent (sonnet/opus) |
| GET | `/{agent_id}/skills` | Lister les skills d'un agent |
| GET | `/{agent_id}/skills/{skill_name}` | Lire un skill spécifique |
| PUT | `/{agent_id}/skills/{skill_name}` | Écrire/mettre à jour un skill |
| DELETE | `/{agent_id}/skills/{skill_name}` | Supprimer un skill |
| POST | `/{agent_id}/knowledge` | Partager un document/URL avec un agent |
| POST | `/{agent_id}/research` | Lancer une recherche web autonome |
| POST | `/{agent_id}/reflect` | Déclencher une réflexion périodique |
| GET | `/{agent_id}/learning-profile` | Profil d'apprentissage de l'agent |
| DELETE | `/{agent_id}` | Supprimer un agent |

### Tasks — `/api/tasks`

| Méthode | Path | Description |
|---------|------|-------------|
| POST | `/sufficiency-check` | Vérifier si une description de tâche est suffisante |
| GET | `/` | Lister toutes les tâches |
| GET | `/execution-wave-suggestion` | Suggestion de vagues d'exécution parallèle pour les tâches en file |
| GET | `/{task_id}` | Détail d'une tâche |
| POST | `/` | Créer une tâche |
| PATCH | `/{task_id}/status` | Transitionner le statut d'une tâche |
| PATCH | `/{task_id}` | Modifier les champs d'une tâche |
| POST | `/{task_id}/execute` | Lancer l'exécution d'une tâche |
| POST | `/{task_id}/iterate` | Fournir un feedback pour itération |
| POST | `/{task_id}/provide-input` | Fournir une entrée à une tâche en attente |
| DELETE | `/{task_id}` | Supprimer une tâche |
| GET | `/{task_id}/deliverables` | Lister les livrables d'une tâche |
| GET | `/{task_id}/deliverables/read` | Lire le contenu d'un livrable |
| GET | `/{task_id}/deliverables/download` | Télécharger un livrable |
| POST | `/{task_id}/nodes/{node_id}/rerun` | Relancer un nœud spécifique |

### Task Comments — `/api/tasks`

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/{task_id}/comments/` | Lister les commentaires d'une tâche |
| POST | `/{task_id}/comments/` | Ajouter un commentaire à une tâche |

### Task Relations — `/api/tasks`

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/{task_id}/relations/` | Lister les relations d'une tâche |
| POST | `/{task_id}/relations/` | Créer une relation entre tâches |
| DELETE | `/{task_id}/relations/{relation_id}` | Supprimer une relation |

### Teams — `/api/teams`

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/` | Lister toutes les équipes |
| GET | `/organigramme` | Organigramme hiérarchique des agents |
| GET | `/project-context` | État du brief projet (draft + published) |
| PUT | `/project-context/draft` | Sauvegarder un brouillon de brief projet |
| GET | `/recommendations` | Recommandations d'équipes (LLM ou heuristique) |
| POST | `/project-context/publish` | Publier le brief et déclencher le rebriefing |
| PUT | `/project-context` | Alias rétro-compatible de publish |
| POST | `/from-template` | Créer une équipe depuis un template |
| POST | `/custom` | Créer une équipe personnalisée |
| POST | `/{team_id}/agents` | Ajouter un agent à une équipe |
| PATCH | `/{team_id}/scope` | Modifier le scope/description d'une équipe |
| POST | `/reset` | Réinitialiser toutes les équipes |
| GET | `/{team_id}` | Détail d'une équipe |
| DELETE | `/{team_id}` | Supprimer une équipe |

### Chat — `/api/chat`

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/reviews` | Lister les snapshots de plan reviews |
| GET | `/reviews/{review_id}` | Détail d'un plan review |
| WS | `/ws` | WebSocket principal de chat et planification |
| WS | `/team-builder/ws` | WebSocket team builder (déprécié) |

### Task Planning — `/api/task-planning`

| Méthode | Path | Description |
|---------|------|-------------|
| WS | `/ws` | WebSocket de création de tâche conversationnelle |

### Documents — `/api/documents`

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/` | Lister tous les documents uploadés |
| POST | `/` | Uploader un document |
| GET | `/{doc_id}/preview` | Prévisualiser un document (2400 chars max) |
| POST | `/{doc_id}/brief-agents` | Re-briefer tous les agents avec ce document |
| DELETE | `/{doc_id}` | Supprimer un document |

### Projects — `/api/projects`

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/` | Lister tous les projets |
| GET | `/{project_id}` | Détail d'un projet |
| POST | `/` | Créer un projet |
| PATCH | `/{project_id}` | Modifier un projet |
| DELETE | `/{project_id}` | Supprimer un projet |

### Labels — `/api/labels`

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/` | Lister tous les labels |
| POST | `/` | Créer un label |
| PATCH | `/{label_id}` | Modifier un label |
| DELETE | `/{label_id}` | Supprimer un label |

### MCP Connections — `/api/mcp`

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/connections` | Lister toutes les connexions MCP |
| POST | `/connections` | Créer une connexion MCP |
| PATCH | `/connections/{connection_id}` | Modifier une connexion MCP |
| DELETE | `/connections/{connection_id}` | Supprimer une connexion MCP |
| POST | `/connections/{connection_id}/test` | Tester une connexion MCP |
| POST | `/connections/{connection_id}/discover-tools` | Découvrir les outils disponibles |
| GET | `/connections/{connection_id}/tools` | Lister les outils disponibles |

### Git Providers — `/api/git-providers`

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/connections` | Lister toutes les connexions Git |
| POST | `/connections` | Créer une connexion Git |
| PATCH | `/connections/{connection_id}` | Modifier une connexion Git |
| DELETE | `/connections/{connection_id}` | Supprimer une connexion Git |
| POST | `/connections/{connection_id}/test` | Tester une connexion Git |
| GET | `/connections/{connection_id}/repos` | Lister les dépôts disponibles |
| POST | `/connections/{connection_id}/repos/refresh` | Rafraîchir la liste des dépôts |

### Usage — `/api/usage`

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/` | Obtenir les statistiques de consommation (tokens, coûts, historique journalier) |
| POST | `/reset` | Remettre à zéro les compteurs |

### Système

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/health` | Health check de l'application |

---

## 6. Inventaire des événements WebSocket

### Chat principal — `WS /api/chat/ws`

#### Client → Serveur

| Événement | Description |
|-----------|-------------|
| `chat` | Envoyer un message au chat. Données : `content`, `tagged_doc_ids?`, `workflow?` |
| `form_response` | Soumettre les valeurs d'un formulaire. Données : `values`, `form_title`, `workflow?` |
| `resume_plan_session` | Reprendre une session de plan sauvegardée. Données : `review_id` |
| `plan_confirm` | Confirmer et exécuter un plan proposé. Données : `session_id`, `draft_id` |
| `plan_cancel` | Annuler un plan en attente. Données : `session_id`, `draft_id` |
| `plan_revise` | Demander une révision du plan. Données : `session_id`, `draft_id`, `content?`, `clarification_values?` |
| `ping` | Keep-alive |

#### Serveur → Client (personal)

| Événement | Description |
|-----------|-------------|
| `stream_start` | Début d'une réponse streaming de l'assistant |
| `stream_chunk` | Fragment de texte streaming. Données : `data` (string) |
| `stream_end` | Fin du streaming, texte complet inclus. Données : `data` (string) |
| `plan_preview` | Proposition de plan à afficher. Données : `session_id`, `state`, `kind`, `draft`, `last_error?` |
| `plan_confirmation_required` | Demande de confirmation utilisateur. Données : `session_id`, `kind` |
| `plan_form` | Formulaire à afficher pour collecter des informations. Données : `session_id`, `form` |
| `plan_executing` | Exécution du plan démarrée. Données : `session_id`, `draft_id`, `kind`, `draft` |
| `plan_completed` | Plan exécuté avec succès. Données : `session_id`, `draft_id`, `kind`, `result` |
| `plan_failed` | Échec du plan. Données : `session_id`, `state`, `kind`, `draft`, `error` |
| `plan_cancelled` | Plan annulé. Données : `session_id`, `draft_id`, `state` |
| `plan_revising` | Révision du plan en cours. Données : `session_id`, `draft_id`, `state` |
| `navigate` | Instruction de navigation. Données : `to` (string, ex: "team-builder") |
| `error` | Erreur générique. Données : `data` (string) |
| `pong` | Réponse au ping |

### Task Planning — `WS /api/task-planning/ws`

#### Client → Serveur

| Événement | Description |
|-----------|-------------|
| `message` | Message utilisateur pour la planification. Données : `data.text` |
| `confirm` | Confirmer et créer la tâche depuis le brouillon. Données : titre, description, priorité, execution_mode |
| `reset` | Réinitialiser la conversation |
| `ping` | Keep-alive |

#### Serveur → Client (personal)

| Événement | Description |
|-----------|-------------|
| `stream_start` | Début du streaming |
| `stream_chunk` | Fragment de texte |
| `stream_end` | Fin du streaming |
| `task_draft` | Brouillon de tâche généré par l'IA. Données : `draft_id`, `title`, `description`, `priority`, `execution_mode` |
| `task_created` | Tâche créée avec succès. Données : TaskResponse complet |
| `reset_ack` | Confirmation du reset |
| `error` | Erreur |
| `pong` | Réponse au ping |

### Broadcasts — Émis à tous les clients connectés

#### Tâches

| Événement | Source | Description |
|-----------|--------|-------------|
| `task_update` | `routes/tasks.py`, `core/orchestrator.py` | État d'une tâche mis à jour. Données : TaskResponse complet |
| `task_created` | `core/universal_plan.py` | Nouvelle tâche créée via plan. Données : TaskResponse |
| `task_deleted` | `routes/tasks.py` | Tâche supprimée. Données : `{id}` |
| `task_input_needed` | `core/orchestrator.py` | Tâche en attente d'input utilisateur. Données : `{task_id, comment}` |

#### Nœuds d'exécution

| Événement | Source | Description |
|-----------|--------|-------------|
| `node_started` | `core/orchestrator.py` | Exécution d'un nœud démarrée. Données : `{task_id, node_id, node_title, status, agent_id, agent_name}` |
| `node_completed` | `core/orchestrator.py` | Nœud terminé. Données : idem + `quality_score` |
| `node_failed` | `core/orchestrator.py` | Nœud échoué. Données : idem |
| `node_stream_chunk` | `core/orchestrator.py` | Fragment de sortie temps réel d'un nœud. Données : `{node_id, chunk}` |

#### Agents

| Événement | Source | Description |
|-----------|--------|-------------|
| `agent_status` | `core/orchestrator.py`, `core/learning.py` | Statut/occupancy d'un agent modifié. Données : payload de statut complet |

#### Équipes & Plans

| Événement | Source | Description |
|-----------|--------|-------------|
| `team_created` | `core/universal_plan.py` | Équipe(s) créée(s) via plan. Données : `{created_teams, created_agents}` |

#### Apprentissage

| Événement | Source | Description |
|-----------|--------|-------------|
| `reflection_complete` | `core/learning.py` | Réflexion d'un agent terminée. Données : `{agent_id, agent_name}` |
| `briefing_start` | `core/learning.py` | Début du briefing document. Données : `{doc_id, filename, agent_count}` |
| `briefing_complete` | `core/learning.py` | Briefing terminé. Données : `{doc_id, filename, agents_updated}` ou `{team_id, agent_count, agents_updated}` |
| `research_complete` | `core/learning.py` | Recherche web terminée. Données : `{agent_id, topic, skill_name}` |

#### Projets

| Événement | Source | Description |
|-----------|--------|-------------|
| `project_created` | `routes/projects.py` | Nouveau projet. Données : ProjectResponse |
| `project_updated` | `routes/projects.py` | Projet modifié. Données : ProjectResponse |
| `project_deleted` | `routes/projects.py` | Projet supprimé. Données : `{id}` |

#### Labels

| Événement | Source | Description |
|-----------|--------|-------------|
| `label_created` | `routes/labels.py` | Nouveau label. Données : LabelResponse |
| `label_updated` | `routes/labels.py` | Label modifié. Données : LabelResponse |
| `label_deleted` | `routes/labels.py` | Label supprimé. Données : `{id}` |

#### Relations et commentaires

| Événement | Source | Description |
|-----------|--------|-------------|
| `task_relation_created` | `routes/task_relations.py` | Relation créée. Données : TaskRelationResponse |
| `task_relation_deleted` | `routes/task_relations.py` | Relation supprimée. Données : `{id, task_id}` |
| `task_comment` | `routes/task_comments.py` | Commentaire ajouté. Données : `{task_id, comment}` |

---

## 7. Inventaire des enums et constantes

### Statuts et cycles de vie

| Enum | Fichier | Valeurs |
|------|---------|---------|
| `AgentStatus` | `models/agent.py` | `pending`, `learning`, `ready`, `working`, `error` |
| `AgentOccupancyStatus` | `models/agent.py` | `idle`, `assigned`, `busy` |
| `AgentOccupancyReason` | `models/agent.py` | `task_execution`, `learning`, `research`, `rebriefing`, `project_briefing` |
| `AgentRole` | `models/agent.py` | `associate`, `team_lead`, `specialist` |
| `ModelTier` | `models/agent.py` | `sonnet`, `opus` |
| `TaskStatus` | `models/task.py` | `triage`, `backlog`, `queued`, `planning`, `executing`, `input_needed`, `review`, `done`, `partial`, `cancelled` |
| `TaskPriority` | `models/task.py` | `none`, `low`, `medium`, `high`, `urgent` |
| `TaskExecutionMode` | `models/task.py` | `auto`, `standalone`, `dependency_graph` |
| `TaskExecutionEligibility` | `models/task.py` | `eligible`, `clarification_required`, `ineligible` |
| `TaskPlanStatus` | `models/task.py` | `not_planned`, `planning`, `ready`, `running`, `completed`, `failed`, `partial` |
| `TaskNodeStatus` | `models/task.py` | `pending`, `blocked`, `ready`, `running`, `completed`, `failed`, `skipped` |
| `TaskNodeType` | `models/task.py` | `single_agent`, `specialist`, `lead_compile` |
| `CreatorType` | `models/task.py` | `human_form`, `human_chat`, `system` |
| `AssignmentStrategy` | `models/task.py` | `specific`, `team_auto`, `role_based` |
| `ProjectStatus` | `models/project.py` | `planned`, `active`, `paused`, `completed`, `cancelled` |

### Planification

| Enum | Fichier | Valeurs |
|------|---------|---------|
| `PlanKind` | `models/plan.py` | `task`, `team` |
| `PlanState` | `models/plan.py` | `discovery`, `draft`, `awaiting_confirmation`, `executing`, `completed`, `cancelled`, `failed` |
| `PlanReviewWorkflow` | `models/plan.py` | `plan`, `ask`, `design-team` |
| `PlanFieldType` | `models/plan.py` | `text`, `textarea`, `select` |
| `PlanValidationSeverity` | `models/plan.py` | `info`, `warning`, `blocking` |
| `PlanValidationStatus` | `models/plan.py` | `valid`, `needs_clarification`, `invalid` |
| `PlanExecutionEligibility` | `models/plan.py` | `eligible`, `clarification_required`, `ineligible` |

### Connexions externes

| Enum | Fichier | Valeurs |
|------|---------|---------|
| `McpTransport` | `models/mcp.py` | `streamable_http` |
| `McpConnectionStatus` | `models/mcp.py` | `unknown`, `healthy`, `degraded`, `unavailable` |
| `McpApprovalMode` | `models/mcp.py` | `auto`, `confirm_each_use`, `blocked` |
| `McpCapabilityClass` | `models/mcp.py` | `read_only`, `write`, `unknown` |
| `GitProvider` | `models/git_providers.py` | `github`, `gitlab` |
| `GitProviderConnectionStatus` | `models/git_providers.py` | `unknown`, `healthy`, `degraded`, `unavailable` |
| `GitProviderAuthMode` | `models/git_providers.py` | `personal_access_token` |
| `GitRepoPermission` | `models/git_providers.py` | `read`, `push`, `open_pr` |

### Connaissances

| Enum | Fichier | Valeurs |
|------|---------|---------|
| `KnowledgeReadinessLevel` | `models/knowledge.py` | `sufficient`, `partial`, `insufficient` |
| `KnowledgeRecommendationPriority` | `models/knowledge.py` | `high`, `medium`, `low` |
| `KnowledgeRecommendationType` | `models/knowledge.py` | `project_private`, `internal_context`, `user_feedback`, `technical_context`, `market_context`, `domain_context`, `process_preference` |
| `KnowledgeRecommendationAction` | `models/knowledge.py` | `provide_document`, `add_url`, `launch_research`, `no_action_needed` |
| `KnowledgeRecommendationStatus` | `models/knowledge.py` | `suggested`, `applied`, `dismissed`, `stale` |
| `KnowledgeGenerationSource` | `models/knowledge.py` | `llm`, `heuristic_fallback` |

### Relations et commentaires

| Enum | Fichier | Valeurs |
|------|---------|---------|
| `RelationType` | `models/task_relation.py` | `blocks`, `related`, `duplicate` |
| `IterationTrigger` | `models/task_iteration.py` | `initial`, `review_feedback`, `input_provided`, `manual_rerun` |
| `CommentAuthorType` | `models/task_comment.py` | `human`, `agent`, `system` |
| `CommentType` | `models/task_comment.py` | `message`, `input_request`, `review_feedback`, `status_change` |

### Brief projet

| Enum | Fichier | Valeurs |
|------|---------|---------|
| `ProjectBriefStatus` | `models/brief.py` | `draft`, `published` |

### Recommandations d'équipe (constantes Literal)

| Constante | Fichier | Valeurs |
|-----------|---------|---------|
| `urgency` | `models/team_recommendations.py` | `"now"`, `"soon"`, `"later"` |
| `change_type` | `models/team_recommendations.py` | `"add_specialist"`, `"remove_agent"`, `"adjust_scope"` |
| `generation_source` | `models/team_recommendations.py` | `"llm"`, `"heuristic_fallback"` |
| `progression_level` | `models/agent.py` | `"apprenti"`, `"opérationnel"`, `"expert"` |

---

## 8. Carte des fichiers sources

### `DATA_MODELS.md`
| Fichier | Contenu |
|---------|---------|
| `models/agent.py` | AgentConfig, AgentResponse, AgentLearningProfile, AgentModelUpdate, enums Agent* |
| `models/task.py` | TaskResponse, TaskCreate, TaskUpdate, TaskExecutionPlan, TaskExecutionNode, TaskProgressEntry, TaskDeliverable, enums Task* |
| `models/team.py` | TeamConfig, TeamResponse, OrganigrammeNode |
| `models/plan.py` | PlanDraftBase, TaskPlanDraft, TeamPlanDraft, PlanForm, PlanField, PlanSessionState, PlanReviewSnapshot, enums Plan* |
| `models/brief.py` | ProjectBriefSnapshot, ProjectBriefStateResponse, ProjectContextDraftRequest, ProjectContextPublishRequest |
| `models/project.py` | ProjectCreate, ProjectResponse, ProjectStatus |
| `models/label.py` | LabelCreate, LabelResponse |
| `models/knowledge.py` | AgentKnowledgeReadiness, GlobalKnowledgeReadiness, KnowledgeRecommendation, enums Knowledge* |
| `models/mcp.py` | McpConnectionConfig, McpConnectionResponse, McpToolDescriptor, AgentMcpToolBinding, enums Mcp* |
| `models/git_providers.py` | GitProviderConnectionConfig, GitProviderConnectionResponse, GitRemoteRepo, AgentGitBinding, enums Git* |
| `models/task_relation.py` | TaskRelationCreate, TaskRelationResponse, RelationType |
| `models/task_comment.py` | TaskCommentCreate, TaskCommentResponse, CommentAuthorType, CommentType |
| `models/task_iteration.py` | TaskIterationResponse, IterationTrigger |
| `models/team_recommendations.py` | TeamRecommendation, TeamChangeRecommendation, RecommendationResponse, RecommendedAgentSpec |
| `models/chat.py` | WSMessage, ChatMessageIn, ChatMessageOut |
| `models/chat_actions.py` | AssistantAction (union), TaskPlanProposalAction, TeamPlanProposalAction, GatherInfoAction, TriggerLearningAction |

### `API_REFERENCE.md`
| Fichier | Contenu |
|---------|---------|
| `api/routes/agents.py` | Endpoints agents, workspaces, skills, knowledge, git/mcp bindings |
| `api/routes/tasks.py` | Endpoints tâches, exécution, itération, deliverables, nœuds |
| `api/routes/teams.py` | Endpoints équipes, organigramme, project context, recommandations, templates |
| `api/routes/chat.py` | Endpoints plan reviews (REST) |
| `api/routes/documents.py` | Endpoints documents (upload, preview, rebriefing) |
| `api/routes/projects.py` | Endpoints projets CRUD |
| `api/routes/labels.py` | Endpoints labels CRUD |
| `api/routes/mcp.py` | Endpoints connexions MCP, test, discover |
| `api/routes/git_providers.py` | Endpoints connexions Git, test, repos |
| `api/routes/usage.py` | Endpoints usage et reset |
| `api/routes/task_comments.py` | Endpoints commentaires de tâche |
| `api/routes/task_relations.py` | Endpoints relations entre tâches |
| `main.py` | Health check, montage des routers, CORS |

### `WEBSOCKET_PROTOCOL.md`
| Fichier | Contenu |
|---------|---------|
| `api/websocket_manager.py` | ConnectionManager, format de messages, connect/disconnect/broadcast |
| `api/routes/chat.py` | WS `/api/chat/ws` (chat, plan lifecycle), WS `/api/chat/team-builder/ws` (déprécié) |
| `api/routes/task_chat.py` | WS `/api/task-planning/ws` (création conversationnelle de tâche) |
| `api/routes/tasks.py` | Broadcasts task_update, task_deleted |
| `api/routes/projects.py` | Broadcasts project_created/updated/deleted |
| `api/routes/labels.py` | Broadcasts label_created/updated/deleted |
| `api/routes/task_comments.py` | Broadcast task_comment |
| `api/routes/task_relations.py` | Broadcasts task_relation_created/deleted |
| `core/orchestrator.py` | Broadcasts node_started/completed/failed, node_stream_chunk, agent_status, task_update, task_input_needed |
| `core/learning.py` | Broadcasts agent_status, reflection_complete, briefing_start/complete, research_complete |
| `core/universal_plan.py` | Broadcasts task_created, team_created |

### `USER_FLOWS.md`
| Fichier | Contenu |
|---------|---------|
| `core/orchestrator.py` | Flow d'exécution de tâche : planification → vagues → nœuds → résultat |
| `core/universal_plan.py` | Flow de planification : discovery → draft → confirmation → exécution |
| `core/learning.py` | Flow d'apprentissage : briefing → learning phase → réflexion → work learnings |
| `core/agent_factory.py` | Flow de création d'agents/équipes, templates, associate singleton |
| `core/team_builder.py` | Flow conversationnel de création d'équipe (déprécié) |
| `core/knowledge.py` | Flow d'audit de connaissances et recommandations |
| `core/document_store.py` | Flow d'upload et indexation de documents |
| `core/task_sufficiency.py` | Flow de vérification de suffisance |
| `core/cost_estimator.py` | Flow d'estimation de coût |
| `core/execution_wave.py` | Algorithme de planification en vagues parallèles |
| `agents/associate.py` | Flow de conversation Associate (Alex), routage d'actions |
| `agents/anthropic_runner.py` | Boucle agentique : system prompt → tool use → résultat |

### `ERRORS_AND_LIMITS.md`
| Fichier | Contenu |
|---------|---------|
| `config/token_budgets.py` | Tous les budgets de tokens par contexte |
| `config/document_limits.py` | Limites de documents, chunks, recherche |
| `config/tool_runtime.py` | Timeouts Git, MCP, shell, limites de caractères |
| `config/pricing.py` | Tarification par modèle |
| `config/brief.py` | Poids de complétude du brief, limites |
| `config/knowledge.py` | Limites de recommandations et d'audit |
| `config/team_recommendations.py` | Limites de recommandations d'équipes |
| `core/structured_json.py` | Gestion d'erreurs JSON structuré, types de failure, réparation |
| `core/cost_estimator.py` | Heuristiques de coût et multiplicateur opus |
| `agents/anthropic_runner.py` | AgentMaxIterError, limite d'itérations |

### `FRONTEND_GUIDELINES.md`
| Fichier | Contenu |
|---------|---------|
| `config/settings.py` | Configuration CORS, modèles disponibles, tiers |
| `config/feature_flags.py` | Feature flags (web search, github, model override) |
| `api/websocket_manager.py` | Contrat WebSocket, format de messages JSON |
| `models/chat.py` | Format des messages chat |
| `models/chat_actions.py` | Actions structurées de l'Associate |
| `agents/specialists/templates.py` | Templates d'agents et d'équipes disponibles |
| `core/project_brief.py` | Champs du brief projet, poids de complétude |

---

## 9. Limites et contraintes système

### Documents

| Contrainte | Valeur | Source |
|------------|--------|--------|
| Taille max upload | 20 MB | `api/routes/documents.py` |
| Formats supportés | .pdf, .docx, .txt, .md, .csv, .json, .yaml, .yml | `api/routes/documents.py` |
| Taille de chunk | 1 000 caractères | `config/document_limits.py` |
| Overlap de chunk | 100 caractères | `config/document_limits.py` |
| Résultats de recherche vectorielle | 3 | `config/document_limits.py` |
| Résultats de contexte document | 4 | `config/document_limits.py` |
| Max caractères contexte document | 4 000 | `config/document_limits.py` |
| Max caractères texte complet | 20 000 | `config/document_limits.py` |
| Documents dans résumé brief | 4 | `config/document_limits.py` |
| Extrait par document dans brief | 320 caractères | `config/document_limits.py` |
| Preview max | 2 400 caractères | `api/routes/documents.py` |

### Tokens et coûts

| Contrainte | Valeur | Source |
|------------|--------|--------|
| Budget max tokens Associate | 8 192 | `config/token_budgets.py` |
| Historique max Associate | 50 messages | `config/token_budgets.py` |
| Budget tokens briefing projet | 8 192 | `config/token_budgets.py` |
| Budget tokens planner orchestrateur | 8 192 | `config/token_budgets.py` |
| Budget tokens réflexion | 4 096 | `config/token_budgets.py` |
| Budget tokens consolidation skills | 4 096 | `config/token_budgets.py` |
| Budget tokens recommandations équipe | 8 192 | `config/token_budgets.py` |
| Budget tokens audit connaissances | 8 192 | `config/token_budgets.py` |
| Seuil résumé résultat dépendance | 3 000 caractères | `config/token_budgets.py` |
| Cible résumé résultat dépendance | 5 000 caractères | `config/token_budgets.py` |
| Top-K résultats vectoriels | 5 | `config/token_budgets.py` |
| Seuil déclenchement réflexion | 5 épisodes | `config/token_budgets.py` |
| Prix Sonnet | $3 / M input, $15 / M output | `config/pricing.py` |
| Prix Opus | $5 / M input, $25 / M output | `config/pricing.py` |
| Multiplicateur coût Opus | ×1.67 | `core/cost_estimator.py` |

### Agents et équipes

| Contrainte | Valeur | Source |
|------------|--------|--------|
| Max itérations agent par tâche | 15 (défaut) | `models/agent.py` |
| Max tokens output agent | 8 192 (défaut) | `models/agent.py` |
| Max recommandations nouvelles équipes | 4 | `config/team_recommendations.py` |
| Max recommandations changements | 6 | `config/team_recommendations.py` |
| Max agents par équipe (recommandation) | 3 | `config/team_recommendations.py` |
| Max recommandations connaissance par agent | 3 | `config/knowledge.py` |
| Max résumés manquants | 3 | `config/knowledge.py` |
| Max plan reviews persistés | 50 | `core/plan_review_store.py` |
| Max context_document_ids par tâche | 8 | `models/chat_actions.py` |

### Outils et connexions

| Contrainte | Valeur | Source |
|------------|--------|--------|
| Timeout clone Git | 300 secondes | `config/tool_runtime.py` |
| Timeout pull Git | 120 secondes | `config/tool_runtime.py` |
| Timeout push Git | 180 secondes | `config/tool_runtime.py` |
| Timeout API Git provider | 30 secondes | `config/tool_runtime.py` |
| Max caractères résultat Git provider | 20 000 | `config/tool_runtime.py` |
| Timeout test connexion MCP | 20 secondes | `config/tool_runtime.py` |
| Timeout appel outil MCP | 45 secondes | `config/tool_runtime.py` |
| Max caractères résultat MCP | 20 000 | `config/tool_runtime.py` |
| Timeout shell workspace | 120 secondes | `config/tool_runtime.py` |
| Max résultats recherche web | 5 | `tools/registry.py` |
| Max caractères page web | 8 000 | `tools/registry.py` |

### Skills et apprentissage

| Contrainte | Valeur | Source |
|------------|--------|--------|
| Max caractères note skill | 6 000 | `config/tool_runtime.py` |
| Seuil consolidation note skill | 5 000 caractères | `config/tool_runtime.py` |
| Max caractères par entrée skill_note | 400 | `config/tool_runtime.py` |
| Max tokens consolidation skill_note | 1 500 | `config/tool_runtime.py` |
| Max insights par nœud (work learnings) | 3 | `core/learning.py` |
| Max cautions par nœud (work learnings) | 2 | `core/learning.py` |
| Max items insight total | 18 | `core/learning.py` |
| Max items caution total | 12 | `core/learning.py` |
| Max caractères par item learning | 280 | `core/learning.py` |
| Seuil consolidation work learnings | 4 200 caractères | `core/learning.py` |
| Max caractères work learnings | 5 000 | `core/learning.py` |
| Seuil déduplication sémantique | distance 0.30 | `core/learning.py` |
| Seuil consolidation core skills | 3 nœuds | `config/token_budgets.py` |
| Seuil sélection smart skills | 4 000 caractères | `config/token_budgets.py` |

### Estimation de coût par nœud (heuristiques Sonnet)

| Type de nœud | Tokens input estimés | Tokens output estimés | Source |
|-------------|---------------------|----------------------|--------|
| `specialist` | 3 000 | 4 000 | `core/cost_estimator.py` |
| `lead_compile` | 5 000 + 1 000/specialist | 6 000 | `core/cost_estimator.py` |
| `single_agent` | 3 000 | 4 000 | `core/cost_estimator.py` |

### Durée estimée

| Contrainte | Valeur | Source |
|------------|--------|--------|
| Durée estimée par nœud | 3 minutes | `core/execution_wave.py` |

### Stockage (filesystem)

| Chemin | Contenu |
|--------|---------|
| `data/agents.json` | Registre des agents |
| `data/teams.json` | Registre des équipes |
| `data/documents.json` | Index des documents uploadés |
| `data/documents/` | Fichiers documents bruts |
| `data/mcp_connections.json` | Connexions MCP |
| `data/git_provider_connections.json` | Connexions Git |
| `data/projects.json` | Projets |
| `data/labels.json` | Labels |
| `data/task_comments.json` | Commentaires de tâches |
| `data/task_relations.json` | Relations entre tâches |
| `data/plan_reviews.json` | Snapshots de plan reviews |
| `data/usage.json` | Statistiques d'utilisation |
| `data/project_context.json` | Brief projet (draft + published) |
| `data/knowledge_readiness/` | Cache des audits de connaissance |
| `data/workspaces/{agent_id}/` | Workspace isolé par agent |
| `data/workspaces/{agent_id}/skills/` | Skills Markdown |
| `data/workspaces/{agent_id}/repos/` | Dépôts Git clonés |
| `data/workspaces/{agent_id}/output/` | Livrables de tâches |
| `data/workspaces/{agent_id}/tmp/` | Fichiers temporaires (nettoyés entre tâches) |
| `data/workspaces/{agent_id}/downloads/` | Documents téléchargés |
| `data/workspaces/shared/` | Workspace partagé inter-agents |
| `data/chromadb/` | Base vectorielle ChromaDB |
