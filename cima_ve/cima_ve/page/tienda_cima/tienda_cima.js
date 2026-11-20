frappe.pages["tienda-cima"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Tienda CIMA Electronic VE",
		single_column: true,
	});
	new CimaTiendaView(page, wrapper);
};

class CimaTiendaView {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = $(wrapper);
		this.state = {
			items: [],
			cart: [],
			priceList: "",
			warehouse: "",
			customer: "",
			paymentMethod: "Cashea",
			casheaQr: {
				qr_code: "GOHAQN",
				store_label: "Cimaelectronic ve, C.A - Caja 1",
				rif: "J501934070",
				qr_image: "/assets/cima_ve/images/cashea-qr.png",
			},
		};
		this.renderShell();
		this.bindEvents();
		this.loadBootstrap();
	}

	renderShell() {
		this.wrapper.find(".layout-main-section").html(`
			<div class="cima-shell">
				<div class="cima-hero">
					<div class="cima-hero-brand">
						<img src="/assets/cima_ve/images/cima-logo-blanco.png" alt="CIMA" class="cima-hero-logo" />
						<div class="cima-hero-title">
							<h2>Tienda CIMA Electronic VE</h2>
							<p>Catálogo de tienda, precios en tiempo real y pago inmediato con QR Cashea sin interés.</p>
						</div>
					</div>
					<div class="cima-hero-actions">
						<button type="button" class="cima-btn-cashea" data-action="open-qr">
							Ver QR Cashea (GOHAQN)
						</button>
						<button type="button" class="cima-btn-ghost" data-action="go-pos">
							Ir a Facturación Rápida
						</button>
					</div>
				</div>

				<div id="tienda-result-banner"></div>

				<div class="cima-tienda-grid">
					<div class="cima-card">
						<div class="cima-card-title">
							<span>Catálogo de Productos</span>
							<span class="cima-badge cima-badge-teal" id="tienda-count-badge">0 productos</span>
						</div>
						<div class="d-flex flex-wrap mb-3" style="gap: 10px;">
							<input type="text" id="tienda-search" class="form-control" style="flex:1;min-width:200px;"
								placeholder="Buscar producto, código o categoría..." />
							<select id="tienda-price-list" class="form-control" style="max-width:210px;"></select>
							<select id="tienda-warehouse" class="form-control" style="max-width:210px;"></select>
						</div>
						<div id="tienda-catalog" class="cima-catalog-cards">
							<div class="text-muted p-4">Cargando catálogo...</div>
						</div>
					</div>

					<div>
						<div class="cima-card mb-3">
							<div class="cima-card-title">
								<span>Carrito de Tienda</span>
								<button type="button" class="btn btn-xs btn-default" data-action="clear-cart">Vaciar</button>
							</div>
							<div class="form-group">
								<label class="control-label">Cliente</label>
								<select id="tienda-customer" class="form-control"></select>
							</div>
							<div id="tienda-cart-list" class="mb-3 text-muted small">Sin productos en el carrito.</div>
							<div class="form-group">
								<label class="control-label">Método de Pago</label>
								<select id="tienda-payment-method" class="form-control">
									<option value="Cashea">Cashea (QR / Inicial + Cuotas)</option>
									<option value="Contado USD">Contado USD</option>
									<option value="Pago Móvil / Bs">Pago Móvil / Bs</option>
									<option value="Punto de Venta">Punto de Venta</option>
								</select>
							</div>
							<div id="tienda-summary" class="cima-summary-box"></div>
							<button type="button" id="tienda-checkout-btn" class="cima-btn-primary w-100 mt-3" disabled>
								COBRAR Y FACTURAR
							</button>
						</div>

						<div class="cima-cashea-qr-card" id="tienda-cashea-box">
							<div class="small font-weight-bold">Paga en cuotas sin interés con Cashea</div>
							<img src="/assets/cima_ve/images/cashea-qr.png" alt="QR Cashea" />
							<div class="cima-cashea-code" id="tienda-qr-code">GOHAQN</div>
							<div class="small text-muted mt-2" id="tienda-qr-store">Cimaelectronic ve, C.A - Caja 1 · RIF J501934070</div>
						</div>
					</div>
				</div>
			</div>
		`);
	}

	bindEvents() {
		const root = this.wrapper;
		root.on("click", "[data-action='go-pos']", () => frappe.set_route("venta-rapida"));
		root.on("click", "[data-action='open-qr']", () => this.showQrModal());
		root.on("click", "[data-action='clear-cart']", () => {
			this.state.cart = [];
			this.renderCart();
		});

		let timer = null;
		root.on("input", "#tienda-search", (e) => {
			clearTimeout(timer);
			timer = setTimeout(() => this.loadItems($(e.target).val()), 220);
		});

		root.on("change", "#tienda-price-list", (e) => {
			this.state.priceList = $(e.target).val();
			this.loadItems(root.find("#tienda-search").val() || "");
		});

		root.on("change", "#tienda-warehouse", (e) => {
			this.state.warehouse = $(e.target).val();
			this.loadItems(root.find("#tienda-search").val() || "");
		});

		root.on("change", "#tienda-customer", (e) => {
			this.state.customer = $(e.target).val();
			this.renderCart();
		});

		root.on("change", "#tienda-payment-method", (e) => {
			this.state.paymentMethod = $(e.target).val();
			root.find("#tienda-cashea-box").toggle(this.state.paymentMethod === "Cashea");
			this.renderCart();
		});

		root.on("click", "[data-tienda-add]", (e) => {
			const code = $(e.currentTarget).attr("data-tienda-add");
			const item = this.state.items.find((i) => i.item_code === code);
			if (!item) return;
			const existing = this.state.cart.find((c) => c.item_code === code);
			if (existing) existing.qty += 1;
			else {
				this.state.cart.push({
					item_code: item.item_code,
					item_name: item.item_name,
					qty: 1,
					rate: Number(item.price || 0),
				});
			}
			this.renderCart();
		});

		root.on("click", "[data-tienda-remove]", (e) => {
			const code = $(e.currentTarget).attr("data-tienda-remove");
			this.state.cart = this.state.cart.filter((c) => c.item_code !== code);
			this.renderCart();
		});

		root.on("click", "#tienda-checkout-btn", () => this.checkout());
	}

	loadBootstrap() {
		frappe.call({
			method: "cima_ve.api.seller_pos.get_seller_bootstrap",
			callback: (r) => {
				if (!r.message) return;
				this.state.priceList = r.message.default_price_list || "";
				this.state.warehouse = r.message.default_warehouse || "";
				if (r.message.cashea_qr) {
					this.state.casheaQr = r.message.cashea_qr;
					this.wrapper.find("#tienda-qr-code").text(this.state.casheaQr.qr_code);
					this.wrapper.find("#tienda-qr-store").text(
						`${this.state.casheaQr.store_label} · RIF ${this.state.casheaQr.rif}`
					);
				}

				const pls = (r.message.price_lists || [])
					.map((p) => `<option value="${frappe.utils.escape_html(p.name)}">${frappe.utils.escape_html(p.name)}</option>`)
					.join("");
				const whs = `<option value="">Todos los almacenes</option>` +
					(r.message.warehouses || [])
						.map((w) => `<option value="${frappe.utils.escape_html(w.name)}">${frappe.utils.escape_html(w.warehouse_name || w.name)}</option>`)
						.join("");
				this.wrapper.find("#tienda-price-list").html(pls).val(this.state.priceList);
				this.wrapper.find("#tienda-warehouse").html(whs).val(this.state.warehouse);

				this.loadCustomers();
				this.loadItems("");
			},
		});
	}

	loadCustomers() {
		frappe.call({
			method: "cima_ve.api.seller_pos.search_customers",
			args: { query: "", limit: 30 },
			callback: (r) => {
				const rows = r.message || [];
				const opts = `<option value="">-- Seleccionar cliente --</option>` +
					rows.map((c) => `<option value="${frappe.utils.escape_html(c.name)}">${frappe.utils.escape_html(c.customer_name)}</option>`).join("");
				this.wrapper.find("#tienda-customer").html(opts);
			},
		});
	}

	loadItems(query) {
		frappe.call({
			method: "cima_ve.api.seller_pos.search_inventory_and_prices",
			args: {
				query: query || "",
				price_list: this.state.priceList,
				warehouse: this.state.warehouse,
				limit: 80,
			},
			callback: (r) => {
				this.state.items = r.message || [];
				this.renderCatalog();
			},
		});
	}

	renderCatalog() {
		this.wrapper.find("#tienda-count-badge").text(`${this.state.items.length} productos`);
		const box = this.wrapper.find("#tienda-catalog");
		if (!this.state.items.length) {
			box.html(`<div class="text-muted p-4">No se encontraron productos.</div>`);
			return;
		}
		box.html(
			this.state.items
				.map((item) => {
					const price = Number(item.price || 0);
					const inicial = (price * 0.4).toFixed(2);
					const stock = Number(item.stock_qty || 0);
					return `
						<div class="cima-item-card">
							<div>
								<div class="small text-muted">${frappe.utils.escape_html(item.item_group || "General")}</div>
								<div class="font-weight-bold mt-1">${frappe.utils.escape_html(item.item_name)}</div>
								<div class="small text-muted"><code>${frappe.utils.escape_html(item.item_code)}</code></div>
							</div>
							<div>
								<div class="cima-item-price">$${price.toFixed(2)}</div>
								<div class="cima-cashea-installment">Cashea: Inicial ~$${inicial} + 3 cuotas</div>
								<div class="d-flex justify-content-between align-items-center">
									<span class="cima-badge ${stock > 0 ? "cima-badge-green" : "cima-badge-red"}">
										Stock: ${stock}
									</span>
									<button type="button" class="btn btn-xs btn-primary" data-tienda-add="${frappe.utils.escape_html(item.item_code)}">
										+ Agregar
									</button>
								</div>
							</div>
						</div>
					`;
				})
				.join("")
		);
	}

	renderCart() {
		const list = this.wrapper.find("#tienda-cart-list");
		const btn = this.wrapper.find("#tienda-checkout-btn");
		if (!this.state.cart.length) {
			list.html(`<div class="text-muted small">Sin productos en el carrito.</div>`);
			this.wrapper.find("#tienda-summary").html(`<div><strong>Total: $0.00</strong></div>`);
			btn.prop("disabled", true);
			return;
		}
		list.html(
			this.state.cart
				.map(
					(c) => `
					<div class="d-flex justify-content-between align-items-center py-1 border-bottom">
						<div><strong>${c.qty}x</strong> ${frappe.utils.escape_html(c.item_name)}</div>
						<div>
							<strong>$${(c.qty * c.rate).toFixed(2)}</strong>
							<button type="button" class="btn btn-xs btn-danger ml-1" data-tienda-remove="${frappe.utils.escape_html(c.item_code)}">×</button>
						</div>
					</div>`
				)
				.join("")
		);
		const base = this.state.cart.reduce((s, r) => s + r.qty * r.rate, 0);
		const iva = base * 0.16;
		const total = base + iva;
		this.wrapper.find("#tienda-summary").html(`
			<div class="d-flex justify-content-between small"><span>Base:</span><span>$${base.toFixed(2)}</span></div>
			<div class="d-flex justify-content-between small"><span>IVA (16%):</span><span>$${iva.toFixed(2)}</span></div>
			<div class="d-flex justify-content-between font-weight-bold mt-1"><span>TOTAL:</span><span>$${total.toFixed(2)}</span></div>
		`);
		btn.prop("disabled", !this.state.customer || !this.state.cart.length);
	}

	showQrModal() {
		const qr = this.state.casheaQr;
		const d = new frappe.ui.Dialog({
			title: "QR Cashea — Tienda CIMA",
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "qr",
					options: `
						<div class="cima-cashea-qr-card" style="margin-top:0;">
							<h4 style="margin:0 0 6px;">Compra aquí en cuotas sin interés</h4>
							<img src="${frappe.utils.escape_html(qr.qr_image)}" alt="QR Cashea" style="max-width:260px;" />
							<div class="cima-cashea-code" style="font-size:18px;">${frappe.utils.escape_html(qr.qr_code)}</div>
							<p class="small text-muted mt-2 mb-0">${frappe.utils.escape_html(qr.store_label)} · RIF ${frappe.utils.escape_html(qr.rif)}</p>
						</div>
					`,
				},
			],
		});
		d.show();
	}

	checkout() {
		const btn = this.wrapper.find("#tienda-checkout-btn");
		btn.prop("disabled", true).text("Procesando...");
		frappe.call({
			method: "cima_ve.api.seller_pos.create_quick_invoice",
			args: {
				customer: this.state.customer,
				items: JSON.stringify(this.state.cart),
				price_list: this.state.priceList,
				warehouse: this.state.warehouse,
				payment_method: this.state.paymentMethod,
				sales_channel: "Tienda / Detal",
				apply_igtf: this.state.paymentMethod === "Contado USD" ? 1 : 0,
				submit: 1,
			},
			callback: (r) => {
				btn.text("COBRAR Y FACTURAR");
				if (r.message) {
					this.state.cart = [];
					this.renderCart();
					this.wrapper.find("#tienda-result-banner").html(`
						<div class="alert alert-success">
							<strong>Venta registrada:</strong> ${frappe.utils.escape_html(r.message.invoice_name)} —
							Total $${Number(r.message.grand_total).toFixed(2)}
						</div>
					`);
					this.loadItems(this.wrapper.find("#tienda-search").val() || "");
				}
			},
			error: () => btn.prop("disabled", false).text("COBRAR Y FACTURAR"),
		});
	}
}
