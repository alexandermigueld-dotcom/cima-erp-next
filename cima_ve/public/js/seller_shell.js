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

  function getNavbarContainer() {
    return document.querySelector("header.navbar .container, header.navbar .container-fluid, header.navbar");
  }

  function updateActiveSellerTab() {
    const tabs = document.getElementById("cima-seller-tabs");
    if (!tabs) return;
    const current = frappe.get_route ? frappe.get_route()[0] : "";
    tabs.querySelectorAll("a[data-route]").forEach((a) => {
      a.classList.toggle("is-active", a.getAttribute("data-route") === current);
    });
  }

  function addSellerTopTabs() {
    if (document.getElementById("cima-seller-tabs")) {
      updateActiveSellerTab();
      return true;
    }
    const container = getNavbarContainer();
    if (!container) return false;

    const nav = document.createElement("nav");
    nav.id = "cima-seller-tabs";
    nav.setAttribute("aria-label", "Navegación Vendedor");
    nav.innerHTML =
      '<a href="/app/venta-rapida" data-route="venta-rapida">Facturaci\u00f3n R\u00e1pida</a>' +
      '<a href="/app/notas-entrega" data-route="notas-entrega">Notas de Entrega</a>';
    container.insertBefore(nav, container.firstChild);

    nav.addEventListener("click", (e) => {
      const a = e.target.closest("a[data-route]");
      if (!a) return;
      e.preventDefault();
      frappe.set_route(a.getAttribute("data-route"));
    });
    updateActiveSellerTab();
    return true;
  }

  function addAdminNavbarButton() {
    if (document.getElementById("cima-admin-pos-item")) return true;
    const navList =
      document.querySelector("header.navbar .navbar-collapse > ul.navbar-nav:last-of-type") ||
      document.querySelector("header.navbar ul.navbar-nav:last-of-type");
    if (!navList) return false;

    const li = document.createElement("li");
    li.id = "cima-admin-pos-item";
    li.className = "nav-item";
    li.innerHTML =
      '<a id="cima-admin-pos-btn" class="nav-link" href="/app/venta-rapida" title="Ir a Facturaci\u00f3n R\u00e1pida">' +
      '<span class="cima-admin-pos-full">Facturaci\u00f3n R\u00e1pida</span>' +
      '<span class="cima-admin-pos-short">Facturaci\u00f3n</span>' +
      "</a>";
    navList.insertBefore(li, navList.firstChild);

    li.querySelector("a").addEventListener("click", (e) => {
      e.preventDefault();
      frappe.set_route(LANDING);
    });
    return true;
  }

  function removeLegacyQuickNav() {
    const legacy = document.getElementById("cima-quick-nav");
    if (legacy) legacy.remove();
  }

  let started = false;

  function init() {
    if (started) return;
    if (typeof frappe === "undefined" || !frappe.session || frappe.session.user === "Guest") return;
    if (!getNavbarContainer()) return;
    started = true;
    addPwaMeta();
    removeLegacyQuickNav();

    if (isAdmin()) {
      addAdminNavbarButton();
      return;
    }

    document.body.classList.add("cima-seller-mode");
    addSellerTopTabs();
    blockNavigation();
    enforceSellerRoute();
    $(document).on("page-change", () => {
      enforceSellerRoute();
      updateActiveSellerTab();
    });
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
