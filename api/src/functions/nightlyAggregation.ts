import { app, InvocationContext, Timer } from "@azure/functions";
import { getContainer } from "../shared/cosmos";
import { computeNightDate, computeSummary } from "../shared/aggregation";
import { Patient, Reading } from "../shared/types";

async function nightlyAggregation(
  timer: Timer,
  context: InvocationContext
): Promise<void> {
  const patientsContainer = getContainer("patients");
  const readingsContainer = getContainer("readings");
  const summariesContainer = getContainer("dailySummaries");

  const { resources: patients } = await patientsContainer.items
    .query<Patient>({ query: "SELECT * FROM c" })
    .fetchAll();

  const yesterday = new Date();
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  const nightDate = computeNightDate(yesterday.toISOString());

  for (const patient of patients) {
    const sinceDate = new Date(nightDate);
    sinceDate.setUTCHours(-12, 0, 0, 0);
    const untilDate = new Date(nightDate);
    untilDate.setUTCHours(12, 0, 0, 0);

    const { resources: readings } = await readingsContainer.items
      .query<Reading>({
        query: "SELECT * FROM r WHERE r.patientId = @pid AND r.timestamp >= @since AND r.timestamp < @until ORDER BY r.timestamp ASC",
        parameters: [
          { name: "@pid", value: patient.id },
          { name: "@since", value: sinceDate.toISOString() },
          { name: "@until", value: untilDate.toISOString() },
        ],
      })
      .fetchAll();

    if (readings.length === 0) {
      context.log(`No readings for patient ${patient.id} on night ${nightDate}`);
      continue;
    }

    const summary = computeSummary(patient.id, nightDate, readings);
    await summariesContainer.items.upsert(summary);

    context.log(
      `Aggregated night ${nightDate} for ${patient.name}: ${summary.readingCount} readings, avg SpO2 ${summary.spo2Avg}`
    );
  }
}

app.timer("nightlyAggregation", {
  schedule: "0 0 8 * * *",
  handler: nightlyAggregation,
});
