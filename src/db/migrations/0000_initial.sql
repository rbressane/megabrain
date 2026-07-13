CREATE TYPE "agent_status" AS ENUM ('pending', 'active', 'revoked');
CREATE TYPE "fact_status" AS ENUM ('active', 'superseded', 'forgotten');
CREATE TYPE "confidence" AS ENUM ('confirmed', 'inferred', 'unconfirmed');
CREATE TYPE "sensitivity" AS ENUM ('general', 'private', 'sensitive');
CREATE TYPE "resource_type" AS ENUM ('document', 'secret-reference', 'external-record');

CREATE TABLE "users" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "display_name" text NOT NULL,
  "created_at" timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE "agents" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "user_id" uuid NOT NULL REFERENCES "users"("id"),
  "display_name" text NOT NULL,
  "harness_type" text NOT NULL,
  "status" agent_status NOT NULL DEFAULT 'pending',
  "credential_hash" text,
  "claim_secret_hash" text NOT NULL,
  "approved_scopes" text[] NOT NULL DEFAULT '{}',
  "requested_scopes" text[] NOT NULL DEFAULT '{}',
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "approved_at" timestamptz,
  "credential_issued_at" timestamptz,
  "last_used_at" timestamptz,
  "revoked_at" timestamptz
);
CREATE INDEX "agents_user_idx" ON "agents" ("user_id");
CREATE UNIQUE INDEX "agents_credential_hash_idx" ON "agents" ("credential_hash");

CREATE TABLE "brainlinks" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "user_id" uuid NOT NULL REFERENCES "users"("id"),
  "token_hash" text NOT NULL,
  "expires_at" timestamptz NOT NULL,
  "maximum_claims" integer NOT NULL DEFAULT 1 CHECK (maximum_claims = 1),
  "claimed_at" timestamptz,
  "created_at" timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX "brainlinks_token_hash_idx" ON "brainlinks" ("token_hash");

CREATE TABLE "facts" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "user_id" uuid NOT NULL REFERENCES "users"("id"),
  "subject" text NOT NULL,
  "predicate" text NOT NULL,
  "value" jsonb NOT NULL,
  "status" fact_status NOT NULL DEFAULT 'active',
  "confidence" confidence NOT NULL,
  "sensitivity" sensitivity NOT NULL DEFAULT 'private',
  "source_type" text NOT NULL,
  "source_reference" text NOT NULL,
  "created_by_agent_id" uuid REFERENCES "agents"("id"),
  "valid_from" timestamptz NOT NULL DEFAULT now(),
  "valid_until" timestamptz,
  "supersedes_fact_id" uuid REFERENCES "facts"("id"),
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "updated_at" timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX "facts_current_lookup_idx" ON "facts" ("user_id", "status", "subject", "predicate");
CREATE INDEX "facts_supersedes_idx" ON "facts" ("supersedes_fact_id");
CREATE UNIQUE INDEX "facts_one_active_value_idx" ON "facts" ("user_id", "subject", "predicate") WHERE "status" = 'active';

CREATE TABLE "resource_references" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "user_id" uuid NOT NULL REFERENCES "users"("id"),
  "resource_type" resource_type NOT NULL,
  "name" text NOT NULL,
  "locator" text NOT NULL,
  "sensitivity" sensitivity NOT NULL DEFAULT 'private',
  "metadata" jsonb NOT NULL DEFAULT '{}',
  "created_by_agent_id" uuid NOT NULL REFERENCES "agents"("id"),
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "updated_at" timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX "resources_lookup_idx" ON "resource_references" ("user_id", "resource_type", "name");

CREATE TABLE "audit_events" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "user_id" uuid REFERENCES "users"("id"),
  "agent_id" uuid REFERENCES "agents"("id"),
  "event_type" text NOT NULL,
  "outcome" text NOT NULL,
  "reason_code" text,
  "target_type" text,
  "target_id" text,
  "request_id" text,
  "metadata" jsonb NOT NULL DEFAULT '{}',
  "created_at" timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX "audit_user_time_idx" ON "audit_events" ("user_id", "created_at");
