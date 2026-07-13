import { sql } from "drizzle-orm";
import { beforeAll, beforeEach } from "vitest";
import type { FastifyInstance } from "fastify";
import { approveAgent, createBrainlink } from "../src/brainlinks/service.js";
import { createDatabase } from "../src/db/client.js";
import { runMigrations } from "../src/db/migrate.js";
import { users } from "../src/db/schema.js";
import type { Scope } from "../src/contracts.js";

export const TEST_DATABASE_URL = process.env.DATABASE_URL!;
export const database = createDatabase({ DATABASE_URL: TEST_DATABASE_URL });

export function useCleanDatabase(): void {
  beforeAll(async () => runMigrations(TEST_DATABASE_URL));
  beforeEach(async () => {
    await database.db.execute(sql`
      TRUNCATE TABLE audit_events, resource_references, facts, brainlinks, agents, users RESTART IDENTITY CASCADE
    `);
  });
}

export async function createOwner(displayName = "Casey Example") {
  const [user] = await database.db
    .insert(users)
    .values({ displayName })
    .returning();
  return user!;
}

export async function claimAndApprove(
  app: FastifyInstance,
  userId: string,
  scopes: Scope[],
  displayName = "Test Agent",
) {
  const { token } = await createBrainlink(database.db, userId, 60_000);
  const claim = await app.inject({
    method: "POST",
    url: "/v1/brainlinks/claim",
    payload: {
      token,
      displayName,
      harnessType: "test-harness",
      requestedScopes: scopes,
    },
  });
  if (claim.statusCode !== 201) throw new Error(claim.body);
  const claimBody = claim.json<{ requestId: string; claimSecret: string }>();
  await approveAgent(database.db, claimBody.requestId, scopes);
  const exchange = await app.inject({
    method: "POST",
    url: "/v1/brainlinks/exchange",
    payload: claimBody,
  });
  if (exchange.statusCode !== 200) throw new Error(exchange.body);
  const exchangeBody = exchange.json<{
    credential: string;
    scopes: string[];
  }>();
  return {
    agentId: claimBody.requestId,
    credential: exchangeBody.credential,
    claimSecret: claimBody.claimSecret,
    token,
  };
}

export function authorization(credential: string) {
  return { authorization: `Bearer ${credential}` };
}
