"use client";

/**
 * Git providers settings page.
 * Ref: TDD-05 Section 16.1, TDD-01 J6 Steps 1-3
 */

import { useState, useCallback } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod/v4";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, Trash2, CheckCircle, XCircle, Loader2, GitBranch, Webhook, AlertCircle } from "lucide-react";
import {
  useGitConnections, useCreateGitConnection, useTestGitConnection,
  useDeleteGitConnection, useGitRepos, useConfigureWebhook,
} from "@/lib/hooks/use-git-providers";
import type { GitConnectionItem, GitProvider } from "@/lib/types/api";

const addSchema = z.object({
  provider: z.enum(["github", "gitlab"]),
  display_name: z.string().min(1, "Name is required"),
  access_token: z.string().min(1, "Token is required"),
});
type AddValues = z.infer<typeof addSchema>;

export default function GitSettingsPage() {
  const { data, isLoading } = useGitConnections();
  const [addOpen, setAddOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<GitConnectionItem | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const connections = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--color-text-secondary)]">Connect your Git providers to enable code artifacts.</p>
        <Button onClick={() => setAddOpen(true)}><Plus className="h-4 w-4" /> Connect</Button>
      </div>

      {isLoading ? (
        <div className="space-y-4">{[1, 2].map((i) => <Skeleton key={i} className="h-28 w-full rounded-[var(--radius-lg)]" />)}</div>
      ) : connections.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <GitBranch className="h-8 w-8 text-[var(--color-text-tertiary)]" />
          <p className="text-sm text-[var(--color-text-secondary)]">No git providers connected.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {connections.map((conn) => (
            <ConnectionCard
              key={conn.id}
              connection={conn}
              expanded={expandedId === conn.id}
              onToggle={() => setExpandedId(expandedId === conn.id ? null : conn.id)}
              onDelete={() => setDeleteTarget(conn)}
            />
          ))}
        </div>
      )}

      <AddConnectionDialog open={addOpen} onOpenChange={setAddOpen} />
      <DeleteConnectionDialog target={deleteTarget} onClose={() => setDeleteTarget(null)} />
    </div>
  );
}

// ── Connection card ──────────────────────────────────────────────────
function ConnectionCard({ connection, expanded, onToggle, onDelete }: {
  connection: GitConnectionItem; expanded: boolean; onToggle: () => void; onDelete: () => void;
}) {
  const testConn = useTestGitConnection();
  const configureWebhook = useConfigureWebhook();
  const { data: reposData } = useGitRepos(expanded ? connection.id : "");
  const repos = reposData?.items ?? [];
  const [testResult, setTestResult] = useState<{ ok: boolean; user: string } | null>(null);

  const handleTest = useCallback(() => {
    testConn.mutate(connection.id, {
      onSuccess: (r) => setTestResult(r),
      onError: () => setTestResult({ ok: false, user: "" }),
    });
  }, [connection.id, testConn]);

  const statusVariant = connection.status === "active" ? "default" : "destructive";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-[var(--color-text-secondary)]" />
            <CardTitle className="text-base">{connection.display_name}</CardTitle>
            <Badge variant={statusVariant}>{connection.status}</Badge>
            <Badge variant="outline">{connection.provider}</Badge>
          </div>
          <div className="flex gap-1">
            <Button size="xs" variant="ghost" onClick={handleTest} disabled={testConn.isPending}>
              {testConn.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Test"}
            </Button>
            <Button size="xs" variant="ghost" onClick={onToggle}>
              {expanded ? "Collapse" : "Repos"}
            </Button>
            <Button size="icon-xs" variant="ghost" onClick={onDelete} aria-label="Delete connection">
              <Trash2 />
            </Button>
          </div>
        </div>
        {testResult && (
          <div className={`mt-1 flex items-center gap-1 text-xs ${testResult.ok ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>
            {testResult.ok ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
            {testResult.ok ? `Connected as ${testResult.user}` : "Connection failed"}
          </div>
        )}
      </CardHeader>
      {expanded && repos.length > 0 && (
        <CardContent>
          <div className="divide-y divide-[var(--color-border-primary)] rounded-[var(--radius-md)] border border-[var(--color-border-primary)]">
            {repos.map((repo) => {
              const fullName = repo.full_name ?? `${repo.owner}/${repo.name}`;
              return (
                <div key={fullName} className="flex items-center justify-between px-3 py-2">
                  <span className="truncate font-mono text-xs text-[var(--color-text-primary)]">{fullName}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    {repo.webhook_configured ? (
                      <Badge variant="outline" className="text-[10px] bg-[var(--color-success-subtle)] text-[var(--color-success)]">
                        <Webhook className="mr-1 h-2.5 w-2.5" /> Webhook
                      </Badge>
                    ) : (
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => configureWebhook.mutate(
                          { connectionId: connection.id, owner: repo.owner, repo: repo.name },
                          { onSuccess: () => toast.success("Webhook configured"), onError: (e) => toast.error(e.message || "Failed") },
                        )}
                        disabled={configureWebhook.isPending}
                      >
                        Configure Webhook
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

// ── Add connection dialog ────────────────────────────────────────────
function AddConnectionDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const createConn = useCreateGitConnection();
  const { register, handleSubmit, reset, formState: { errors } } = useForm<AddValues>({
    resolver: zodResolver(addSchema),
    defaultValues: { provider: "github", display_name: "", access_token: "" },
  });

  const onSubmit = (values: AddValues) => {
    createConn.mutate(values, {
      onSuccess: () => { toast.success("Connection created"); reset(); onOpenChange(false); },
      onError: (e) => toast.error(e.message || "Failed"),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Connect Git Provider</DialogTitle>
          <DialogDescription>Add a GitHub or GitLab PAT to enable code artifacts.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Provider</label>
            <select {...register("provider")} className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm">
              <option value="github">GitHub</option>
              <option value="gitlab">GitLab</option>
            </select>
          </div>
          <div className="space-y-2">
            <label htmlFor="git-name" className="text-sm font-medium">Display Name</label>
            <Input id="git-name" placeholder="My GitHub" {...register("display_name")} />
            {errors.display_name && <p className="text-xs text-destructive">{errors.display_name.message}</p>}
          </div>
          <div className="space-y-2">
            <label htmlFor="git-token" className="text-sm font-medium">Personal Access Token</label>
            <Input id="git-token" type="password" placeholder="ghp_..." {...register("access_token")} />
            {errors.access_token && <p className="text-xs text-destructive">{errors.access_token.message}</p>}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={createConn.isPending}>
              {createConn.isPending ? <><Loader2 className="animate-spin" />Connecting...</> : "Connect"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Delete confirmation ──────────────────────────────────────────────
function DeleteConnectionDialog({ target, onClose }: { target: GitConnectionItem | null; onClose: () => void }) {
  const deleteConn = useDeleteGitConnection();
  return (
    <Dialog open={!!target} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-[var(--color-danger)]" /> Delete Connection
          </DialogTitle>
          <DialogDescription>
            Remove <strong>{target?.display_name}</strong>? All webhooks will stop working.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant="destructive" onClick={() => {
            if (!target) return;
            deleteConn.mutate(target.id, { onSuccess: () => { toast.success("Deleted"); onClose(); }, onError: (e) => toast.error(e.message || "Failed") });
          }} disabled={deleteConn.isPending}>
            {deleteConn.isPending ? <Loader2 className="animate-spin" /> : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
