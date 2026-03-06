const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export type AgentStatus = "pending" | "learning" | "ready" | "working" | "error";
export type AgentRole = "associate" | "team_lead" | "specialist";
export type ModelTier = "sonnet" | "opus";
export type TaskStatus = "pending" | "running" | "completed" | "failed";
export type TaskPriority = "low" | "medium" | "high";

export interface Agent {
  id: string;
  name: string;
  role: AgentRole;
  title: string;
  specialization: string;
  status: AgentStatus;
  team_id: string | null;
  parent_id: string | null;
  workspace_path: string | null;
  tools: string[];
  model_tier: ModelTier;
  max_iter: number;
}

export interface Team {
  id: string;
  name: string;
  description: string;
  domain: string;
  lead_agent_id: string | null;
  agents: Agent[];
}

export interface OrgNode {
  id: string;
  name: string;
  title: string;
  role: string;
  status: AgentStatus;
  parent_id: string | null;
  children: OrgNode[];
}

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  assigned_team_id: string | null;
  assigned_agent_ids: string[];
  result: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  progress_log: { timestamp: string; message: string; agent?: string }[];
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

export const api = {
  // Teams
  getTeams: () => fetchApi<Team[]>("/teams/"),
  getOrganigramme: () => fetchApi<OrgNode[]>("/teams/organigramme"),
  createTeamFromTemplate: (template: string) =>
    fetchApi<Team>("/teams/from-template", {
      method: "POST",
      body: JSON.stringify({ template }),
    }),
  deleteTeam: (id: string) =>
    fetchApi<{ ok: boolean }>(`/teams/${id}`, { method: "DELETE" }),
  resetAll: () =>
    fetchApi<{ ok: boolean }>("/teams/reset", { method: "POST" }),

  // Agents
  getAgents: () => fetchApi<Agent[]>("/agents/"),
  getAgent: (id: string) => fetchApi<Agent>(`/agents/${id}`),

  // Tasks
  getTasks: () => fetchApi<Task[]>("/tasks/"),
  getTask: (id: string) => fetchApi<Task>(`/tasks/${id}`),
  createTask: (data: { title: string; description: string; priority: TaskPriority; assigned_team_id?: string }) =>
    fetchApi<Task>("/tasks/", {
      method: "POST",
      body: JSON.stringify(data),
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
    fetchApi<{ web_search: boolean }>("/agents/capabilities"),
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
  getProjectContext: () => fetchApi<Record<string, string>>("/teams/project-context"),
  saveProjectContext: (data: {
    name: string;
    description: string;
    domain?: string;
    tech_stack?: string;
    target_audience?: string;
    business_model?: string;
    notes?: string;
  }) =>
    fetchApi<{ ok: boolean; message: string }>("/teams/project-context", {
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
