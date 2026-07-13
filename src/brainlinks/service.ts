import { and, eq, gt, isNull } from "drizzle-orm";
import { audit } from "../audit/service.js";
import { SCOPES, type Scope } from "../contracts.js";
import type { Database } from "../db/client.js";
import { agents, brainlinks } from "../db/schema.js";
import { AppError } from "../errors.js";
import { hashToken, issueToken, tokenHashMatches } from "../security/tokens.js";

export async function createBrainlink(
  db: Database,
  userId: string,
  expiresInMs: number,
) {
  const token = issueToken("mb_invite");
  const [record] = await db
    .insert(brainlinks)
    .values({
      userId,
      tokenHash: hashToken(token),
      expiresAt: new Date(Date.now() + expiresInMs),
    })
    .returning();
  if (!record) throw new Error("Brainlink insert returned no record");
  await audit(db, {
    userId,
    eventType: "brainlink.created",
    outcome: "success",
    targetType: "brainlink",
    targetId: record.id,
    metadata: { expiresAt: record.expiresAt.toISOString(), maximumClaims: 1 },
  });
  return { record, token };
}

export async function claimBrainlink(
  db: Database,
  input: {
    token: string;
    displayName: string;
    harnessType: string;
    requestedScopes: Scope[];
  },
  requestId: string,
) {
  const tokenHash = hashToken(input.token);
  const now = new Date();
  const claimed = await db.transaction(async (tx) => {
    const [link] = await tx
      .update(brainlinks)
      .set({ claimedAt: now })
      .where(
        and(
          eq(brainlinks.tokenHash, tokenHash),
          isNull(brainlinks.claimedAt),
          gt(brainlinks.expiresAt, now),
        ),
      )
      .returning();
    if (!link) return undefined;
    const claimSecret = issueToken("mb_claim");
    const [agent] = await tx
      .insert(agents)
      .values({
        userId: link.userId,
        displayName: input.displayName,
        harnessType: input.harnessType,
        requestedScopes: [...new Set(input.requestedScopes)],
        claimSecretHash: hashToken(claimSecret),
      })
      .returning();
    if (!agent) throw new Error("Agent insert returned no record");
    return { link, agent, claimSecret };
  });

  if (!claimed) {
    const [existing] = await db
      .select()
      .from(brainlinks)
      .where(eq(brainlinks.tokenHash, tokenHash))
      .limit(1);
    const reasonCode = !existing
      ? "INVITATION_INVALID"
      : existing.claimedAt
        ? "INVITATION_REPLAY"
        : "INVITATION_EXPIRED";
    await audit(db, {
      userId: existing?.userId,
      eventType:
        reasonCode === "INVITATION_REPLAY"
          ? "brainlink.replay_rejected"
          : reasonCode === "INVITATION_EXPIRED"
            ? "brainlink.expired"
            : "brainlink.claim_rejected",
      outcome: "denied",
      reasonCode,
      targetType: "brainlink",
      targetId: existing?.id,
      requestId,
    });
    throw new AppError(reasonCode, "The Brainlink cannot be claimed", 410);
  }

  await audit(db, {
    userId: claimed.link.userId,
    agentId: claimed.agent.id,
    eventType: "brainlink.claimed",
    outcome: "success",
    targetType: "brainlink",
    targetId: claimed.link.id,
    requestId,
    metadata: { requestedScopes: claimed.agent.requestedScopes },
  });
  await audit(db, {
    userId: claimed.link.userId,
    agentId: claimed.agent.id,
    eventType: "agent.requested",
    outcome: "success",
    targetType: "agent",
    targetId: claimed.agent.id,
    requestId,
    metadata: {
      harnessType: claimed.agent.harnessType,
      requestedScopes: claimed.agent.requestedScopes,
    },
  });
  return {
    requestId: claimed.agent.id,
    status: "pending" as const,
    claimSecret: claimed.claimSecret,
  };
}

export async function approveAgent(
  db: Database,
  agentId: string,
  scopes: Scope[],
) {
  const uniqueScopes = [...new Set(scopes)];
  if (uniqueScopes.some((scope) => !SCOPES.includes(scope)))
    throw new AppError("INVALID_SCOPE", "Unknown scope", 400);
  const [agent] = await db
    .update(agents)
    .set({
      status: "active",
      approvedScopes: uniqueScopes,
      approvedAt: new Date(),
    })
    .where(and(eq(agents.id, agentId), eq(agents.status, "pending")))
    .returning();
  if (!agent)
    throw new AppError(
      "REQUEST_NOT_PENDING",
      "The request is not pending",
      409,
    );
  await audit(db, {
    userId: agent.userId,
    agentId: agent.id,
    eventType: "agent.approved",
    outcome: "success",
    targetType: "agent",
    targetId: agent.id,
    metadata: { approvedScopes: uniqueScopes },
  });
  return agent;
}

export async function denyAgent(db: Database, agentId: string) {
  const [agent] = await db
    .update(agents)
    .set({ status: "revoked", revokedAt: new Date() })
    .where(and(eq(agents.id, agentId), eq(agents.status, "pending")))
    .returning();
  if (!agent)
    throw new AppError(
      "REQUEST_NOT_PENDING",
      "The request is not pending",
      409,
    );
  await audit(db, {
    userId: agent.userId,
    agentId: agent.id,
    eventType: "agent.denied",
    outcome: "denied",
    targetType: "agent",
    targetId: agent.id,
  });
  return agent;
}

export async function exchangeCredential(
  db: Database,
  input: { requestId: string; claimSecret: string },
  requestId: string,
) {
  const [agent] = await db
    .select()
    .from(agents)
    .where(eq(agents.id, input.requestId))
    .limit(1);
  if (!agent || !tokenHashMatches(input.claimSecret, agent.claimSecretHash)) {
    throw new AppError(
      "CLAIM_AUTH_INVALID",
      "The claim exchange credentials are invalid",
      401,
    );
  }
  if (agent.status === "pending")
    throw new AppError(
      "APPROVAL_PENDING",
      "Administrator approval is pending",
      409,
    );
  if (agent.status === "revoked")
    throw new AppError(
      "REQUEST_DENIED",
      "The request was denied or revoked",
      403,
    );
  if (agent.credentialIssuedAt)
    throw new AppError(
      "CREDENTIAL_ALREADY_ISSUED",
      "The credential was already issued",
      409,
    );

  const credential = issueToken("mb_agent");
  const [updated] = await db
    .update(agents)
    .set({
      credentialHash: hashToken(credential),
      credentialIssuedAt: new Date(),
    })
    .where(and(eq(agents.id, agent.id), isNull(agents.credentialIssuedAt)))
    .returning();
  if (!updated)
    throw new AppError(
      "CREDENTIAL_ALREADY_ISSUED",
      "The credential was already issued",
      409,
    );
  await audit(db, {
    userId: agent.userId,
    agentId: agent.id,
    eventType: "agent.credential_issued",
    outcome: "success",
    targetType: "agent",
    targetId: agent.id,
    requestId,
  });
  return { credential, scopes: updated.approvedScopes };
}

export async function revokeAgent(db: Database, agentId: string) {
  const [agent] = await db
    .update(agents)
    .set({ status: "revoked", revokedAt: new Date() })
    .where(eq(agents.id, agentId))
    .returning();
  if (!agent) throw new AppError("AGENT_NOT_FOUND", "Agent not found", 404);
  await audit(db, {
    userId: agent.userId,
    agentId: agent.id,
    eventType: "agent.revoked",
    outcome: "success",
    targetType: "agent",
    targetId: agent.id,
  });
  return agent;
}
