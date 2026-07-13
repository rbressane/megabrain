import { describe, expect, it } from "vitest";
import { detectSecret } from "../../src/security/secret-detection.js";
import {
  hashToken,
  issueToken,
  tokenHashMatches,
} from "../../src/security/tokens.js";

describe("security primitives", () => {
  it("issues 256-bit random tokens and verifies only their hashes", () => {
    const token = issueToken("mb_test");
    expect(
      Buffer.from(token.slice("mb_test_".length), "base64url"),
    ).toHaveLength(32);
    expect(hashToken(token)).not.toContain(token);
    expect(tokenHashMatches(token, hashToken(token))).toBe(true);
    expect(tokenHashMatches(`${token}x`, hashToken(token))).toBe(false);
  });

  it.each([
    "sk-example012345678901234567890", // secret-scan: allow-test-fixture
    "password=hunter2", // secret-scan: allow-test-fixture
    "-----BEGIN PRIVATE KEY-----", // secret-scan: allow-test-fixture
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
    "4111 1111 1111 1111",
  ])("detects representative secret material: %s", (value) => {
    expect(detectSecret({ value })).toBeDefined();
  });

  it("does not classify a synthetic address as a secret", () => {
    expect(detectSecret("14 Example Lane, Testville")).toBeUndefined();
  });
});
