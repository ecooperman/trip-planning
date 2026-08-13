// Shown in the corner of every page so it's easy to confirm a deploy
// actually reached the server (vs. a stale cached copy) - see the
// Cache-Control: no-store header set on every response for the other half
// of that story.
fetch("/api/version")
  .then((res) => res.json())
  .then((data) => {
    const el = document.getElementById("app-version");
    if (el) el.textContent = `v${data.version}`;
  })
  .catch(() => {});
