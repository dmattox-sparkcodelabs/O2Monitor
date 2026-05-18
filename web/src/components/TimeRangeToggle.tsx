"use client";

/**
 * TimeRangeToggle — Windows baseline viewer zoom toolbar style.
 * Pill buttons with accent color (#4dabf7) for active state.
 * Matches the zoom-toolbar from the reference design.
 */

interface TimeRangeToggleProps {
  value: number;
  onChange: (hours: number) => void;
}

const options = [
  { label: "15m", hours: 0.25 },
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "12h", hours: 12 },
  { label: "24h", hours: 24 },
];

export default function TimeRangeToggle({ value, onChange }: TimeRangeToggleProps) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[#8a96a7] text-xs uppercase tracking-[0.5px] font-medium mr-1">
        Zoom
      </span>
      <div className="flex gap-1.5">
        {options.map((opt) => (
          <button
            key={opt.hours}
            onClick={() => onChange(opt.hours)}
            className={`px-3 py-1.5 rounded-md text-[13px] font-medium border transition-colors duration-200 ${
              value === opt.hours
                ? "bg-[#4dabf7] border-[#4dabf7] text-[#0b1220]"
                : "bg-[#1a2332] border-[#2a3a52] text-[#e4e6eb] hover:border-[#4dabf7]"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
