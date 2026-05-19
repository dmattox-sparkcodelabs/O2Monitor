"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { fetchNightReadings, fetchSummaries, triggerAggregation } from "@/lib/api";
import { ReadingRecord, NightlySummary } from "@/lib/types";
import { countDesaturationEvents } from "@/lib/stats";
import { usePatient } from "@/hooks/usePatient";
import { classifyMinSpo2, classifyPctBelow, classifyOdi } from "@/components/VitalsCard";
import Nav from "@/components/Nav";
import PatientSelector from "@/components/PatientSelector";
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
  const { patients, selectedId, selectPatient, loading: patientsLoading } = usePatient();
  const [summaries, setSummaries] = useState<NightlySummary[]>([]);
  const [rangeDays, setRangeDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [nightData, setNightData] = useState<Record<string, NightOdi>>({});
  const [sleepOnly, setSleepOnly] = useState(false);

  const load = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      await triggerAggregation(selectedId).catch(() => {});
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

  const currentNightDate = useMemo(() => {
    const now = new Date();
    const noon = new Date(now);
    noon.setHours(12, 0, 0, 0);
    const d = now >= noon ? new Date(now.getTime() + 24 * 60 * 60 * 1000) : now;
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }, []);

  const nightDataRef = useRef(nightData);
  nightDataRef.current = nightData;

  const loadNightReadings = useCallback(async (nightDate: string, force = false) => {
    if (!selectedId || (!force && nightDataRef.current[nightDate])) return;
    const [y, m, d] = nightDate.split("-").map(Number);
    const sinceDate = new Date(y, m - 1, d - 1, 12, 0, 0, 0);
    const since = sinceDate.toISOString();
    const untilDate = new Date(y, m - 1, d, 12, 0, 0, 0);
    const until = untilDate.toISOString();

    try {
      const res = await fetchNightReadings(selectedId, since, until);
      const nightReadings = res.readings
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
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId || !currentNightDate) return;
    loadNightReadings(currentNightDate, true);
    const interval = setInterval(() => {
      loadNightReadings(currentNightDate, true);
    }, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [selectedId, currentNightDate, loadNightReadings]);

  useEffect(() => {
    const onBeforePrint = () => {
      const pageWidthPx = 7.3 * 96;
      const chart = document.querySelector(".recharts-wrapper") as HTMLElement | null;
      if (chart) {
        const chartWidth = chart.offsetWidth;
        const scaleX = Math.min(1, pageWidthPx / chartWidth);
        const scaleY = scaleX * 2;
        const containerHeight = 120 * scaleY;
        document.documentElement.style.setProperty("--print-chart-scale", String(scaleX));
        document.documentElement.style.setProperty("--print-chart-scale-y", String(scaleY));
        document.documentElement.style.setProperty("--print-chart-height", `${containerHeight}px`);
      }
    };
    const onAfterPrint = () => {
      document.documentElement.style.removeProperty("--print-chart-scale");
      document.documentElement.style.removeProperty("--print-chart-scale-y");
      document.documentElement.style.removeProperty("--print-chart-height");
    };
    window.addEventListener("beforeprint", onBeforePrint);
    window.addEventListener("afterprint", onAfterPrint);
    return () => {
      window.removeEventListener("beforeprint", onBeforePrint);
      window.removeEventListener("afterprint", onAfterPrint);
    };
  }, []);

  if (patientsLoading) {
    return (
      <main className="flex-1 bg-[#0f1419] text-[#e4e6eb] flex items-center justify-center">
        <div className="text-[#8a96a7]">Loading...</div>
      </main>
    );
  }

  return (
    <main className="flex-1 bg-[#0f1419] text-[#e4e6eb]">
      <div className="hidden print:block text-center mb-4">
        <h1 className="text-xl font-bold text-black">O2 Monitor — Sleep History</h1>
      </div>
      <header className="border-b border-[#2a3a52] px-6 py-4 print:hidden">
        <div className="w-full flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-xl font-semibold">History</h1>
            <Nav />
            <PatientSelector
              patients={patients}
              selectedId={selectedId}
              onSelect={selectPatient}
            />
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={sleepOnly}
                onChange={(e) => setSleepOnly(e.target.checked)}
                className="w-4 h-4 rounded border-[#2a3a52] bg-[#1a2332] text-[#4dabf7] focus:ring-[#4dabf7] focus:ring-offset-0 cursor-pointer"
              />
              <span className="text-sm text-[#a0aec0]">Sleep only (10p–6a)</span>
            </label>
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
              sleepOnly={sleepOnly}
              classifyMinSpo2={classifyMinSpo2}
              classifyPctBelow={classifyPctBelow}
              classifyOdi={classifyOdi}
            />
          ))
        )}
      </div>

    </main>
  );
}
