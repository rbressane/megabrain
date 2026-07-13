import { and, eq } from "drizzle-orm";
import { describe, expect, it } from "vitest";
import { buildApp } from "../../src/app.js";
import { approveAgent, createBrainlink } from "../../src/brainlinks/service.js";
import { agents, auditEvents, brainlinks } from "../../src/db/schema.js";
import {
  authorization,
  claimAndApprove,
  createOwner,
  database,
  useCleanDatabase,
} from "../helpers.js";

useCleanDatabase();

type ErrorResponse = { error: { code: string } };

describe("Brainlinks and authentication", () => {
  it("allows one claim, keeps it pending, and issues one credential after approval", async () => {
    const app = buildApp({ db: database.db });
    const owner = await createOwner();
    const { token } = await createBrainlink(database.db, owner.id, 60_000);
    const payload = {
      token,
      displayName: "Agent One",
      harnessType: "integration",
      requestedScopes: ["context:read:private"],
    };

    const claim = await app.inject({
      method: "POST",
      url: "/v1/brainlinks/claim",
      payload,
    });
    expect(claim.statusCode).toBe(201);
    const claimed = claim.json<{
      requestId: string;
      claimSecret: string;
      status: string;
    }>();
    expect(claimed.status).toBe("pending");
    expect(
      (
        await app.inject({
          method: "POST",
          url: "/v1/brainlinks/claim",
          payload,
        })
      ).json<ErrorResponse>().error.code,
    ).toBe("INVITATION_REPLAY");
    expect(
      (
        await app.inject({
          method: "POST",
          url: "/v1/brainlinks/exchange",
          payload: {
            requestId: claimed.requestId,
            claimSecret: claimed.claimSecret,
          },
        })
      ).json<ErrorResponse>().error.code,
    ).toBe("APPROVAL_PENDING");

    await approveAgent(database.db, claimed.requestId, [
      "context:read:private",
    ]);
    const exchange = await app.inject({
      method: "POST",
      url: "/v1/brainlinks/exchange",
      payload: {
        requestId: claimed.requestId,
        claimSecret: claimed.claimSecret,
      },
    });
    expect(exchange.statusCode).toBe(200);
    const credential = exchange.json<{ credential: string }>().credential;
    expect(credential).toMatch(/^mb_agent_/);
    expect(
      (
        await app.inject({
          method: "POST",
          url: "/v1/brainlinks/exchange",
          payload: {
            requestId: claimed.requestId,
            claimSecret: claimed.claimSecret,
          },
        })
      ).json<ErrorResponse>().error.code,
    ).toBe("CREDENTIAL_ALREADY_ISSUED");

    const [storedAgent] = await database.db
      .select()
      .from(agents)
      .where(eq(agents.id, claimed.requestId));
    const [storedLink] = await database.db.select().from(brainlinks);
    const audit = await database.db.select().from(auditEvents);
    const storedText = JSON.stringify({ storedAgent, storedLink, audit });
    expect(storedText).not.toContain(token);
    expect(storedText).not.toContain(claimed.claimSecret);
    expect(storedText).not.toContain(credential);
    await app.close();
  });

  it("rejects expired invitations", async () => {
    const app = buildApp({ db: database.db });
    const owner = await createOwner();
    const { token } = await createBrainlink(database.db, owner.id, -1);
    const response = await app.inject({
      method: "POST",
      url: "/v1/brainlinks/claim",
      payload: {
        token,
        displayName: "Late Agent",
        harnessType: "integration",
        requestedScopes: ["context:read:general"],
      },
    });
    expect(response.statusCode).toBe(410);
    expect(response.json<ErrorResponse>().error.code).toBe(
      "INVITATION_EXPIRED",
    );
    await app.close();
  });

  it("denies missing, invalid, pending, and revoked credentials and audits denials", async () => {
    const app = buildApp({ db: database.db });
    const owner = await createOwner();
    const active = await claimAndApprove(app, owner.id, [
      "context:read:general",
    ]);

    expect(
      (
        await app.inject({
          method: "POST",
          url: "/v1/context",
          payload: { task: "home" },
        })
      ).statusCode,
    ).toBe(401);
    expect(
      (
        await app.inject({
          method: "POST",
          url: "/v1/context",
          headers: authorization("mb_agent_invalid"),
          payload: { task: "home" },
        })
      ).statusCode,
    ).toBe(401);

    await database.db
      .update(agents)
      .set({ status: "pending" })
      .where(eq(agents.id, active.agentId));
    expect(
      (
        await app.inject({
          method: "POST",
          url: "/v1/context",
          headers: authorization(active.credential),
          payload: { task: "home" },
        })
      ).json<ErrorResponse>().error.code,
    ).toBe("AGENT_PENDING");
    await database.db
      .update(agents)
      .set({ status: "revoked" })
      .where(eq(agents.id, active.agentId));
    expect(
      (
        await app.inject({
          method: "POST",
          url: "/v1/context",
          headers: authorization(active.credential),
          payload: { task: "home" },
        })
      ).json<ErrorResponse>().error.code,
    ).toBe("AGENT_REVOKED");

    const denials = await database.db
      .select()
      .from(auditEvents)
      .where(
        and(
          eq(auditEvents.eventType, "access.denied"),
          eq(auditEvents.outcome, "denied"),
        ),
      );
    expect(denials.map((event) => event.reasonCode)).toEqual(
      expect.arrayContaining([
        "MISSING_CREDENTIAL",
        "INVALID_CREDENTIAL",
        "AGENT_PENDING",
        "AGENT_REVOKED",
      ]),
    );
    await app.close();
  });
});
