export interface ReadingsQueryParams {
  hours: number;
  limit: number;
  since?: string;
  until?: string;
}

export function parseReadingsQueryParams(params: URLSearchParams): ReadingsQueryParams {
  const hoursRaw = parseInt(params.get("hours") ?? "1", 10);
  const limitRaw = parseInt(params.get("limit") ?? "1000", 10);

  const hours = Math.min(168, Math.max(1, isNaN(hoursRaw) ? 1 : hoursRaw));
  const limit = Math.min(50000, Math.max(1, isNaN(limitRaw) ? 1000 : limitRaw));

  const since = params.get("since") ?? undefined;
  const until = params.get("until") ?? undefined;

  return { hours, limit, since, until };
}
