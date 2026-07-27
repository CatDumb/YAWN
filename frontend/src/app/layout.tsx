import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "YAWN — Yet Another WIO Tracker",
  description: "Work-in-office tracking and approval workflows.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(() => { try { const preference = JSON.parse(localStorage.getItem("yawn.preferences") || "{}"); const theme = preference.theme || "system"; const dark = window.matchMedia("(prefers-color-scheme: dark)").matches; document.documentElement.dataset.theme = theme === "dark" || (theme === "system" && dark) ? "yawn-dark" : "yawn-light"; const browserLanguage = navigator.language.toLowerCase().startsWith("vi") ? "vi" : "en"; document.documentElement.lang = preference.language === "vi" ? "vi" : preference.language === "en" ? "en" : browserLanguage; document.documentElement.dataset.reducedMotion = preference.reduced_motion ? "reduce" : ""; document.documentElement.dataset.navigation = localStorage.getItem("yawn.navigation-collapsed") === "true" ? "collapsed" : "expanded"; } catch { document.documentElement.dataset.theme = "yawn-light"; document.documentElement.dataset.navigation = "expanded"; } })();`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
