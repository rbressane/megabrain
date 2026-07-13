import { migrate } from "drizzle-orm/postgres-js/migrator";
import { loadConfig } from "../config.js";
import { createDatabase } from "./client.js";

export async function runMigrations(
  databaseUrl = loadConfig().DATABASE_URL,
): Promise<void> {
  const { db, client } = createDatabase({ DATABASE_URL: databaseUrl });
  try {
    await migrate(db, { migrationsFolder: "src/db/migrations" });
  } finally {
    await client.end();
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await runMigrations();
  console.log("Database migrations complete.");
}
