// How a schedule repeats, in words; shared by the schedules of a template and the area
// Activities → Schedules.

import { formatTime } from "../landscape/ui";
import type { Translate } from "./i18n";
import type { ScheduleRow } from "./types";

export function describeSchedule(s: ScheduleRow, t: Translate, language: string): string {
  if (s.recurrence === "once") return t("sched.once_at", { time: formatTime(s.run_at, language) });
  if (s.recurrence === "interval") return t("sched.every", { minutes: s.interval_minutes ?? 0 });
  const days = s.weekdays
    .split("")
    .map((d) => t(`sched.day.${d}`))
    .join(", ");
  return t("sched.daily_at", { time: s.time_of_day ?? "", days });
}
