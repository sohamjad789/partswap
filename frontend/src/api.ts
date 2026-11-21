import type { BomLine, DesignContext, EvalResults, Extraction, Health, Mode, PartInfo, RunEvent } from "./types";

/** An HTTP error that may carry a list of readable messages (BOM row errors). */
export class ApiError extends Error {
  constructor(message: string, readonly details: string[] = []) {
    super(message);
  }
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const text = await response.text();
    let details: string[] = [];
    try {
      const body = JSON.parse(text) as { errors?: Array<{ row: number; message: string }>; detail?: string };
      if (body.errors) details = body.errors.map(error => `Row ${error.row}: ${error.message}`);
      else if (body.detail) details = [body.detail];
    } catch {
      details = text ? [text] : [];
    }
    throw new ApiError(details[0] ?? `Request failed (${response.status})`, details);
  }
  return response.json() as Promise<T>;
}

export const getHealth = () => json<Health>("/api/health");
export const fetchDemoBom = () => json<{ csv: string; design_context: DesignContext }>("/api/demo-bom");
export const parseBom = (csv: string) => json<{ lines: BomLine[] }>("/api/bom/parse", { method: "POST", headers: { "Content-Type": "text/csv" }, body: csv });
export const fetchPart = (mpn: string) => json<PartInfo>(`/api/parts/${encodeURIComponent(mpn)}`);
export const fetchEval = () => json<EvalResults>("/api/eval");
export const fetchExtraction = (mpn: string) => json<Extraction>(`/api/extract/${encodeURIComponent(mpn)}`);
export const datasheetUrl = (mpn: string, page?: number | null) => `/api/datasheets/${encodeURIComponent(mpn)}${page ? `#page=${page}` : ""}`;

export async function streamRun(body: { lines: BomLine[]; design_context: DesignContext; mode: Mode }, onEvent: (event: RunEvent) => void) {
  const response = await fetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok || !response.body) throw new ApiError(`Unable to start run (${response.status})`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = block.match(/^event:\s*(.+)$/m)?.[1];
      const raw = block.match(/^data:\s*(.+)$/m)?.[1];
      if (event && raw) onEvent({ event, data: JSON.parse(raw) } as RunEvent);
    }
    if (done) break;
  }
}
