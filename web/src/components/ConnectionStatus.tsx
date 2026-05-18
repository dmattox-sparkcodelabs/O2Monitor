"use client";

/**
 * ConnectionStatus — Compact inline status matching Windows viewer style.
 * Green/red dot + label + time-since-reading.
 */

interface ConnectionStatusProps {
  online: boolean;
  secondsSinceReading: number | null;
}

export default function ConnectionStatus({ online, secondsSinceReading }: ConnectionStatusProps) {
  const dotColor = online ? "bg-[#51cf66]" : "bg-[#ff6b6b]";
  const label = online ? "Online" : "Offline";
  const ageText = secondsSinceReading !== null
    ? secondsSinceReading < 60
      ? `${secondsSinceReading}s ago`
      : `${Math.floor(secondsSinceReading / 60)}m ago`
    : "No data";

  return (
    <div className="flex items-center gap-2.5 text-sm">
      <span className={`${dotColor} w-2.5 h-2.5 rounded-full ${online ? "animate-pulse" : ""}`} />
      <span className="font-medium text-[#e4e6eb]">{label}</span>
      <span className="text-[#8a96a7]">{ageText}</span>
    </div>
  );
}
