"use client";

import { useEffect, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, type OrgNode, type AgentStatus } from "@/lib/api";
import { Loader2 } from "lucide-react";
import { useState } from "react";

const STATUS_COLORS: Record<AgentStatus, string> = {
  pending: "#94a3b8",
  learning: "#f59e0b",
  ready: "#22c55e",
  working: "#3b82f6",
  error: "#ef4444",
};

const ROLE_BG: Record<string, string> = {
  associate: "linear-gradient(135deg, #7c3aed, #4f46e5)",
  team_lead: "linear-gradient(135deg, #0ea5e9, #6366f1)",
  specialist: "linear-gradient(135deg, #64748b, #94a3b8)",
};

interface FlatNode extends OrgNode {
  parent_id: string | null;
}

function flattenNodes(nodes: OrgNode[], parentId: string | null = null): FlatNode[] {
  return nodes.flatMap((n) => [
    { ...n, parent_id: parentId ?? n.parent_id },
    ...flattenNodes(n.children, n.id),
  ]);
}

function buildLayout(flat: FlatNode[]): { nodes: Node[]; edges: Edge[] } {
  const levelMap: Record<string, number> = {};
  const parentMap: Record<string, string | null> = {};
  flat.forEach((n) => (parentMap[n.id] = n.parent_id));

  function getLevel(id: string): number {
    if (levelMap[id] !== undefined) return levelMap[id];
    const parent = parentMap[id];
    const level = parent ? getLevel(parent) + 1 : 0;
    levelMap[id] = level;
    return level;
  }
  flat.forEach((n) => getLevel(n.id));

  const levelGroups: Record<number, FlatNode[]> = {};
  flat.forEach((n) => {
    const l = levelMap[n.id];
    if (!levelGroups[l]) levelGroups[l] = [];
    levelGroups[l].push(n);
  });

  const nodes: Node[] = flat.map((n) => {
    const level = levelMap[n.id];
    const siblings = levelGroups[level];
    const idx = siblings.findIndex((s) => s.id === n.id);
    const totalWidth = siblings.length * 220;
    const x = idx * 220 - totalWidth / 2 + 110;
    const y = level * 180;

    return {
      id: n.id,
      position: { x, y },
      data: { label: n.name, title: n.title, role: n.role, status: n.status, model_tier: (n as OrgNode & { model_tier?: string }).model_tier },
      type: "agentNode",
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    };
  });

  const edges: Edge[] = flat
    .filter((n) => n.parent_id && flat.some((p) => p.id === n.parent_id))
    .map((n) => ({
      id: `e-${n.parent_id}-${n.id}`,
      source: n.parent_id!,
      target: n.id,
      type: "smoothstep",
      style: { stroke: "#cbd5e1", strokeWidth: 2 },
    }));

  return { nodes, edges };
}

function AgentNode({ data }: { data: { label: string; title: string; role: string; status: AgentStatus; model_tier?: string } }) {
  return (
    <>
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: "#cbd5e1", width: 8, height: 8, border: "2px solid #fff" }}
      />
      <div
        style={{
          background: "#ffffff",
          border: "1.5px solid #e2e8f0",
          borderRadius: "12px",
          padding: "12px 16px",
          minWidth: 145,
          boxShadow: "0 2px 10px rgba(0,0,0,0.07)",
          textAlign: "center",
          cursor: "pointer",
        }}
      >
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: "50%",
            margin: "0 auto 8px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: ROLE_BG[data.role] ?? ROLE_BG.specialist,
            color: "white",
            fontWeight: "bold",
            fontSize: 18,
          }}
        >
          {data.label.charAt(0)}
        </div>
        <div style={{ fontWeight: 600, fontSize: 13, color: "#1e293b" }}>{data.label}</div>
        <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>{data.title}</div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
          <div
            style={{
              display: "inline-block",
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: STATUS_COLORS[data.status] ?? "#94a3b8",
            }}
          />
          {data.model_tier === "opus" && (
            <span style={{ fontSize: 9, color: "#7c3aed", fontWeight: 600, letterSpacing: "0.05em" }}>
              OPUS
            </span>
          )}
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: "#cbd5e1", width: 8, height: 8, border: "2px solid #fff" }}
      />
    </>
  );
}

const nodeTypes = { agentNode: AgentNode };

interface OrgChartProps {
  onAgentClick?: (agentId: string, agentName: string) => void;
  /** Increment this value from the parent to trigger a data reload. */
  refreshKey?: number;
}

export function OrgChart({ onAgentClick, refreshKey }: OrgChartProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const orgNodes = await api.getOrganigramme();
      const flat = flattenNodes(orgNodes);
      if (flat.length === 0) {
        setLoading(false);
        return;
      }
      const { nodes: n, edges: e } = buildLayout(flat);
      setNodes(n);
      setEdges(e);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [setNodes, setEdges]);

  // Initial load
  useEffect(() => {
    load();
  }, [load]);

  // Reload when parent signals a change via refreshKey
  useEffect(() => {
    if (refreshKey !== undefined && refreshKey > 0) {
      load();
    }
  }, [refreshKey, load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <div className="text-6xl mb-4">🏗️</div>
        <h3 className="text-lg font-semibold text-slate-700 mb-2">Aucune équipe créée</h3>
        <p className="text-sm text-slate-500">
          Parlez à Alex dans le chat pour construire votre équipe d&apos;agents.
        </p>
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.3 }}
      nodesDraggable={false}
      onNodeClick={(_event, node) => {
        if (onAgentClick) onAgentClick(node.id, node.data.label as string);
      }}
    >
      <Background color="#f1f5f9" gap={24} />
      <Controls />
      <MiniMap maskColor="rgba(241, 245, 249, 0.7)" />
    </ReactFlow>
  );
}
