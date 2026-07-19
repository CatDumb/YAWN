import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "WIO Tracker",
  description: "Work-in-office tracking and approval workflows.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
