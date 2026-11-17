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

  function blockNavigation() {
    document.addEventListener(
      "click",
      (e) => {
        const el = e.target.closest && e.target.closest(".navbar-home, .navbar-brand, .app-logo, .search-bar, #navbar-search, .awesomplete");
        if (el) {
          e.preventDefault();
          e.stopPropagation();
          frappe.set_route(LANDING);
        }
      },
      true
    );
    document.addEventListener(
      "keydown",
      (e) => {
        if ((e.ctrlKey || e.metaKey) && ["g", "k"].includes((e.key || "").toLowerCase())) {
          e.preventDefault();
          e.stopPropagation();
        }
      },
      true
    );
  }

  function addQuickNav() {
    if (document.getElementById("cima-quick-nav")) return;
    const bar = document.createElement("div");
    bar.id = "cima-quick-nav";
    bar.innerHTML =
      '<a href="/app/venta-rapida" data-route="venta-rapida">Facturaci\u00f3n R\u00e1pida</a>' +
      '<a href="/app/notas-entrega" data-route="notas-entrega">Notas de Entrega</a>';
    document.body.appendChild(bar);
    bar.addEventListener("click", (e) => {
      const a = e.target.closest("a[data-route]");
      if (!a) return;
      e.preventDefault();
      frappe.set_route(a.getAttribute("data-route"));
    });
  }

  let started = false;

  function init() {
    if (started) return;
    if (typeof frappe === "undefined" || !frappe.session || frappe.session.user === "Guest") return;
    started = true;
    addPwaMeta();
    addQuickNav();
    if (isAdmin()) return;
    document.body.classList.add("cima-seller-mode");
    blockNavigation();
    enforceSellerRoute();
    $(document).on("page-change", enforceSellerRoute);
  }

  function boot() {
    try {
      if (document.body) init();
    } catch (e) {
      console.error("seller_shell", e);
    }
    if (!started) setTimeout(boot, 300);
  }

  boot();
})();
