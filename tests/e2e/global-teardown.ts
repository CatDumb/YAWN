import { rm } from "node:fs/promises";
import path from "node:path";

export default async function globalTeardown() {
  const backendRoot = path.resolve(__dirname, "../../backend");
  const artifactRoot = path.resolve(backendRoot, ".e2e");
  if (path.dirname(artifactRoot) !== backendRoot) {
    throw new Error(
      "Refusing to clean E2E artifacts outside backend directory.",
    );
  }
  await rm(artifactRoot, { force: true, recursive: true });
}
