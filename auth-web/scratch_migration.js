
const { Client } = require('pg');

const client = new Client({
  connectionString: "postgresql://postgres:postgres@localhost:54322/postgres"
});

async function run() {
  try {
    await client.connect();
    console.log("Connected to DB");
    await client.query("ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS custom_api_keys JSONB DEFAULT '{}'::jsonb;");
    console.log("Migration Success: Added custom_api_keys column");
  } catch (err) {
    console.error("Migration Failed:", err);
  } finally {
    await client.end();
  }
}

run();
