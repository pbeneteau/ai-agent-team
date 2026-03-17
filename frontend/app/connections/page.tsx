"use client";

import { Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Cable,
  GitBranch,
  Github,
  Loader2,
  PlugZap,
  RefreshCw,
  Save,
  Search,
  ShieldAlert,
  Trash2,
} from "lucide-react";

import { DomainSecondaryNav } from "@/components/layout/DomainSecondaryNav";
import { EmptyState } from "@/components/layout/EmptyState";
import { SectionPanel } from "@/components/layout/SectionPanel";
import { StatBlock } from "@/components/layout/StatBlock";
import { WorkspacePageShell } from "@/components/layout/WorkspacePageShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  extractApiErrorMessage,
  type GitProvider,
  type GitProviderConnection,
  type GitRemoteRepo,
  type McpConnection,
  type McpToolDescriptor,
} from "@/lib/api";
import { formatRelativeTimestamp } from "@/lib/config/formatting";

interface McpConnectionDraft {
  name: string;
  endpoint_url: string;
  enabled: boolean;
  auth_header_name: string;
  auth_token: string;
  notes: string;
}

interface GitConnectionDraft {
  provider: GitProvider;
  name: string;
  base_url: string;
  enabled: boolean;
  auth_token: string;
  notes: string;
}

const EMPTY_MCP_DRAFT: McpConnectionDraft = {
  name: "",
  endpoint_url: "",
  enabled: true,
  auth_header_name: "Authorization",
  auth_token: "",
  notes: "",
};

const EMPTY_GIT_DRAFT: GitConnectionDraft = {
  provider: "github",
  name: "",
  base_url: "",
  enabled: true,
  auth_token: "",
  notes: "",
};

type ActiveEditor = "git:new" | `git:${string}` | "mcp:new" | `mcp:${string}` | null;

function getStatusBadgeClass(status: "healthy" | "degraded" | "unavailable" | "unknown"): string {
  switch (status) {
    case "healthy":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "degraded":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "unavailable":
      return "border-rose-200 bg-rose-50 text-rose-700";
    case "unknown":
      return "border-slate-200 bg-slate-100 text-slate-600";
    default: {
      const exhaustive: never = status;
      return exhaustive;
    }
  }
}

function getCapabilityBadgeClass(tool: McpToolDescriptor): string {
  return tool.read_only
    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
    : "border-amber-200 bg-amber-50 text-amber-700";
}

function getProviderLabel(provider: GitProvider): string {
  switch (provider) {
    case "github":
      return "GitHub";
    case "gitlab":
      return "GitLab";
    default: {
      const exhaustive: never = provider;
      return exhaustive;
    }
  }
}

export default function ConnectionsPage() {
  return (
    <Suspense fallback={<div className="h-full min-h-0 bg-[var(--ops-canvas)]" />}>
      <ConnectionsPageContent />
    </Suspense>
  );
}

function ConnectionsPageContent() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [activeEditor, setActiveEditor] = useState<ActiveEditor>(null);

  const [mcpConnections, setMcpConnections] = useState<McpConnection[]>([]);
  const [mcpDraft, setMcpDraft] = useState<McpConnectionDraft>(EMPTY_MCP_DRAFT);
  const [mcpSaving, setMcpSaving] = useState(false);
  const [mcpBusyAction, setMcpBusyAction] = useState<string | null>(null);

  const [gitConnections, setGitConnections] = useState<GitProviderConnection[]>([]);
  const [gitDraft, setGitDraft] = useState<GitConnectionDraft>(EMPTY_GIT_DRAFT);
  const [gitSaving, setGitSaving] = useState(false);
  const [gitBusyAction, setGitBusyAction] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const [mcp, git] = await Promise.all([api.getMcpConnections(), api.getGitProviderConnections()]);
      setMcpConnections(mcp);
      setGitConnections(git);
      setError(null);
    } catch (err) {
      setError(extractApiErrorMessage(err, "Unable to load connections."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const selectedGitConnection = useMemo(() => {
    if (!activeEditor?.startsWith("git:") || activeEditor === "git:new") {
      return null;
    }
    const connectionId = activeEditor.slice(4);
    return gitConnections.find((item) => item.id === connectionId) ?? null;
  }, [activeEditor, gitConnections]);

  const selectedMcpConnection = useMemo(() => {
    if (!activeEditor?.startsWith("mcp:") || activeEditor === "mcp:new") {
      return null;
    }
    const connectionId = activeEditor.slice(4);
    return mcpConnections.find((item) => item.id === connectionId) ?? null;
  }, [activeEditor, mcpConnections]);

  const isGitDialogOpen = activeEditor === "git:new" || (activeEditor?.startsWith("git:") ?? false);
  const isMcpDialogOpen = activeEditor === "mcp:new" || (activeEditor?.startsWith("mcp:") ?? false);

  useEffect(() => {
    if (activeEditor === "mcp:new" || !selectedMcpConnection) {
      setMcpDraft(EMPTY_MCP_DRAFT);
      return;
    }
    setMcpDraft({
      name: selectedMcpConnection.name,
      endpoint_url: selectedMcpConnection.endpoint_url,
      enabled: selectedMcpConnection.enabled,
      auth_header_name: selectedMcpConnection.auth_header_name,
      auth_token: "",
      notes: selectedMcpConnection.notes,
    });
  }, [activeEditor, selectedMcpConnection]);

  useEffect(() => {
    if (activeEditor === "git:new" || !selectedGitConnection) {
      setGitDraft(EMPTY_GIT_DRAFT);
      return;
    }
    setGitDraft({
      provider: selectedGitConnection.provider,
      name: selectedGitConnection.name,
      base_url: selectedGitConnection.base_url,
      enabled: selectedGitConnection.enabled,
      auth_token: "",
      notes: selectedGitConnection.notes,
    });
  }, [activeEditor, selectedGitConnection]);

  async function handleSaveMcp() {
    setMcpSaving(true);
    setActionMessage(null);
    try {
      if (selectedMcpConnection) {
        await api.updateMcpConnection(selectedMcpConnection.id, {
          name: mcpDraft.name,
          endpoint_url: mcpDraft.endpoint_url,
          enabled: mcpDraft.enabled,
          auth_header_name: mcpDraft.auth_header_name,
          auth_token: mcpDraft.auth_token || undefined,
          notes: mcpDraft.notes,
        });
        setActionMessage("MCP connection updated.");
      } else {
        await api.createMcpConnection(mcpDraft);
        setActionMessage("MCP connection created.");
      }
      setMcpDraft((current) => ({ ...current, auth_token: "" }));
      await load(true);
      setActiveEditor(null);
    } catch (err) {
      setError(extractApiErrorMessage(err, "Unable to save the MCP connection."));
    } finally {
      setMcpSaving(false);
    }
  }

  async function handleSaveGit() {
    setGitSaving(true);
    setActionMessage(null);
    try {
      if (selectedGitConnection) {
        await api.updateGitProviderConnection(selectedGitConnection.id, {
          name: gitDraft.name,
          base_url: gitDraft.base_url || undefined,
          enabled: gitDraft.enabled,
          auth_token: gitDraft.auth_token || undefined,
          notes: gitDraft.notes,
        });
        setActionMessage(`${getProviderLabel(gitDraft.provider)} connection updated.`);
      } else {
        await api.createGitProviderConnection({
          provider: gitDraft.provider,
          name: gitDraft.name,
          base_url: gitDraft.base_url || undefined,
          enabled: gitDraft.enabled,
          auth_token: gitDraft.auth_token,
          notes: gitDraft.notes,
        });
        setActionMessage(`${getProviderLabel(gitDraft.provider)} connection created.`);
      }
      setGitDraft((current) => ({ ...current, auth_token: "" }));
      await load(true);
      setActiveEditor(null);
    } catch (err) {
      setError(extractApiErrorMessage(err, "Unable to save the git provider connection."));
    } finally {
      setGitSaving(false);
    }
  }

  async function handleDeleteMcp(connectionId: string) {
    if (!confirm("Delete this MCP connection?")) return;
    setMcpBusyAction(`delete:${connectionId}`);
    try {
      await api.deleteMcpConnection(connectionId);
      if (activeEditor === `mcp:${connectionId}`) {
        setActiveEditor(null);
      }
      await load(true);
      setActionMessage("MCP connection deleted.");
    } catch (err) {
      setError(extractApiErrorMessage(err, "Unable to delete the MCP connection."));
    } finally {
      setMcpBusyAction(null);
    }
  }

  async function handleDeleteGit(connectionId: string) {
    if (!confirm("Delete this git provider connection?")) return;
    setGitBusyAction(`delete:${connectionId}`);
    try {
      await api.deleteGitProviderConnection(connectionId);
      if (activeEditor === `git:${connectionId}`) {
        setActiveEditor(null);
      }
      await load(true);
      setActionMessage("Git provider connection deleted.");
    } catch (err) {
      setError(extractApiErrorMessage(err, "Unable to delete the git provider connection."));
    } finally {
      setGitBusyAction(null);
    }
  }

  async function handleTestMcp(connectionId: string) {
    setMcpBusyAction(`test:${connectionId}`);
    try {
      const result = await api.testMcpConnection(connectionId);
      await load(true);
      setActionMessage(result.ok ? "MCP connection is healthy." : result.error || "MCP connection test failed.");
    } catch (err) {
      setError(extractApiErrorMessage(err, "Unable to test the MCP connection."));
    } finally {
      setMcpBusyAction(null);
    }
  }

  async function handleDiscoverMcp(connectionId: string) {
    setMcpBusyAction(`discover:${connectionId}`);
    try {
      await api.discoverMcpTools(connectionId);
      await load(true);
      setActionMessage("MCP tools discovered successfully.");
    } catch (err) {
      setError(extractApiErrorMessage(err, "Unable to discover MCP tools."));
    } finally {
      setMcpBusyAction(null);
    }
  }

  async function handleTestGit(connectionId: string) {
    setGitBusyAction(`test:${connectionId}`);
    try {
      const result = await api.testGitProviderConnection(connectionId);
      await load(true);
      setActionMessage(
        result.ok
          ? `${result.account_username || "Account"} authenticated successfully.`
          : result.error || "Git provider test failed.",
      );
    } catch (err) {
      setError(extractApiErrorMessage(err, "Unable to test the git provider connection."));
    } finally {
      setGitBusyAction(null);
    }
  }

  async function handleRefreshGitRepos(connectionId: string) {
    setGitBusyAction(`refresh:${connectionId}`);
    try {
      await api.refreshGitProviderRepos(connectionId);
      await load(true);
      setActionMessage("Accessible repositories refreshed.");
    } catch (err) {
      setError(extractApiErrorMessage(err, "Unable to refresh repositories for this provider."));
    } finally {
      setGitBusyAction(null);
    }
  }

  const totalConnections = gitConnections.length + mcpConnections.length;
  const healthyConnections =
    gitConnections.filter((connection) => connection.status === "healthy").length +
    mcpConnections.filter((connection) => connection.status === "healthy").length;
  const degradedConnections =
    gitConnections.filter((connection) => connection.status === "degraded" || connection.status === "unavailable").length +
    mcpConnections.filter((connection) => connection.status === "degraded" || connection.status === "unavailable").length;
  const totalRepos = gitConnections.reduce((count, connection) => count + connection.discovered_repos.length, 0);
  const totalTools = mcpConnections.reduce((count, connection) => count + connection.discovered_tools.length, 0);

  return (
    <WorkspacePageShell
      title="Infrastructure"
      description="Monitor connection health first, then open the editor surfaces for backend-executed MCP and git integrations."
      meta={
        <>
          <span>{mcpConnections.length} MCP connection(s)</span>
          <span>{gitConnections.length} git connection(s)</span>
          <span>All remote actions are executed by the backend, never directly from the browser.</span>
        </>
      }
      actions={
        <Button variant="outline" size="sm" onClick={() => load(true)} className="gap-2 rounded-full">
          {refreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          Refresh
        </Button>
      }
    >
      {error ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      ) : null}
      {actionMessage ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {actionMessage}
        </div>
      ) : null}

      <DomainSecondaryNav domain="observability" />

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        </div>
      ) : (
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <StatBlock label="Configured" value={totalConnections} description="Total infrastructure connections" icon={<Cable className="size-4" />} />
            <StatBlock
              label="Healthy"
              value={healthyConnections}
              description="Connections currently passing health checks"
              tone={healthyConnections > 0 ? "positive" : "default"}
              icon={<ShieldAlert className="size-4" />}
            />
            <StatBlock
              label="Needs attention"
              value={degradedConnections}
              description="Degraded or unavailable connections"
              tone={degradedConnections > 0 ? "warning" : "default"}
              icon={<PlugZap className="size-4" />}
            />
            <StatBlock
              label="Indexed surface"
              value={totalRepos + totalTools}
              description={`${totalRepos} repo(s) and ${totalTools} tool(s) discovered`}
              icon={<Search className="size-4" />}
            />
          </div>

          <SectionPanel
            eyebrow="System"
            title="Infrastructure posture"
            description="Read health and coverage first. Open configuration only when you need to edit or test a connection."
            tone="subtle"
          >
            <div className="grid gap-4 xl:grid-cols-3">
              <InfrastructurePill
                title="Git providers"
                description={
                  gitConnections.length > 0
                    ? `${gitConnections.filter((item) => item.status === "healthy").length} healthy connection(s), ${totalRepos} repo(s) indexed.`
                    : "No git provider connection configured yet."
                }
                icon={<GitBranch className="size-4" />}
              />
              <InfrastructurePill
                title="MCP"
                description={
                  mcpConnections.length > 0
                    ? `${mcpConnections.filter((item) => item.status === "healthy").length} healthy connection(s), ${totalTools} tool(s) discovered.`
                    : "No MCP connection configured yet."
                }
                icon={<Cable className="size-4" />}
              />
              <InfrastructurePill
                title="Execution model"
                description="Remote actions stay backend-executed. Secrets are never re-exposed in the browser editor."
                icon={<ShieldAlert className="size-4" />}
              />
            </div>
          </SectionPanel>

          <SectionPanel
            eyebrow="Inventory"
            title="Git connections"
            description="Status-first inventory for repository integrations. Multiple connections per provider are supported."
            actions={
              <Button
                size="sm"
                className="gap-2 rounded-full"
                onClick={() => {
                  setGitDraft(EMPTY_GIT_DRAFT);
                  setActiveEditor("git:new");
                }}
              >
                <Github className="h-3.5 w-3.5" />
                Add git connection
              </Button>
            }
          >
            {gitConnections.length === 0 ? (
              <EmptyState description="No git provider connection configured yet." />
            ) : (
              <div className="grid gap-4 xl:grid-cols-2">
                {gitConnections.map((connection) => (
                  <InventoryCard
                    key={connection.id}
                    title={connection.name}
                    subtitle={`${getProviderLabel(connection.provider)} · ${connection.base_url}`}
                    status={connection.status}
                    metaItems={[
                      `${connection.discovered_repos.length} repo(s)`,
                      `${connection.total_repo_actions} remote action(s)`,
                      `Last test ${formatRelativeTimestamp(connection.last_tested_at)}`,
                    ]}
                    error={connection.last_error}
                    actions={
                      <>
                        <Button variant="outline" size="sm" onClick={() => setActiveEditor(`git:${connection.id}`)}>
                          Configure
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleTestGit(connection.id)}
                          disabled={gitBusyAction === `test:${connection.id}`}
                          className="gap-2"
                        >
                          {gitBusyAction === `test:${connection.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlugZap className="h-3.5 w-3.5" />}
                          Test
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleRefreshGitRepos(connection.id)}
                          disabled={gitBusyAction === `refresh:${connection.id}`}
                          className="gap-2"
                        >
                          {gitBusyAction === `refresh:${connection.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                          Refresh repos
                        </Button>
                      </>
                    }
                  />
                ))}
              </div>
            )}
          </SectionPanel>

          <SectionPanel
            eyebrow="Inventory"
            title="MCP connections"
            description="Multi-connection inventory for backend-executed MCP endpoints and discovered tools."
            actions={
              <Button
                size="sm"
                className="gap-2 rounded-full"
                onClick={() => {
                  setMcpDraft(EMPTY_MCP_DRAFT);
                  setActiveEditor("mcp:new");
                }}
              >
                <Cable className="h-3.5 w-3.5" />
                Add MCP connection
              </Button>
            }
          >
            {mcpConnections.length === 0 ? (
              <EmptyState description="No MCP connection configured yet." />
            ) : (
              <div className="grid gap-4 xl:grid-cols-2">
                {mcpConnections.map((connection) => (
                  <InventoryCard
                    key={connection.id}
                    title={connection.name}
                    subtitle={connection.endpoint_url}
                    status={connection.status}
                    metaItems={[
                      `${connection.discovered_tools.length} tool(s)`,
                      `${connection.total_calls} call(s)`,
                      `Last test ${formatRelativeTimestamp(connection.last_tested_at)}`,
                    ]}
                    error={connection.last_error}
                    actions={
                      <>
                        <Button variant="outline" size="sm" onClick={() => setActiveEditor(`mcp:${connection.id}`)}>
                          Configure
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleTestMcp(connection.id)}
                          disabled={mcpBusyAction === `test:${connection.id}`}
                          className="gap-2"
                        >
                          {mcpBusyAction === `test:${connection.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlugZap className="h-3.5 w-3.5" />}
                          Test
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDiscoverMcp(connection.id)}
                          disabled={mcpBusyAction === `discover:${connection.id}`}
                          className="gap-2"
                        >
                          {mcpBusyAction === `discover:${connection.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                          Discover
                        </Button>
                      </>
                    }
                  />
                ))}
              </div>
            )}
          </SectionPanel>
        </div>
      )}

      <Dialog open={isGitDialogOpen} onOpenChange={(open) => { if (!open) setActiveEditor(null); }}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{selectedGitConnection ? selectedGitConnection.name : "New git connection"}</DialogTitle>
            <DialogDescription>
              Configure a backend-executed git provider connection. Multiple connections per provider are supported.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 md:col-span-1">
              <span className="text-xs font-medium text-slate-600">Provider</span>
              <select
                value={gitDraft.provider}
                disabled={Boolean(selectedGitConnection)}
                onChange={(e) =>
                  setGitDraft((current) => ({
                    ...current,
                    provider: e.target.value as GitProvider,
                  }))
                }
                className="h-10 w-full rounded-xl border border-input bg-white px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 disabled:opacity-70"
              >
                <option value="github">GitHub</option>
                <option value="gitlab">GitLab</option>
              </select>
            </label>
            <label className="space-y-2 md:col-span-1">
              <span className="text-xs font-medium text-slate-600">Name</span>
              <Input value={gitDraft.name} onChange={(e) => setGitDraft((current) => ({ ...current, name: e.target.value }))} />
            </label>
            <label className="space-y-2 md:col-span-2">
              <span className="text-xs font-medium text-slate-600">Base URL</span>
              <Input
                placeholder={gitDraft.provider === "github" ? "https://api.github.com" : "https://gitlab.com/api/v4"}
                value={gitDraft.base_url}
                onChange={(e) => setGitDraft((current) => ({ ...current, base_url: e.target.value }))}
              />
            </label>
            <label className="space-y-2 md:col-span-2">
              <span className="text-xs font-medium text-slate-600">
                Personal access token {selectedGitConnection?.has_auth_token ? "(leave empty to keep current secret)" : ""}
              </span>
              <Input
                type="password"
                value={gitDraft.auth_token}
                onChange={(e) => setGitDraft((current) => ({ ...current, auth_token: e.target.value }))}
              />
            </label>
            <label className="space-y-2 md:col-span-2">
              <span className="text-xs font-medium text-slate-600">Notes</span>
              <Textarea
                value={gitDraft.notes}
                onChange={(e) => setGitDraft((current) => ({ ...current, notes: e.target.value }))}
                className="min-h-[100px]"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700 md:col-span-2">
              <input
                type="checkbox"
                checked={gitDraft.enabled}
                onChange={(e) =>
                  setGitDraft((current) => ({
                    ...current,
                    enabled: e.target.checked,
                  }))
                }
              />
              Enable this connection
            </label>
          </div>

          {selectedGitConnection ? (
            selectedGitConnection.discovered_repos.length === 0 ? (
              <EmptyState description="No repository indexed yet. Run Refresh repos first." />
            ) : (
              <div className="max-h-[280px] space-y-3 overflow-y-auto pr-1">
                {selectedGitConnection.discovered_repos.map((repo) => (
                  <GitRepoCard key={repo.full_name} repo={repo} />
                ))}
              </div>
            )
          ) : null}

          <DialogFooter showCloseButton>
            {selectedGitConnection ? (
              <>
                <Button
                  variant="outline"
                  onClick={() => handleDeleteGit(selectedGitConnection.id)}
                  disabled={gitBusyAction === `delete:${selectedGitConnection.id}`}
                  className="text-rose-600 hover:text-rose-700"
                >
                  {gitBusyAction === `delete:${selectedGitConnection.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                  Delete
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleTestGit(selectedGitConnection.id)}
                  disabled={gitBusyAction === `test:${selectedGitConnection.id}`}
                  className="gap-2"
                >
                  {gitBusyAction === `test:${selectedGitConnection.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlugZap className="h-3.5 w-3.5" />}
                  Test
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleRefreshGitRepos(selectedGitConnection.id)}
                  disabled={gitBusyAction === `refresh:${selectedGitConnection.id}`}
                  className="gap-2"
                >
                  {gitBusyAction === `refresh:${selectedGitConnection.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                  Refresh repos
                </Button>
              </>
            ) : null}
            <Button onClick={handleSaveGit} disabled={gitSaving || !gitDraft.name.trim()} className="gap-2">
              {gitSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              {selectedGitConnection ? "Save" : "Create connection"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isMcpDialogOpen} onOpenChange={(open) => { if (!open) setActiveEditor(null); }}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{selectedMcpConnection ? selectedMcpConnection.name : "New MCP connection"}</DialogTitle>
            <DialogDescription>
              Configure a backend-executed MCP connection. MCP remains multi-connection.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 md:col-span-1">
              <span className="text-xs font-medium text-slate-600">Name</span>
              <Input value={mcpDraft.name} onChange={(e) => setMcpDraft((current) => ({ ...current, name: e.target.value }))} />
            </label>
            <label className="space-y-2 md:col-span-1">
              <span className="text-xs font-medium text-slate-600">Auth header</span>
              <Input
                value={mcpDraft.auth_header_name}
                onChange={(e) => setMcpDraft((current) => ({ ...current, auth_header_name: e.target.value }))}
              />
            </label>
            <label className="space-y-2 md:col-span-2">
              <span className="text-xs font-medium text-slate-600">Endpoint URL</span>
              <Input
                placeholder="https://mcp.example.com/mcp"
                value={mcpDraft.endpoint_url}
                onChange={(e) => setMcpDraft((current) => ({ ...current, endpoint_url: e.target.value }))}
              />
            </label>
            <label className="space-y-2 md:col-span-2">
              <span className="text-xs font-medium text-slate-600">
                Auth token {selectedMcpConnection?.has_auth_token ? "(leave empty to keep current secret)" : "(optional)"}
              </span>
              <Input
                type="password"
                value={mcpDraft.auth_token}
                onChange={(e) => setMcpDraft((current) => ({ ...current, auth_token: e.target.value }))}
              />
            </label>
            <label className="space-y-2 md:col-span-2">
              <span className="text-xs font-medium text-slate-600">Notes</span>
              <Textarea
                value={mcpDraft.notes}
                onChange={(e) => setMcpDraft((current) => ({ ...current, notes: e.target.value }))}
                className="min-h-[100px]"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700 md:col-span-2">
              <input
                type="checkbox"
                checked={mcpDraft.enabled}
                onChange={(e) => setMcpDraft((current) => ({ ...current, enabled: e.target.checked }))}
              />
              Enable this connection
            </label>
          </div>

          {selectedMcpConnection?.discovered_tools.length ? (
            <div className="max-h-[280px] space-y-3 overflow-y-auto pr-1">
              {selectedMcpConnection.discovered_tools.map((tool) => (
                <div key={tool.name} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-slate-900">{tool.name}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {tool.description || "No description provided by the MCP server."}
                      </p>
                    </div>
                    <Badge variant="outline" className={getCapabilityBadgeClass(tool)}>
                      {tool.read_only ? "read-only" : "write-capable"}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          <DialogFooter showCloseButton>
            {selectedMcpConnection ? (
              <>
                <Button
                  variant="outline"
                  onClick={() => handleDeleteMcp(selectedMcpConnection.id)}
                  disabled={mcpBusyAction === `delete:${selectedMcpConnection.id}`}
                  className="text-rose-600 hover:text-rose-700"
                >
                  {mcpBusyAction === `delete:${selectedMcpConnection.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                  Delete
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleTestMcp(selectedMcpConnection.id)}
                  disabled={mcpBusyAction === `test:${selectedMcpConnection.id}`}
                  className="gap-2"
                >
                  {mcpBusyAction === `test:${selectedMcpConnection.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlugZap className="h-3.5 w-3.5" />}
                  Test
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleDiscoverMcp(selectedMcpConnection.id)}
                  disabled={mcpBusyAction === `discover:${selectedMcpConnection.id}`}
                  className="gap-2"
                >
                  {mcpBusyAction === `discover:${selectedMcpConnection.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                  Discover
                </Button>
              </>
            ) : null}
            <Button
              onClick={handleSaveMcp}
              disabled={mcpSaving || !mcpDraft.name.trim() || !mcpDraft.endpoint_url.trim()}
              className="gap-2"
            >
              {mcpSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              {selectedMcpConnection ? "Save" : "Create connection"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </WorkspacePageShell>
  );
}

function InfrastructurePill({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon: ReactNode;
}) {
  return (
    <div className="rounded-3xl border border-black/5 bg-white/88 px-4 py-4">
      <div className="flex items-start gap-3">
        <div className="rounded-2xl bg-slate-100 p-2 text-slate-700">{icon}</div>
        <div>
          <p className="text-sm font-semibold text-slate-900">{title}</p>
          <p className="mt-1 text-sm leading-6 text-slate-600">{description}</p>
        </div>
      </div>
    </div>
  );
}

function InventoryCard({
  title,
  subtitle,
  status,
  metaItems,
  error,
  actions,
}: {
  title: string;
  subtitle: string;
  status: "healthy" | "degraded" | "unavailable" | "unknown";
  metaItems: string[];
  error: string | null;
  actions: ReactNode;
}) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white px-5 py-5">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="truncate text-sm font-semibold text-slate-900">{title}</p>
              <Badge variant="outline" className={getStatusBadgeClass(status)}>
                {status}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
          {metaItems.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
        {error ? <p className="text-xs leading-5 text-rose-700">{error}</p> : null}
        <div className="flex flex-wrap gap-2">{actions}</div>
      </div>
    </div>
  );
}

function GitRepoCard({ repo }: { repo: GitRemoteRepo }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-900">{repo.full_name}</p>
          <a href={repo.web_url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs text-indigo-600 hover:text-indigo-700">
            {repo.web_url}
          </a>
        </div>
        <Badge variant="outline" className="border-slate-200 bg-slate-100 text-slate-600">
          {repo.default_branch}
        </Badge>
      </div>
      <p className="mt-3 text-[11px] text-slate-500">Clone URL: {repo.clone_url}</p>
    </div>
  );
}
