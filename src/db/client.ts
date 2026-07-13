import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";
import type { Config } from "../config.js";
import * as schema from "./schema.js";

export function createDatabase(config: Pick<Config, "DATABASE_URL">) {
  const client = postgres(config.DATABASE_URL, { max: 10 });
  return { db: drizzle(client, { schema }), client };
}

export type Database = ReturnType<typeof createDatabase>["db"];
