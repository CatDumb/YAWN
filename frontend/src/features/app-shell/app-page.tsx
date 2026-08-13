import type { ComponentPropsWithoutRef, ReactNode } from "react";

const contentWidthClasses = {
  narrow: "max-w-2xl",
  medium: "max-w-3xl",
  wide: "max-w-none",
} as const;

export type AppPageContentWidth = keyof typeof contentWidthClasses;

type AppPageProps = Omit<ComponentPropsWithoutRef<"main">, "children"> & {
  children: ReactNode;
  contentClassName?: string;
  contentWidth?: AppPageContentWidth;
};

export function AppPage({
  children,
  className = "",
  contentClassName = "",
  contentWidth = "wide",
  ...mainProps
}: AppPageProps) {
  return (
    <main
      className={`bg-base-100 min-h-screen px-4 py-8 sm:px-8 ${className}`.trim()}
      {...mainProps}
    >
      <div className="app-page-canvas mx-auto w-full max-w-6xl">
        <div
          className={`app-page-content w-full ${contentWidthClasses[contentWidth]} ${contentClassName}`.trim()}
          data-content-width={contentWidth}
        >
          {children}
        </div>
      </div>
    </main>
  );
}
