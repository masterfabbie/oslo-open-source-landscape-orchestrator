// Start data the server writes into the page (texts, language, user); see landscape.html.

export interface Boot {
  language: string;
  texts: Record<string, string>;
  user: { name: string; role: string };
  timezone?: string;
  /** "utc": times are shown and entered in UTC; otherwise in the browser's local time. */
  time_display?: string;
}

export function readBoot(id = "oslo-boot"): Boot {
  const element = document.getElementById(id);
  if (!element?.textContent) throw new Error(`#${id} is missing`);
  return JSON.parse(element.textContent) as Boot;
}
