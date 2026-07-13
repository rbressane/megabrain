#!/usr/bin/env node
import { Command } from "commander";
import { and, asc, eq } from "drizzle-orm";
import { audit } from "../audit/service.js";
import {
  approveAgent,
  createBrainlink,
  denyAgent,
  revokeAgent,
} from "../brainlinks/service.js";
import { loadConfig } from "../config.js";
import { SCOPES, scopeSchema } from "../contracts.js";
import { createDatabase } from "../db/client.js";
import { runMigrations } from "../db/migrate.js";
import {
  agents,
  auditEvents,
  facts,
  resourceReferences,
  users,
} from "../db/schema.js";
import { AppError } from "../errors.js";

const config = loadConfig();
const { db, client } = createDatabase(config);
const program = new Command()
  .name("megabrain")
  .description("MegaBrain V0 administrator CLI");

function output(value: unknown): void {
  console.log(JSON.stringify(value, null, 2));
}

function parseDuration(value: string): number {
  const match = /^(\d+)(s|m|h|d)$/.exec(value);
  if (!match)
    throw new AppError(
      "INVALID_DURATION",
      "Use a duration such as 15m, 1h, or 1d",
      400,
    );
  const multipliers = {
    s: 1_000,
    m: 60_000,
    h: 3_600_000,
    d: 86_400_000,
  } as const;
  return Number(match[1]) * multipliers[match[2] as keyof typeof multipliers];
}

async function owner() {
  const [user] = await db
    .select()
    .from(users)
    .orderBy(asc(users.createdAt))
    .limit(1);
  if (!user)
    throw new AppError("NOT_INITIALIZED", "Run megabrain init first", 400);
  return user;
}

program
  .command("init")
  .option(
    "--display-name <name>",
    "brain owner display name",
    "MegaBrain Owner",
  )
  .action(async ({ displayName }: { displayName: string }) => {
    await runMigrations(config.DATABASE_URL);
    const existing = await db.select().from(users).limit(1);
    if (existing[0])
      return output({
        userId: existing[0].id,
        displayName: existing[0].displayName,
        created: false,
      });
    const [user] = await db.insert(users).values({ displayName }).returning();
    output({ userId: user!.id, displayName: user!.displayName, created: true });
  });

const invite = program.command("invite");
invite
  .command("create")
  .option("--expires-in <duration>", "invitation lifetime", "15m")
  .action(async ({ expiresIn }: { expiresIn: string }) => {
    const user = await owner();
    const { record, token } = await createBrainlink(
      db,
      user.id,
      parseDuration(expiresIn),
    );
    output({
      id: record.id,
      expiresAt: record.expiresAt,
      brainlink: `${config.MEGABRAIN_BASE_URL}/v1/brainlinks/connect#token=${encodeURIComponent(token)}`,
      warning:
        "This single-use invitation is shown once. Do not commit or log it.",
    });
  });

const requests = program.command("requests");
requests.command("list").action(async () => {
  const user = await owner();
  const rows = await db
    .select({
      id: agents.id,
      displayName: agents.displayName,
      harnessType: agents.harnessType,
      status: agents.status,
      requestedScopes: agents.requestedScopes,
      createdAt: agents.createdAt,
    })
    .from(agents)
    .where(and(eq(agents.userId, user.id), eq(agents.status, "pending")));
  output(rows);
});
requests
  .command("approve <request-id>")
  .requiredOption(
    "--scopes <scopes>",
    `comma-separated scopes: ${SCOPES.join(",")}`,
  )
  .action(async (requestId: string, { scopes }: { scopes: string }) => {
    const parsed = scopes
      .split(",")
      .map((scope) => scopeSchema.parse(scope.trim()));
    const agent = await approveAgent(db, requestId, parsed);
    output({
      id: agent.id,
      status: agent.status,
      approvedScopes: agent.approvedScopes,
    });
  });
requests.command("deny <request-id>").action(async (requestId: string) => {
  const agent = await denyAgent(db, requestId);
  output({ id: agent.id, status: agent.status });
});

const agentCommands = program.command("agents");
agentCommands.command("list").action(async () => {
  const user = await owner();
  const rows = await db
    .select({
      id: agents.id,
      displayName: agents.displayName,
      harnessType: agents.harnessType,
      status: agents.status,
      approvedScopes: agents.approvedScopes,
      createdAt: agents.createdAt,
      approvedAt: agents.approvedAt,
      lastUsedAt: agents.lastUsedAt,
      revokedAt: agents.revokedAt,
    })
    .from(agents)
    .where(eq(agents.userId, user.id));
  output(rows);
});
agentCommands.command("revoke <agent-id>").action(async (agentId: string) => {
  const agent = await revokeAgent(db, agentId);
  output({ id: agent.id, status: agent.status, revokedAt: agent.revokedAt });
});

const inspect = program.command("inspect");
inspect.command("facts").action(async () => {
  const user = await owner();
  output(
    await db
      .select()
      .from(facts)
      .where(eq(facts.userId, user.id))
      .orderBy(asc(facts.createdAt)),
  );
});
inspect.command("audit").action(async () => {
  const user = await owner();
  output(
    await db
      .select()
      .from(auditEvents)
      .where(eq(auditEvents.userId, user.id))
      .orderBy(asc(auditEvents.createdAt)),
  );
});

program.command("export").action(async () => {
  const user = await owner();
  await audit(db, {
    userId: user.id,
    eventType: "export.requested",
    outcome: "success",
    targetType: "user",
    targetId: user.id,
  });
  const agentRows = await db
    .select({
      id: agents.id,
      userId: agents.userId,
      displayName: agents.displayName,
      harnessType: agents.harnessType,
      status: agents.status,
      approvedScopes: agents.approvedScopes,
      createdAt: agents.createdAt,
      approvedAt: agents.approvedAt,
      lastUsedAt: agents.lastUsedAt,
      revokedAt: agents.revokedAt,
    })
    .from(agents)
    .where(eq(agents.userId, user.id));
  output({
    format: "megabrain-export-v0",
    exportedAt: new Date(),
    user,
    agents: agentRows,
    facts: await db.select().from(facts).where(eq(facts.userId, user.id)),
    resources: await db
      .select()
      .from(resourceReferences)
      .where(eq(resourceReferences.userId, user.id)),
  });
});

try {
  await program.parseAsync();
} catch (error) {
  if (error instanceof AppError)
    console.error(`${error.code}: ${error.message}`);
  else console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
} finally {
  await client.end();
}
