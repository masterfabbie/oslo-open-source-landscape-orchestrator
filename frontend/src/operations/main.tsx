// Operations: custom operations and schedules in one app; the server says which page
// (boot.page). Operation templates have their own app (templates).

import { mount } from "../lib/mount";
import "../landscape/landscape.css";
import "../activity/activity.css";
import "../templates/templates.css";
import "../lib/forms.css";
import { CustomOperationPage, CustomOperationsPage } from "./CustomOperations";
import { SchedulePage, SchedulesPage } from "./Schedules";

mount((boot) => {
  if (boot.page === "custom_new") return <CustomOperationPage id={null} />;
  if (boot.page === "custom") return <CustomOperationPage id={Number(boot.id)} />;
  if (boot.page === "schedules") return <SchedulesPage />;
  if (boot.page === "schedule_new") return <SchedulePage />;
  if (boot.page === "schedule") return <SchedulePage id={Number(boot.id)} />;
  return <CustomOperationsPage />;
});
