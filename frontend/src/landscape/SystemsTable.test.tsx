import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SystemRow } from "../lib/types";
import { DEV, instance } from "./fixtures";
import { SystemsTable } from "./SystemsTable";
import { AppContext } from "./ui";

const t = (key: string, values?: Record<string, string | number>) => (values ? `${key}:${Object.values(values).join(",")}` : key);
// DEV with two diagnostics agents, the later label first.
const system: SystemRow = {
  ...DEV,
  instances: [...DEV.instances, instance(9, "DAB/99", "agent", [1, "sapapp1", []], "agent"), instance(8, "DAA/98", "agent", [1, "sapapp1", []], "agent")],
};

function table(expandAll = false) {
  sessionStorage.setItem("lo.landscape.open", JSON.stringify([system.id]));
  render(
    <AppContext.Provider value={{ t, role: "admin", language: "en" }}>
      <table>
        <SystemsTable
          rows={[{ system, instances: system.instances }]}
          expandAll={expandAll}
          selection={{ kind: "SYSTEM", ids: [] }}
          onSelect={() => {}}
          onOpen={() => {}}
          onOpenInstance={() => {}}
          openId={null}
          openInstanceId={null}
        />
      </table>
    </AppContext.Provider>,
  );
}

describe("diagnostics agents in the landscape", () => {
  afterEach(() => {
    cleanup();
    sessionStorage.clear();
  });

  it("come last in their own group, closed at first", () => {
    table();
    expect(screen.getByText("DEV/01")).toBeTruthy();
    expect(screen.queryByText("DAA/98")).toBeNull();
    fireEvent.click(screen.getByText("agents.group (2)").closest("td")!.querySelector("button")!);
    const labels = screen.getAllByRole("button").map((b) => b.textContent);
    expect(labels.indexOf("DAA/98")).toBeLessThan(labels.indexOf("DAB/99"));
    expect(labels.indexOf("DEV/00")).toBeLessThan(labels.indexOf("DAA/98"));
  });

  it("are open while the instance type filter is active", () => {
    table(true);
    expect(screen.getByText("DAA/98")).toBeTruthy();
  });
});
