import { CosmosClient, Database, Container } from "@azure/cosmos";

let client: CosmosClient | null = null;
let database: Database | null = null;

function getClient(): CosmosClient {
  if (!client) {
    const connectionString = process.env.COSMOS_CONNECTION_STRING;
    if (!connectionString) {
      throw new Error("COSMOS_CONNECTION_STRING is not set");
    }
    client = new CosmosClient(connectionString);
  }
  return client;
}

function getDatabase(): Database {
  if (!database) {
    const dbName = process.env.COSMOS_DATABASE_NAME || "o2monitor";
    database = getClient().database(dbName);
  }
  return database;
}

export function getContainer(name: string): Container {
  return getDatabase().container(name);
}

export async function initializeDatabase(): Promise<void> {
  const client = getClient();
  const dbName = process.env.COSMOS_DATABASE_NAME || "o2monitor";

  await client.databases.createIfNotExists({ id: dbName });
  const db = client.database(dbName);

  await db.containers.createIfNotExists({
    id: "readings",
    partitionKey: { paths: ["/patientId"] },
    defaultTtl: -1,
  });

  await db.containers.createIfNotExists({
    id: "patients",
    partitionKey: { paths: ["/id"] },
  });
}
