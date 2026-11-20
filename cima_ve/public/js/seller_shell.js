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
    add("meta", { name: "theme-color", content: "#1c2532" });
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

  function getRoute() {
    if (typeof frappe === "undefined" || !frappe.get_route) return [];
    return frappe.get_route() || [];
  }

  function isAllowedSellerRoute(route) {
    if (!route || !route.length) return false;
    if (ALLOWED_ROUTES.includes(route[0])) return true;
    return route[0] === "cima-ve" && ALLOWED_ROUTES.includes(route[1]);
  }

  function currentAllowedSlug(route) {
    if (!route || !route.length) return "";
    if (ALLOWED_ROUTES.includes(route[0])) return route[0];
    if (route[0] === "cima-ve" && ALLOWED_ROUTES.includes(route[1])) return route[1];
    return "";
  }

  function isAllowedPath() {
    const path = (window.location && window.location.pathname) || "";
    return ALLOWED_ROUTES.some((slug) => path.endsWith("/" + slug) || path.includes("/" + slug + "/"));
  }

  function enforceSellerRoute() {
    const route = getRoute();
    if (isAllowedSellerRoute(route) || isAllowedPath()) return;
    frappe.set_route(LANDING);
  }

  function blockNavigation() {
    document.addEventListener(
      "click",
      (e) => {
        const el =
          e.target.closest &&
          e.target.closest(
            ".navbar-home, .navbar-brand, .app-logo, .search-bar, #navbar-search, .awesomplete, .body-sidebar-container, frappe-mobile-nav, flow-launcher, a[href='/desk'], a[href='/app'], a[href*='/search']"
          );
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
    const current = currentAllowedSlug(getRoute());
    tabs.querySelectorAll("a[data-route]").forEach((a) => {
      a.classList.toggle("is-active", a.getAttribute("data-route") === current);
    });
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function getSellerUserInfo() {
    const email = (frappe.session && frappe.session.user) || "";
    const fullName =
      (frappe.session && frappe.session.user_fullname) ||
      (frappe.boot && frappe.boot.user && frappe.boot.user.full_name) ||
      email;
    const parts = String(fullName || email).trim().split(/\s+/).filter(Boolean);
    const initials =
      parts.length >= 2
        ? (parts[0][0] + parts[1][0]).toUpperCase()
        : String(fullName || email).slice(0, 2).toUpperCase() || "U";
    const roles = ((typeof frappe !== "undefined" && frappe.user_roles) || []).filter(
      (r) => !["All", "Guest", "Desk User"].includes(r)
    );
    return { email, fullName, initials, roles: roles.length ? roles.join(", ") : "Vendedor" };
  }

  function logoutSeller() {
    const goLogin = () => {
      window.location.href = "/login";
    };
    if (typeof frappe !== "undefined" && frappe.call) {
      frappe.call({
        method: "logout",
        callback: goLogin,
        error: () => {
          fetch("/api/method/logout", { method: "POST", credentials: "same-origin" }).finally(goLogin);
        },
      });
      return;
    }
    fetch("/api/method/logout", { method: "POST", credentials: "same-origin" }).finally(goLogin);
  }

  function openSellerProfileDialog() {
    const info = getSellerUserInfo();
    const html =
      '<div class="cima-seller-profile-card">' +
      '<div class="cima-seller-profile-avatar">' + escapeHtml(info.initials) + "</div>" +
      '<div class="cima-seller-profile-rows">' +
      '<p><strong>Nombre:</strong> ' + escapeHtml(info.fullName) + "</p>" +
      '<p><strong>Usuario / Correo:</strong> ' + escapeHtml(info.email) + "</p>" +
      '<p><strong>Rol:</strong> ' + escapeHtml(info.roles) + "</p>" +
      "</div>" +
      "</div>";

    if (typeof frappe !== "undefined" && frappe.ui && frappe.ui.Dialog) {
      const d = new frappe.ui.Dialog({
        title: "Mi Perfil",
        fields: [{ fieldtype: "HTML", fieldname: "profile_html", options: html }],
        primary_action_label: "Cerrar",
        primary_action: () => d.hide(),
        secondary_action_label: "Cerrar Sesi\u00f3n",
        secondary_action: () => {
          d.hide();
          logoutSeller();
        },
      });
      d.show();
      return;
    }
    if (typeof frappe !== "undefined" && frappe.msgprint) {
      frappe.msgprint({ title: "Mi Perfil", message: html });
    }
  }

  function refreshSellerUserInfo() {
    const info = getSellerUserInfo();
    const avatar = document.querySelector("#cima-seller-user-btn .cima-seller-avatar");
    const nameEl = document.querySelector("#cima-seller-user-btn .cima-seller-user-name");
    const menuName = document.querySelector("#cima-seller-user-menu .cima-seller-menu-name");
    const menuEmail = document.querySelector("#cima-seller-user-menu .cima-seller-menu-email");
    if (avatar) avatar.textContent = info.initials;
    if (nameEl) nameEl.textContent = info.fullName;
    if (menuName) menuName.textContent = info.fullName;
    if (menuEmail) menuEmail.textContent = info.email;
  }

  function addSellerTopTabs() {
    if (document.getElementById("cima-seller-tabs")) {
      updateActiveSellerTab();
      refreshSellerUserInfo();
      return true;
    }

    const info = getSellerUserInfo();
    const nav = document.createElement("nav");
    nav.id = "cima-seller-tabs";
    nav.setAttribute("aria-label", "Navegación Vendedor");
    nav.innerHTML =
      '<div class="cima-seller-tabs-links">' +
      '<a href="/app/venta-rapida" data-route="venta-rapida">Facturaci\u00f3n R\u00e1pida</a>' +
      '<a href="/app/notas-entrega" data-route="notas-entrega">Notas de Entrega</a>' +
      "</div>" +
      '<div class="cima-seller-user-wrap">' +
      '<button type="button" id="cima-seller-user-btn" aria-haspopup="true" aria-expanded="false" title="Perfil y sesi\u00f3n">' +
      '<span class="cima-seller-avatar">' + escapeHtml(info.initials) + "</span>" +
      '<span class="cima-seller-user-name">' + escapeHtml(info.fullName) + "</span>" +
      '<span class="cima-seller-caret">&#9662;</span>' +
      "</button>" +
      '<div id="cima-seller-user-menu" role="menu" hidden>' +
      '<div class="cima-seller-user-header">' +
      '<strong class="cima-seller-menu-name">' + escapeHtml(info.fullName) + "</strong>" +
      '<small class="cima-seller-menu-email">' + escapeHtml(info.email) + "</small>" +
      "</div>" +
      '<button type="button" class="cima-seller-menu-item" data-seller-action="profile" role="menuitem">Mi Perfil</button>' +
      '<button type="button" class="cima-seller-menu-item is-danger" data-seller-action="logout" role="menuitem">Cerrar Sesi\u00f3n</button>' +
      "</div>" +
      "</div>";

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

    const userBtn = nav.querySelector("#cima-seller-user-btn");
    const userMenu = nav.querySelector("#cima-seller-user-menu");
    const closeMenu = () => {
      if (!userMenu || userMenu.hidden) return;
      userMenu.hidden = true;
      if (userBtn) userBtn.setAttribute("aria-expanded", "false");
    };

    nav.addEventListener("click", (e) => {
      const a = e.target.closest("a[data-route]");
      if (a) {
        e.preventDefault();
        closeMenu();
        frappe.set_route(a.getAttribute("data-route"));
        return;
      }
      if (e.target.closest("#cima-seller-user-btn")) {
        e.preventDefault();
        e.stopPropagation();
        const nextHidden = !userMenu.hidden;
        userMenu.hidden = nextHidden;
        userBtn.setAttribute("aria-expanded", nextHidden ? "false" : "true");
        return;
      }
      const actionBtn = e.target.closest("button[data-seller-action]");
      if (actionBtn) {
        e.preventDefault();
        closeMenu();
        const action = actionBtn.getAttribute("data-seller-action");
        if (action === "profile") openSellerProfileDialog();
        if (action === "logout") logoutSeller();
      }
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".cima-seller-user-wrap")) closeMenu();
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
    const route = getRoute();
    if (route[0] === LANDING || (route[0] === "cima-ve" && route[1] === LANDING)) return;
    const pages = document.querySelectorAll(".page-container");
    pages.forEach((page) => {
      if (getComputedStyle(page).display === "none") return;
      const head = page.querySelector(".page-head");
      if (!head || getComputedStyle(head).display === "none") return;
      const actions = head.querySelector(".page-actions");
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
    const route = getRoute();
    const r0 = (route[0] || "").toLowerCase();
    const r1 = (route[1] || "").toLowerCase();
    return (
      !r0 ||
      r0 === "home" ||
      r0 === "desktop" ||
      (r0 === "workspaces" && (!r1 || r1 === "home")) ||
      !!document.querySelector("#page-desktop .layout-main-section")
    );
  }

  function addAdminHomeShortcut() {
    if (!isHomeRoute()) return;
    const containers = document.querySelectorAll(
      "#page-desktop .layout-main-section, .workspace-page .layout-main-section, .desktop-container, #page-Workspaces .layout-main-section"
    );
    containers.forEach((container) => {
      if (getComputedStyle(container).display === "none") return;
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
    if (typeof frappe === "undefined" || !frappe.session || !frappe.session.user || frappe.session.user === "Guest" || !frappe.get_route) return;
    if (!document.querySelector(".main-section, .page-head, header.navbar, #toolbar-user")) return;
    addPwaMeta();
    removeLegacyQuickNav();

    if (isAdmin()) {
      addAdminNavbarButton();
      addAdminPageHeaderButton();
      addAdminHomeShortcut();
      setTimeout(addAdminHomeShortcut, 300);
      setTimeout(addAdminHomeShortcut, 900);
      $(document).on("page-change", () => {
        addAdminNavbarButton();
        addAdminPageHeaderButton();
        setTimeout(addAdminHomeShortcut, 150);
        setTimeout(addAdminHomeShortcut, 500);
      });
      started = true;
      return;
    }

    document.body.classList.add("cima-seller-mode");
    addSellerTopTabs();
    setTimeout(refreshSellerUserInfo, 400);
    setTimeout(refreshSellerUserInfo, 1200);
    blockNavigation();
    enforceSellerRoute();
    $(document).on("page-change", () => {
      enforceSellerRoute();
      addSellerTopTabs();
      updateActiveSellerTab();
    });
    started = true;
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
