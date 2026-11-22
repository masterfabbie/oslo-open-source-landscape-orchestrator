import { mount } from "../lib/mount";
import "../landscape/landscape.css";
import "../activity/activity.css";
import "../templates/templates.css";
import "../lib/forms.css";
import { ActivitiesPage } from "./ActivitiesPage";
import { SchedulePage } from "./SchedulesArea";

mount((boot) => {
  switch (boot.page) {
    case "schedule_new":
      return <SchedulePage />;
    case "schedule":
      return <SchedulePage id={Number(boot.id)} />;
    case "logs":
      return <ActivitiesPage tab="logs" />;
    case "schedules":
      return <ActivitiesPage tab="schedules" />;
    default:
      return <ActivitiesPage tab="activities" />;
  }
});
