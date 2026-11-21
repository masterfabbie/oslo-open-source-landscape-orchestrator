// Start data the server writes into the page (texts, language, user); see landscape.html.

export interface Boot {
  language: string;
  texts: Record<string, string>;
  user: { name: string; role: string };
  timezone?: string;
}

export function readBoot(id = "oslo-boot"): Boot {
  const element = document.getElementById(id);
  if (!element?.textContent) throw new Error(`#${id} is missing`);
  return JSON.parse(element.textContent) as Boot;
}
