import type { Database } from "../db/client.js";
import { auditEvents } from "../db/schema.js";

export interface AuditInput {
  userId?: string | null | undefined;
  agentId?: string | null | undefined;
  eventType: string;
  outcome: "success" | "denied" | "failure";
  reasonCode?: string | undefined;
  targetType?: string | undefined;
  targetId?: string | undefined;
  requestId?: string | undefined;
  metadata?: Record<string, unknown> | undefined;
}

export async function audit(db: Database, input: AuditInput): Promise<void> {
  await db.insert(auditEvents).values({
    userId: input.userId ?? null,
    agentId: input.agentId ?? null,
    eventType: input.eventType,
    outcome: input.outcome,
    reasonCode: input.reasonCode,
    targetType: input.targetType,
    targetId: input.targetId,
    requestId: input.requestId,
    metadata: input.metadata ?? {},
  });
}
