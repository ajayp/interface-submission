// Mirrors harness/contract.py. Only plain data crosses the boundary.
export interface Page { url: string; title: string; markdown: string; fetchedAt: string }
export interface Snapshot { snapshotId: string; takenOn: string; pages: Page[] }
export interface Source { url: string; snapshotId?: string | null; quote?: string | null }
export interface Answer {
  text: string;
  sources: Source[];
  confident: boolean;
  conflictNote?: string | null;
}
export interface Conflict {
  topic: string;
  values: string[];
  sources: Source[];
  resolution?: string | null;
  reason?: string | null;
}
export interface KnowledgeSystem {
  ingest(snapshot: Snapshot): Promise<void>;
  answer(question: string, asOf?: string | null): Promise<Answer>;
  conflicts(): Promise<Conflict[]>;
}
