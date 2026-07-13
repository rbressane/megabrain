import "dotenv/config";
import { z } from "zod";

const configSchema = z.object({
  DATABASE_URL: z
    .string()
    .url()
    .default("postgres://megabrain:megabrain@localhost:5432/megabrain"),
  HOST: z.string().default("127.0.0.1"),
  PORT: z.coerce.number().int().min(1).max(65_535).default(3210),
  LOG_LEVEL: z
    .enum(["fatal", "error", "warn", "info", "debug", "trace", "silent"])
    .default("info"),
  MEGABRAIN_BASE_URL: z.string().url().default("http://127.0.0.1:3210"),
});

export type Config = z.infer<typeof configSchema>;

export function loadConfig(
  environment: NodeJS.ProcessEnv = process.env,
): Config {
  return configSchema.parse(environment);
}
