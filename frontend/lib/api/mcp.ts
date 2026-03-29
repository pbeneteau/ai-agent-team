import { request } from "@/lib/api-client";
import type {
  CreateMcpConnectionRequest,
  DiscoverToolsResponse,
  McpConnectionItem,
  TestMcpResponse,
} from "@/lib/types/api";

export const mcp = {
  list: () => request<{ items: McpConnectionItem[] }>("/mcp/connections"),

  create: (data: CreateMcpConnectionRequest) =>
    request<McpConnectionItem>("/mcp/connections", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  test: (id: string) =>
    request<TestMcpResponse>(`/mcp/connections/${id}/test`, { method: "POST" }),

  discoverTools: (id: string) =>
    request<DiscoverToolsResponse>(`/mcp/connections/${id}/discover-tools`, { method: "POST" }),

  delete: (id: string) =>
    request<void>(`/mcp/connections/${id}`, { method: "DELETE" }),
};
