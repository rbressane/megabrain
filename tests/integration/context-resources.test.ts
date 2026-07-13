import { eq } from "drizzle-orm";
import { describe, expect, it } from "vitest";
import { buildApp } from "../../src/app.js";
import { auditEvents, facts } from "../../src/db/schema.js";
import {
  authorization,
  claimAndApprove,
  createOwner,
  database,
  useCleanDatabase,
} from "../helpers.js";

useCleanDatabase();

type ErrorResponse = { error: { code: string } };

const source = {
  type: "direct-statement",
  reference: "synthetic test statement",
};

async function remember(
  app: ReturnType<typeof buildApp>,
  credential: string,
  body: Record<string, unknown>,
) {
  return app.inject({
    method: "POST",
    url: "/v1/facts",
    headers: authorization(credential),
    payload: {
      confidence: "confirmed",
      sensitivity: "private",
      source,
      ...body,
    },
  });
}

describe("context, facts, and resources", () => {
  it("filters sensitivity before returning values and enforces limits", async () => {
    const app = buildApp({ db: database.db });
    const owner = await createOwner();
    const writer = await claimAndApprove(app, owner.id, [
      "context:read:general",
      "context:read:private",
      "context:read:sensitive",
      "facts:write",
    ]);
    await remember(app, writer.credential, {
      subject: "person",
      predicate: "favorite_store",
      value: "Synthetic Market",
      sensitivity: "general",
    });
    await remember(app, writer.credential, {
      subject: "person",
      predicate: "home_address",
      value: "14 Example Lane, Testville",
      sensitivity: "private",
    });
    await remember(app, writer.credential, {
      subject: "person",
      predicate: "tax_identifier",
      value: "SYNTHETIC-TAX-ID",
      sensitivity: "sensitive",
    });
    await remember(app, writer.credential, {
      subject: "pet",
      predicate: "nickname",
      value: "Unrelated synthetic value",
      sensitivity: "general",
    });

    const general = await claimAndApprove(
      app,
      owner.id,
      ["context:read:general"],
      "General Reader",
    );
    const generalResponse = await app.inject({
      method: "POST",
      url: "/v1/context",
      headers: authorization(general.credential),
      payload: {
        task: "person home address tax identifier favorite store",
        maxItems: 1,
      },
    });
    expect(generalResponse.statusCode).toBe(200);
    const generalBody = generalResponse.json<{
      facts: Array<{ value: unknown }>;
      omissions: Array<{ count: number }>;
    }>();
    expect(generalBody.facts).toHaveLength(1);
    expect(generalBody.facts[0]!.value).toBe("Synthetic Market");
    expect(generalBody.omissions[0]!.count).toBe(2);
    expect(generalResponse.body).not.toContain("14 Example Lane");
    expect(generalResponse.body).not.toContain("SYNTHETIC-TAX-ID");

    const privateReader = await claimAndApprove(
      app,
      owner.id,
      ["context:read:general", "context:read:private"],
      "Private Reader",
    );
    const privateResponse = await app.inject({
      method: "POST",
      url: "/v1/context",
      headers: authorization(privateReader.credential),
      payload: { task: "person home address tax identifier favorite store" },
    });
    expect(privateResponse.body).toContain("14 Example Lane");
    expect(privateResponse.body).not.toContain("SYNTHETIC-TAX-ID");
    const auditText = JSON.stringify(
      await database.db.select().from(auditEvents),
    );
    expect(auditText).not.toContain("14 Example Lane");
    expect(auditText).not.toContain("SYNTHETIC-TAX-ID");
    await app.close();
  });

  it("rejects duplicate active facts and secret values, and tombstones forgotten facts", async () => {
    const app = buildApp({ db: database.db });
    const owner = await createOwner();
    const agent = await claimAndApprove(app, owner.id, [
      "facts:write",
      "facts:forget",
      "context:read:private",
    ]);
    const first = await remember(app, agent.credential, {
      subject: "person",
      predicate: "home_address",
      value: "21 Sample Street, Test City",
    });
    expect(first.statusCode).toBe(201);
    const duplicate = await remember(app, agent.credential, {
      subject: "person",
      predicate: "home_address",
      value: "22 Sample Street, Test City",
    });
    expect(duplicate.statusCode).toBe(409);
    expect(duplicate.json<ErrorResponse>().error.code).toBe(
      "ACTIVE_FACT_EXISTS",
    );

    const secret = await remember(app, agent.credential, {
      subject: "account",
      predicate: "api_key",
      value: "sk-example012345678901234567890", // secret-scan: allow-test-fixture
    });
    expect(secret.statusCode).toBe(422);
    expect(secret.json<ErrorResponse>().error.code).toBe(
      "SECRET_VALUE_REJECTED",
    );

    const factId = first.json<{ id: string }>().id;
    expect(
      (
        await app.inject({
          method: "POST",
          url: "/v1/facts/forget",
          headers: authorization(agent.credential),
          payload: { factId, reason: "synthetic test cleanup" },
        })
      ).statusCode,
    ).toBe(200);
    const context = await app.inject({
      method: "POST",
      url: "/v1/context",
      headers: authorization(agent.credential),
      payload: { task: "distance from my home" },
    });
    expect(context.json<{ facts: unknown[] }>().facts).toEqual([]);
    expect(
      (await database.db.select().from(facts).where(eq(facts.id, factId)))[0]!
        .status,
    ).toBe("forgotten");
    await app.close();
  });

  it("stores and locates references without dereferencing secrets, and audits denied lookup", async () => {
    const app = buildApp({ db: database.db });
    const owner = await createOwner();
    const writer = await claimAndApprove(app, owner.id, [
      "resources:write",
      "resources:locate",
      "context:read:private",
    ]);
    for (const payload of [
      {
        type: "document",
        name: "Project brief",
        locator: "https://example.invalid/documents/project-brief",
        sensitivity: "private",
        metadata: { format: "markdown" },
      },
      {
        type: "secret-reference",
        name: "Deployment credential",
        locator: "1password://Engineering/Deploy/token",
        sensitivity: "private",
        metadata: { provider: "1password" },
      },
    ]) {
      expect(
        (
          await app.inject({
            method: "POST",
            url: "/v1/resources",
            headers: authorization(writer.credential),
            payload,
          })
        ).statusCode,
      ).toBe(201);
    }
    const located = await app.inject({
      method: "POST",
      url: "/v1/resources/locate",
      headers: authorization(writer.credential),
      payload: { query: "deployment credential" },
    });
    const resource = located.json<{
      resources: Array<{ type: string; locator: string }>;
    }>().resources[0]!;
    expect(resource.type).toBe("secret-reference");
    expect(resource.locator).toBe("1password://Engineering/Deploy/token");
    expect(located.body).not.toContain("secretValue");

    const unauthorized = await claimAndApprove(
      app,
      owner.id,
      ["context:read:private"],
      "No Resource Scope",
    );
    const denied = await app.inject({
      method: "POST",
      url: "/v1/resources/locate",
      headers: authorization(unauthorized.credential),
      payload: { query: "deployment" },
    });
    expect(denied.statusCode).toBe(403);
    expect(denied.json<ErrorResponse>().error.code).toBe("SCOPE_DENIED");
    expect(
      (await database.db.select().from(auditEvents)).some(
        (event) =>
          event.reasonCode === "SCOPE_DENIED" && event.outcome === "denied",
      ),
    ).toBe(true);
    await app.close();
  });
});
