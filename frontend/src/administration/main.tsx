// Administration (general, users, rules of "needs attention", certificates, import/export): one app; the server says
// which page (boot.page).

import { mount } from "../lib/mount";
import "../landscape/landscape.css";
import "../activity/activity.css";
import "../templates/templates.css";
import "../lib/forms.css";
import { AttentionPage, CertificateNewPage, CertificatesPage, GeneralPage, UserNewPage, UserPage, UsersPage } from "./Administration";
import { TransferPage } from "./Transfer";

mount((boot) => {
  switch (boot.page) {
    case "users":
      return <UsersPage />;
    case "user_new":
      return <UserNewPage />;
    case "user":
      return <UserPage id={Number(boot.id)} />;
    case "attention":
      return <AttentionPage />;
    case "certificates":
      return <CertificatesPage />;
    case "certificate_new":
      return <CertificateNewPage />;
    case "transfer":
      return <TransferPage />;
    default:
      return <GeneralPage />;
  }
});
