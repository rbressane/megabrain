import { asc, eq } from "drizzle-orm";
import { afterEach, describe, expect, it } from "vitest";
import { buildApp } from "../../src/app.js";
import {
  approveAgent,
  createBrainlink,
  revokeAgent,
} from "../../src/brainlinks/service.js";
import type { Scope } from "../../src/contracts.js";
import { agents, auditEvents, facts } from "../../src/db/schema.js";
import { createOwner, database, useCleanDatabase } from "../helpers.js";

useCleanDatabase();

let app: ReturnType<typeof buildApp> | undefined;
afterEach(async () => app?.close());

describe("cross-agent context portability", () => {
  it("shares a current fact across independent HTTP clients, corrects it, and revokes immediately", async () => {
    app = buildApp({ db: database.db });
    const address = await app.listen({ host: "127.0.0.1", port: 0 });
    const owner = await createOwner("Taylor Example");

    async function request(path: string, body: unknown, credential?: string) {
      return fetch(`${address}${path}`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...(credential ? { authorization: `Bearer ${credential}` } : {}),
        },
        body: JSON.stringify(body),
      });
    }

    async function connectAgent(name: string, scopes: Scope[]) {
      const { token } = await createBrainlink(database.db, owner.id, 60_000);
      const claimedResponse = await request("/v1/brainlinks/claim", {
        token,
        displayName: name,
        harnessType: `${name.toLowerCase().replaceAll(" ", "-")}-harness`,
        requestedScopes: scopes,
      });
      expect(claimedResponse.status).toBe(201);
      const claimed = (await claimedResponse.json()) as {
        requestId: string;
        claimSecret: string;
      };
      await approveAgent(database.db, claimed.requestId, scopes);
      const exchange = await request("/v1/brainlinks/exchange", claimed);
      expect(exchange.status).toBe(200);
      return {
        id: claimed.requestId,
        credential: ((await exchange.json()) as { credential: string })
          .credential,
      };
    }

    const agentA = await connectAgent("Agent A", [
      "facts:write",
      "facts:correct",
      "context:read:private",
    ]);
    const agentB = await connectAgent("Agent B", ["context:read:private"]);

    const remembered = await request(
      "/v1/facts",
      {
        subject: "person",
        predicate: "home_address",
        value: "18 Example Avenue, Sampletown",
        confidence: "confirmed",
        sensitivity: "private",
        source: {
          type: "direct-statement",
          reference: "synthetic user statement",
        },
      },
      agentA.credential,
    );
    expect(remembered.status).toBe(201);
    const rememberedFact = (await remembered.json()) as { id: string };

    const firstContext = await request(
      "/v1/context",
      { task: "Calculate the distance between my home and the supermarket." },
      agentB.credential,
    );
    expect(firstContext.status).toBe(200);
    const firstBody = (await firstContext.json()) as {
      facts: Array<{
        id: string;
        value: unknown;
        confidence: string;
        provenance: { sourceReference: string };
      }>;
    };
    expect(firstBody.facts).toHaveLength(1);
    expect(firstBody.facts[0]).toMatchObject({
      id: rememberedFact.id,
      value: "18 Example Avenue, Sampletown",
      confidence: "confirmed",
      provenance: { sourceReference: "synthetic user statement" },
    });

    const correction = await request(
      "/v1/facts/correct",
      {
        previousFactId: rememberedFact.id,
        replacementValue: "42 Testing Road, Sampletown",
        source: { type: "direct-statement", reference: "synthetic correction" },
        reason: "address changed",
      },
      agentA.credential,
    );
    expect(correction.status).toBe(200);
    const replacement = (await correction.json()) as {
      id: string;
      supersededFactId: string;
    };

    const secondContext = await request(
      "/v1/context",
      { task: "Calculate the distance between my home and the supermarket." },
      agentB.credential,
    );
    const secondBody = (await secondContext.json()) as {
      facts: Array<{ id: string; value: unknown }>;
    };
    expect(secondBody.facts).toHaveLength(1);
    expect(secondBody.facts[0]).toMatchObject({
      id: replacement.id,
      value: "42 Testing Road, Sampletown",
    });
    expect(JSON.stringify(secondBody)).not.toContain("18 Example Avenue");

    const history = await database.db
      .select()
      .from(facts)
      .orderBy(asc(facts.createdAt));
    expect(history).toHaveLength(2);
    expect(history[0]).toMatchObject({
      id: rememberedFact.id,
      status: "superseded",
    });
    expect(history[1]).toMatchObject({
      id: replacement.id,
      status: "active",
      supersedesFactId: rememberedFact.id,
    });
    expect(history[1]!.sourceReference).toBe("synthetic correction");

    await revokeAgent(database.db, agentB.id);
    const revoked = await request(
      "/v1/context",
      { task: "Calculate the distance between my home and the supermarket." },
      agentB.credential,
    );
    expect(revoked.status).toBe(403);
    expect(
      ((await revoked.json()) as { error: { code: string } }).error.code,
    ).toBe("AGENT_REVOKED");
    expect(
      (
        await database.db.select().from(agents).where(eq(agents.id, agentB.id))
      )[0]!.status,
    ).toBe("revoked");

    const eventTypes = (
      await database.db
        .select()
        .from(auditEvents)
        .orderBy(asc(auditEvents.createdAt))
    ).map((event) => event.eventType);
    for (const expected of [
      "brainlink.created",
      "brainlink.claimed",
      "agent.approved",
      "agent.credential_issued",
      "fact.created",
      "fact.read",
      "fact.corrected",
      "fact.superseded",
      "agent.revoked",
      "access.denied",
    ]) {
      expect(eventTypes).toContain(expected);
    }
    const auditText = JSON.stringify(
      await database.db.select().from(auditEvents),
    );
    expect(auditText).not.toContain("18 Example Avenue");
    expect(auditText).not.toContain("42 Testing Road");
    expect(auditText).not.toContain(agentA.credential);
    expect(auditText).not.toContain(agentB.credential);
  });
});
