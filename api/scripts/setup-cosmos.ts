import { CosmosClient } from "@azure/cosmos";

const connectionString =
  "AccountEndpoint=https://localhost:8081/;AccountKey=C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==";

async function main() {
  // The emulator uses a self-signed cert
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";

  const client = new CosmosClient(connectionString);

  console.log("Creating database 'o2monitor'...");
  const { database } = await client.databases.createIfNotExists({ id: "o2monitor" });

  console.log("Creating 'readings' container...");
  await database.containers.createIfNotExists({
    id: "readings",
    partitionKey: { paths: ["/patientId"] },
    defaultTtl: -1,
    indexingPolicy: {
      automatic: true,
      indexingMode: "consistent",
      compositeIndexes: [
        [
          { path: "/patientId", order: "ascending" },
          { path: "/timestamp", order: "descending" },
        ],
      ],
    },
  });

  console.log("Creating 'alerts' container...");
  await database.containers.createIfNotExists({
    id: "alerts",
    partitionKey: { paths: ["/patientId"] },
    defaultTtl: -1,
  });

  console.log("Creating 'patients' container...");
  await database.containers.createIfNotExists({
    id: "patients",
    partitionKey: { paths: ["/id"] },
  });

  console.log("Seeding test patient...");
  const patients = database.container("patients");
  await patients.items.upsert({
    id: "test-patient-1",
    name: "Dad (Test)",
    deviceMac: "C8:F1:6B:56:7B:F1",
    deviceName: "O2M 2781",
    alertConfig: {
      spo2CriticalThreshold: 90,
      spo2CriticalDurationSec: 30,
      spo2WarningThreshold: 92,
      spo2WarningDurationSec: 60,
      hrHighThreshold: 120,
      hrLowThreshold: 50,
      hrDurationSec: 60,
      batteryWarningThreshold: 25,
      batteryCriticalThreshold: 10,
      disconnectAlertSec: 120,
      pagerdutyRoutingKey: "",
      resendIntervalSec: 300,
    },
    createdAt: new Date().toISOString(),
    createdBy: "setup-script",
  });

  console.log("Done. Database and containers ready.");
}

main().catch((err) => {
  console.error("Setup failed:", err.message);
  process.exit(1);
});
