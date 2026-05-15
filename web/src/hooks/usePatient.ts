"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchPatients } from "@/lib/api";
import { PatientSummary } from "@/lib/types";

const STORAGE_KEY = "o2monitor-selected-patient";

export function usePatient() {
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await fetchPatients();
      setPatients(list);
      setError(null);

      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && list.some((p) => p.id === stored)) {
        setSelectedId(stored);
      } else if (list.length > 0) {
        setSelectedId(list[0].id);
        localStorage.setItem(STORAGE_KEY, list[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load patients");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const selectPatient = useCallback((id: string) => {
    setSelectedId(id);
    localStorage.setItem(STORAGE_KEY, id);
  }, []);

  const selected = patients.find((p) => p.id === selectedId) ?? null;

  return { patients, selected, selectedId, selectPatient, loading, error, reload: load };
}
