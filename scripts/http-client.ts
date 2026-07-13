import { readFileSync } from "node:fs";

const path = process.argv[2];
if (!path?.startsWith("/"))
  throw new Error("Usage: npm run http -- /v1/path < request.json");

const body = readFileSync(0, "utf8").trim();
const credential = process.env.MEGABRAIN_AGENT_TOKEN;
const response = await fetch(
  `${process.env.MEGABRAIN_BASE_URL ?? "http://127.0.0.1:3210"}${path}`,
  {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(credential ? { authorization: `Bearer ${credential}` } : {}),
    },
    body: body || "{}",
  },
);

process.stdout.write(await response.text());
if (!response.ok) process.exitCode = 1;
