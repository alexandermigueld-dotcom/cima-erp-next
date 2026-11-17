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
    return document.querySelector(
      "header.navbar .container, header.navbar .container-fluid, .navbar .container, .navbar .container-fluid"
    );
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

    const nav = document.createElement("nav");
    nav.id = "cima-seller-tabs";
    nav.setAttribute("aria-label", "Navegación Vendedor");
    nav.innerHTML =
      '<a href="/app/venta-rapida" data-route="venta-rapida">Facturaci\u00f3n R\u00e1pida</a>' +
      '<a href="/app/notas-entrega" data-route="notas-entrega">Notas de Entrega</a>';

    const navbarContainer = getNavbarContainer();
    if (navbarContainer) {
      navbarContainer.insertBefore(nav, navbarContainer.firstChild);
    } else {
      const host =
        document.querySelector("div.sticky-top") ||
        document.querySelector(".main-section") ||
        document.body;
      if (!host) return false;
      nav.classList.add("cima-seller-tabs-docked");
      host.insertBefore(nav, host.firstChild);
    }

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
    const toolbarUser = document.getElementById("toolbar-user");
    const navList =
      (toolbarUser && toolbarUser.closest("ul.navbar-nav")) ||
      document.querySelector("header.navbar ul.navbar-nav:last-of-type") ||
      document.querySelector(".navbar ul.navbar-nav:last-of-type");
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

  function addAdminPageHeaderButton() {
    const route = frappe.get_route ? frappe.get_route() : [];
    if (route[0] === LANDING) return;
    const pages = document.querySelectorAll(".page-container");
    pages.forEach((page) => {
      if (page.style.display === "none") return;
      const actions = page.querySelector(".page-head .page-actions");
      if (!actions || actions.querySelector(".cima-page-pos-btn")) return;
      const btn = document.createElement("a");
      btn.className = "btn btn-primary btn-sm cima-page-pos-btn";
      btn.href = "/app/venta-rapida";
      btn.textContent = "Facturaci\u00f3n R\u00e1pida";
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        frappe.set_route(LANDING);
      });
      actions.insertBefore(btn, actions.firstChild);
    });
  }

  function isHomeRoute() {
    const route = frappe.get_route ? frappe.get_route() : [];
    const r0 = (route[0] || "").toLowerCase();
    const r1 = (route[1] || "").toLowerCase();
    return (
      !r0 ||
      r0 === "home" ||
      r0 === "desktop" ||
      (r0 === "workspaces" && (!r1 || r1 === "home"))
    );
  }

  function addAdminHomeShortcut() {
    if (!isHomeRoute()) return;
    const containers = document.querySelectorAll(
      ".workspace-page .layout-main-section, .desktop-container, #page-Workspaces .layout-main-section"
    );
    containers.forEach((container) => {
      if (container.offsetParent === null) return;
      if (container.querySelector("#cima-home-shortcuts")) return;
      const box = document.createElement("div");
      box.id = "cima-home-shortcuts";
      box.innerHTML =
        '<a class="cima-home-btn cima-home-btn-primary" href="/app/venta-rapida" data-route="venta-rapida">Facturaci\u00f3n R\u00e1pida</a>' +
        '<a class="cima-home-btn" href="/app/notas-entrega" data-route="notas-entrega">Notas de Entrega</a>';
      box.addEventListener("click", (e) => {
        const a = e.target.closest("a[data-route]");
        if (!a) return;
        e.preventDefault();
        frappe.set_route(a.getAttribute("data-route"));
      });
      container.insertBefore(box, container.firstChild);
    });
  }

  function removeLegacyQuickNav() {
    const legacy = document.getElementById("cima-quick-nav");
    if (legacy) legacy.remove();
  }

  let started = false;

  function init() {
    if (started) return;
    if (typeof frappe === "undefined" || !frappe.session || frappe.session.user === "Guest") return;
    if (!document.querySelector(".main-section, .page-head, header.navbar, #toolbar-user")) return;
    started = true;
    addPwaMeta();
    removeLegacyQuickNav();

    if (isAdmin()) {
      addAdminNavbarButton();
      addAdminPageHeaderButton();
      addAdminHomeShortcut();
      $(document).on("page-change", () => {
        addAdminNavbarButton();
        addAdminPageHeaderButton();
        setTimeout(addAdminHomeShortcut, 150);
      });
      return;
    }

    document.body.classList.add("cima-seller-mode");
    addSellerTopTabs();
    blockNavigation();
    enforceSellerRoute();
    $(document).on("page-change", () => {
      enforceSellerRoute();
      addSellerTopTabs();
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
