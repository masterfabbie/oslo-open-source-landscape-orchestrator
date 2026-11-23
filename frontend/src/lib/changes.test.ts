import { describe, expect, it } from "vitest";
import { type ConfigChange, changeLines, objectHref } from "./changes";
import { makeTranslate } from "./i18n";

const t = makeTranslate({
  "cfg.field.address": "Adresse",
  "cfg.field.tags": "Tags",
  "cfg.field.password_encrypted": "Passwort",
  "cfg.field.https": "HTTPS",
  "cfg.changed": "geändert",
  "cfg.yes": "ja",
  "cfg.no": "nein",
  "cfg.count.created": "angelegt",
});

function change(changes: ConfigChange["changes"], action = "updated"): ConfigChange {
  return { id: 1, changed_at: "", username: "admin", object_type: "host", object_id: 1, object_name: "sapapp1", action, changes };
}

describe("changeLines", () => {
  it("shows old and new values, additions, removals and secrets", () => {
    const lines = changeLines(
      change({ address: ["sapapp1", "sapapp1.example"], tags: ["sla=1", "sla=2"], https: [false, true], password_encrypted: [null, "(changed)"] }),
      t,
    );
    expect(lines).toEqual(["Adresse: sapapp1 → sapapp1.example", "Tags: sla=1 → sla=2", "HTTPS: nein → ja", "Passwort: geändert"]);
    expect(changeLines(change({ tags: [null, "dev"] }), t)).toEqual(["Tags: + dev"]);
    expect(changeLines(change({ tags: ["dev", null] }), t)).toEqual(["Tags: − dev"]);
    // Plain fields that were empty.
    expect(changeLines(change({ address: [null, "sapapp1"] }), t)).toEqual(["Adresse: — → sapapp1"]);
    expect(changeLines(change({ address: ["sapapp1", null] }), t)).toEqual(["Adresse: sapapp1 → —"]);
    // Unknown fields keep their name; a new object lists its values.
    expect(changeLines(change({ address: [null, "sapapp1"], other: [null, 3] }, "created"), t)).toEqual(["Adresse: sapapp1", "other: 3"]);
    expect(changeLines(change({ created: [null, 2] }, "imported"), t)).toEqual(["angelegt: 2"]);
  });

  it("links to the object unless it is gone", () => {
    expect(objectHref(change({}))).toBe("/configuration/hosts/1");
    expect(objectHref(change({}, "deleted"))).toBeNull();
  });
});
