import { eq } from "drizzle-orm";
import { audit } from "../audit/service.js";
import type { AgentContext } from "../auth/service.js";
import type { JsonValue, Sensitivity } from "../contracts.js";
import type { Database } from "../db/client.js";
import { resourceReferences } from "../db/schema.js";

function canRead(scopes: string[], sensitivity: Sensitivity): boolean {
  return scopes.includes(`context:read:${sensitivity}`);
}

export async function createResource(
  db: Database,
  context: AgentContext,
  input: {
    type: "document" | "secret-reference" | "external-record";
    name: string;
    locator: string;
    sensitivity: Sensitivity;
    metadata: Record<string, JsonValue>;
  },
  requestId: string,
) {
  const [resource] = await db
    .insert(resourceReferences)
    .values({
      userId: context.user.id,
      createdByAgentId: context.agent.id,
      ...input,
    })
    .returning();
  if (!resource) throw new Error("Resource insert returned no record");
  await audit(db, {
    userId: context.user.id,
    agentId: context.agent.id,
    eventType: "resource.created",
    outcome: "success",
    targetType: "resource",
    targetId: resource.id,
    requestId,
    metadata: { type: resource.type, sensitivity: resource.sensitivity },
  });
  return { id: resource.id, type: resource.type };
}

export async function locateResources(
  db: Database,
  context: AgentContext,
  input: { query: string; maxItems: number },
  requestId: string,
) {
  const queryTokens = input.query.toLowerCase().split(/\W+/).filter(Boolean);
  const records = await db
    .select()
    .from(resourceReferences)
    .where(eq(resourceReferences.userId, context.user.id));
  const matching = records.filter((resource) => {
    const searchable =
      `${resource.name} ${resource.type} ${resource.locator}`.toLowerCase();
    return queryTokens.some((token) => searchable.includes(token));
  });
  const denied = matching.filter(
    (resource) => !canRead(context.agent.approvedScopes, resource.sensitivity),
  );
  const permitted = matching
    .filter((resource) =>
      canRead(context.agent.approvedScopes, resource.sensitivity),
    )
    .slice(0, input.maxItems)
    .map((resource) => ({
      id: resource.id,
      type: resource.type,
      name: resource.name,
      locator: resource.locator,
      sensitivity: resource.sensitivity,
      metadata: resource.metadata,
      updatedAt: resource.updatedAt,
    }));
  await audit(db, {
    userId: context.user.id,
    agentId: context.agent.id,
    eventType: "resource.located",
    outcome: "success",
    requestId,
    metadata: {
      returnedResourceIds: permitted.map((resource) => resource.id),
      omittedCount: denied.length,
    },
  });
  return {
    resources: permitted,
    omissions: denied.length
      ? [
          {
            category: "resources",
            reason: "insufficient_scope",
            count: denied.length,
          },
        ]
      : [],
  };
}
