import english from "./messages/en.json";
import vietnamese from "./messages/vi.json";

export type Language = "en" | "vi";
export type Messages = typeof english;

const catalogs: Record<Language, Messages> = {
  en: english,
  vi: vietnamese,
};

export function languageFromDocument(): Language {
  if (typeof document !== "undefined" && document.documentElement.lang === "vi")
    return "vi";
  return "en";
}

export function messagesFor(language: Language = languageFromDocument()) {
  return catalogs[language];
}

export function formatMessage(
  template: string,
  parameters: Record<string, string | number> = {},
) {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in parameters ? String(parameters[key]) : match,
  );
}
