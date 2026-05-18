"use client";

/**
 * PatientSelector — Dropdown styled to match Windows viewer toolbar selects.
 */

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
      className="bg-[#1a2332] text-[#e4e6eb] border border-[#2a3a52] rounded-md px-3 py-1.5 text-sm cursor-pointer hover:border-[#4dabf7] transition-colors duration-200"
    >
      {patients.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </select>
  );
}
