import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createMcpServer } from "./create-server.js";

const baseUrl = process.env.MEGABRAIN_BASE_URL ?? "http://127.0.0.1:3210";
const credential = process.env.MEGABRAIN_AGENT_TOKEN;
if (!credential) throw new Error("MEGABRAIN_AGENT_TOKEN is required");

const server = createMcpServer({ baseUrl, credential });
await server.connect(new StdioServerTransport());
