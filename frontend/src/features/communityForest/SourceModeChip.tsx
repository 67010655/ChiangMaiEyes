import type { SourceMode } from "../../lib/types";

const LABELS: Record<SourceMode, string> = {
  LIVE: "สด",
  SNAPSHOT: "สแนปชอต",
  DERIVED: "คำนวณ",
  PROTOTYPE: "ข้อมูลต้นแบบ",
  UNAVAILABLE: "ไม่พร้อม",
};

export function SourceModeChip({ mode }: { mode: SourceMode }) {
  return (
    <span className={`source-mode-chip source-mode-chip--${mode.toLowerCase()}`}>
      {LABELS[mode]}
    </span>
  );
}
