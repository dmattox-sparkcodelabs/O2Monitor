"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchReadings, fetchSummaries } from "@/lib/api";
import { ReadingRecord, NightlySummary } from "@/lib/types";
import { countDesaturationEvents } from "@/lib/stats";
import { usePatient } from "@/hooks/usePatient";
import { classifyMinSpo2, classifyPctBelow, classifyOdi } from "@/components/VitalsCard";
import Nav from "@/components/Nav";
import NightCard from "@/components/NightCard";

const RANGE_OPTIONS = [
  { label: "7d", days: 7 },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
];

export interface NightOdi {
  odi3: number | null;
  odi4: number | null;
  readings: ReadingRecord[];
}

export default function HistoryPage() {
  const { selectedId, loading: patientsLoading } = usePatient();
  const [summaries, setSummaries] = useState<NightlySummary[]>([]);
  const [rangeDays, setRangeDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [nightData, setNightData] = useState<Record<string, NightOdi>>({});

  const load = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      const res = await fetchSummaries(selectedId, rangeDays);
      setSummaries(res.summaries);
      setNightData({});
    } catch {
      setSummaries([]);
    } finally {
      setLoading(false);
    }
  }, [selectedId, rangeDays]);

  useEffect(() => {
    load();
  }, [load]);

  const loadNightReadings = useCallback(async (nightDate: string) => {
    if (!selectedId || nightData[nightDate]) return;
    const nightStart = new Date(nightDate + "T20:00:00");
    const nightEnd = new Date(nightDate + "T20:00:00");
    nightEnd.setDate(nightEnd.getDate() + 1);
    nightEnd.setHours(12, 0, 0, 0);

    const now = new Date();
    const hoursAgo = Math.max(1, (now.getTime() - nightStart.getTime()) / (1000 * 60 * 60));

    try {
      const res = await fetchReadings(selectedId, Math.ceil(hoursAgo));
      const nightReadings = res.readings
        .filter((r) => {
          const ts = new Date(r.timestamp);
          return ts >= nightStart && ts <= nightEnd;
        })
        .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

      const durationHours = nightReadings.length >= 2
        ? (new Date(nightReadings[nightReadings.length - 1].timestamp).getTime() - new Date(nightReadings[0].timestamp).getTime()) / (1000 * 3600)
        : 0;

      const odi3Events = countDesaturationEvents(nightReadings, 3);
      const odi4Events = countDesaturationEvents(nightReadings, 4);

      setNightData((prev) => ({
        ...prev,
        [nightDate]: {
          odi3: durationHours > 0 ? Math.round((odi3Events / durationHours) * 10) / 10 : 0,
          odi4: durationHours > 0 ? Math.round((odi4Events / durationHours) * 10) / 10 : 0,
          readings: nightReadings,
        },
      }));
    } catch {
      setNightData((prev) => ({
        ...prev,
        [nightDate]: { odi3: null, odi4: null, readings: [] },
      }));
    }
  }, [selectedId, nightData]);

  if (patientsLoading) {
    return (
      <main className="flex-1 bg-[#0f1419] text-[#e4e6eb] flex items-center justify-center">
        <div className="text-[#8a96a7]">Loading...</div>
      </main>
    );
  }

  return (
    <main className="flex-1 bg-[#0f1419] text-[#e4e6eb]">
      <header className="border-b border-[#2a3a52] px-6 py-4">
        <div className="w-full flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-xl font-semibold">History</h1>
            <Nav />
          </div>
          <div className="flex gap-1.5">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.days}
                onClick={() => setRangeDays(opt.days)}
                className={`px-3 py-1.5 rounded-md text-[13px] font-medium border transition-colors duration-200 ${
                  rangeDays === opt.days
                    ? "bg-[#4dabf7] border-[#4dabf7] text-[#0b1220]"
                    : "bg-[#1a2332] border-[#2a3a52] text-[#e4e6eb] hover:border-[#4dabf7]"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="w-full px-6 py-6 space-y-4">
        {loading ? (
          <div className="text-center text-[#8a96a7] py-20">Loading summaries...</div>
        ) : summaries.length === 0 ? (
          <div className="text-center text-[#8a96a7] py-20">No nightly data available yet.</div>
        ) : (
          summaries.map((s) => (
            <NightCard
              key={s.nightDate}
              summary={s}
              odi={nightData[s.nightDate] ?? null}
              onVisible={() => loadNightReadings(s.nightDate)}
              classifyMinSpo2={classifyMinSpo2}
              classifyPctBelow={classifyPctBelow}
              classifyOdi={classifyOdi}
            />
          ))
        )}
      </div>

      <footer className="text-center text-xs text-[#5a6a7a] py-4 pb-20 md:pb-4">
        NOT FOR MEDICAL USE -- Proof of concept only
      </footer>
    </main>
  );
}
