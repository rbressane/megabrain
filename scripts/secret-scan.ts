import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const result = spawnSync(
  "git",
  ["ls-files", "--cached", "--others", "--exclude-standard"],
  {
    encoding: "utf8",
  },
);
if (result.status !== 0)
  throw new Error(result.stderr || "Unable to list repository files");

const patterns = [
  {
    name: "private key",
    value: /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  },
  { name: "OpenAI-style key", value: /\bsk-[A-Za-z0-9_-]{20,}\b/ },
  { name: "GitHub token", value: /\bgh[pousr]_[A-Za-z0-9]{20,}\b/ },
  { name: "AWS access key", value: /\bAKIA[0-9A-Z]{16}\b/ },
  {
    name: "labeled secret",
    value:
      /\b(?:password|passwd|api[_ -]?key|access[_ -]?token)\s*[:=]\s*[^\s<]+/i,
  },
];
const findings: string[] = [];

for (const file of result.stdout.split("\n").filter(Boolean)) {
  if (file === "scripts/secret-scan.ts" || file === "package-lock.json")
    continue;
  let content: string;
  try {
    content = readFileSync(file, "utf8");
  } catch {
    continue;
  }
  content.split("\n").forEach((line, index) => {
    if (line.includes("secret-scan: allow-test-fixture")) return;
    for (const pattern of patterns) {
      if (pattern.value.test(line))
        findings.push(`${file}:${index + 1}: possible ${pattern.name}`);
    }
  });
}

if (findings.length) {
  console.error(findings.join("\n"));
  process.exitCode = 1;
} else {
  console.log(
    "Secret scan passed: no unallowlisted credential patterns found.",
  );
}
