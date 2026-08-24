export const SCREEN_IDS = ["dashboard", "create", "exports", "templates", "assets", "brands"];

export function normaliseRoute(hash) {
  const candidate = String(hash || "").replace(/^#/, "");
  return SCREEN_IDS.includes(candidate) ? candidate : "create";
}

export function applyRoute(documentRef, hash) {
  const activeRoute = normaliseRoute(hash);
  documentRef.querySelectorAll(".screen").forEach((screen) => {
    const isActive = screen.id === activeRoute;
    screen.hidden = !isActive;
    screen.classList.toggle("is-active", isActive);
  });
  documentRef.querySelectorAll("[data-route]").forEach((link) => {
    link.classList.toggle("active", link.dataset.route === activeRoute);
  });
  return activeRoute;
}

export function startRouter({ documentRef = document, windowRef = window } = {}) {
  const updateRoute = () => {
    const activeRoute = normaliseRoute(windowRef.location.hash);
    if (windowRef.location.hash !== `#${activeRoute}`) {
      windowRef.history.replaceState(null, "", `#${activeRoute}`);
    }
    return applyRoute(documentRef, activeRoute);
  };
  windowRef.addEventListener("hashchange", updateRoute);
  updateRoute();
  return updateRoute;
}
