import { and, eq, isNull, or, gt } from "drizzle-orm";
import { audit } from "../audit/service.js";
import type { AgentContext } from "../auth/service.js";
import type { Sensitivity } from "../contracts.js";
import type { Database } from "../db/client.js";
import { facts } from "../db/schema.js";
import { AppError } from "../errors.js";
import { locateResources } from "../resources/service.js";

const ALIASES: Record<string, string[]> = {
  "person.home_address": [
    "my home",
    "home",
    "where i live",
    "home address",
    "distance",
  ],
  "person.writing_voice": ["my writing", "writing voice", "tone", "style"],
};

function tokens(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[^a-z0-9]+/g, " ")
      .trim()
      .split(/\s+/)
      .filter((token) => token.length > 1),
  );
}

function relevance(subject: string, predicate: string, query: string): number {
  const queryTokens = tokens(query);
  const fieldTokens = tokens(`${subject} ${predicate}`);
  let score =
    [...queryTokens].filter((token) => fieldTokens.has(token)).length * 3;
  for (const [canonical, aliases] of Object.entries(ALIASES)) {
    if (`${subject}.${predicate}` !== canonical && predicate !== canonical)
      continue;
    for (const alias of aliases) {
      if (query.toLowerCase().includes(alias)) score += 10;
      score += [...tokens(alias)].filter((token) =>
        queryTokens.has(token),
      ).length;
    }
  }
  return score;
}

function canRead(scopes: string[], sensitivity: Sensitivity): boolean {
  return scopes.includes(`context:read:${sensitivity}`);
}

export async function getContext(
  db: Database,
  context: AgentContext,
  input: {
    task: string;
    subjectHints?: string[] | undefined;
    maxItems: number;
  },
  requestId: string,
) {
  if (
    !context.agent.approvedScopes.some((scope) =>
      scope.startsWith("context:read:"),
    )
  ) {
    await audit(db, {
      userId: context.user.id,
      agentId: context.agent.id,
      eventType: "access.denied",
      outcome: "denied",
      reasonCode: "SCOPE_DENIED",
      requestId,
      metadata: { requiredCategory: "context:read" },
    });
    throw new AppError(
      "SCOPE_DENIED",
      "The operation requires a context:read scope",
      403,
    );
  }
  const now = new Date();
  const currentFacts = await db
    .select()
    .from(facts)
    .where(
      and(
        eq(facts.userId, context.user.id),
        eq(facts.status, "active"),
        or(isNull(facts.validUntil), gt(facts.validUntil, now)),
      ),
    );
  const query = [input.task, ...(input.subjectHints ?? [])].join(" ");
  const relevant = currentFacts
    .map((fact) => ({
      fact,
      score: relevance(fact.subject, fact.predicate, query),
    }))
    .filter(({ score }) => score > 0);
  const denied = relevant.filter(
    ({ fact }) => !canRead(context.agent.approvedScopes, fact.sensitivity),
  );
  const permitted = relevant
    .filter(({ fact }) =>
      canRead(context.agent.approvedScopes, fact.sensitivity),
    )
    .sort(
      (left, right) =>
        right.score - left.score ||
        right.fact.createdAt.getTime() - left.fact.createdAt.getTime(),
    )
    .slice(0, input.maxItems)
    .map(({ fact }) => ({
      id: fact.id,
      subject: fact.subject,
      predicate: fact.predicate,
      value: fact.value,
      confidence: fact.confidence,
      sensitivity: fact.sensitivity,
      provenance: {
        sourceType: fact.sourceType,
        sourceReference: fact.sourceReference,
        createdByAgentId: fact.createdByAgentId,
      },
      validFrom: fact.validFrom,
      updatedAt: fact.updatedAt,
    }));

  await audit(db, {
    userId: context.user.id,
    agentId: context.agent.id,
    eventType: "fact.read",
    outcome: "success",
    requestId,
    metadata: {
      returnedFactIds: permitted.map((fact) => fact.id),
      omittedCount: denied.length,
    },
  });
  const located = context.agent.approvedScopes.includes("resources:locate")
    ? await locateResources(
        db,
        context,
        { query: input.task, maxItems: input.maxItems },
        requestId,
      )
    : {
        resources: [],
        omissions: [{ category: "resources", reason: "scope_not_granted" }],
      };
  return {
    identity: {
      userId: context.user.id,
      displayName: context.user.displayName,
    },
    facts: permitted,
    resources: located.resources,
    omissions: [
      ...(denied.length
        ? [
            {
              category: "facts",
              reason: "insufficient_scope",
              count: denied.length,
            },
          ]
        : []),
      ...located.omissions,
    ],
  };
}
