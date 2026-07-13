import { buildApp } from "./app.js";
import { loadConfig } from "./config.js";
import { createDatabase } from "./db/client.js";

const config = loadConfig();
const { db, client } = createDatabase(config);
const app = buildApp({ db, logger: { level: config.LOG_LEVEL } });

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.once(signal, () => {
    void app.close().finally(() => client.end());
  });
}

await app.listen({ host: config.HOST, port: config.PORT });
