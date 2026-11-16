(function () {
  "use strict";

  const root = document.getElementById("cima-storefront");
  if (!root) return;

  const CSRF = root.dataset.csrf || (window.frappe && frappe.csrf_token) || "";
  const CART_STORAGE_KEY = "cima_ve_storefront_cart_v1";

  const state = {
    bootstrap: null,
    catalog: { items: [], total: 0, page: 1, page_size: 24 },
    filters: { query: "", item_group: "", only_in_stock: true, sort: "stock_desc", page: 1 },
    cart: loadCart(),
    cartPreview: null,
    selectedPayment: "cashea",
    selectedDelivery: "pickup",
  };

  function loadCart() {
    try {
      const raw = localStorage.getItem(CART_STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  function saveCart() {
    localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(state.cart));
    updateCartBadge();
  }

  function money(val) {
    return "$" + Number(val || 0).toFixed(2);
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showToast(msg) {
    const el = document.getElementById("cima-toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.add("hidden"), 3200);
  }

  async function apiCall(method, params = {}) {
    const res = await fetch(`/api/method/${method}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Frappe-CSRF-Token": CSRF,
      },
      credentials: "same-origin",
      body: JSON.stringify(params),
    });
    const data = await res.json();
    if (!res.ok || data.exc) {
      let errMsg = "Ocurrió un error al procesar la solicitud.";
      if (data._server_messages) {
        try {
          const msgs = JSON.parse(data._server_messages);
          const first = JSON.parse(msgs[0]);
          errMsg = first.message || errMsg;
        } catch {}
      } else if (data.message) {
        errMsg = typeof data.message === "string" ? data.message : errMsg;
      }
      throw new Error(errMsg);
    }
    return data.message;
  }

  function updateCartBadge() {
    const count = state.cart.reduce((acc, row) => acc + Number(row.qty || 0), 0);
    document.getElementById("cart-badge").textContent = String(count);
  }

  async function init() {
    updateCartBadge();
    bindEvents();
    try {
      state.bootstrap = await apiCall("cima_ve.api.storefront.get_storefront_bootstrap");
      const providers = state.bootstrap?.delivery_providers || [];
      if (providers.length && !providers.some((p) => p.id === state.selectedDelivery)) {
        state.selectedDelivery = providers[0].id;
      }
      renderBootstrap();
      await loadCatalog();
    } catch (err) {
      showToast(err.message);
    }
  }

  function renderBootstrap() {
    const b = state.bootstrap;
    if (!b) return;
    document.getElementById("nav-warehouse").textContent = b.settings.warehouse || "Venezuela";

    const user = b.user || {};
    if (user.is_guest) {
      document.getElementById("nav-user-greeting").textContent = "Hola, Identifícate";
      document.getElementById("nav-user-label").textContent = "Google / Cuenta";
    } else {
      document.getElementById("nav-user-greeting").textContent = `Hola, ${user.full_name.split(" ")[0]}`;
      document.getElementById("nav-user-label").textContent = user.ve_rif_cedula ? `RIF: ${user.ve_rif_cedula}` : "Mi Cuenta y RIF";
    }

    const catSelect = document.getElementById("nav-category-select");
    const subnav = document.getElementById("subnav-categories");
    catSelect.innerHTML = `<option value="">Todas</option>`;
    subnav.innerHTML = `<button type="button" class="cima-cat-pill active" data-cat="">Todos</button>`;

    (b.categories || []).slice(0, 12).forEach((cat) => {
      const opt = document.createElement("option");
      opt.value = cat.name;
      opt.textContent = `${cat.name} (${cat.item_count})`;
      catSelect.appendChild(opt);

      const pill = document.createElement("button");
      pill.type = "button";
      pill.className = "cima-cat-pill";
      pill.dataset.cat = cat.name;
      pill.textContent = cat.name;
      subnav.appendChild(pill);
    });
  }

  async function loadCatalog() {
    const grid = document.getElementById("product-grid");
    grid.innerHTML = `<div style="grid-column:1/-1;padding:30px;text-align:center;color:#64748b;">Cargando productos...</div>`;
    const res = await apiCall("cima_ve.api.storefront.get_catalog", {
      query: state.filters.query,
      item_group: state.filters.item_group,
      only_in_stock: state.filters.only_in_stock ? 1 : 0,
      sort: state.filters.sort,
      page: state.filters.page,
      page_size: 24,
    });
    state.catalog = res;
    renderCatalog();
  }

  function renderCatalog() {
    const { items, total, page, page_size } = state.catalog;
    const defaultImg = state.bootstrap?.settings?.default_image || "/assets/cima_ve/images/pending-product.svg";
    document.getElementById("results-info").textContent = `${total} producto(s) encontrado(s)`;

    const grid = document.getElementById("product-grid");
    if (!items.length) {
      grid.innerHTML = `<div style="grid-column:1/-1;background:#fff;padding:40px;border-radius:8px;text-align:center;">
        <h3>No encontramos productos con esos filtros</h3>
        <p style="color:#64748b;">Prueba limpiando la búsqueda o desmarcando "Solo con stock disponible".</p>
      </div>`;
      document.getElementById("pagination-bar").innerHTML = "";
      return;
    }

    grid.innerHTML = items
      .map((item) => {
        const inStock = item.stock_qty > 0;
        const casheaInit = (item.price * 0.4).toFixed(2);
        return `
        <article class="cima-card">
          <div class="cima-card-img-wrap" data-view-item="${escapeHtml(item.item_code)}">
            <img src="${escapeHtml(item.image || defaultImg)}" alt="${escapeHtml(item.item_name)}"
                 onerror="this.onerror=null;this.src='${escapeHtml(defaultImg)}'">
          </div>
          <div class="cima-card-cat">${escapeHtml(item.item_group)}</div>
          <div class="cima-card-title" data-view-item="${escapeHtml(item.item_code)}">${escapeHtml(item.item_name)}</div>
          <div class="cima-stock-badge ${inStock ? "cima-stock-in" : "cima-stock-out"}">
            ${inStock ? `Disponible: ${item.stock_qty} uds` : "Agotado temporalmente"}
          </div>
          <div class="cima-price-row">
            <span class="cima-price-main">${money(item.price)}</span>
          </div>
          <div class="cima-cashea-mini">Cashea: $${casheaInit} inicial + 3 cuotas</div>
          <div class="cima-card-actions">
            <input type="number" min="1" step="1" value="1" class="cima-qty-box" id="qty-${escapeHtml(item.item_code)}">
            <button type="button" class="cima-btn-primary" style="flex:1;" data-add-item="${escapeHtml(item.item_code)}" ${!inStock ? "disabled" : ""}>
              ${inStock ? "Agregar" : "Sin stock"}
            </button>
          </div>
        </article>`;
      })
      .join("");

    const totalPages = Math.max(1, Math.ceil(total / page_size));
    const pagEl = document.getElementById("pagination-bar");
    if (totalPages <= 1) {
      pagEl.innerHTML = "";
    } else {
      let html = "";
      for (let p = 1; p <= Math.min(totalPages, 10); p++) {
        html += `<button type="button" class="cima-btn-outline ${p === page ? "cima-btn-primary" : ""}" data-page="${p}">${p}</button>`;
      }
      pagEl.innerHTML = html;
    }
  }

  function addToCart(itemCode, qty) {
    const item = state.catalog.items.find((x) => x.item_code === itemCode);
    if (!item) return;
    const cleanQty = Math.max(1, Number(qty || 1));
    const existing = state.cart.find((c) => c.item_code === itemCode);
    if (existing) {
      existing.qty += cleanQty;
    } else {
      state.cart.push({
        item_code: item.item_code,
        item_name: item.item_name,
        price: item.price,
        image: item.image,
        qty: cleanQty,
      });
    }
    saveCart();
    showToast(`Agregado: ${item.item_name} (x${cleanQty})`);
  }

  async function openCart() {
    document.getElementById("cart-backdrop").classList.remove("hidden");
    document.getElementById("cart-drawer").classList.remove("hidden");
    await refreshCartPreview();
  }

  function closeCart() {
    document.getElementById("cart-backdrop").classList.add("hidden");
    document.getElementById("cart-drawer").classList.add("hidden");
  }

  async function refreshCartPreview() {
    const listEl = document.getElementById("cart-items-list");
    const defaultImg = state.bootstrap?.settings?.default_image || "/assets/cima_ve/images/pending-product.svg";
    if (!state.cart.length) {
      listEl.innerHTML = `<div style="padding:30px;text-align:center;color:#64748b;">Tu carrito está vacío.</div>`;
      document.getElementById("cart-subtotal").textContent = "$0.00";
      document.getElementById("cart-iva").textContent = "$0.00";
      document.getElementById("cart-grand").textContent = "$0.00";
      document.getElementById("cart-cashea-hint").textContent = "";
      document.getElementById("btn-proceed-checkout").disabled = true;
      return;
    }

    document.getElementById("btn-proceed-checkout").disabled = false;
    const preview = await apiCall("cima_ve.api.storefront.preview_storefront_cart", {
      items: state.cart,
      payment_method: state.selectedPayment,
    });
    state.cartPreview = preview;

    listEl.innerHTML = state.cart
      .map((row) => {
        const priced = (preview.items || []).find((p) => p.item_code === row.item_code) || row;
        const discBadge = priced.discount_percentage > 0
          ? `<div style="color:#067d62;font-size:11px;font-weight:700;">-${priced.discount_percentage}% desc. volumen</div>`
          : "";
        return `
        <div class="cima-cart-item">
          <img src="${escapeHtml(row.image || defaultImg)}" onerror="this.onerror=null;this.src='${escapeHtml(defaultImg)}'">
          <div>
            <div style="font-weight:700;font-size:13px;">${escapeHtml(row.item_name)}</div>
            <div style="font-size:12px;color:#565959;">${money(priced.rate)} c/u</div>
            ${discBadge}
            <button type="button" data-remove-cart="${escapeHtml(row.item_code)}" style="background:none;border:none;color:#b12704;font-size:11px;padding:0;cursor:pointer;">Eliminar</button>
          </div>
          <div style="text-align:right;">
            <input type="number" min="1" step="1" value="${row.qty}" class="cima-cart-qty-input" data-cart-qty="${escapeHtml(row.item_code)}">
            <div style="font-weight:800;font-size:13px;margin-top:4px;">${money(priced.amount || priced.rate * row.qty)}</div>
          </div>
        </div>`;
      })
      .join("");

    const t = preview.totals;
    document.getElementById("cart-subtotal").textContent = money(t.taxable_base);
    document.getElementById("cart-iva").textContent = money(t.iva_amount);
    document.getElementById("cart-grand").textContent = money(t.grand_total);
    document.getElementById("cart-cashea-hint").textContent =
      `Con Cashea: ${money(t.cashea.down_payment_usd)} inicial + 3 cuotas de ${money(t.cashea.installment_usd)}`;
  }

  function openProductModal(itemCode) {
    const item = state.catalog.items.find((x) => x.item_code === itemCode);
    if (!item) return;
    const defaultImg = state.bootstrap?.settings?.default_image || "/assets/cima_ve/images/pending-product.svg";
    const inStock = item.stock_qty > 0;
    document.getElementById("product-modal-body").innerHTML = `
      <div class="cima-grid-2" style="align-items:start;">
        <div style="background:#f8fafc;border-radius:8px;padding:16px;text-align:center;">
          <img src="${escapeHtml(item.image || defaultImg)}" style="max-width:100%;max-height:280px;object-fit:contain;"
               onerror="this.onerror=null;this.src='${escapeHtml(defaultImg)}'">
        </div>
        <div>
          <div class="cima-card-cat">${escapeHtml(item.item_group)} • ${escapeHtml(item.item_code)}</div>
          <h2 style="margin:6px 0 10px;">${escapeHtml(item.item_name)}</h2>
          <div class="cima-stock-badge ${inStock ? "cima-stock-in" : "cima-stock-out"}">
            ${inStock ? `En stock: ${item.stock_qty} unidades` : "Agotado temporalmente"}
          </div>
          <div class="cima-price-main" style="margin:8px 0;">${money(item.price)} <span style="font-size:12px;color:#64748b;">+ IVA</span></div>
          <div class="cima-cashea-mini">Cashea 0%: ${money(item.price * 0.4)} inicial + 3 cuotas</div>
          <p style="font-size:13px;color:#475569;">${item.description || "Producto garantizado por CIMA ELECTRONIC VE."}</p>
          <div style="display:flex;gap:10px;margin-top:16px;">
            <input type="number" min="1" value="1" id="modal-qty-input" class="cima-qty-box">
            <button type="button" id="modal-add-btn" class="cima-btn-primary" style="flex:1;" ${!inStock ? "disabled" : ""}>
              Agregar al Carrito
            </button>
          </div>
        </div>
      </div>`;
    document.getElementById("product-modal").classList.remove("hidden");
    document.getElementById("modal-add-btn").onclick = () => {
      addToCart(item.item_code, document.getElementById("modal-qty-input").value);
      document.getElementById("product-modal").classList.add("hidden");
    };
  }

  async function openAccountModal(defaultTab = "login") {
    const modal = document.getElementById("account-modal");
    const body = document.getElementById("account-modal-body");
    modal.classList.remove("hidden");

    const user = state.bootstrap?.user || { is_guest: true };
    const auth = state.bootstrap?.auth || {};

    if (!user.is_guest) {
      body.innerHTML = `<p>Cargando tu perfil y pedidos...</p>`;
      const data = await apiCall("cima_ve.api.storefront.get_my_profile_and_orders");
      const p = data.profile;
      body.innerHTML = `
        <div class="cima-tabs">
          <button type="button" class="cima-tab ${defaultTab !== "orders" ? "active" : ""}" id="tab-profile">Mi Perfil Fiscal</button>
          <button type="button" class="cima-tab ${defaultTab === "orders" ? "active" : ""}" id="tab-orders">Mis Pedidos (${data.orders.length})</button>
        </div>
        <div id="pane-profile" class="${defaultTab === "orders" ? "hidden" : ""}">
          <p style="font-size:13px;color:#565959;">Actualiza tus datos para facturación fiscal SENIAT (opcional).</p>
          <div class="cima-field"><label>Nombre completo</label><input id="prof-name" value="${escapeHtml(p.full_name)}"></div>
          <div class="cima-grid-2">
            <div class="cima-field"><label>RIF / Cédula (Opcional)</label><input id="prof-rif" placeholder="V-12345678 o J-12345678-9" value="${escapeHtml(p.ve_rif_cedula)}"></div>
            <div class="cima-field"><label>Tipo Contribuyente</label>
              <select id="prof-taxpayer">
                ${["No Contribuyente", "Ordinario", "Especial", "Formal"].map((t) => `<option ${p.ve_taxpayer_type === t ? "selected" : ""}>${t}</option>`).join("")}
              </select>
            </div>
          </div>
          <div class="cima-field"><label>Teléfono / WhatsApp</label><input id="prof-phone" value="${escapeHtml(p.phone)}"></div>
          <div class="cima-field"><label>Dirección Fiscal / Entrega</label><input id="prof-address" value="${escapeHtml(p.address)}"></div>
          <div style="display:flex;gap:10px;margin-top:12px;">
            <button type="button" id="btn-save-profile" class="cima-btn-primary" style="flex:1;">Guardar Datos</button>
            <button type="button" id="btn-logout" class="cima-btn-outline">Cerrar Sesión</button>
          </div>
        </div>
        <div id="pane-orders" class="${defaultTab !== "orders" ? "hidden" : ""}">
          ${data.orders.length ? data.orders.map((o) => `
            <div style="border:1px solid #d5d9d9;border-radius:8px;padding:10px;margin-bottom:8px;">
              <div style="display:flex;justify-content:space-between;font-weight:700;">
                <span>${escapeHtml(o.name)}</span><span>${money(o.grand_total)}</span>
              </div>
              <div style="font-size:12px;color:#565959;">Fecha: ${o.transaction_date} • Estado: ${escapeHtml(o.status)} ${o.po_no ? "• " + escapeHtml(o.po_no) : ""}</div>
            </div>`).join("") : "<p style='color:#64748b;'>Aún no tienes pedidos registrados.</p>"}
        </div>`;

      document.getElementById("tab-profile").onclick = () => {
        document.getElementById("tab-profile").classList.add("active");
        document.getElementById("tab-orders").classList.remove("active");
        document.getElementById("pane-profile").classList.remove("hidden");
        document.getElementById("pane-orders").classList.add("hidden");
      };
      document.getElementById("tab-orders").onclick = () => {
        document.getElementById("tab-orders").classList.add("active");
        document.getElementById("tab-profile").classList.remove("active");
        document.getElementById("pane-orders").classList.remove("hidden");
        document.getElementById("pane-profile").classList.add("hidden");
      };
      document.getElementById("btn-save-profile").onclick = async () => {
        try {
          const resp = await apiCall("cima_ve.api.storefront.update_my_fiscal_profile", {
            full_name: document.getElementById("prof-name").value,
            ve_rif_cedula: document.getElementById("prof-rif").value,
            ve_taxpayer_type: document.getElementById("prof-taxpayer").value,
            phone: document.getElementById("prof-phone").value,
            address: document.getElementById("prof-address").value,
          });
          state.bootstrap.user = resp.profile;
          renderBootstrap();
          showToast("Datos fiscales guardados.");
        } catch (err) {
          showToast(err.message);
        }
      };
      document.getElementById("btn-logout").onclick = async () => {
        await apiCall("logout");
        location.reload();
      };
      return;
    }

    const googleHtml = auth.google_enabled
      ? `<a href="${escapeHtml(auth.google_auth_url)}" class="cima-google-btn" style="text-decoration:none;">
           <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" width="18" height="18" alt="">
           Continuar con Google
         </a>`
      : `<button type="button" class="cima-google-btn" id="btn-google-unconfigured">
           <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" width="18" height="18" alt="">
           Continuar con Google
         </button>`;

    body.innerHTML = `
      <h2 style="margin-top:0;">Tu Cuenta CIMA VE</h2>
      ${googleHtml}
      <div style="text-align:center;font-size:12px;color:#64748b;margin-bottom:10px;">o usa tu correo electrónico</div>
      <div class="cima-tabs">
        <button type="button" class="cima-tab active" id="tab-login">Iniciar Sesión</button>
        <button type="button" class="cima-tab" id="tab-register">Crear Cuenta</button>
      </div>
      <div id="pane-login">
        <div class="cima-field"><label>Correo electrónico *</label><input id="login-email" type="email" required placeholder="tu@correo.com"></div>
        <div class="cima-field"><label>Contraseña *</label><input id="login-pwd" type="password" required></div>
        <button type="button" id="btn-do-login" class="cima-btn-primary cima-btn-block">Entrar</button>
      </div>
      <div id="pane-register" class="hidden">
        <div class="cima-field"><label>Nombre completo *</label><input id="reg-name" required></div>
        <div class="cima-field"><label>Correo electrónico *</label><input id="reg-email" type="email" required placeholder="tu@correo.com"></div>
        <div class="cima-field"><label>Contraseña (mín. 6 caracteres) *</label><input id="reg-pwd" type="password" required></div>
        <div class="cima-grid-2">
          <div class="cima-field"><label>RIF / Cédula (Opcional)</label><input id="reg-rif" placeholder="V-12345678"></div>
          <div class="cima-field"><label>Tipo Contribuyente</label>
            <select id="reg-taxpayer">
              <option>No Contribuyente</option><option>Ordinario</option><option>Especial</option><option>Formal</option>
            </select>
          </div>
        </div>
        <div class="cima-field"><label>Teléfono / WhatsApp (Opcional, recomendado para envíos)</label><input id="reg-phone" placeholder="0412-1234567"></div>
        <button type="button" id="btn-do-register" class="cima-btn-primary cima-btn-block">Crear Cuenta</button>
      </div>`;

    const gBtn = document.getElementById("btn-google-unconfigured");
    if (gBtn) {
      gBtn.onclick = () => showToast("Configura el Client ID de Google en ERPNext > Social Login Key.");
    }

    document.getElementById("tab-login").onclick = () => {
      document.getElementById("tab-login").classList.add("active");
      document.getElementById("tab-register").classList.remove("active");
      document.getElementById("pane-login").classList.remove("hidden");
      document.getElementById("pane-register").classList.add("hidden");
    };
    document.getElementById("tab-register").onclick = () => {
      document.getElementById("tab-register").classList.add("active");
      document.getElementById("tab-login").classList.remove("active");
      document.getElementById("pane-register").classList.remove("hidden");
      document.getElementById("pane-login").classList.add("hidden");
    };

    document.getElementById("btn-do-login").onclick = async () => {
      try {
        const emailVal = (document.getElementById("login-email").value || "").trim().toLowerCase();
        if (!emailVal || !emailVal.includes("@") || !emailVal.split("@").pop().includes(".")) {
          throw new Error("Ingresa un correo electrónico válido para iniciar sesión.");
        }
        await apiCall("login", {
          usr: emailVal,
          pwd: document.getElementById("login-pwd").value,
        });
        location.reload();
      } catch (err) {
        showToast(err.message);
      }
    };

    document.getElementById("btn-do-register").onclick = async () => {
      try {
        await apiCall("cima_ve.api.storefront.register_customer", {
          full_name: document.getElementById("reg-name").value,
          email: document.getElementById("reg-email").value,
          password: document.getElementById("reg-pwd").value,
          ve_rif_cedula: document.getElementById("reg-rif").value,
          ve_taxpayer_type: document.getElementById("reg-taxpayer").value,
          phone: document.getElementById("reg-phone").value,
        });
        location.reload();
      } catch (err) {
        showToast(err.message);
      }
    };
  }

  async function openCheckoutModal() {
    closeCart();
    const modal = document.getElementById("checkout-modal");
    const body = document.getElementById("checkout-modal-body");
    modal.classList.remove("hidden");

    const user = state.bootstrap?.user || { is_guest: true };
    const methods = state.bootstrap?.payment_methods || [];
    const providers = state.bootstrap?.delivery_providers || [];
    if (providers.length && !providers.some((p) => p.id === state.selectedDelivery)) {
      state.selectedDelivery = providers[0].id;
    }

    state.cartPreview = await apiCall("cima_ve.api.storefront.preview_storefront_cart", {
      items: state.cart,
      payment_method: state.selectedPayment,
      delivery_provider: state.selectedDelivery,
    });

    body.innerHTML = `
      <h2 style="margin-top:0;">Finalizar Compra</h2>
      <div class="cima-grid-2">
        <div>
          <h4>1. Tus datos y facturación (RIF opcional)</h4>
          <div class="cima-field"><label>Nombre completo *</label><input id="chk-name" value="${escapeHtml(user.full_name === "Invitado" ? "" : user.full_name)}"></div>
          <div class="cima-field"><label>Correo electrónico *</label><input id="chk-email" type="email" required value="${escapeHtml(user.email || "")}" ${!user.is_guest ? "readonly" : ""}></div>
          <div class="cima-grid-2">
            <div class="cima-field"><label>RIF / Cédula (Opcional)</label><input id="chk-rif" placeholder="V-12345678" value="${escapeHtml(user.ve_rif_cedula || "")}"></div>
            <div class="cima-field"><label>Contribuyente</label>
              <select id="chk-taxpayer">
                ${["No Contribuyente", "Ordinario", "Especial", "Formal"].map((t) => `<option ${user.ve_taxpayer_type === t ? "selected" : ""}>${t}</option>`).join("")}
              </select>
            </div>
          </div>
          <div class="cima-field"><label>Teléfono / WhatsApp (Opcional, para coordinar envío)</label><input id="chk-phone" placeholder="0412-1234567" value="${escapeHtml(user.phone || "")}"></div>
          <div class="cima-field"><label>Dirección de entrega / Agencia (MRW, Zoom, etc.)</label><input id="chk-address" placeholder="Ej. Agencia MRW Altamira / Dirección exacta" value="${escapeHtml(user.address || "")}"></div>

          <h4 style="margin-top:14px;">2. Proveedor de Envío / Delivery</h4>
          <div class="cima-pay-grid" id="chk-delivery-grid">
            ${providers.map((p) => `
              <button type="button" class="cima-pay-option ${p.id === state.selectedDelivery ? "selected" : ""}" data-delivery-id="${escapeHtml(p.id)}">
                <div style="font-weight:800;font-size:13px;">${escapeHtml(p.label)}</div>
                <span class="cima-pay-option-badge">${p.cost > 0 ? money(p.cost) : "Gratis"}</span>
              </button>`).join("")}
          </div>
          <div id="chk-delivery-desc" style="font-size:12px;color:#475569;margin-bottom:8px;"></div>
        </div>
        <div>
          <h4>3. Método de pago</h4>
          <div class="cima-pay-grid" id="chk-pay-grid">
            ${methods.map((m) => `
              <button type="button" class="cima-pay-option ${m.id === state.selectedPayment ? "selected" : ""}" data-pay-id="${m.id}">
                <div style="font-weight:800;font-size:13px;">${escapeHtml(m.short_label)}</div>
                <span class="cima-pay-option-badge">${escapeHtml(m.badge)}</span>
              </button>`).join("")}
          </div>
          <div id="chk-pay-details" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin-bottom:12px;"></div>
          <div id="chk-totals-summary" style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px;margin-bottom:12px;"></div>
          <button type="button" id="btn-confirm-order" class="cima-btn-primary cima-btn-block">Confirmar Pedido</button>
        </div>
      </div>`;

    renderCheckoutPaymentDetails();

    body.querySelectorAll("[data-delivery-id]").forEach((btn) => {
      btn.onclick = async () => {
        state.selectedDelivery = btn.dataset.deliveryId;
        body.querySelectorAll("[data-delivery-id]").forEach((b) => b.classList.toggle("selected", b.dataset.deliveryId === state.selectedDelivery));
        const preview = await apiCall("cima_ve.api.storefront.preview_storefront_cart", {
          items: state.cart,
          payment_method: state.selectedPayment,
          delivery_provider: state.selectedDelivery,
        });
        state.cartPreview = preview;
        renderCheckoutPaymentDetails();
      };
    });

    body.querySelectorAll("[data-pay-id]").forEach((btn) => {
      btn.onclick = async () => {
        state.selectedPayment = btn.dataset.payId;
        body.querySelectorAll("[data-pay-id]").forEach((b) => b.classList.toggle("selected", b.dataset.payId === state.selectedPayment));
        const preview = await apiCall("cima_ve.api.storefront.preview_storefront_cart", {
          items: state.cart,
          payment_method: state.selectedPayment,
          delivery_provider: state.selectedDelivery,
        });
        state.cartPreview = preview;
        renderCheckoutPaymentDetails();
      };
    });

    document.getElementById("btn-confirm-order").onclick = submitOrder;
  }

  function renderCheckoutPaymentDetails() {
    const methods = state.bootstrap?.payment_methods || [];
    const m = methods.find((x) => x.id === state.selectedPayment) || methods[0];
    const t = state.cartPreview?.totals || { taxable_base: 0, iva_amount: 0, igtf_amount: 0, grand_total: 0, cashea: { down_payment_usd: 0, installment_usd: 0 } };

    const detailsEl = document.getElementById("chk-pay-details");
    let extraHtml = `<div style="font-size:12px;color:#475569;margin-bottom:8px;">${escapeHtml(m.description)}</div>`;
    if (m.instructions) {
      extraHtml += `<div style="font-size:12px;background:#fff;padding:8px;border-radius:6px;border:1px dashed #cbd5e1;margin-bottom:8px;">${escapeHtml(m.instructions)}</div>`;
    }
    if (m.requires_reference) {
      extraHtml += `
        <div class="cima-field"><label>Número de Referencia / TXID *</label><input id="pay-ref" placeholder="Ej. 00123456"></div>
        <div class="cima-field"><label>Banco / Emisor</label><input id="pay-bank" placeholder="Ej. Banesco / Binance / Titular"></div>`;
    }
    if (m.id === "cashea") {
      extraHtml += `<div style="font-size:13px;font-weight:700;color:#4338ca;">Inicial hoy (40%): ${money(t.cashea.down_payment_usd)} • 3 cuotas de ${money(t.cashea.installment_usd)}</div>`;
    }
    detailsEl.innerHTML = extraHtml;

    const providers = state.bootstrap?.delivery_providers || [];
    const dp = providers.find((x) => x.id === state.selectedDelivery) || providers[0];
    const deliveryDescEl = document.getElementById("chk-delivery-desc");
    if (deliveryDescEl && dp) {
      deliveryDescEl.textContent = `${dp.description || dp.label} ${dp.cost > 0 ? "• Costo: " + money(dp.cost) : "• Sin costo"}`;
    }

    document.getElementById("chk-totals-summary").innerHTML = `
      <div class="cima-total-row"><span>Base imponible:</span><strong>${money(t.taxable_base)}</strong></div>
      <div class="cima-total-row"><span>IVA (16%):</span><strong>${money(t.iva_amount)}</strong></div>
      ${t.igtf_amount > 0 ? `<div class="cima-total-row"><span>IGTF (3%):</span><strong>${money(t.igtf_amount)}</strong></div>` : ""}
      <div class="cima-total-row"><span>Envío (${escapeHtml(dp?.label || "Retiro")}):</span><strong>${Number(t.shipping_cost || 0) > 0 ? money(t.shipping_cost) : "Gratis"}</strong></div>
      <div class="cima-total-row cima-total-grand"><span>Total a pagar:</span><span>${money(t.grand_total)}</span></div>`;
  }

  async function tryBrowserGooglePay(totalUsd) {
    const method = (state.bootstrap?.payment_methods || []).find((m) => m.id === "google_pay") || {};
    if (window.google && window.google.payments && window.google.payments.api && method.merchant_id) {
      const client = new google.payments.api.PaymentsClient({
        environment: method.simulation_mode ? "TEST" : "PRODUCTION",
      });
      const req = {
        apiVersion: 2,
        apiVersionMinor: 0,
        allowedPaymentMethods: [
          {
            type: "CARD",
            parameters: { allowedAuthMethods: ["PAN_ONLY", "CRYPTOGRAM_3DS"], allowedCardNetworks: ["VISA", "MASTERCARD"] },
            tokenizationSpecification: {
              type: "PAYMENT_GATEWAY",
              parameters: { gateway: "example", gatewayMerchantId: method.merchant_id },
            },
          },
        ],
        merchantInfo: { merchantId: method.merchant_id, merchantName: method.merchant_name || "CIMA ELECTRONIC VE" },
        transactionInfo: { totalPriceStatus: "FINAL", totalPrice: Number(totalUsd).toFixed(2), currencyCode: "USD" },
      };
      const paymentData = await client.loadPaymentData(req);
      return `GooglePay:${paymentData.paymentMethodData?.description || "TokenOK"}`;
    }
    return `BrowserTokenSim:${Date.now()}`;
  }

  async function submitOrder() {
    const btn = document.getElementById("btn-confirm-order");
    btn.disabled = true;
    btn.textContent = "Procesando pedido...";
    try {
      const paymentDetails = {};
      if (document.getElementById("pay-ref")) {
        paymentDetails.reference = document.getElementById("pay-ref").value.trim();
        paymentDetails.bank = document.getElementById("pay-bank")?.value.trim() || "";
        if (!paymentDetails.reference) {
          throw new Error("Ingresa el número de referencia de tu pago.");
        }
      }
      if (state.selectedPayment === "google_pay") {
        paymentDetails.token_summary = await tryBrowserGooglePay(state.cartPreview?.totals?.grand_total || 0);
      }

      const resp = await apiCall("cima_ve.api.storefront.place_storefront_order", {
        items: state.cart,
        payment_method: state.selectedPayment,
        delivery_provider: state.selectedDelivery,
        payment_details: paymentDetails,
        customer_info: {
          full_name: document.getElementById("chk-name").value,
          email: document.getElementById("chk-email").value,
          ve_rif_cedula: document.getElementById("chk-rif").value,
          ve_taxpayer_type: document.getElementById("chk-taxpayer").value,
          phone: document.getElementById("chk-phone").value,
          address: document.getElementById("chk-address").value,
        },
      });

      state.cart = [];
      saveCart();
      const casheaHtml = resp.cashea
        ? `<div style="background:#eef2ff;padding:12px;border-radius:8px;margin:12px 0;">
             <strong>Orden Cashea: ${escapeHtml(resp.cashea.order_id)}</strong><br>
             Inicial: ${money(resp.cashea.down_payment_usd)} • Cuotas: ${resp.cashea.installments}x ${money(resp.cashea.installment_usd)}<br>
             <a href="${escapeHtml(resp.cashea.checkout_url)}" target="_blank" class="cima-btn-primary" style="display:inline-block;margin-top:8px;text-decoration:none;">
               Ir a pagar con Cashea
             </a>
           </div>`
        : "";
      const waStoreUrl = resp.notifications?.store_whatsapp_url || "";
      const waHtml = waStoreUrl
        ? `<div style="margin:10px 0;">
             <a href="${escapeHtml(waStoreUrl)}" target="_blank" class="cima-btn-outline" style="display:inline-block;text-decoration:none;border-color:#16a34a;color:#15803d;">
               Coordinar entrega por WhatsApp
             </a>
           </div>`
        : "";

      document.getElementById("checkout-modal-body").innerHTML = `
        <div style="text-align:center;padding:20px 10px;">
          <div style="font-size:42px;">✅</div>
          <h2>¡Pedido confirmado!</h2>
          <p>Orden ERPNext: <strong>${escapeHtml(resp.sales_order)}</strong> ${resp.sales_invoice ? `• Factura: <strong>${escapeHtml(resp.sales_invoice)}</strong>` : ""}</p>
          <p>Envío: <strong>${escapeHtml(resp.delivery_provider?.label || "Retiro en Tienda")}</strong> • Estado: <strong>${escapeHtml(resp.status)}</strong></p>
          ${casheaHtml}
          ${waHtml}
          <button type="button" class="cima-btn-primary" onclick="document.getElementById('checkout-modal').classList.add('hidden')">Seguir comprando</button>
        </div>`;
    } catch (err) {
      showToast(err.message);
      btn.disabled = false;
      btn.textContent = "Confirmar Pedido";
    }
  }

  function bindEvents() {
    document.getElementById("nav-search-form").onsubmit = (e) => {
      e.preventDefault();
      state.filters.query = document.getElementById("nav-search-input").value.trim();
      state.filters.item_group = document.getElementById("nav-category-select").value;
      state.filters.page = 1;
      loadCatalog();
    };

    document.getElementById("subnav-categories").onclick = (e) => {
      const btn = e.target.closest("[data-cat]");
      if (!btn) return;
      state.filters.item_group = btn.dataset.cat;
      state.filters.page = 1;
      document.getElementById("nav-category-select").value = btn.dataset.cat;
      document.querySelectorAll(".cima-cat-pill").forEach((p) => p.classList.toggle("active", p === btn));
      loadCatalog();
    };

    document.getElementById("filter-in-stock").onchange = (e) => {
      state.filters.only_in_stock = e.target.checked;
      state.filters.page = 1;
      loadCatalog();
    };

    document.getElementById("sort-select").onchange = (e) => {
      state.filters.sort = e.target.value;
      state.filters.page = 1;
      loadCatalog();
    };

    document.getElementById("product-grid").onclick = (e) => {
      const addBtn = e.target.closest("[data-add-item]");
      if (addBtn) {
        const code = addBtn.dataset.addItem;
        const qtyInput = document.getElementById(`qty-${code}`);
        addToCart(code, qtyInput ? qtyInput.value : 1);
        return;
      }
      const viewEl = e.target.closest("[data-view-item]");
      if (viewEl) {
        openProductModal(viewEl.dataset.viewItem);
      }
    };

    document.getElementById("pagination-bar").onclick = (e) => {
      const btn = e.target.closest("[data-page]");
      if (!btn) return;
      state.filters.page = Number(btn.dataset.page);
      loadCatalog();
      window.scrollTo({ top: 0, behavior: "smooth" });
    };

    document.getElementById("btn-cart").onclick = openCart;
    document.getElementById("close-cart-btn").onclick = closeCart;
    document.getElementById("cart-backdrop").onclick = closeCart;

    document.getElementById("cart-items-list").onchange = (e) => {
      const inp = e.target.closest("[data-cart-qty]");
      if (!inp) return;
      const row = state.cart.find((c) => c.item_code === inp.dataset.cartQty);
      if (row) {
        row.qty = Math.max(1, Number(inp.value || 1));
        saveCart();
        refreshCartPreview();
      }
    };

    document.getElementById("cart-items-list").onclick = (e) => {
      const rem = e.target.closest("[data-remove-cart]");
      if (!rem) return;
      state.cart = state.cart.filter((c) => c.item_code !== rem.dataset.removeCart);
      saveCart();
      refreshCartPreview();
    };

    document.getElementById("btn-account").onclick = () => openAccountModal("login");
    document.getElementById("hero-account-btn").onclick = () => openAccountModal("login");
    document.getElementById("btn-orders").onclick = () => openAccountModal("orders");
    document.getElementById("hero-in-stock-btn").onclick = () => {
      document.getElementById("filter-in-stock").checked = true;
      state.filters.only_in_stock = true;
      loadCatalog();
      document.querySelector(".cima-main").scrollIntoView({ behavior: "smooth" });
    };

    document.getElementById("btn-proceed-checkout").onclick = openCheckoutModal;

    document.querySelectorAll("[data-close]").forEach((btn) => {
      btn.onclick = () => document.getElementById(btn.dataset.close).classList.add("hidden");
    });
  }

  init();
})();
