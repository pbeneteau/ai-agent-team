export type FrontendArchetype =
  | "command-center"
  | "collection"
  | "detail"
  | "conversation";

export type WorkspaceShellArchetype = Exclude<FrontendArchetype, "conversation">;

export interface ArchetypeMeta {
  label: string;
  description: string;
}

export const FRONTEND_ARCHETYPE_META: Record<FrontendArchetype, ArchetypeMeta> = {
  "command-center": {
    label: "Command Center",
    description: "Top-level operational overview with the clearest next actions first.",
  },
  collection: {
    label: "Collection",
    description: "Portfolio, inventory, or list view where scan speed matters more than ornament.",
  },
  detail: {
    label: "Detail",
    description: "Readout-style detail view that prioritizes content depth over dashboard chrome.",
  },
  conversation: {
    label: "Conversation",
    description: "Conversation workspace with the transcript and composer as the center of gravity.",
  },
};
