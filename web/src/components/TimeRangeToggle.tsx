"use client";

interface TimeRangeToggleProps {
  value: number;
  onChange: (hours: number) => void;
}

const options = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
];

export default function TimeRangeToggle({ value, onChange }: TimeRangeToggleProps) {
  return (
    <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
      {options.map((opt) => (
        <button
          key={opt.hours}
          onClick={() => onChange(opt.hours)}
          className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
            value === opt.hours
              ? "bg-gray-600 text-white"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
