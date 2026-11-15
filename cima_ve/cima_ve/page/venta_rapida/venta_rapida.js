frappe.pages["venta-rapida"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Portal de Vendedores",
		single_column: true,
	});

	new CimaSellerPortal(page, wrapper);
};

class CimaSellerPortal {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = $(wrapper);
		this.state = {
			activeTab: "facturar",
			bootstrap: {
				price_lists: [],
				warehouses: [],
				sales_channels: [],
				sales_persons: [],
				default_price_list: "",
				default_warehouse: "",
				default_sales_channel: "Detal",
				default_sales_person: "",
			},
			priceList: "",
			warehouse: "",
			salesChannel: "Detal",
			salesPerson: "",
			selectedCustomer: null,
			cart: [],
			paymentMethod: "Contado USD",
			applyIgtf: false,
			inventoryItems: [],
			lastInvoiceResult: null,
		};
		this._pricingSeq = 0;
		this._pricingTimer = null;

		this.renderShell();
		this.bindEvents();
		this.loadBootstrap();
	}

	renderShell() {
		const html = `
			<div class="cima-seller-shell">
				<div class="cima-hero-bar">
					<div class="cima-hero-title">
						<h2>Facturación Rápida — Cima Electronic</h2>
						<p>Interfaz simplificada para vendedores: factura en segundos o consulta stock y precios.</p>
					</div>
					<div class="cima-hero-actions">
						<button type="button" class="cima-btn-start-invoice" data-action="start-invoice">
							+ INICIAR FACTURACIÓN
						</button>
						<button type="button" class="cima-btn-inventory" data-action="tab-inventory">
							Ver Inventario y Precios
						</button>
						<button type="button" class="cima-btn-inventory" data-action="open-metrics">
							Métricas de Ventas
						</button>
					</div>
				</div>

				<div id="cima-result-area"></div>

				<div id="cima-view-facturar">
					<div class="cima-grid-invoice">
						<div class="cima-card">
							<div class="cima-card-title">
								<span>1. Cliente y Productos</span>
								<button type="button" class="btn btn-xs btn-default" data-action="new-customer">
									+ Nuevo Cliente
								</button>
							</div>

							<div class="cima-search-row">
								<input type="text" id="cima-customer-search" class="form-control cima-search-input"
									placeholder="Buscar cliente por nombre o Cédula/RIF..." />
								<select id="cima-customer-select" class="form-control" style="max-width: 240px;">
									<option value="">-- Seleccionar cliente --</option>
								</select>
							</div>

							<div class="cima-search-row">
								<select id="cima-price-list" class="form-control" style="max-width: 220px;"></select>
								<select id="cima-warehouse" class="form-control" style="max-width: 220px;"></select>
							</div>

							<div class="cima-search-row">
								<input type="text" id="cima-invoice-item-search" class="form-control cima-search-input"
									placeholder="Buscar producto por código, nombre o categoría..." />
							</div>

							<div id="cima-invoice-item-results" class="cima-product-list">
								<div class="text-muted text-center p-4">Cargando productos...</div>
							</div>
						</div>

						<div class="cima-card">
							<div class="cima-card-title">
								<span>2. Resumen de Factura</span>
								<button type="button" class="btn btn-xs btn-default" data-action="clear-cart">
									Limpiar
								</button>
							</div>
							<div id="cima-logged-seller-badge" class="text-muted small mb-2"></div>

							<div id="cima-cart-items">
								<div class="text-muted text-center p-4">
									Agrega productos desde la izquierda para comenzar.
								</div>
							</div>

							<div class="cima-search-row mt-3">
								<div class="form-group" style="flex: 1; min-width: 140px; margin-bottom: 0;">
									<label class="control-label">Canal de Venta</label>
									<select id="cima-sales-channel" class="form-control"></select>
								</div>
								<div class="form-group" style="flex: 1; min-width: 160px; margin-bottom: 0;">
									<label class="control-label">Vendedor</label>
									<select id="cima-sales-person" class="form-control"></select>
								</div>
							</div>

							<div class="form-group mt-3">
								<label class="control-label">Método de Pago</label>
								<select id="cima-payment-method" class="form-control">
									<option value="Contado USD">Contado USD (Efectivo / Zelle)</option>
									<option value="Pago Móvil / Bs">Pago Móvil / Transferencia Bs</option>
									<option value="Cashea">Cashea (Inicial + Cuotas)</option>
									<option value="Punto de Venta">Punto de Venta</option>
								</select>
							</div>

							<div class="checkbox">
								<label>
									<input type="checkbox" id="cima-apply-igtf" />
									Aplicar IGTF 3% (pago en divisas)
								</label>
							</div>

							<div class="cima-summary-box" id="cima-tax-summary">
								<div class="cima-summary-line"><span>Base Imponible:</span><strong>$0.00</strong></div>
								<div class="cima-summary-line"><span>IVA (16%):</span><strong>$0.00</strong></div>
								<div class="cima-summary-line"><span>IGTF (3%):</span><strong>$0.00</strong></div>
								<div class="cima-summary-total"><span>TOTAL:</span><span>$0.00</span></div>
							</div>

							<button type="button" id="cima-btn-emit" class="cima-btn-emit" disabled>
								EMITIR FACTURA FISCAL
							</button>
						</div>
					</div>
				</div>

				<div id="cima-view-inventario" style="display: none;">
					<div class="cima-card">
						<div class="cima-card-title">
							<span>Inventario y Precios</span>
							<button type="button" class="btn btn-sm btn-primary" data-action="start-invoice">
								Ir a Facturar
							</button>
						</div>
						<div class="cima-search-row">
							<input type="text" id="cima-inv-search" class="form-control cima-search-input"
								placeholder="Buscar por código, nombre o categoría..." />
							<select id="cima-inv-price-list" class="form-control" style="max-width: 220px;"></select>
							<select id="cima-inv-warehouse" class="form-control" style="max-width: 220px;"></select>
						</div>
						<div class="table-responsive">
							<table class="table table-bordered table-hover">
								<thead>
									<tr>
										<th>Código</th>
										<th>Producto</th>
										<th>Categoría</th>
										<th class="text-right">Stock</th>
										<th class="text-right">Precio</th>
										<th class="text-center">Acción</th>
									</tr>
								</thead>
								<tbody id="cima-inv-table-body">
									<tr><td colspan="6" class="text-center text-muted">Cargando inventario...</td></tr>
								</tbody>
							</table>
						</div>
					</div>
				</div>
			</div>
		`;

		this.wrapper.find(".layout-main-section").html(html);
	}

	bindEvents() {
		const root = this.wrapper;

		root.on("click", "[data-action='start-invoice']", () => {
			this.switchTab("facturar");
			root.find("#cima-invoice-item-search").focus();
		});

		root.on("click", "[data-action='tab-inventory']", () => {
			this.switchTab("inventario");
			this.loadInventory(root.find("#cima-inv-search").val() || "");
		});

		root.on("click", "[data-action='open-metrics']", () => {
			frappe.set_route("metricas-ventas");
		});

		root.on("click", "[data-action='clear-cart']", () => {
			clearTimeout(this._pricingTimer);
			this._pricingSeq += 1;
			this.state.cart = [];
			this.state.lastInvoiceResult = null;
			this.renderResultBanner();
			this.renderCart();
		});

		root.on("click", "[data-action='new-customer']", () => {
			this.openNewCustomerDialog();
		});

		let itemSearchTimer = null;
		root.on("input", "#cima-invoice-item-search", (e) => {
			clearTimeout(itemSearchTimer);
			itemSearchTimer = setTimeout(() => {
				this.loadInventory($(e.target).val());
			}, 220);
		});

		let invSearchTimer = null;
		root.on("input", "#cima-inv-search", (e) => {
			clearTimeout(invSearchTimer);
			invSearchTimer = setTimeout(() => {
				this.loadInventory($(e.target).val());
			}, 220);
		});

		let custSearchTimer = null;
		root.on("input", "#cima-customer-search", (e) => {
			clearTimeout(custSearchTimer);
			custSearchTimer = setTimeout(() => {
				this.loadCustomers($(e.target).val());
			}, 220);
		});

		root.on("change", "#cima-customer-select", (e) => {
			this.state.selectedCustomer = $(e.target).val() || null;
			this.renderCart();
			this.refreshCartPricing();
		});

		root.on("change", "#cima-price-list, #cima-inv-price-list", (e) => {
			this.state.priceList = $(e.target).val();
			root.find("#cima-price-list").val(this.state.priceList);
			root.find("#cima-inv-price-list").val(this.state.priceList);
			this.loadInventory(
				this.state.activeTab === "facturar"
					? root.find("#cima-invoice-item-search").val()
					: root.find("#cima-inv-search").val()
			);
			this.refreshCartPricing();
		});

		root.on("change", "#cima-warehouse, #cima-inv-warehouse", (e) => {
			this.state.warehouse = $(e.target).val();
			root.find("#cima-warehouse").val(this.state.warehouse);
			root.find("#cima-inv-warehouse").val(this.state.warehouse);
			this.loadInventory(
				this.state.activeTab === "facturar"
					? root.find("#cima-invoice-item-search").val()
					: root.find("#cima-inv-search").val()
			);
			this.refreshCartPricing();
		});

		root.on("change", "#cima-sales-channel", (e) => {
			this.state.salesChannel = $(e.target).val();
		});

		root.on("change", "#cima-sales-person", (e) => {
			this.state.salesPerson = $(e.target).val();
		});

		root.on("change", "#cima-payment-method", (e) => {
			this.state.paymentMethod = $(e.target).val();
			const isUsdCash = this.state.paymentMethod === "Contado USD";
			this.state.applyIgtf = isUsdCash;
			root.find("#cima-apply-igtf").prop("checked", isUsdCash);
			this.renderCart();
		});

		root.on("change", "#cima-apply-igtf", (e) => {
			this.state.applyIgtf = $(e.target).is(":checked");
			this.renderCart();
		});

		root.on("click", "[data-add-item]", (e) => {
			const code = $(e.currentTarget).attr("data-add-item");
			const item = this.state.inventoryItems.find((r) => r.item_code === code);
			if (item) {
				this.addItemToCart(item);
				this.switchTab("facturar");
			}
		});

		root.on("click", "[data-qty-delta]", (e) => {
			const code = $(e.currentTarget).attr("data-item-code");
			const delta = parseFloat($(e.currentTarget).attr("data-qty-delta"));
			this.updateCartQty(code, delta);
		});

		root.on("focus", "[data-qty-input]", (e) => {
			e.target.select();
		});

		root.on("keydown", "[data-qty-input]", (e) => {
			if (e.key === "Enter") {
				e.preventDefault();
				$(e.target).blur();
			}
		});

		root.on("input", "[data-qty-input]", (e) => {
			const code = $(e.currentTarget).attr("data-qty-input");
			const val = parseFloat($(e.currentTarget).val());
			if (!isNaN(val) && val > 0) {
				this.setCartQty(code, val, { skipRender: true, debouncePricing: true });
			}
		});

		root.on("change", "[data-qty-input]", (e) => {
			const code = $(e.currentTarget).attr("data-qty-input");
			let val = parseFloat($(e.currentTarget).val());
			if (isNaN(val) || val <= 0) {
				val = 1;
				$(e.currentTarget).val(1);
			}
			this.setCartQty(code, val, { skipRender: false, debouncePricing: false });
		});

		root.on("click", "[data-remove-item]", (e) => {
			const code = $(e.currentTarget).attr("data-remove-item");
			this.state.cart = this.state.cart.filter((c) => c.item_code !== code);
			this.renderCart();
			this.refreshCartPricing();
		});

		root.on("click", "#cima-btn-emit", () => {
			this.submitQuickInvoice();
		});
	}

	switchTab(tab) {
		this.state.activeTab = tab;
		const showFacturar = tab === "facturar";
		this.wrapper.find("#cima-view-facturar").toggle(showFacturar);
		this.wrapper.find("#cima-view-inventario").toggle(!showFacturar);
		this.wrapper.find("[data-action='tab-inventory']").toggleClass("active", !showFacturar);
	}

	loadBootstrap() {
		frappe.call({
			method: "cima_ve.api.seller_pos.get_seller_bootstrap",
			callback: (r) => {
				if (!r.message) return;
				this.state.bootstrap = r.message;
				this.state.priceList = r.message.default_price_list || "";
				this.state.warehouse = r.message.default_warehouse || "";
				this.state.salesChannel = r.message.default_sales_channel || "Detal";
				this.state.salesPerson = r.message.default_sales_person || "";

				const plOptions = (r.message.price_lists || [])
					.map((pl) => `<option value="${frappe.utils.escape_html(pl.name)}">${frappe.utils.escape_html(pl.name)} (${pl.currency})</option>`)
					.join("");
				const whOptions =
					`<option value="">Todos los almacenes</option>` +
					(r.message.warehouses || [])
						.map((w) => `<option value="${frappe.utils.escape_html(w.name)}">${frappe.utils.escape_html(w.warehouse_name || w.name)}</option>`)
						.join("");
				const chList = (r.message.sales_channels && r.message.sales_channels.length)
					? r.message.sales_channels
					: ["Detal", "Mayor", "Meta Ads"];
				const chOptions = chList
					.map((ch) => `<option value="${frappe.utils.escape_html(ch)}">${frappe.utils.escape_html(ch)}</option>`)
					.join("");
				const spOptions =
					`<option value="">-- Automático --</option>` +
					(r.message.sales_persons || [])
						.map((sp) => `<option value="${frappe.utils.escape_html(sp)}">${frappe.utils.escape_html(sp)}</option>`)
						.join("");

				this.wrapper.find("#cima-price-list, #cima-inv-price-list").html(plOptions).val(this.state.priceList);
				this.wrapper.find("#cima-warehouse, #cima-inv-warehouse").html(whOptions).val(this.state.warehouse);
				this.wrapper.find("#cima-sales-channel").html(chOptions).val(this.state.salesChannel);
				this.wrapper.find("#cima-sales-person").html(spOptions).val(this.state.salesPerson);

				const sellerFull = r.message.current_user_fullname || frappe.session.user_fullname || frappe.session.user;
				const sellerUser = r.message.current_user || frappe.session.user;
				this.wrapper.find("#cima-logged-seller-badge").html(
					`Responsable: <strong>${frappe.utils.escape_html(sellerFull)}</strong> (${frappe.utils.escape_html(sellerUser)})`
				);

				this.loadCustomers("");
				this.loadInventory("");
			},
		});
	}

	loadCustomers(query) {
		frappe.call({
			method: "cima_ve.api.seller_pos.search_customers",
			args: { query: query || "", limit: 25 },
			callback: (r) => {
				const rows = r.message || [];
				const options =
					`<option value="">-- Seleccionar cliente --</option>` +
					rows
						.map((c) => {
							const rif = c.ve_rif_cedula || c.tax_id || "Sin RIF";
							return `<option value="${frappe.utils.escape_html(c.name)}">${frappe.utils.escape_html(c.customer_name)} (${frappe.utils.escape_html(rif)})</option>`;
						})
						.join("");
				const select = this.wrapper.find("#cima-customer-select");
				select.html(options);
				if (this.state.selectedCustomer) {
					select.val(this.state.selectedCustomer);
				}
			},
		});
	}

	loadInventory(query) {
		frappe.call({
			method: "cima_ve.api.seller_pos.search_inventory_and_prices",
			args: {
				query: query || "",
				price_list: this.state.priceList,
				warehouse: this.state.warehouse,
				limit: 80,
			},
			callback: (r) => {
				this.state.inventoryItems = r.message || [];
				this.renderInvoiceProductList();
				this.renderInventoryTable();
			},
		});
	}

	stockBadge(qty) {
		const n = Number(qty || 0);
		if (n <= 0) return `<span class="cima-stock-badge cima-stock-empty">Sin stock (0)</span>`;
		if (n <= 5) return `<span class="cima-stock-badge cima-stock-low">Stock bajo (${n})</span>`;
		return `<span class="cima-stock-badge cima-stock-ok">Disponible: ${n}</span>`;
	}

	renderInvoiceProductList() {
		const container = this.wrapper.find("#cima-invoice-item-results");
		if (!this.state.inventoryItems.length) {
			container.html(`<div class="text-muted text-center p-4">No se encontraron productos.</div>`);
			return;
		}
		const html = this.state.inventoryItems
			.map((item) => {
				const price = Number(item.price || 0).toFixed(2);
				return `
					<div class="cima-product-row">
						<div>
							<div><strong>${frappe.utils.escape_html(item.item_name)}</strong></div>
							<div class="text-muted small">
								${frappe.utils.escape_html(item.item_code)} · ${this.stockBadge(item.stock_qty)}
							</div>
						</div>
						<div class="text-right">
							<div class="font-weight-bold mb-1">${frappe.utils.escape_html(item.currency || "USD")} ${price}</div>
							<button type="button" class="btn btn-xs btn-primary" data-add-item="${frappe.utils.escape_html(item.item_code)}">
								+ Agregar
							</button>
						</div>
					</div>
				`;
			})
			.join("");
		container.html(html);
	}

	renderInventoryTable() {
		const tbody = this.wrapper.find("#cima-inv-table-body");
		if (!this.state.inventoryItems.length) {
			tbody.html(`<tr><td colspan="6" class="text-center text-muted">Sin resultados para esa búsqueda.</td></tr>`);
			return;
		}
		const html = this.state.inventoryItems
			.map((item) => {
				const price = Number(item.price || 0).toFixed(2);
				return `
					<tr>
						<td><code>${frappe.utils.escape_html(item.item_code)}</code></td>
						<td><strong>${frappe.utils.escape_html(item.item_name)}</strong></td>
						<td>${frappe.utils.escape_html(item.item_group || "-")}</td>
						<td class="text-right">${this.stockBadge(item.stock_qty)}</td>
						<td class="text-right"><strong>${frappe.utils.escape_html(item.currency || "USD")} ${price}</strong></td>
						<td class="text-center">
							<button type="button" class="btn btn-xs btn-success" data-add-item="${frappe.utils.escape_html(item.item_code)}">
								Facturar
							</button>
						</td>
					</tr>
				`;
			})
			.join("");
		tbody.html(html);
	}

	addItemToCart(item) {
		const existing = this.state.cart.find((c) => c.item_code === item.item_code);
		if (existing) {
			existing.qty += 1;
		} else {
			this.state.cart.push({
				item_code: item.item_code,
				item_name: item.item_name,
				qty: 1,
				price_list_rate: Number(item.price || 0),
				discount_percentage: 0,
				discount_amount: 0,
				rate: Number(item.price || 0),
				currency: item.currency || "USD",
			});
		}
		this.renderCart();
		this.refreshCartPricing();
	}

	updateCartQty(code, delta) {
		const row = this.state.cart.find((c) => c.item_code === code);
		if (!row) return;
		row.qty = Math.max(1, row.qty + delta);
		this.renderCart();
		this.refreshCartPricing();
	}

	setCartQty(code, qty, opts = {}) {
		const row = this.state.cart.find((c) => c.item_code === code);
		if (!row) return;
		row.qty = Math.max(0.01, qty);
		if (opts.skipRender) {
			this.updateRowSubtotalDom(row);
			this.updateSummaryFromCart();
		} else {
			this.renderCart();
		}
		if (opts.debouncePricing) {
			clearTimeout(this._pricingTimer);
			this._pricingTimer = setTimeout(() => {
				this.refreshCartPricing();
			}, 280);
		} else {
			clearTimeout(this._pricingTimer);
			this.refreshCartPricing();
		}
	}

	formatRowPriceHtml(row) {
		const rate = Number(row.rate || 0);
		const listRate = Number(row.price_list_rate || rate);
		const discPct = Number(row.discount_percentage || 0);
		const hasDiscount = discPct > 0 || (listRate > 0 && rate < listRate - 0.0001);
		if (hasDiscount) {
			const pctText = discPct > 0
				? `-${discPct.toFixed(discPct % 1 === 0 ? 0 : 1)}%`
				: `-$${(listRate - rate).toFixed(2)}`;
			return `<del class="text-muted">${listRate.toFixed(2)}</del> <strong>${rate.toFixed(2)}</strong> c/u <span class="cima-discount-badge">${pctText}</span>`;
		}
		return `${rate.toFixed(2)} c/u`;
	}

	updateRowSubtotalDom(row) {
		const codeEsc = CSS.escape ? CSS.escape(row.item_code) : row.item_code;
		const sub = (row.qty * row.rate).toFixed(2);
		this.wrapper.find(`[data-item-subtotal="${codeEsc}"]`).text(sub);
		this.wrapper.find(`[data-item-price="${codeEsc}"]`).html(this.formatRowPriceHtml(row));
	}

	refreshCartPricing() {
		if (!this.state.cart.length) return;
		const seq = ++this._pricingSeq;
		frappe.call({
			method: "cima_ve.api.seller_pos.preview_cart_pricing",
			args: {
				items: JSON.stringify(this.state.cart),
				customer: this.state.selectedCustomer || "",
				price_list: this.state.priceList || "",
				warehouse: this.state.warehouse || "",
				apply_igtf: this.state.applyIgtf ? 1 : 0,
			},
			callback: (r) => {
				if (seq !== this._pricingSeq || !r.message) return;
				const priced = r.message.items || [];
				for (const p of priced) {
					const local = this.state.cart.find((c) => c.item_code === p.item_code);
					if (local) {
						local.price_list_rate = Number(p.price_list_rate ?? p.rate ?? local.rate);
						local.discount_percentage = Number(p.discount_percentage || 0);
						local.discount_amount = Number(p.discount_amount || 0);
						local.rate = Number(p.rate ?? local.rate);
					}
				}
				const isEditingQty = $(document.activeElement).is("[data-qty-input]");
				if (isEditingQty) {
					for (const row of this.state.cart) {
						this.updateRowSubtotalDom(row);
					}
					this.updateSummaryFromCart();
				} else {
					this.renderCart();
				}
			},
		});
	}

	updateSummaryFromCart(summaryOverride = null) {
		if (summaryOverride) {
			this.renderSummary(
				Number(summaryOverride.taxable_base || 0),
				Number(summaryOverride.iva_amount || 0),
				Number(summaryOverride.igtf_amount || 0),
				Number(summaryOverride.grand_total || 0)
			);
			return;
		}
		const base = this.state.cart.reduce((acc, r) => acc + r.qty * r.rate, 0);
		const iva = base * 0.16;
		const subtotal = base + iva;
		const igtf = this.state.applyIgtf ? subtotal * 0.03 : 0;
		const total = subtotal + igtf;
		this.renderSummary(base, iva, igtf, total);
	}

	renderCart(summaryOverride = null) {
		const container = this.wrapper.find("#cima-cart-items");
		const emitBtn = this.wrapper.find("#cima-btn-emit");

		if (!this.state.cart.length) {
			container.html(`<div class="text-muted text-center p-4">Agrega productos desde la izquierda para comenzar.</div>`);
			this.renderSummary(0, 0, 0, 0);
			emitBtn.prop("disabled", true);
			return;
		}

		const rowsHtml = this.state.cart
			.map((row) => {
				const sub = (row.qty * row.rate).toFixed(2);
				const codeEsc = frappe.utils.escape_html(row.item_code);
				return `
					<div class="cima-product-row">
						<div>
							<div><strong>${frappe.utils.escape_html(row.item_name)}</strong></div>
							<div class="text-muted small" data-item-price="${codeEsc}">${this.formatRowPriceHtml(row)}</div>
						</div>
						<div class="d-flex align-items-center" style="gap: 6px;">
							<button type="button" class="btn btn-xs btn-default" data-item-code="${codeEsc}" data-qty-delta="-1">-</button>
							<input type="number" class="form-control input-sm cima-qty-input" data-qty-input="${codeEsc}" value="${row.qty}" min="1" step="1" />
							<button type="button" class="btn btn-xs btn-default" data-item-code="${codeEsc}" data-qty-delta="1">+</button>
							<span class="ml-2 font-weight-bold" data-item-subtotal="${codeEsc}">${sub}</span>
							<button type="button" class="btn btn-xs btn-danger" data-remove-item="${codeEsc}">×</button>
						</div>
					</div>
				`;
			})
			.join("");
		container.html(`<div class="cima-product-list">${rowsHtml}</div>`);

		this.updateSummaryFromCart(summaryOverride);

		emitBtn.prop("disabled", !this.state.selectedCustomer || !this.state.cart.length);
	}

	renderSummary(base, iva, igtf, total) {
		this.wrapper.find("#cima-tax-summary").html(`
			<div class="cima-summary-line"><span>Base Imponible:</span><strong>${base.toFixed(2)}</strong></div>
			<div class="cima-summary-line"><span>IVA (16%):</span><strong>${iva.toFixed(2)}</strong></div>
			<div class="cima-summary-line"><span>IGTF (3%):</span><strong>${igtf.toFixed(2)}</strong></div>
			<div class="cima-summary-total"><span>TOTAL:</span><span>${total.toFixed(2)}</span></div>
		`);
	}

	openNewCustomerDialog() {
		const d = new frappe.ui.Dialog({
			title: "Nuevo Cliente Rápido",
			fields: [
				{ label: "Nombre / Razón Social", fieldname: "customer_name", fieldtype: "Data", reqd: 1 },
				{ label: "Cédula o RIF", fieldname: "rif_cedula", fieldtype: "Data", reqd: 1, description: "Ej: V-12345678 o J-12345678-9" },
				{
					label: "Tipo de Contribuyente",
					fieldname: "taxpayer_type",
					fieldtype: "Select",
					options: "No Contribuyente\nOrdinario\nEspecial\nFormal",
					default: "No Contribuyente",
				},
			],
			primary_action_label: "Guardar Cliente",
			primary_action: (values) => {
				frappe.call({
					method: "cima_ve.api.seller_pos.quick_create_customer",
					args: values,
					callback: (r) => {
						if (r.message) {
							this.state.selectedCustomer = r.message.name;
							this.loadCustomers("");
							this.renderCart();
							d.hide();
							frappe.show_alert({ message: "Cliente creado", indicator: "green" });
						}
					},
				});
			},
		});
		d.show();
	}

	submitQuickInvoice() {
		if (!this.state.selectedCustomer || !this.state.cart.length) {
			frappe.msgprint("Selecciona un cliente y al menos un producto.");
			return;
		}
		const btn = this.wrapper.find("#cima-btn-emit");
		btn.prop("disabled", true).text("Emitiendo factura...");

		frappe.call({
			method: "cima_ve.api.seller_pos.create_quick_invoice",
			args: {
				customer: this.state.selectedCustomer,
				items: JSON.stringify(this.state.cart),
				price_list: this.state.priceList,
				warehouse: this.state.warehouse,
				sales_channel: this.state.salesChannel,
				sales_person: this.state.salesPerson,
				payment_method: this.state.paymentMethod,
				apply_igtf: this.state.applyIgtf ? 1 : 0,
				submit: 1,
			},
			callback: (r) => {
				btn.text("EMITIR FACTURA FISCAL");
				if (r.message) {
					this.state.lastInvoiceResult = r.message;
					this.state.cart = [];
					this.renderCart();
					this.renderResultBanner();
					this.loadInventory(this.wrapper.find("#cima-invoice-item-search").val() || "");
				}
			},
			error: () => {
				btn.prop("disabled", false).text("EMITIR FACTURA FISCAL");
			},
		});
	}

	renderResultBanner() {
		const box = this.wrapper.find("#cima-result-area");
		const res = this.state.lastInvoiceResult;
		if (!res) {
			box.empty();
			return;
		}
		const fiscal = res.fiscal || {};
		const cashea = res.cashea || null;
		const seller = res.seller || {};
		const sellerLabel = seller.fullname
			? `${seller.fullname} (${seller.user || ""})`
			: (seller.user || frappe.session.user || "");
		box.html(`
			<div class="cima-result-banner">
				<div><strong>Factura emitida:</strong> ${frappe.utils.escape_html(res.invoice_name)} — Total: ${frappe.utils.escape_html(res.currency)} ${Number(res.grand_total).toFixed(2)}</div>
				<div class="small mt-1">
					<strong>Vendedor:</strong> ${frappe.utils.escape_html(sellerLabel)} ·
					<strong>N° Control Fiscal:</strong> ${frappe.utils.escape_html(fiscal.control_number || "Pendiente")} ·
					<strong>Estado:</strong> ${frappe.utils.escape_html(fiscal.status || "-")}
					${fiscal.pdf_url ? ` · <a href="${frappe.utils.escape_html(fiscal.pdf_url)}" target="_blank">Ver PDF Fiscal</a>` : ""}
				</div>
				${cashea ? `<div class="small mt-1"><strong>Cashea:</strong> Orden ${frappe.utils.escape_html(cashea.order_id)} — Inicial $${Number(cashea.down_payment_usd).toFixed(2)} (<a href="${frappe.utils.escape_html(cashea.checkout_url)}" target="_blank">Link de pago</a>)</div>` : ""}
			</div>
		`);
	}
}
