import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { afterEach, describe, expect, it } from "vitest";
import { buildApp } from "../../src/app.js";
import { createMcpServer } from "../../src/mcp/create-server.js";
import {
  authorization,
  claimAndApprove,
  createOwner,
  database,
  useCleanDatabase,
} from "../helpers.js";

useCleanDatabase();

let app: ReturnType<typeof buildApp> | undefined;
afterEach(async () => app?.close());

describe("MCP boundary", () => {
  it("exposes exactly five tools and forwards get_context through HTTP", async () => {
    app = buildApp({ db: database.db });
    const address = await app.listen({ host: "127.0.0.1", port: 0 });
    const owner = await createOwner();
    const agent = await claimAndApprove(app, owner.id, [
      "facts:write",
      "context:read:private",
    ]);
    const remembered = await app.inject({
      method: "POST",
      url: "/v1/facts",
      headers: authorization(agent.credential),
      payload: {
        subject: "person",
        predicate: "home_address",
        value: "7 Protocol Place, Sampletown",
        confidence: "confirmed",
        sensitivity: "private",
        source: { type: "direct-statement", reference: "synthetic MCP test" },
      },
    });
    expect(remembered.statusCode).toBe(201);

    const server = createMcpServer({
      baseUrl: address,
      credential: agent.credential,
    });
    const client = new Client({
      name: "megabrain-test-client",
      version: "0.0.1",
    });
    const [clientTransport, serverTransport] =
      InMemoryTransport.createLinkedPair();
    await Promise.all([
      server.connect(serverTransport),
      client.connect(clientTransport),
    ]);

    const tools = await client.listTools();
    expect(tools.tools.map((tool) => tool.name).sort()).toEqual([
      "correct",
      "forget",
      "get_context",
      "locate",
      "remember",
    ]);
    const result = await client.callTool({
      name: "get_context",
      arguments: { task: "distance between my home and the station" },
    });
    expect(result.isError).not.toBe(true);
    expect(JSON.stringify(result.structuredContent)).toContain(
      "7 Protocol Place, Sampletown",
    );
    await client.close();
    await server.close();
  });
});
