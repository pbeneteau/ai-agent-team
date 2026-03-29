"use client";

/**
 * File tree — builds a navigable tree from a flat file manifest.
 *
 * Phase 6 of CODE_FACTORY_UI_OVERHAUL.md
 */

import { useMemo } from "react";
import { FileCode, FolderOpen, Folder, ChevronRight, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FileManifestEntry } from "@/lib/types/api";

// ---------------------------------------------------------------------------
// Tree data structure
// ---------------------------------------------------------------------------

interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  children: TreeNode[];
  entry?: FileManifestEntry;
}

function buildTree(files: FileManifestEntry[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", isDir: true, children: [] };

  for (const file of files) {
    const parts = file.path.split("/");
    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;
      const currentPath = parts.slice(0, i + 1).join("/");

      let child = current.children.find((c) => c.name === part);
      if (!child) {
        child = {
          name: part,
          path: currentPath,
          isDir: !isLast,
          children: [],
          entry: isLast ? file : undefined,
        };
        current.children.push(child);
      }
      current = child;
    }
  }

  // Sort: directories first, then alphabetical
  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    for (const node of nodes) {
      if (node.isDir) sortNodes(node.children);
    }
  };
  sortNodes(root.children);

  return root.children;
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

interface FileTreeProps {
  files: FileManifestEntry[];
  selectedPath: string;
  onSelectFile: (path: string) => void;
}

export function FileTree({ files, selectedPath, onSelectFile }: FileTreeProps) {
  const tree = useMemo(() => buildTree(files), [files]);

  if (files.length === 0) {
    return (
      <p className="px-3 py-4 text-xs text-[var(--color-text-tertiary)]">
        No files in this version.
      </p>
    );
  }

  return (
    <div className="py-1">
      {tree.map((node) => (
        <TreeNodeItem
          key={node.path}
          node={node}
          depth={0}
          selectedPath={selectedPath}
          onSelectFile={onSelectFile}
        />
      ))}
    </div>
  );
}

interface TreeNodeItemProps {
  node: TreeNode;
  depth: number;
  selectedPath: string;
  onSelectFile: (path: string) => void;
}

function TreeNodeItem({ node, depth, selectedPath, onSelectFile }: TreeNodeItemProps) {
  const isSelected = !node.isDir && node.path === selectedPath;

  if (node.isDir) {
    // Directories are always expanded (small file trees)
    return (
      <div>
        <div
          className="flex items-center gap-1 px-2 py-0.5 text-xs text-[var(--color-text-secondary)]"
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
        >
          <ChevronDown className="h-3 w-3 shrink-0 text-[var(--color-text-tertiary)]" />
          <FolderOpen className="h-3.5 w-3.5 shrink-0 text-[var(--color-text-tertiary)]" />
          <span className="truncate">{node.name}</span>
        </div>
        {node.children.map((child) => (
          <TreeNodeItem
            key={child.path}
            node={child}
            depth={depth + 1}
            selectedPath={selectedPath}
            onSelectFile={onSelectFile}
          />
        ))}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onSelectFile(node.path)}
      className={cn(
        "flex w-full items-center gap-1.5 px-2 py-1 text-xs transition-colors",
        isSelected
          ? "bg-[var(--color-accent-subtle)] text-[var(--color-accent)] font-medium"
          : "text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)]",
      )}
      style={{ paddingLeft: `${depth * 12 + 20}px` }}
    >
      <FileCode className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate font-mono">{node.name}</span>
    </button>
  );
}
