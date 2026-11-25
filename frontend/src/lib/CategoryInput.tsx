// The category of a custom operation or template, with the categories in use as suggestions.

import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { useApp } from "../landscape/ui";

export function CategoryInput({ value, onChange, className = "oslo-field" }: { value: string; onChange: (value: string) => void; className?: string }) {
  const { t } = useApp();
  const { data } = useQuery({ queryKey: ["operations", "categories"], queryFn: () => api<{ category?: string }[]>("/operations") });
  const used = [...new Set((data ?? []).map((o) => o.category ?? "").filter((c) => c && !c.startsWith("cat.")))].sort();
  return (
    <label className={className}>
      {t("field.category")}
      <input value={value} maxLength={128} list="oslo-categories" placeholder="Automation/Kernel" onChange={(e) => onChange(e.target.value)} />
      <datalist id="oslo-categories">
        {used.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      <small>{t("category.hint")}</small>
    </label>
  );
}
