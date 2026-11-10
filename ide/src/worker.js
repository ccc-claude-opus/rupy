// The rupy IDE's API. Programs compile and run in the browser; the server only
// serves the assets. Accounts and cloud files (D1 + R2) come in M3.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/health") return Response.json({ ok: true, name: "rupy-ide" });
    if (url.pathname.startsWith("/api/")) return Response.json({ error: "not found" }, { status: 404 });
    return env.ASSETS.fetch(request);
  },
};
