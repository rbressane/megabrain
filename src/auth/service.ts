import { eq } from "drizzle-orm";
import { audit } from "../audit/service.js";
import type { Scope } from "../contracts.js";
import type { Database } from "../db/client.js";
import { agents, users, type Agent } from "../db/schema.js";
import { AppError } from "../errors.js";
import { tokenHashMatches } from "../security/tokens.js";

export interface AgentContext {
  agent: Agent;
  user: { id: string; displayName: string };
}

export function bearerToken(header: string | undefined): string | undefined {
  const match = /^Bearer\s+(.+)$/i.exec(header ?? "");
  return match?.[1];
}

export async function authenticateAgent(
  db: Database,
  token: string | undefined,
  requestId: string,
): Promise<AgentContext> {
  if (!token) {
    await audit(db, {
      eventType: "access.denied",
      outcome: "denied",
      reasonCode: "MISSING_CREDENTIAL",
      requestId,
    });
    throw new AppError(
      "MISSING_CREDENTIAL",
      "An agent credential is required",
      401,
    );
  }

  const candidates = await db.select().from(agents);
  const agent = candidates.find(
    (candidate) =>
      candidate.credentialHash &&
      tokenHashMatches(token, candidate.credentialHash),
  );
  if (!agent) {
    await audit(db, {
      eventType: "access.denied",
      outcome: "denied",
      reasonCode: "INVALID_CREDENTIAL",
      requestId,
    });
    throw new AppError(
      "INVALID_CREDENTIAL",
      "The agent credential is invalid",
      401,
    );
  }
  if (agent.status !== "active") {
    const reasonCode =
      agent.status === "revoked" ? "AGENT_REVOKED" : "AGENT_PENDING";
    await audit(db, {
      userId: agent.userId,
      agentId: agent.id,
      eventType: "access.denied",
      outcome: "denied",
      reasonCode,
      requestId,
    });
    throw new AppError(reasonCode, "The agent is not active", 403);
  }

  const [user] = await db
    .select({ id: users.id, displayName: users.displayName })
    .from(users)
    .where(eq(users.id, agent.userId))
    .limit(1);
  if (!user)
    throw new AppError(
      "USER_NOT_FOUND",
      "The credential owner no longer exists",
      401,
    );

  await db
    .update(agents)
    .set({ lastUsedAt: new Date() })
    .where(eq(agents.id, agent.id));
  await audit(db, {
    userId: agent.userId,
    agentId: agent.id,
    eventType: "agent.authenticated",
    outcome: "success",
    requestId,
  });
  return { agent, user };
}

export async function requireScope(
  db: Database,
  context: AgentContext,
  scope: Scope,
  requestId: string,
): Promise<void> {
  if (context.agent.approvedScopes.includes(scope)) return;
  await audit(db, {
    userId: context.user.id,
    agentId: context.agent.id,
    eventType: "access.denied",
    outcome: "denied",
    reasonCode: "SCOPE_DENIED",
    requestId,
    metadata: { requiredScope: scope },
  });
  throw new AppError("SCOPE_DENIED", `The operation requires ${scope}`, 403, {
    requiredScope: scope,
  });
}
