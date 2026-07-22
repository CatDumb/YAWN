"use client";

import { AccessConfirmedView } from "../features/auth/components/access-confirmed-view";
import { AccessRequestView } from "../features/auth/components/access-request-view";
import { LoginView } from "../features/auth/components/login-view";
import { useAuthFlow } from "../features/auth/use-auth-flow";

export default function Home() {
  const flow = useAuthFlow();

  if (flow.view === "access-confirmed") {
    return <AccessConfirmedView flow={flow} />;
  }
  if (flow.view === "login") {
    return <LoginView flow={flow} />;
  }
  return <AccessRequestView flow={flow} />;
}
