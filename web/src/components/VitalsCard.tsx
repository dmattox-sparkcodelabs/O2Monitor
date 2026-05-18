"use client";

/**
 * VitalsCard — Windows baseline viewer stat card style.
 * Dark card (#1a2332) with #2a3a52 border, uppercase muted label,
 * large bold value, optional unit and color coding.
 */

interface VitalsCardProps {
  label: string;
  value: string | number | null;
  unit?: string;
  colorClass?: string;
  large?: boolean;
}

// --- Color classification functions (exported for use in page.tsx) ---

function spo2Color(value: number): string {
  if (value >= 95) return "text-[#51cf66]";
  if (value >= 90) return "text-[#ffd43b]";
  return "text-[#ff6b6b]";
}

function hrColor(value: number): string {
  if (value >= 50 && value <= 120) return "text-[#51cf66]";
  return "text-[#ff6b6b]";
}

function batteryColor(value: number): string {
  if (value > 25) return "text-[#51cf66]";
  if (value > 10) return "text-[#ffd43b]";
  return "text-[#ff6b6b]";
}

function classifyMinSpo2(value: number): string {
  if (value >= 90) return "text-[#51cf66]";
  if (value >= 85) return "text-[#ffd43b]";
  return "text-[#ff6b6b]";
}

function classifyPctBelow(pct: number): string {
  if (pct >= 5) return "text-[#ff6b6b]";
  if (pct >= 1) return "text-[#ffd43b]";
  return "text-[#51cf66]";
}

function classifyOdi(odi: number): string {
  if (odi >= 15) return "text-[#ff6b6b]";
  if (odi >= 5) return "text-[#ffd43b]";
  return "text-[#51cf66]";
}

export { spo2Color, hrColor, batteryColor, classifyMinSpo2, classifyPctBelow, classifyOdi };

export default function VitalsCard({ label, value, unit, colorClass, large }: VitalsCardProps) {
  const valueSize = large
    ? "text-4xl sm:text-5xl"
    : "text-2xl sm:text-3xl";

  return (
    <div className="bg-[#1a2332] border border-[#2a3a52] rounded-lg px-4 py-3 sm:px-5 sm:py-4 min-h-[80px] flex flex-col justify-center">
      <div className="text-[#8a96a7] text-[11px] sm:text-xs uppercase tracking-[0.5px] font-medium mb-1">
        {label}
      </div>
      <div className="flex items-baseline gap-1">
        <span className={`${valueSize} font-semibold tabular-nums ${colorClass ?? "text-[#e4e6eb]"}`}>
          {value !== null && value !== undefined ? value : "--"}
        </span>
        {unit && (
          <span className="text-sm text-[#8a96a7] ml-1">{unit}</span>
        )}
      </div>
    </div>
  );
}
