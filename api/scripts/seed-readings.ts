const API_URL = "http://localhost:7071/api/readings";
const API_KEY = "test-dev-key";
const PATIENT_ID = "test-patient-1";

async function seed() {
  const now = Date.now();
  const oneHourAgo = now - 60 * 60 * 1000;
  const intervalMs = 15_000; // one reading every 15 seconds
  const count = Math.floor((now - oneHourAgo) / intervalMs);

  console.log(`Seeding ${count} readings over the last hour...`);

  let success = 0;
  for (let i = 0; i < count; i++) {
    const ts = new Date(oneHourAgo + i * intervalMs).toISOString();
    const spo2 = 88 + Math.floor(Math.random() * 12); // 88-99
    const hr = 60 + Math.floor(Math.random() * 30); // 60-89
    const battery = Math.max(50, 90 - Math.floor(i / 10));

    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-api-key": API_KEY },
      body: JSON.stringify({
        patientId: PATIENT_ID,
        spo2,
        heartRate: hr,
        batteryLevel: battery,
        movement: 0,
        timestamp: ts,
        source: "live",
        deviceId: "seed-script",
      }),
    });

    if (res.ok) success++;
    if (i % 50 === 0) process.stdout.write(".");
  }

  console.log(`\nDone. ${success}/${count} readings inserted.`);
}

seed().catch(console.error);
