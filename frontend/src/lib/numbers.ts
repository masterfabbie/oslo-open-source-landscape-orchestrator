// How activities and steps are numbered on the pages (wish of the owner): an activity is
// "A100002", a step "O100002". Both are the activity's id in the database plus 100000, so a
// single operation has the same number as activity and as step.

const OFFSET = 100000;

export function activityNumber(id: number): string {
  return `A${OFFSET + id}`;
}

export function stepNumber(id: number): string {
  return `O${OFFSET + id}`;
}

/** "1:02" (minutes and seconds) or "1:02:03" from one hour on; "" without a start. */
export function formatDuration(start: string | null, end: string | null, now: number = Date.now()): string {
  if (!start) return "";
  const seconds = Math.max(0, Math.round(((end ? Date.parse(end) : now) - Date.parse(start)) / 1000));
  const pad = (n: number) => String(n).padStart(2, "0");
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}
