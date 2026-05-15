"use client";

import { PatientSummary } from "@/lib/types";

interface PatientSelectorProps {
  patients: PatientSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function PatientSelector({ patients, selectedId, onSelect }: PatientSelectorProps) {
  if (patients.length <= 1) return null;

  return (
    <select
      value={selectedId ?? ""}
      onChange={(e) => onSelect(e.target.value)}
      className="bg-gray-800 text-white border border-gray-700 rounded px-2 py-1 text-sm"
    >
      {patients.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </select>
  );
}
