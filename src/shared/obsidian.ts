export interface ObsidianPreview { folderName: string; files: number; tasks: number; warnings: string[] }
export interface ObsidianResult { imported: number; updated: number; skipped: number; conflicts: string[]; warnings: string[] }
export interface ObsidianTaskLink { key: string; id: string; baseCompleted?: boolean }
export interface ObsidianFileLink { relativePath: string; hash: string; noteId: string; noteBody: string; tasks: ObsidianTaskLink[] }
export interface ObsidianVaultLink { root: string; scope: string; files: ObsidianFileLink[] }
/** Local-only metadata. Absolute vault paths must never enter cloud Item payloads. */
export interface ObsidianState { version: 1; vaults: ObsidianVaultLink[] }
