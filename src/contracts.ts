import { z } from "zod";

export const SCOPES = [
  "context:read:general",
  "context:read:private",
  "context:read:sensitive",
  "facts:write",
  "facts:correct",
  "facts:forget",
  "resources:locate",
  "resources:write",
] as const;

export const scopeSchema = z.enum(SCOPES);
export type Scope = z.infer<typeof scopeSchema>;

export const sensitivitySchema = z.enum(["general", "private", "sensitive"]);
export type Sensitivity = z.infer<typeof sensitivitySchema>;

export type JsonValue =
  null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export const jsonValueSchema: z.ZodType<JsonValue> = z.lazy(() =>
  z.union([
    z.null(),
    z.boolean(),
    z.number(),
    z.string(),
    z.array(jsonValueSchema),
    z.record(jsonValueSchema),
  ]),
);

export const sourceSchema = z.object({
  type: z.string().trim().min(1).max(80),
  reference: z.string().trim().min(1).max(500),
});

export const claimBrainlinkSchema = z.object({
  token: z.string().min(40).max(200),
  displayName: z.string().trim().min(1).max(100),
  harnessType: z.string().trim().min(1).max(100),
  requestedScopes: z.array(scopeSchema).min(1).max(SCOPES.length),
});

export const exchangeCredentialSchema = z.object({
  requestId: z.string().uuid(),
  claimSecret: z.string().min(40).max(200),
});

export const getContextSchema = z.object({
  task: z.string().trim().min(1).max(2_000),
  subjectHints: z.array(z.string().trim().min(1).max(200)).max(20).optional(),
  maxItems: z.number().int().min(1).max(100).default(20),
});

export const rememberSchema = z.object({
  subject: z.string().trim().min(1).max(200),
  predicate: z.string().trim().min(1).max(200),
  value: jsonValueSchema,
  confidence: z.enum(["confirmed", "inferred", "unconfirmed"]),
  sensitivity: sensitivitySchema.default("private"),
  source: sourceSchema,
});

export const correctInputSchema = z.object({
  previousFactId: z.string().uuid().optional(),
  subject: z.string().trim().min(1).max(200).optional(),
  predicate: z.string().trim().min(1).max(200).optional(),
  replacementValue: jsonValueSchema,
  source: sourceSchema,
  reason: z.string().trim().min(1).max(500).optional(),
});

export const correctSchema = correctInputSchema.superRefine(
  (value, context) => {
    if (!value.previousFactId && !(value.subject && value.predicate)) {
      context.addIssue({
        code: "custom",
        message: "Provide previousFactId or both subject and predicate",
      });
    }
  },
);

export const locateSchema = z.object({
  query: z.string().trim().min(1).max(1_000),
  maxItems: z.number().int().min(1).max(100).default(20),
});

export const forgetSchema = z.object({
  factId: z.string().uuid(),
  reason: z.string().trim().min(1).max(500).optional(),
});

export const createResourceSchema = z.object({
  type: z.enum(["document", "secret-reference", "external-record"]),
  name: z.string().trim().min(1).max(200),
  locator: z.string().trim().min(1).max(2_000),
  sensitivity: sensitivitySchema.default("private"),
  metadata: z.record(jsonValueSchema).default({}),
});
