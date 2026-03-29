"use client";

/**
 * MCP connections settings page.
 * Ref: TDD-05 Section 16.2, TDD-01 J6 Steps 4-6
 */

import { useState, useCallback } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod/v4";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, Trash2, Plug, CheckCircle, XCircle, Loader2, AlertCircle, RefreshCw } from "lucide-react";
import {
  useMcpConnections, useCreateMcpConnection, useTestMcpConnection,
  useDiscoverMcpTools, useDeleteMcpConnection,
} from "@/lib/hooks/use-settings";
import type { McpConnectionItem } from "@/lib/types/api";

const addSchema = z.object({
  name: z.string().min(1, "Name is required"),
  server_url: z.string().min(1, "URL is required"),
  auth_type: z.enum(["api_key", "oauth", "none"]),
});
type AddValues = z.infer<typeof addSchema>;

export default function McpSettingsPage() {
  const { data, isLoading } = useMcpConnections();
  const [addOpen, setAddOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<McpConnectionItem | null>(null);

  const connections = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--color-text-secondary)]">Connect MCP servers to give your agents external tools.</p>
        <Button onClick={() => setAddOpen(true)}><Plus className="h-4 w-4" /> Add Connection</Button>
      </div>

      {isLoading ? (
        <div className="space-y-4">{[1, 2].map((i) => <Skeleton key={i} className="h-28 w-full rounded-[var(--radius-lg)]" />)}</div>
      ) : connections.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <Plug className="h-8 w-8 text-[var(--color-text-tertiary)]" />
          <p className="text-sm text-[var(--color-text-secondary)]">No MCP connections configured.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {connections.map((conn) => (
            <McpCard key={conn.id} connection={conn} onDelete={() => setDeleteTarget(conn)} />
          ))}
        </div>
      )}

      <AddMcpDialog open={addOpen} onOpenChange={setAddOpen} />

      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><AlertCircle className="h-5 w-5 text-[var(--color-danger)]" /> Delete Connection</DialogTitle>
            <DialogDescription>Remove <strong>{deleteTarget?.name}</strong>? Agents will lose access to its tools.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <DeleteMcpButton id={deleteTarget?.id ?? ""} onDone={() => setDeleteTarget(null)} />
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function DeleteMcpButton({ id, onDone }: { id: string; onDone: () => void }) {
  const deleteMcp = useDeleteMcpConnection();
  return (
    <Button variant="destructive" onClick={() => deleteMcp.mutate(id, {
      onSuccess: () => { toast.success("Deleted"); onDone(); },
      onError: (e) => toast.error(e.message || "Failed"),
    })} disabled={deleteMcp.isPending}>
      {deleteMcp.isPending ? <Loader2 className="animate-spin" /> : "Delete"}
    </Button>
  );
}

function McpCard({ connection, onDelete }: { connection: McpConnectionItem; onDelete: () => void }) {
  const testMcp = useTestMcpConnection();
  const discoverTools = useDiscoverMcpTools();
  const [testResult, setTestResult] = useState<{ ok: boolean } | null>(null);
  const tools = connection.discovered_tools ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Plug className="h-4 w-4 text-[var(--color-text-secondary)]" />
            <CardTitle className="text-base">{connection.name}</CardTitle>
            <Badge variant={connection.status === "active" ? "default" : "destructive"}>{connection.status}</Badge>
          </div>
          <div className="flex gap-1">
            <Button size="xs" variant="ghost" onClick={() => testMcp.mutate(connection.id, {
              onSuccess: (r) => setTestResult(r),
              onError: () => setTestResult({ ok: false }),
            })} disabled={testMcp.isPending}>
              {testMcp.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Test"}
            </Button>
            <Button size="xs" variant="ghost" onClick={() => discoverTools.mutate(connection.id, {
              onSuccess: () => toast.success("Tools rediscovered"),
              onError: (e) => toast.error(e.message || "Failed"),
            })} disabled={discoverTools.isPending}>
              <RefreshCw className="h-3 w-3" /> Rediscover
            </Button>
            <Button size="icon-xs" variant="ghost" onClick={onDelete} aria-label="Delete"><Trash2 /></Button>
          </div>
        </div>
        <p className="text-xs text-[var(--color-text-tertiary)]">{connection.server_url}</p>
        {testResult && (
          <div className={`mt-1 flex items-center gap-1 text-xs ${testResult.ok ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>
            {testResult.ok ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
            {testResult.ok ? "Connected" : "Connection failed"}
          </div>
        )}
      </CardHeader>
      {tools.length > 0 && (
        <CardContent>
          <p className="mb-2 text-xs font-medium text-[var(--color-text-secondary)]">Discovered Tools ({tools.length})</p>
          <div className="flex flex-wrap gap-1">
            {tools.map((t) => (
              <Badge key={t.name} variant="outline" className="text-[10px]">{t.name}</Badge>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

function AddMcpDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const createMcp = useCreateMcpConnection();
  const { register, handleSubmit, reset, formState: { errors } } = useForm<AddValues>({
    resolver: zodResolver(addSchema),
    defaultValues: { name: "", server_url: "", auth_type: "none" },
  });

  const onSubmit = (values: AddValues) => {
    createMcp.mutate(values, {
      onSuccess: () => { toast.success("Connection created"); reset(); onOpenChange(false); },
      onError: (e) => toast.error(e.message || "Failed"),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add MCP Connection</DialogTitle>
          <DialogDescription>Connect an MCP server to give your agents external tools.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="mcp-name" className="text-sm font-medium">Name</label>
            <Input id="mcp-name" placeholder="Notion" {...register("name")} />
            {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
          </div>
          <div className="space-y-2">
            <label htmlFor="mcp-url" className="text-sm font-medium">Server URL</label>
            <Input id="mcp-url" placeholder="https://mcp.example.com" {...register("server_url")} />
            {errors.server_url && <p className="text-xs text-destructive">{errors.server_url.message}</p>}
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Auth Type</label>
            <select {...register("auth_type")} className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm">
              <option value="none">None</option>
              <option value="api_key">API Key</option>
              <option value="oauth">OAuth</option>
            </select>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={createMcp.isPending}>
              {createMcp.isPending ? <><Loader2 className="animate-spin" />Creating...</> : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
