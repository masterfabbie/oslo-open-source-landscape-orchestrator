import { mount } from "../lib/mount";
import "../landscape/landscape.css";
import "../activity/activity.css";
import "../lib/forms.css";
import { ActivitiesPage } from "./ActivitiesPage";

mount((boot) => <ActivitiesPage tab={boot.page === "steps" || boot.page === "changes" ? boot.page : "activities"} />);
