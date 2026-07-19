import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
};

const hasSentryBuildConfig = Boolean(
  process.env.SENTRY_AUTH_TOKEN &&
  process.env.SENTRY_ORG &&
  process.env.SENTRY_PROJECT,
);

export default hasSentryBuildConfig
  ? withSentryConfig(nextConfig, {
      authToken: process.env.SENTRY_AUTH_TOKEN,
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      silent: true,
      widenClientFileUpload: true,
    })
  : nextConfig;
