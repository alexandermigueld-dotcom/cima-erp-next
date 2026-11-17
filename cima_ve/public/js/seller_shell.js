(function () {
  const ALLOWED_ROUTES = ["venta-rapida", "notas-entrega"];
  const LANDING = "venta-rapida";

  function addPwaMeta() {
    if (document.querySelector("link[rel='manifest']")) return;
    const head = document.head;
    const add = (tag, attrs) => {
      const el = document.createElement(tag);
      Object.keys(attrs).forEach((k) => el.setAttribute(k, attrs[k]));
      head.appendChild(el);
    };
    add("link", { rel: "manifest", href: "/assets/cima_ve/manifest.json" });
    add("link", { rel: "apple-touch-icon", href: "/assets/cima_ve/images/icon-192.png" });
    add("meta", { name: "theme-color", content: "#0f172a" });
    add("meta", { name: "mobile-web-app-capable", content: "yes" });
    add("meta", { name: "apple-mobile-web-app-capable", content: "yes" });
    add("meta", { name: "apple-mobile-web-app-title", content: "Cima Ventas" });
  }

  function isAdmin() {
    return (
      frappe.session.user === "Administrator" ||
      (frappe.user && frappe.user.has_role && frappe.user.has_role("System Manager"))
    );
  }

  function enforceSellerRoute() {
    const route = frappe.get_route ? frappe.get_route() : [];
    if (!route.length || !ALLOWED_ROUTES.includes(route[0])) {
      frappe.set_route(LANDING);
    }
  }

  let started = false;

  function init() {
    if (started) return;
    if (typeof frappe === "undefined" || !frappe.session || frappe.session.user === "Guest") return;
    started = true;
    addPwaMeta();
    if (isAdmin()) return;
    document.body.classList.add("cima-seller-mode");
    enforceSellerRoute();
    $(document).on("page-change", enforceSellerRoute);
  }

  $(document).on("startup", init);
  if (window.frappe && frappe.boot) init();
})();
