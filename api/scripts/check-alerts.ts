import { CosmosClient } from "@azure/cosmos";

process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";

const client = new CosmosClient(
  "AccountEndpoint=https://localhost:8081/;AccountKey=C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
);

async function main() {
  const db = client.database("o2monitor");
  const alerts = db.container("alerts");
  const { resources } = await alerts.items
    .query('SELECT a.id, a.alertType, a.severity, a.message, a.spo2, a.resolvedAt FROM a WHERE a.patientId = "test-patient-1"')
    .fetchAll();
  console.log(`Found ${resources.length} alerts:`);
  console.log(JSON.stringify(resources, null, 2));
}

main().catch(console.error);
