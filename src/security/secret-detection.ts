const SECRET_PATTERNS: Array<{ code: string; pattern: RegExp }> = [
  {
    code: "PRIVATE_KEY",
    pattern: /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/i,
  },
  { code: "OPENAI_STYLE_KEY", pattern: /\bsk-[A-Za-z0-9_-]{20,}\b/ },
  { code: "GITHUB_TOKEN", pattern: /\bgh[pousr]_[A-Za-z0-9]{20,}\b/ },
  { code: "AWS_ACCESS_KEY", pattern: /\bAKIA[0-9A-Z]{16}\b/ },
  {
    code: "JWT",
    pattern: /\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/,
  },
  {
    code: "LABELED_SECRET",
    pattern:
      /\b(?:password|passwd|api[_ -]?key|access[_ -]?token|session[_ -]?cookie)\s*[:=]\s*\S+/i,
  },
  { code: "CARD_NUMBER", pattern: /\b(?:\d[ -]*?){13,19}\b/ },
];

function stringsIn(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(stringsIn);
  if (value && typeof value === "object")
    return Object.entries(value).flatMap(([key, item]) => [
      key,
      ...stringsIn(item),
    ]);
  return [];
}

export function detectSecret(value: unknown): string | undefined {
  for (const text of stringsIn(value)) {
    const match = SECRET_PATTERNS.find(({ pattern }) => pattern.test(text));
    if (match) return match.code;
  }
  return undefined;
}
