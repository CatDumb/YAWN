const foundations = [
  {
    title: "Secure access",
    description: "Email OTP sessions with company membership and role checks.",
  },
  {
    title: "Documented API",
    description:
      "Versioned Django REST API with OpenAPI, Swagger UI, and ReDoc.",
  },
  {
    title: "Operational baseline",
    description:
      "Health checks, structured logs, tests, and reproducible builds.",
  },
];

export default function Home() {
  return (
    <main className="bg-base-100 text-base-content min-h-screen">
      <nav
        className="navbar bg-base-200 px-4 sm:px-8"
        aria-label="Primary navigation"
      >
        <div className="navbar-start">
          <span className="text-lg font-semibold">WIO Tracker</span>
        </div>
        <div className="navbar-end">
          <span className="badge badge-success">Foundation active</span>
        </div>
      </nav>

      <section className="hero py-16 sm:py-24">
        <div className="hero-content max-w-5xl flex-col gap-10 text-center">
          <div className="max-w-2xl">
            <p className="text-base-content/70 mb-3 text-sm font-semibold tracking-widest uppercase">
              Phase 1
            </p>
            <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
              Work-in-office tracking, built on a secure foundation.
            </h1>
            <p className="text-base-content/70 mt-6 text-lg">
              Authentication, API boundaries, infrastructure, and quality checks
              are prepared before daily-log features begin.
            </p>
          </div>

          <div className="grid w-full gap-4 text-left sm:grid-cols-3">
            {foundations.map((foundation) => (
              <article key={foundation.title} className="card bg-base-200">
                <div className="card-body">
                  <h2 className="card-title">{foundation.title}</h2>
                  <p className="text-base-content/70">
                    {foundation.description}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
