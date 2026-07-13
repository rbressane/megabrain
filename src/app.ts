import Fastify, { type FastifyInstance } from "fastify";
import { ZodError } from "zod";
import {
  authenticateAgent,
  bearerToken,
  requireScope,
} from "./auth/service.js";
import { claimBrainlink, exchangeCredential } from "./brainlinks/service.js";
import {
  claimBrainlinkSchema,
  correctSchema,
  createResourceSchema,
  exchangeCredentialSchema,
  forgetSchema,
  getContextSchema,
  locateSchema,
  rememberSchema,
} from "./contracts.js";
import { getContext } from "./context/service.js";
import type { Database } from "./db/client.js";
import { AppError } from "./errors.js";
import { correctFact, forgetFact, rememberFact } from "./facts/service.js";
import { createResource, locateResources } from "./resources/service.js";

export function buildApp(options: {
  db: Database;
  logger?: boolean | { level: string };
}): FastifyInstance {
  const app = Fastify({
    logger:
      typeof options.logger === "object"
        ? {
            ...options.logger,
            redact: ["req.headers.authorization", "headers.authorization"],
          }
        : (options.logger ?? false),
    requestIdHeader: "x-request-id",
    genReqId: () => crypto.randomUUID(),
  });
  const { db } = options;

  app.setErrorHandler((error, request, reply) => {
    if (error instanceof ZodError) {
      return reply.status(400).send({
        error: {
          code: "VALIDATION_ERROR",
          message: "The request body is invalid",
          details: error.flatten(),
        },
        requestId: request.id,
      });
    }
    if (error instanceof AppError) {
      return reply.status(error.statusCode).send({
        error: {
          code: error.code,
          message: error.message,
          ...(error.details ? { details: error.details } : {}),
        },
        requestId: request.id,
      });
    }
    request.log.error({ err: error }, "request failed");
    return reply.status(500).send({
      error: {
        code: "INTERNAL_ERROR",
        message: "An internal error occurred",
      },
      requestId: request.id,
    });
  });

  app.get("/health", () => ({ status: "ok" }));
  app.get("/v1/brainlinks/connect", () => ({
    protocol: "megabrain-brainlink-v0",
    instructions: [
      "Read the invitation token from the URL fragment; do not put it in logs or command history.",
      "POST the token, harness identity, display name, and requested scopes to /v1/brainlinks/claim.",
      "Keep the returned claimSecret private and poll /v1/brainlinks/exchange after human approval.",
      "Store the one-time agent credential outside the repository and send it only as a Bearer authorization header.",
      "Run get_context with a harmless task to verify the connection.",
    ],
    claimEndpoint: "/v1/brainlinks/claim",
    exchangeEndpoint: "/v1/brainlinks/exchange",
    credentialTransport: "Authorization: Bearer <agent credential>",
  }));

  app.post("/v1/brainlinks/claim", async (request, reply) => {
    const input = claimBrainlinkSchema.parse(request.body);
    return reply.status(201).send(await claimBrainlink(db, input, request.id));
  });
  app.post("/v1/brainlinks/exchange", async (request) => {
    const input = exchangeCredentialSchema.parse(request.body);
    return exchangeCredential(db, input, request.id);
  });

  app.post("/v1/context", async (request) => {
    const context = await authenticateAgent(
      db,
      bearerToken(request.headers.authorization),
      request.id,
    );
    return getContext(
      db,
      context,
      getContextSchema.parse(request.body),
      request.id,
    );
  });
  app.post("/v1/facts", async (request, reply) => {
    const context = await authenticateAgent(
      db,
      bearerToken(request.headers.authorization),
      request.id,
    );
    await requireScope(db, context, "facts:write", request.id);
    return reply
      .status(201)
      .send(
        await rememberFact(
          db,
          context,
          rememberSchema.parse(request.body),
          request.id,
        ),
      );
  });
  app.post("/v1/facts/correct", async (request) => {
    const context = await authenticateAgent(
      db,
      bearerToken(request.headers.authorization),
      request.id,
    );
    await requireScope(db, context, "facts:correct", request.id);
    return correctFact(
      db,
      context,
      correctSchema.parse(request.body),
      request.id,
    );
  });
  app.post("/v1/facts/forget", async (request) => {
    const context = await authenticateAgent(
      db,
      bearerToken(request.headers.authorization),
      request.id,
    );
    await requireScope(db, context, "facts:forget", request.id);
    return forgetFact(
      db,
      context,
      forgetSchema.parse(request.body),
      request.id,
    );
  });
  app.post("/v1/resources/locate", async (request) => {
    const context = await authenticateAgent(
      db,
      bearerToken(request.headers.authorization),
      request.id,
    );
    await requireScope(db, context, "resources:locate", request.id);
    return locateResources(
      db,
      context,
      locateSchema.parse(request.body),
      request.id,
    );
  });

  // Resource creation is an internal HTTP primitive, not a sixth MCP operation.
  app.post("/v1/resources", async (request, reply) => {
    const context = await authenticateAgent(
      db,
      bearerToken(request.headers.authorization),
      request.id,
    );
    await requireScope(db, context, "resources:write", request.id);
    return reply
      .status(201)
      .send(
        await createResource(
          db,
          context,
          createResourceSchema.parse(request.body),
          request.id,
        ),
      );
  });

  return app;
}
