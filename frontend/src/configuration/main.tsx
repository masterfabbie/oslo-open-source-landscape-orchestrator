// Configuration (hosts, systems, pools): one app; the server says which page (boot.page).

import { mount } from "../lib/mount";
import "../landscape/landscape.css";
import "../activity/activity.css";
import "../templates/templates.css";
import "../lib/forms.css";
import { HostNewPage, HostPage, HostsPage } from "./Hosts";
import { PoolNewPage, PoolPage, PoolsPage } from "./Pools";
import { SystemNewPage, SystemPage, SystemsPage, UnassignedPage } from "./Systems";

mount((boot) => {
  const id = Number(boot.id);
  switch (boot.page) {
    case "host_new":
      return <HostNewPage />;
    case "host":
      return <HostPage id={id} />;
    case "systems":
      return <SystemsPage />;
    case "unassigned":
      return <UnassignedPage />;
    case "system_new":
      return <SystemNewPage />;
    case "system":
      return <SystemPage id={id} />;
    case "pools":
      return <PoolsPage />;
    case "pool_new":
      return <PoolNewPage />;
    case "pool":
      return <PoolPage id={id} />;
    default:
      return <HostsPage />;
  }
});
