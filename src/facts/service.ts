import { and, eq } from "drizzle-orm";
import { audit } from "../audit/service.js";
import type { AgentContext } from "../auth/service.js";
import type { correctSchema, rememberSchema } from "../contracts.js";
import type { Database } from "../db/client.js";
import { facts } from "../db/schema.js";
import { AppError } from "../errors.js";
import { detectSecret } from "../security/secret-detection.js";

type RememberInput = import("zod").infer<typeof rememberSchema>;

function assertSafeFactValue(value: unknown): void {
  try {
    JSON.stringify(value);
  } catch {
    throw new AppError(
      "INVALID_FACT_VALUE",
      "Fact values must be JSON serializable",
      400,
    );
  }
  const secretType = detectSecret(value);
  if (secretType) {
    throw new AppError(
      "SECRET_VALUE_REJECTED",
      "Likely secret material cannot be stored as a fact; store an external secret reference instead",
      422,
      { detectedPattern: secretType },
    );
  }
}

export async function rememberFact(
  db: Database,
  context: AgentContext,
  input: RememberInput,
  requestId: string,
) {
  try {
    assertSafeFactValue(input.value);
  } catch (error) {
    await audit(db, {
      userId: context.user.id,
      agentId: context.agent.id,
      eventType: "fact.create_rejected",
      outcome: "denied",
      reasonCode: error instanceof AppError ? error.code : "INVALID_FACT_VALUE",
      requestId,
      metadata: {
        subject: input.subject,
        predicate: input.predicate,
        sensitivity: input.sensitivity,
      },
    });
    throw error;
  }
  const [existing] = await db
    .select({ id: facts.id })
    .from(facts)
    .where(
      and(
        eq(facts.userId, context.user.id),
        eq(facts.subject, input.subject),
        eq(facts.predicate, input.predicate),
        eq(facts.status, "active"),
      ),
    )
    .limit(1);
  if (existing) {
    await audit(db, {
      userId: context.user.id,
      agentId: context.agent.id,
      eventType: "fact.create_rejected",
      outcome: "denied",
      reasonCode: "ACTIVE_FACT_EXISTS",
      targetType: "fact",
      targetId: existing.id,
      requestId,
    });
    throw new AppError(
      "ACTIVE_FACT_EXISTS",
      "An active fact already exists for this subject and predicate; use correct",
      409,
      { factId: existing.id },
    );
  }

  const [fact] = await db
    .insert(facts)
    .values({
      userId: context.user.id,
      subject: input.subject,
      predicate: input.predicate,
      value: input.value,
      confidence: input.confidence,
      sensitivity: input.sensitivity,
      sourceType: input.source.type,
      sourceReference: input.source.reference,
      createdByAgentId: context.agent.id,
    })
    .returning();
  if (!fact) throw new Error("Fact insert returned no record");
  await audit(db, {
    userId: context.user.id,
    agentId: context.agent.id,
    eventType: "fact.created",
    outcome: "success",
    targetType: "fact",
    targetId: fact.id,
    requestId,
    metadata: {
      sensitivity: fact.sensitivity,
      confidence: fact.confidence,
      subject: fact.subject,
      predicate: fact.predicate,
    },
  });
  return { id: fact.id, status: fact.status };
}

type CorrectInput = import("zod").infer<typeof correctSchema>;

export async function correctFact(
  db: Database,
  context: AgentContext,
  input: CorrectInput,
  requestId: string,
) {
  try {
    assertSafeFactValue(input.replacementValue);
  } catch (error) {
    await audit(db, {
      userId: context.user.id,
      agentId: context.agent.id,
      eventType: "fact.correction_rejected",
      outcome: "denied",
      reasonCode: error instanceof AppError ? error.code : "INVALID_FACT_VALUE",
      requestId,
    });
    throw error;
  }
  const now = new Date();
  const result = await db.transaction(async (tx) => {
    const selector = input.previousFactId
      ? and(
          eq(facts.id, input.previousFactId),
          eq(facts.userId, context.user.id),
          eq(facts.status, "active"),
        )
      : and(
          eq(facts.userId, context.user.id),
          eq(facts.subject, input.subject!),
          eq(facts.predicate, input.predicate!),
          eq(facts.status, "active"),
        );
    const previousRecords = await tx
      .select()
      .from(facts)
      .where(selector)
      .limit(2);
    if (previousRecords.length === 0)
      throw new AppError(
        "FACT_NOT_FOUND",
        "No current fact matches the selector",
        404,
      );
    if (previousRecords.length > 1)
      throw new AppError(
        "FACT_SELECTOR_AMBIGUOUS",
        "The fact selector is ambiguous",
        409,
      );
    const previous = previousRecords[0]!;

    await tx
      .update(facts)
      .set({ status: "superseded", validUntil: now, updatedAt: now })
      .where(and(eq(facts.id, previous.id), eq(facts.status, "active")));
    const [replacement] = await tx
      .insert(facts)
      .values({
        userId: previous.userId,
        subject: previous.subject,
        predicate: previous.predicate,
        value: input.replacementValue,
        confidence: previous.confidence,
        sensitivity: previous.sensitivity,
        sourceType: input.source.type,
        sourceReference: input.source.reference,
        createdByAgentId: context.agent.id,
        validFrom: now,
        supersedesFactId: previous.id,
      })
      .returning();
    if (!replacement) throw new Error("Correction insert returned no record");
    return { previous, replacement };
  });

  await audit(db, {
    userId: context.user.id,
    agentId: context.agent.id,
    eventType: "fact.corrected",
    outcome: "success",
    targetType: "fact",
    targetId: result.replacement.id,
    requestId,
    metadata: {
      supersededFactId: result.previous.id,
      sensitivity: result.replacement.sensitivity,
      reasonProvided: Boolean(input.reason),
    },
  });
  await audit(db, {
    userId: context.user.id,
    agentId: context.agent.id,
    eventType: "fact.superseded",
    outcome: "success",
    targetType: "fact",
    targetId: result.previous.id,
    requestId,
    metadata: { replacementFactId: result.replacement.id },
  });
  return {
    id: result.replacement.id,
    status: result.replacement.status,
    supersededFactId: result.previous.id,
  };
}

export async function forgetFact(
  db: Database,
  context: AgentContext,
  input: { factId: string; reason?: string | undefined },
  requestId: string,
) {
  const [fact] = await db
    .update(facts)
    .set({ status: "forgotten", validUntil: new Date(), updatedAt: new Date() })
    .where(
      and(
        eq(facts.id, input.factId),
        eq(facts.userId, context.user.id),
        eq(facts.status, "active"),
      ),
    )
    .returning();
  if (!fact)
    throw new AppError("FACT_NOT_FOUND", "No current fact matches the ID", 404);
  await audit(db, {
    userId: context.user.id,
    agentId: context.agent.id,
    eventType: "fact.forgotten",
    outcome: "success",
    targetType: "fact",
    targetId: fact.id,
    requestId,
    metadata: {
      sensitivity: fact.sensitivity,
      reasonProvided: Boolean(input.reason),
    },
  });
  return { id: fact.id, status: fact.status };
}
