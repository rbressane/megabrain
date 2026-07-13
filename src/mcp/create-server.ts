import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  correctInputSchema,
  correctSchema,
  forgetSchema,
  getContextSchema,
  locateSchema,
  rememberSchema,
} from "../contracts.js";

export function createMcpServer(options: {
  baseUrl: string;
  credential: string;
}): McpServer {
  async function call(path: string, body: unknown) {
    const response = await fetch(`${options.baseUrl}${path}`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${options.credential}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
    });
    const payload: unknown = await response.json();
    const structuredContent =
      payload !== null && typeof payload === "object" && !Array.isArray(payload)
        ? (payload as Record<string, unknown>)
        : { value: payload };
    return {
      ...(response.ok ? {} : { isError: true }),
      content: [
        { type: "text" as const, text: JSON.stringify(payload, null, 2) },
      ],
      structuredContent,
    };
  }

  const server = new McpServer({ name: "megabrain", version: "0.0.1" });
  server.registerTool(
    "get_context",
    {
      description:
        "Compile current, task-relevant personal context within approved scopes.",
      inputSchema: getContextSchema.shape,
    },
    (input) => call("/v1/context", getContextSchema.parse(input)),
  );
  server.registerTool(
    "remember",
    {
      description: "Store a structured fact with provenance.",
      inputSchema: rememberSchema.shape,
    },
    (input) => call("/v1/facts", rememberSchema.parse(input)),
  );
  server.registerTool(
    "correct",
    {
      description:
        "Supersede a current fact with a replacement while preserving history.",
      inputSchema: correctInputSchema.shape,
    },
    (input) => call("/v1/facts/correct", correctSchema.parse(input)),
  );
  server.registerTool(
    "locate",
    {
      description:
        "Locate document, secret, or external record references without dereferencing them.",
      inputSchema: locateSchema.shape,
    },
    (input) => call("/v1/resources/locate", locateSchema.parse(input)),
  );
  server.registerTool(
    "forget",
    {
      description: "Tombstone a current fact so it is no longer returned.",
      inputSchema: forgetSchema.shape,
    },
    (input) => call("/v1/facts/forget", forgetSchema.parse(input)),
  );
  return server;
}
