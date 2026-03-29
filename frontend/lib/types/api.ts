/**
 * API response/request types matching TDD-04 schemas.
 *
 * All types correspond to backend Pydantic models.
 */

// ── Pagination ──────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}

// ── Onboarding ──────────────────────────────────────────────────────────

export interface OnboardingRequest {
  company_name: string;
  domain_description: string;
  product_description?: string;
  tech_stack?: string;
  company_stage?: "idea" | "startup" | "growing" | "established";
  target_audience?: string;
  main_goals?: string;
  existing_team?: string;
  team_size?: number;
  use_case: "code" | "content" | "both";
}

export interface OnboardingResponse {
  workspace: Workspace;
  agents: AgentListItem[];
}

// ── Workspace ───────────────────────────────────────────────────────────

export interface Workspace {
  id: string;
  name: string;
  domain_description: string | null;
  product_description: string | null;
  tech_stack: string | null;
  company_stage: "idea" | "startup" | "growing" | "established" | null;
  target_audience: string | null;
  main_goals: string | null;
  existing_team: string | null;
  team_size: number | null;
  monthly_budget_usd: number;
  monthly_spend_usd: number;
  onboarding_completed: boolean;
  created_at: string;
}

export interface WorkspaceUpdateRequest {
  name?: string;
  domain_description?: string;
  product_description?: string;
  tech_stack?: string;
  company_stage?: "idea" | "startup" | "growing" | "established";
  target_audience?: string;
  main_goals?: string;
  existing_team?: string;
  team_size?: number;
}

export interface WorkspaceDocument {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  processing_status: string;
  created_at: string;
}

// ── Roster ──────────────────────────────────────────────────────────────

export interface AgentListItem {
  id: string;
  name: string;
  specialization: string;
  description: string;
  role: AgentRole;
  status: AgentStatus;
  readiness_score: number;
  progression_level: ProgressionLevel;
  model_tier: ModelTier;
  completed_artifacts: number;
  avg_quality_score: number | null;
  created_at: string;
}

export interface AgentDetail extends AgentListItem {
  system_prompt: string;
  tools: string[];
  skills_summary: SkillsSummary;
  last_reflection_at: string | null;
  archived_at: string | null;
  updated_at: string;
}

export type AgentRole = "lead" | "worker";
export type AgentStatus = "learning" | "ready" | "working" | "reflecting";
export type ProgressionLevel = "apprenti" | "opérationnel" | "expert";
export type ModelTier = "sonnet" | "opus";

export interface SkillsSummary {
  total_tokens: number;
  skill_tokens: number;
  learning_tokens: number;
  briefing_tokens: number;
  budget_limit: number;
}

export interface SkillItem {
  id: string;
  category: "skill" | "work_learning" | "briefing";
  title: string;
  content: string;
  token_count: number;
  created_at: string;
}

export interface SkillsListResponse {
  items: SkillItem[];
  total_tokens: number;
  budget_limit: number;
}

export interface LearningProfile {
  readiness_score: number;
  breakdown: ReadinessComponent[];
}

export interface ReadinessComponent {
  name: string;
  score: number;
  max_score: number;
  met: boolean;
}

export interface GlobalReadiness {
  total_agents: number;
  avg_readiness_score: number;
  by_level: Record<ProgressionLevel, number>;
  by_status: Record<AgentStatus, number>;
  agents_needing_attention: AgentAttentionItem[];
}

export interface AgentAttentionItem {
  id: string;
  name: string;
  readiness_score: number;
  reason: string;
}

export interface CreateAgentRequest {
  name: string;
  specialization: string;
  description: string;
  model_tier?: ModelTier;
}

export interface UpdateAgentRequest {
  name?: string;
  specialization?: string;
  description?: string;
  model_tier?: ModelTier;
}

export interface RosterFilters {
  status?: AgentStatus;
  include_archived?: boolean;
  cursor?: string;
  limit?: number;
}

// ── Projects ────────────────────────────────────────────────────────────

export interface ProjectListItem {
  id: string;
  name: string;
  description: string | null;
  primary_language: string | null;
  framework: string | null;
  git_repo_url: string | null;
  artifact_count: number;
  created_at: string;
}

export interface ProjectDetail extends ProjectListItem {
  package_manager: string | null;
  has_readme: boolean;
  brief_status: "none" | "draft" | "published";
  brief_draft: string | null;
  brief_published: string | null;
  brief_fingerprint: string | null;
  brief_published_at: string | null;
  updated_at: string;
}

export interface CreateProjectRequest {
  name: string;
  description?: string;
  primary_language?: string;
  framework?: string;
  package_manager?: string;
  git_repo_url?: string;
  git_connection_id?: string;
}

export interface UpdateProjectRequest {
  name?: string;
  description?: string;
  primary_language?: string;
  framework?: string;
  package_manager?: string;
  git_repo_url?: string;
}

export interface BriefContext {
  draft: string | null;
  published: string | null;
  fingerprint: string | null;
  published_at: string | null;
}

export interface DocumentItem {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  processing_status: "pending" | "processing" | "ready" | "failed";
  created_at: string;
}

// ── Artifacts ───────────────────────────────────────────────────────────

export type ArtifactType = "code";
export type ArtifactStatus = "drafting" | "in_review" | "approved" | "cancelled";

export interface CreateArtifactRequest {
  project_id: string;
  artifact_type: ArtifactType;
  title: string;
  goal?: string;
  target_audience?: string;
  context?: string;
  description: string;
  max_budget_usd?: number;
  git_repo_url?: string;
  git_base_branch?: string;
}

export interface ArtifactResponse {
  id: string;
  project_id: string;
  artifact_type: ArtifactType;
  title: string;
  goal: string | null;
  target_audience: string | null;
  context: string | null;
  description: string;
  status: ArtifactStatus;
  max_budget_usd: number;
  total_cost_usd: number;
  current_version: number;
  git_repo_url: string | null;
  git_base_branch: string | null;
  git_feature_branch: string | null;
  git_pr_url: string | null;
  git_pr_number: number | null;
  approved_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ArtifactListItem {
  id: string;
  title: string;
  artifact_type: ArtifactType;
  status: ArtifactStatus;
  current_version: number;
  total_cost_usd: number;
  git_feature_branch: string | null;
  git_pr_url: string | null;
  git_pr_number: number | null;
  created_at: string;
}

export interface ArtifactFilters {
  status?: ArtifactStatus;
  cursor?: string;
  limit?: number;
}

export interface SufficiencyResponse {
  eligible: boolean;
  score: number;
  issues: SufficiencyIssue[];
}

export interface SufficiencyIssue {
  field: string;
  severity: "critical" | "warning";
  matched_text: string;
  issue: string;
  suggestion: string;
}

export interface DelegateRequest {
  confirm?: boolean;
  template_override?: string;
  agent_overrides?: Record<string, string>;
}

export interface DelegatePlan {
  template_key: string;
  dag_plan: Record<string, unknown>;
  assembled_team: Record<string, unknown>;
  step_labels: string[];
  estimated_cost_usd: number;
}

export interface DelegatePreviewResponse {
  plan: DelegatePlan;
}

export interface DelegateConfirmResponse {
  execution_wave_id: string;
  plan: DelegatePlan;
}

export interface ArtifactStatusResponse {
  artifact_id: string;
  status: ArtifactStatus;
  current_version: number;
  wave: ExecutionStatus | null;
}

export interface ExecutionStatus {
  wave_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  current_step: number;
  total_steps: number;
  step_labels: string[];
  cost_usd: number;
  started_at: string | null;
}

export interface VersionItem {
  id: string;
  version_number: number;
  file_manifest: FileManifestEntry[];
  token_cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  assumptions: string[];
  sources: string[];
  created_at: string;
}

export interface FileManifestEntry {
  path: string;
  size_bytes: number;
  content_type: string;
}

export interface IterateRequest {
  instruction: string;
  file_path?: string;
  highlight_start?: number;
  highlight_end?: number;
  highlighted_text?: string;
}

export interface IterateResponse {
  execution_wave_id: string;
  comment_id: string;
}

export interface StandaloneSufficiencyRequest {
  artifact_type: ArtifactType;
  title: string;
  goal?: string;
  target_audience?: string;
  context?: string;
  description: string;
}

// ── Git Providers ───────────────────────────────────────────────────────

export type GitProvider = "github" | "gitlab";
export type GitConnectionStatus = "active" | "error" | "revoked";

export interface GitConnectionItem {
  id: string;
  provider: GitProvider;
  display_name: string;
  status: GitConnectionStatus;
  repositories: GitRepoEntry[];
  last_verified_at: string | null;
  created_at: string;
}

export interface GitRepoEntry {
  owner: string;
  name: string;
  full_name?: string;
  default_branch?: string;
  private?: boolean;
  webhook_configured?: boolean;
}

export interface CreateGitConnectionRequest {
  provider: GitProvider;
  display_name: string;
  access_token: string;
}

export interface TestGitConnectionResponse {
  ok: boolean;
  user: string;
  scopes: string[];
  rate_limit_remaining: number | null;
}

export interface GitRepoListResponse {
  items: GitRepoEntry[];
}

export interface WebhookConfiguredResponse {
  webhook_id: number;
  webhook_url: string;
  events: string[];
  status: string;
}

// ── MCP ─────────────────────────────────────────────────────────────────

export type McpAuthType = "api_key" | "oauth" | "none";
export type McpConnectionStatus = "active" | "error" | "unavailable";

export interface McpConnectionItem {
  id: string;
  name: string;
  server_url: string;
  auth_type: McpAuthType;
  status: McpConnectionStatus;
  discovered_tools: McpToolItem[];
  last_verified_at: string | null;
  created_at: string;
}

export interface McpToolItem {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface CreateMcpConnectionRequest {
  name: string;
  server_url: string;
  auth_type?: McpAuthType;
  auth_config?: Record<string, unknown>;
}

export interface TestMcpResponse {
  ok: boolean;
  server_version: string;
  tools_count: number;
  latency_ms: number;
}

export interface DiscoverToolsResponse {
  tools: McpToolItem[];
}

// ── Usage ───────────────────────────────────────────────────────────────

export interface UsageResponse {
  period: string;
  period_start: string;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  budget: BudgetInfo;
  by_model: Record<string, ModelUsage>;
  by_artifact: ArtifactUsage[];
  daily_breakdown: DailyBreakdown[];
}

export interface BudgetInfo {
  monthly_limit_usd: number;
  monthly_spent_usd: number;
  remaining_usd: number;
  usage_pct: number;
}

export interface ModelUsage {
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}

export interface ArtifactUsage {
  artifact_id: string;
  title: string;
  cost_usd: number;
  versions: number;
}

export interface DailyBreakdown {
  date: string;
  cost_usd: number;
  artifact_count: number;
}

export interface UpdateBudgetResponse {
  monthly_budget_usd: number;
  monthly_spent_usd: number;
  remaining_usd: number;
}

// ── Health ──────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: "healthy" | "degraded";
  version: string;
  services: Record<string, "ok" | "error">;
}

// ── WebSocket ───────────────────────────────────────────────────────────

export interface WSEvent {
  type: string;
  payload: Record<string, unknown>;
}

// ── Common ──────────────────────────────────────────────────────────────

export interface ActionResponse {
  status: string;
  message: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}
