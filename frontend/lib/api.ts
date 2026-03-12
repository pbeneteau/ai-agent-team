const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export type AgentStatus = "pending" | "learning" | "ready" | "working" | "error";
export type AgentOccupancyStatus = "idle" | "assigned" | "busy";
export type AgentOccupancyReason =
  | "task_execution"
  | "learning"
  | "research"
  | "rebriefing"
  | "project_briefing";
export type AgentRole = "associate" | "team_lead" | "specialist";
export type ModelTier = "sonnet" | "opus";
export type GitProvider = "github" | "gitlab";
export type GitProviderConnectionStatus = "unknown" | "healthy" | "degraded" | "unavailable";
export type GitProviderAuthMode = "personal_access_token";
export type McpConnectionStatus = "unknown" | "healthy" | "degraded" | "unavailable";
export type McpTransport = "streamable_http";
export type McpApprovalMode = "auto" | "confirm_each_use" | "blocked";
export type McpCapabilityClass = "read_only" | "write" | "unknown";
export type KnowledgeReadinessLevel = "sufficient" | "partial" | "insufficient";
export type KnowledgeRecommendationPriority = "high" | "medium" | "low";
export type KnowledgeRecommendationType =
  | "project_private"
  | "internal_context"
  | "user_feedback"
  | "technical_context"
  | "market_context"
  | "domain_context"
  | "process_preference";
export type KnowledgeRecommendationAction =
  | "provide_document"
  | "add_url"
  | "launch_research"
  | "no_action_needed";
export type KnowledgeRecommendationStatus = "suggested" | "applied" | "dismissed" | "stale";
export type KnowledgeGenerationSource = "llm" | "heuristic_fallback";
export type TaskStatus = "pending" | "running" | "completed" | "failed";
export type TaskPriority = "low" | "medium" | "high";
export type TaskExecutionMode = "auto" | "standalone" | "dependency_graph";
export type TaskExecutionEligibility = "eligible" | "clarification_required" | "ineligible";
export type TaskPlanStatus =
  | "not_planned"
  | "planning"
  | "ready"
  | "running"
  | "completed"
  | "failed";
export type TaskNodeStatus =
  | "pending"
  | "blocked"
  | "ready"
  | "running"
  | "completed"
  | "failed"
  | "skipped";
export type TaskNodeType = "single_agent" | "specialist" | "lead_compile";

export interface McpToolDescriptor {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  read_only: boolean;
  capability_class: McpCapabilityClass;
}

export interface GitRemoteRepo {
  full_name: string;
  owner: string;
  name: string;
  web_url: string;
  clone_url: string;
  default_branch: string;
}

export interface GitProviderConnection {
  id: string;
  provider: GitProvider;
  name: string;
  base_url: string;
  auth_mode: GitProviderAuthMode;
  has_auth_token: boolean;
  enabled: boolean;
  notes: string;
  discovered_repos: GitRemoteRepo[];
  status: GitProviderConnectionStatus;
  last_tested_at: string | null;
  last_error: string | null;
  total_repo_actions: number;
  clone_actions: number;
  push_actions: number;
  pull_request_actions: number;
  last_action_at: string | null;
}

export interface GitProviderTestResult {
  ok: boolean;
  status: GitProviderConnectionStatus;
  account_name: string | null;
  account_username: string | null;
  repo_count: number;
  error: string | null;
}

export interface AgentGitBinding {
  connection_id: string;
  connection_name: string;
  provider: GitProvider;
  repo_full_name: string;
  repo_web_url: string;
  default_branch: string;
  enabled: boolean;
  can_push: boolean;
  can_open_pr: boolean;
  branch_prefix: string;
  connection_status: GitProviderConnectionStatus;
}

export interface McpConnection {
  id: string;
  name: string;
  transport: McpTransport;
  endpoint_url: string;
  enabled: boolean;
  auth_header_name: string;
  has_auth_token: boolean;
  notes: string;
  tool_allowlist: string[];
  discovered_tools: McpToolDescriptor[];
  status: McpConnectionStatus;
  last_tested_at: string | null;
  last_error: string | null;
  total_calls: number;
  total_failures: number;
  last_called_at: string | null;
}

export interface McpTestResult {
  ok: boolean;
  status: McpConnectionStatus;
  server_name: string | null;
  server_version: string | null;
  protocol_version: string | null;
  error: string | null;
}

export interface AgentMcpToolBinding {
  connection_id: string;
  connection_name: string;
  tool_name: string;
  enabled: boolean;
  alias: string | null;
  approval_mode: McpApprovalMode;
  description: string;
  read_only: boolean;
  capability_class: McpCapabilityClass;
  connection_status: McpConnectionStatus;
}

export interface Agent {
  id: string;
  name: string;
  role: AgentRole;
  title: string;
  specialization: string;
  goal: string;
  backstory: string;
  status: AgentStatus;
  occupancy_status: AgentOccupancyStatus;
  occupancy_reason: AgentOccupancyReason | null;
  current_task_id: string | null;
  current_task_title: string | null;
  current_node_id: string | null;
  current_node_title: string | null;
  busy_since: string | null;
  team_id: string | null;
  parent_id: string | null;
  workspace_path: string | null;
  tools: string[];
  git_bindings: AgentGitBinding[];
  mcp_tool_bindings: AgentMcpToolBinding[];
  model_tier: ModelTier;
  max_iter: number;
}

export interface KnowledgeRecommendationEvidence {
  source_label: string;
  source_type: string;
  excerpt: string;
}

export interface KnowledgeRecommendation {
  id: string;
  agent_id: string;
  title: string;
  summary: string;
  reason: string;
  priority: KnowledgeRecommendationPriority;
  knowledge_type: KnowledgeRecommendationType;
  action_type: KnowledgeRecommendationAction;
  can_be_found_on_web: boolean;
  recommended_source: string;
  suggested_topic: string | null;
  status: KnowledgeRecommendationStatus;
  evidence: KnowledgeRecommendationEvidence[];
}

export interface AgentKnowledgeReadiness {
  agent_id: string;
  agent_name: string;
  agent_title: string;
  agent_role: AgentRole;
  team_id: string | null;
  readiness_level: KnowledgeReadinessLevel;
  readiness_score: number;
  summary: string;
  missing_knowledge_summary: string[];
  recommendations: KnowledgeRecommendation[];
  generation_source: KnowledgeGenerationSource;
  generation_channel?: string | null;
  generation_issue: string | null;
  context_fingerprint: string;
  updated_at: string;
}

export interface GlobalKnowledgeGap {
  id: string;
  title: string;
  action_type: KnowledgeRecommendationAction;
  priority: KnowledgeRecommendationPriority;
  can_be_found_on_web: boolean;
  agent_count: number;
  affected_agent_ids: string[];
  affected_agent_names: string[];
}

export interface GlobalKnowledgeReadiness {
  generated_at: string;
  fingerprint: string;
  total_agents: number;
  insufficient_agents: number;
  partial_agents: number;
  sufficient_agents: number;
  fallback_agent_count: number;
  has_fallback_results: boolean;
  generation_channel?: string | null;
  agents: AgentKnowledgeReadiness[];
  shared_gaps: GlobalKnowledgeGap[];
}

export interface Team {
  id: string;
  name: string;
  description: string;
  domain: string;
  lead_agent_id: string | null;
  scope_note: string;
  agents: Agent[];
}

export interface RecommendedAgentSpec {
  name: string;
  title: string;
  specialization: string;
  goal: string;
  backstory: string;
  is_lead: boolean;
  model_tier: ModelTier;
}

export interface TeamRecommendation {
  id: string;
  name: string;
  description: string;
  domain: string;
  urgency: "now" | "soon" | "later";
  score: number;
  reason: string;
  agents: RecommendedAgentSpec[];
}

export interface TeamChangeRecommendation {
  id: string;
  team_id: string;
  team_name: string;
  change_type: "add_specialist" | "remove_agent" | "adjust_scope";
  urgency: "now" | "soon" | "later";
  score: number;
  reason: string;
  target_agent_id?: string | null;
  target_agent_name?: string | null;
  suggested_agent?: RecommendedAgentSpec | null;
  scope_update?: string | null;
}

export interface TeamRecommendationsResponse {
  new_teams: TeamRecommendation[];
  team_changes: TeamChangeRecommendation[];
  generation_source: KnowledgeGenerationSource;
  generation_channel?: string | null;
  generation_issue: string | null;
}

export interface ProjectContext {
  name?: string;
  description?: string;
  domain?: string;
  short_term_goal?: string;
  tech_stack?: string;
  target_audience?: string;
  business_model?: string;
  notes?: string;
}

export interface ProjectBrief extends ProjectContext {
  revision: number;
  status: "draft" | "published";
  updated_at: string;
  published_at: string | null;
  brief_fingerprint: string;
  completeness_score: number;
}

export interface ProjectContextState {
  draft: ProjectBrief | null;
  published: ProjectBrief | null;
  active: ProjectBrief | null;
  has_unpublished_changes: boolean;
}

export interface ProjectContextMutationResult {
  ok: boolean;
  message: string;
  state: ProjectContextState;
}

export interface OrgNode {
  id: string;
  name: string;
  title: string;
  role: string;
  status: AgentStatus;
  occupancy_status: AgentOccupancyStatus;
  occupancy_reason: AgentOccupancyReason | null;
  current_task_id: string | null;
  current_task_title: string | null;
  current_node_id: string | null;
  current_node_title: string | null;
  busy_since: string | null;
  parent_id: string | null;
  children: OrgNode[];
}

export interface TaskProgressEntry {
  timestamp: string;
  message: string;
  agent: string | null;
  agent_id: string | null;
  agent_name: string | null;
  node_id: string | null;
  stage: string | null;
  structured_flow?: string | null;
  structured_channel?: string | null;
}

export interface TaskExecutionNode {
  id: string;
  title: string;
  description: string;
  node_type: TaskNodeType;
  status: TaskNodeStatus;
  assigned_agent_id: string | null;
  assigned_agent_name: string | null;
  depends_on: string[];
  result: string | null;
  error: string | null;
  error_type: string | null;
  error_traceback: string | null;
  failure_stage: string | null;
  started_at: string | null;
  completed_at: string | null;
  sources: string[];
  assumptions: string[];
  warnings: string[];
}

export interface TaskDeliverable {
  path: string;
  name: string;
  type: string;
  size_bytes: number;
  modified_at: string;
}

export interface TaskExecutionPlan {
  status: TaskPlanStatus;
  mode: TaskExecutionMode;
  compiler_agent_id: string | null;
  compiler_agent_name: string | null;
  planning_notes: string;
  nodes: TaskExecutionNode[];
}

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  assigned_team_id: string | null;
  assigned_agent_id: string | null;
  assigned_agent_ids: string[];
  execution_mode: TaskExecutionMode;
  context_document_ids: string[];
  execution_plan: TaskExecutionPlan;
  result: string | null;
  error: string | null;
  error_type: string | null;
  error_traceback: string | null;
  failure_stage: string | null;
  brief_revision: number | null;
  brief_fingerprint: string | null;
  created_at: string;
  updated_at: string;
  execution_eligibility: TaskExecutionEligibility;
  execution_blockers: string[];
  progress_log: TaskProgressEntry[];
  deliverables_dir: string | null;
  deliverables: TaskDeliverable[];
  sources: string[];
  assumptions: string[];
  warnings: string[];
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    headers: isFormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API error ${res.status}: ${error}`);
  }
  return res.json();
}

export function extractApiErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof Error)) {
    return fallback;
  }

  const apiMatch = error.message.match(/^API error \d+: (.+)$/);
  if (!apiMatch) {
    return error.message || fallback;
  }

  const payload = apiMatch[1];
  try {
    const parsed = JSON.parse(payload) as { detail?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    // Fall through to the raw payload when the backend did not return JSON.
  }

  return payload || fallback;
}

export const api = {
  // Teams
  getTeams: () => fetchApi<Team[]>("/teams/"),
  getTeamRecommendations: () => fetchApi<TeamRecommendationsResponse>("/teams/recommendations"),
  getOrganigramme: () => fetchApi<OrgNode[]>("/teams/organigramme"),
  createTeamFromTemplate: (template: string) =>
    fetchApi<Team>("/teams/from-template", {
      method: "POST",
      body: JSON.stringify({ template }),
    }),
  createCustomTeam: (data: {
    name: string;
    description: string;
    domain: string;
    agents: RecommendedAgentSpec[];
  }) =>
    fetchApi<Team>("/teams/custom", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  addAgentToTeam: (teamId: string, agent: RecommendedAgentSpec) =>
    fetchApi<Team>(`/teams/${teamId}/agents`, {
      method: "POST",
      body: JSON.stringify({ agent }),
    }),
  updateTeamScope: (teamId: string, data: { description: string; scope_note: string }) =>
    fetchApi<Team>(`/teams/${teamId}/scope`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteTeam: (id: string) =>
    fetchApi<{ ok: boolean }>(`/teams/${id}`, { method: "DELETE" }),
  resetAll: () =>
    fetchApi<{ ok: boolean }>("/teams/reset", { method: "POST" }),

  // Agents
  getAgents: () => fetchApi<Agent[]>("/agents/"),
  getAgent: (id: string) => fetchApi<Agent>(`/agents/${id}`),
  getKnowledgeReadiness: () => fetchApi<GlobalKnowledgeReadiness>("/agents/readiness/global"),
  getAgentKnowledgeRecommendations: (id: string) =>
    fetchApi<AgentKnowledgeReadiness>(`/agents/${id}/knowledge-recommendations`),
  dismissAgentKnowledgeRecommendation: (agentId: string, recommendationId: string) =>
    fetchApi<AgentKnowledgeReadiness>(`/agents/${agentId}/knowledge-recommendations/${recommendationId}/dismiss`, {
      method: "POST",
    }),
  applyAgentKnowledgeRecommendation: (agentId: string, recommendationId: string) =>
    fetchApi<AgentKnowledgeReadiness>(`/agents/${agentId}/knowledge-recommendations/${recommendationId}/apply`, {
      method: "POST",
    }),

  // Tasks
  getTasks: () => fetchApi<Task[]>("/tasks/"),
  getTask: (id: string) => fetchApi<Task>(`/tasks/${id}`),
  getTaskDeliverables: (id: string) => fetchApi<TaskDeliverable[]>(`/tasks/${id}/deliverables`),
  readTaskDeliverable: (id: string, path: string) =>
    fetchApi<{ path: string; name: string; content: string }>(
      `/tasks/${id}/deliverables/read?path=${encodeURIComponent(path)}`,
    ),
  getTaskDeliverableDownloadUrl: (id: string, path: string) =>
    `${API_BASE}/tasks/${id}/deliverables/download?path=${encodeURIComponent(path)}`,
  createTask: (data: {
    title: string;
    description: string;
    priority: TaskPriority;
    assigned_team_id?: string;
    assigned_agent_id?: string;
    execution_mode?: TaskExecutionMode;
    context_document_ids?: string[];
  }) =>
    fetchApi<Task>("/tasks/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  executeTask: (id: string) =>
    fetchApi<Task>(`/tasks/${id}/execute`, {
      method: "POST",
    }),
  deleteTask: (id: string) =>
    fetchApi<{ ok: boolean }>(`/tasks/${id}`, { method: "DELETE" }),

  // Agent model tier
  setAgentModelTier: (id: string, model_tier: ModelTier) =>
    fetchApi<Agent>(`/agents/${id}/model`, {
      method: "PATCH",
      body: JSON.stringify({ model_tier }),
    }),

  // Agent skills CRUD
  updateAgentSkill: (agentId: string, skillName: string, content: string) =>
    fetchApi<{ ok: boolean }>(`/agents/${agentId}/skills/${skillName}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  deleteAgentSkill: (agentId: string, skillName: string) =>
    fetchApi<{ ok: boolean }>(`/agents/${agentId}/skills/${skillName}`, { method: "DELETE" }),

  // Delete agent
  deleteAgent: (id: string) =>
    fetchApi<{ ok: boolean }>(`/agents/${id}`, { method: "DELETE" }),

  // Documents
  getDocuments: () => fetchApi<Document[]>("/documents/"),
  getDocumentPreview: (id: string) => fetchApi<DocumentPreview>(`/documents/${id}/preview`),
  uploadDocument: (file: File, description?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (description) form.append("description", description);
    return fetch(`${API_BASE}/documents/`, { method: "POST", body: form })
      .then((r) => {
        if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
        return r.json() as Promise<Document>;
      });
  },
  deleteDocument: (id: string) =>
    fetchApi<{ ok: boolean }>(`/documents/${id}`, { method: "DELETE" }),
  briefAgentsWithDocument: (id: string) =>
    fetchApi<{ ok: boolean; message: string }>(`/documents/${id}/brief-agents`, { method: "POST" }),

  // Agent knowledge & research
  getCapabilities: () =>
    fetchApi<{
      web_search: boolean;
      github_search: boolean;
      model_override: boolean;
      mcp_connections: boolean;
      git_provider_connections: boolean;
    }>(
      "/agents/capabilities",
    ),
  getGitProviderConnections: () => fetchApi<GitProviderConnection[]>("/git-providers/connections"),
  createGitProviderConnection: (data: {
    provider: GitProvider;
    name: string;
    base_url?: string;
    auth_token?: string;
    enabled?: boolean;
    notes?: string;
  }) =>
    fetchApi<GitProviderConnection>("/git-providers/connections", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateGitProviderConnection: (
    connectionId: string,
    data: {
      name?: string;
      base_url?: string;
      auth_token?: string;
      clear_auth_token?: boolean;
      enabled?: boolean;
      notes?: string;
    },
  ) =>
    fetchApi<GitProviderConnection>(`/git-providers/connections/${connectionId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteGitProviderConnection: (connectionId: string) =>
    fetchApi<{ ok: boolean }>(`/git-providers/connections/${connectionId}`, { method: "DELETE" }),
  testGitProviderConnection: (connectionId: string) =>
    fetchApi<GitProviderTestResult>(`/git-providers/connections/${connectionId}/test`, { method: "POST" }),
  refreshGitProviderRepos: (connectionId: string) =>
    fetchApi<GitRemoteRepo[]>(`/git-providers/connections/${connectionId}/repos/refresh`, { method: "POST" }),
  getGitProviderRepos: (connectionId: string) =>
    fetchApi<GitRemoteRepo[]>(`/git-providers/connections/${connectionId}/repos`),
  getAgentGitBindings: (agentId: string) =>
    fetchApi<AgentGitBinding[]>(`/agents/${agentId}/git-bindings`),
  updateAgentGitBindings: (
    agentId: string,
    bindings: Array<{
      connection_id: string;
      repo_full_name: string;
      enabled?: boolean;
      can_push?: boolean;
      can_open_pr?: boolean;
      branch_prefix?: string;
    }>,
  ) =>
    fetchApi<AgentGitBinding[]>(`/agents/${agentId}/git-bindings`, {
      method: "PUT",
      body: JSON.stringify({ bindings }),
    }),
  getMcpConnections: () => fetchApi<McpConnection[]>("/mcp/connections"),
  createMcpConnection: (data: {
    name: string;
    endpoint_url: string;
    enabled?: boolean;
    auth_header_name?: string;
    auth_token?: string;
    notes?: string;
    tool_allowlist?: string[];
  }) =>
    fetchApi<McpConnection>("/mcp/connections", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateMcpConnection: (
    connectionId: string,
    data: {
      name?: string;
      endpoint_url?: string;
      enabled?: boolean;
      auth_header_name?: string;
      auth_token?: string;
      clear_auth_token?: boolean;
      notes?: string;
      tool_allowlist?: string[];
    },
  ) =>
    fetchApi<McpConnection>(`/mcp/connections/${connectionId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteMcpConnection: (connectionId: string) =>
    fetchApi<{ ok: boolean }>(`/mcp/connections/${connectionId}`, { method: "DELETE" }),
  testMcpConnection: (connectionId: string) =>
    fetchApi<McpTestResult>(`/mcp/connections/${connectionId}/test`, { method: "POST" }),
  discoverMcpTools: (connectionId: string) =>
    fetchApi<McpToolDescriptor[]>(`/mcp/connections/${connectionId}/discover-tools`, { method: "POST" }),
  getMcpConnectionTools: (connectionId: string) =>
    fetchApi<McpToolDescriptor[]>(`/mcp/connections/${connectionId}/tools`),
  getAgentMcpTools: (agentId: string) =>
    fetchApi<AgentMcpToolBinding[]>(`/agents/${agentId}/mcp-tools`),
  updateAgentMcpTools: (
    agentId: string,
    bindings: Array<{
      connection_id: string;
      tool_name: string;
      enabled?: boolean;
      alias?: string | null;
      approval_mode?: McpApprovalMode;
    }>,
  ) =>
    fetchApi<AgentMcpToolBinding[]>(`/agents/${agentId}/mcp-tools`, {
      method: "PUT",
      body: JSON.stringify({ bindings }),
    }),
  addAgentKnowledge: (agentId: string, formData: FormData) =>
    fetchApi<{ ok: boolean; source: string; chars: number }>(`/agents/${agentId}/knowledge`, {
      method: "POST",
      body: formData,
    }),
  launchAgentResearch: (agentId: string, topic: string) =>
    fetchApi<{ ok: boolean; topic: string }>(`/agents/${agentId}/research`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    }),

  // Project context
  getProjectContext: () => fetchApi<ProjectContextState>("/teams/project-context"),
  saveProjectContextDraft: (data: ProjectContext) =>
    fetchApi<ProjectContextMutationResult>("/teams/project-context/draft", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  publishProjectContext: (data: ProjectContext & { name: string; description: string }) =>
    fetchApi<ProjectContextMutationResult>("/teams/project-context/publish", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  saveProjectContext: (data: ProjectContext & { name: string; description: string }) =>
    fetchApi<ProjectContextMutationResult>("/teams/project-context", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Usage
  getUsage: () => fetchApi<UsageSummary>("/usage/"),
  resetUsage: () => fetchApi<{ ok: boolean }>("/usage/reset", { method: "POST" }),

  // Health — backend exposes /health at root, not under /api
  health: () =>
    fetch(API_BASE.replace(/\/api$/, "") + "/health")
      .then((r) => r.json() as Promise<{ status: string }>)
      .catch(() => ({ status: "offline" })),
};

export interface UsageSummary {
  today: { input_tokens: number; output_tokens: number; cost_usd: number };
  total: { input_tokens: number; output_tokens: number; cost_usd: number; calls: number };
  by_model: Record<string, { input_tokens: number; output_tokens: number; cost_usd: number }>;
  daily: Record<string, { input: number; output: number; cost: number }>;
  structured_outputs?: {
    by_flow: Record<
      string,
      {
        calls: number;
        successes: number;
        failures: number;
        channels: Record<string, number>;
        failures_by_kind?: Record<string, number>;
        last_failure?: {
          at: string | null;
          request_name: string | null;
          channel: string | null;
          error_kind: string;
          stop_reason: string | null;
          validation_failed: boolean;
          message: string | null;
        } | null;
        last_request_name: string | null;
        last_seen_at: string | null;
      }
    >;
  };
  mcp?: {
    total_connections: number;
    healthy_connections: number;
    degraded_connections: number;
    unavailable_connections: number;
    total_calls: number;
    total_failures: number;
    connections: McpConnection[];
  };
  git_providers?: {
    total_connections: number;
    healthy_connections: number;
    degraded_connections: number;
    unavailable_connections: number;
    total_repo_actions: number;
    clone_actions: number;
    push_actions: number;
    pull_request_actions: number;
    connections: GitProviderConnection[];
  };
  pricing_note: string;
}

export interface Document {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  chunk_count: number;
  description: string;
}

export interface DocumentPreview {
  id: string;
  filename: string;
  content_type: string;
  description: string;
  created_at: string;
  size_bytes: number;
  chunk_count: number;
  preview: string;
  truncated: boolean;
}
