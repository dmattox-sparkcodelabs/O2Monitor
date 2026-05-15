"use client";

interface VitalsCardProps {
  label: string;
  value: number | null;
  unit: string;
  colorFn?: (value: number) => string;
  large?: boolean;
}

function spo2Color(value: number): string {
  if (value >= 95) return "bg-green-500";
  if (value >= 92) return "bg-yellow-500";
  if (value >= 90) return "bg-orange-500";
  return "bg-red-600";
}

function hrColor(value: number): string {
  if (value >= 50 && value <= 120) return "bg-green-500";
  return "bg-red-600";
}

function batteryColor(value: number): string {
  if (value > 25) return "bg-green-500";
  if (value > 10) return "bg-yellow-500";
  return "bg-red-600";
}

export { spo2Color, hrColor, batteryColor };

export default function VitalsCard({ label, value, unit, colorFn, large }: VitalsCardProps) {
  const bgColor = value !== null && colorFn ? colorFn(value) : "bg-gray-700";
  const textSize = large ? "text-7xl md:text-8xl" : "text-5xl md:text-6xl";

  return (
    <div className={`${bgColor} rounded-2xl p-6 text-white flex flex-col items-center justify-center min-h-[180px] transition-colors duration-500`}>
      <span className="text-sm font-medium uppercase tracking-wider opacity-80 mb-2">{label}</span>
      <div className="flex items-baseline gap-1">
        <span className={`${textSize} font-bold tabular-nums`}>
          {value !== null ? value : "--"}
        </span>
        <span className="text-2xl font-light opacity-80">{unit}</span>
      </div>
    </div>
  );
}
