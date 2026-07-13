import {
  index,
  integer,
  jsonb,
  pgEnum,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";

export const agentStatus = pgEnum("agent_status", [
  "pending",
  "active",
  "revoked",
]);
export const factStatus = pgEnum("fact_status", [
  "active",
  "superseded",
  "forgotten",
]);
export const confidence = pgEnum("confidence", [
  "confirmed",
  "inferred",
  "unconfirmed",
]);
export const sensitivity = pgEnum("sensitivity", [
  "general",
  "private",
  "sensitive",
]);
export const resourceType = pgEnum("resource_type", [
  "document",
  "secret-reference",
  "external-record",
]);

export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  displayName: text("display_name").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const agents = pgTable(
  "agents",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id),
    displayName: text("display_name").notNull(),
    harnessType: text("harness_type").notNull(),
    status: agentStatus("status").notNull().default("pending"),
    credentialHash: text("credential_hash"),
    claimSecretHash: text("claim_secret_hash").notNull(),
    approvedScopes: text("approved_scopes").array().notNull().default([]),
    requestedScopes: text("requested_scopes").array().notNull().default([]),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    approvedAt: timestamp("approved_at", { withTimezone: true }),
    credentialIssuedAt: timestamp("credential_issued_at", {
      withTimezone: true,
    }),
    lastUsedAt: timestamp("last_used_at", { withTimezone: true }),
    revokedAt: timestamp("revoked_at", { withTimezone: true }),
  },
  (table) => [
    index("agents_user_idx").on(table.userId),
    uniqueIndex("agents_credential_hash_idx").on(table.credentialHash),
  ],
);

export const brainlinks = pgTable(
  "brainlinks",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id),
    tokenHash: text("token_hash").notNull(),
    expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
    maximumClaims: integer("maximum_claims").notNull().default(1),
    claimedAt: timestamp("claimed_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [uniqueIndex("brainlinks_token_hash_idx").on(table.tokenHash)],
);

export const facts = pgTable(
  "facts",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id),
    subject: text("subject").notNull(),
    predicate: text("predicate").notNull(),
    value: jsonb("value").notNull(),
    status: factStatus("status").notNull().default("active"),
    confidence: confidence("confidence").notNull(),
    sensitivity: sensitivity("sensitivity").notNull().default("private"),
    sourceType: text("source_type").notNull(),
    sourceReference: text("source_reference").notNull(),
    createdByAgentId: uuid("created_by_agent_id").references(() => agents.id),
    validFrom: timestamp("valid_from", { withTimezone: true })
      .notNull()
      .defaultNow(),
    validUntil: timestamp("valid_until", { withTimezone: true }),
    supersedesFactId: uuid("supersedes_fact_id"),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    index("facts_current_lookup_idx").on(
      table.userId,
      table.status,
      table.subject,
      table.predicate,
    ),
    index("facts_supersedes_idx").on(table.supersedesFactId),
  ],
);

export const resourceReferences = pgTable(
  "resource_references",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id),
    type: resourceType("resource_type").notNull(),
    name: text("name").notNull(),
    locator: text("locator").notNull(),
    sensitivity: sensitivity("sensitivity").notNull().default("private"),
    metadata: jsonb("metadata").notNull().default({}),
    createdByAgentId: uuid("created_by_agent_id")
      .notNull()
      .references(() => agents.id),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    index("resources_lookup_idx").on(table.userId, table.type, table.name),
  ],
);

export const auditEvents = pgTable(
  "audit_events",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id").references(() => users.id),
    agentId: uuid("agent_id").references(() => agents.id),
    eventType: text("event_type").notNull(),
    outcome: text("outcome").notNull(),
    reasonCode: text("reason_code"),
    targetType: text("target_type"),
    targetId: text("target_id"),
    requestId: text("request_id"),
    metadata: jsonb("metadata").notNull().default({}),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [index("audit_user_time_idx").on(table.userId, table.createdAt)],
);

export type Agent = typeof agents.$inferSelect;
export type Fact = typeof facts.$inferSelect;
export type ResourceReference = typeof resourceReferences.$inferSelect;
