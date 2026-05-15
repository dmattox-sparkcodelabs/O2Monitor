"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchAccess, grantAccess, revokeAccess } from "@/lib/api";

interface AccessEntry {
  id: string;
  email: string;
  role: string;
  createdAt: string;
}

interface AccessManagerProps {
  patientId: string;
}

export default function AccessManager({ patientId }: AccessManagerProps) {
  const [entries, setEntries] = useState<AccessEntry[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("viewer");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchAccess(patientId);
      setEntries(data);
    } catch {
      setEntries([]);
    }
  }, [patientId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleInvite = async () => {
    if (!email.trim()) return;
    setError(null);
    setLoading(true);
    try {
      await grantAccess(patientId, email.trim(), role);
      setEmail("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to invite");
    } finally {
      setLoading(false);
    }
  };

  const handleRevoke = async (accessId: string) => {
    setError(null);
    try {
      await revokeAccess(patientId, accessId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke");
    }
  };

  return (
    <div>
      {error && (
        <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-2 mb-4 text-red-200 text-sm">{error}</div>
      )}

      {entries.length > 0 && (
        <table className="w-full text-sm text-left mb-4">
          <thead className="text-xs text-gray-400 uppercase border-b border-gray-700">
            <tr>
              <th className="px-4 py-2">Email</th>
              <th className="px-4 py-2">Role</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id} className="border-b border-gray-800">
                <td className="px-4 py-2">{entry.email}</td>
                <td className="px-4 py-2 capitalize">{entry.role}</td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() => handleRevoke(entry.id)}
                    className="text-red-400 hover:text-red-300 text-xs"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {entries.length === 0 && (
        <p className="text-gray-500 text-sm mb-4">No one else has access yet.</p>
      )}

      <div className="flex gap-2 items-end">
        <div className="flex-1">
          <label className="block text-sm text-gray-400 mb-1">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="family@example.com"
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Role</label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm"
          >
            <option value="viewer">Viewer</option>
            <option value="responder">Responder</option>
            <option value="owner">Owner</option>
          </select>
        </div>
        <button
          onClick={handleInvite}
          disabled={loading || !email.trim()}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded transition-colors"
        >
          {loading ? "..." : "Invite"}
        </button>
      </div>
    </div>
  );
}
