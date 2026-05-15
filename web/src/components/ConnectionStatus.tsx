"use client";

interface ConnectionStatusProps {
  online: boolean;
  secondsSinceReading: number | null;
}

export default function ConnectionStatus({ online, secondsSinceReading }: ConnectionStatusProps) {
  const dotColor = online ? "bg-green-400" : "bg-red-500";
  const label = online ? "Online" : "Offline";
  const ageText = secondsSinceReading !== null
    ? secondsSinceReading < 60
      ? `${secondsSinceReading}s ago`
      : `${Math.floor(secondsSinceReading / 60)}m ago`
    : "No data";

  return (
    <div className="flex items-center gap-3 text-sm text-gray-300">
      <span className={`${dotColor} w-3 h-3 rounded-full ${online ? "animate-pulse" : ""}`} />
      <span className="font-medium">{label}</span>
      <span className="opacity-60">{ageText}</span>
    </div>
  );
}
