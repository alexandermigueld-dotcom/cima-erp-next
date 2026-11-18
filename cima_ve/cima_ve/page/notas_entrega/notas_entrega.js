frappe.pages["notas-entrega"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Notas de Entrega",
		single_column: true,
	});
	new CimaNotasEntrega(page, wrapper);
};

class CimaNotasEntrega {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = $(wrapper);
		this.data = null;
		this.filters = {
			status: "",
			from_date: "",
			to_date: "",
			seller: "",
			search: "",
		};
		this.renderShell();
		this.bindEvents();
		this.loadNotes();
	}

	renderShell() {
		const html = `
			<div class="cima-ne-shell">
				<div class="cima-ne-hero">
					<div>
						<h2 id="ne-hero-title">Control de Notas de Entrega — Cima Electronic</h2>
						<p id="ne-hero-subtitle">Seguimiento de despachos pendientes de pago: marca como Pagado (con método e impuestos) o Cancela para devolver el stock.</p>
					</div>
					<div class="d-flex" style="gap:8px;flex-wrap:wrap;">
						<button type="button" class="btn btn-sm btn-primary" data-action="go-pos">+ Nueva Nota de Entrega</button>
						<button type="button" class="btn btn-sm btn-success" data-action="calc-commission" id="ne-btn-calc-commission" style="display:none;">Calcular Comisiones</button>
						<button type="button" class="btn btn-sm btn-default" data-action="go-clients" id="ne-btn-clients" style="display:none;">Clientes y Consumo</button>
						<button type="button" class="btn btn-sm btn-default" data-action="refresh">Actualizar</button>
					</div>
				</div>

				<div class="cima-ne-card">
					<div class="cima-ne-filters">
						<div>
							<label class="small text-muted">Estado</label>
							<select id="ne-filter-status" class="form-control input-sm">
								<option value="">Todos</option>
								<option value="Pendiente" selected>Pendiente por Cobrar</option>
								<option value="Pago Parcial">Pago Parcial</option>
								<option value="Pagada">Pagada</option>
								<option value="Cancelada">Cancelada</option>
							</select>
						</div>
						<div id="ne-seller-filter-wrap">
							<label class="small text-muted">Vendedor</label>
							<select id="ne-filter-seller" class="form-control input-sm">
								<option value="">Todos</option>
							</select>
						</div>
						<div>
							<label class="small text-muted">Desde</label>
							<input type="date" id="ne-filter-from" class="form-control input-sm" />
						</div>
						<div>
							<label class="small text-muted">Hasta</label>
							<input type="date" id="ne-filter-to" class="form-control input-sm" />
						</div>
						<div>
							<label class="small text-muted">Buscar (N° o Cliente)</label>
							<input type="text" id="ne-filter-search" class="form-control input-sm" placeholder="MAT-DN o cliente..." />
						</div>
					</div>
				</div>

				<div class="cima-ne-kpis" id="ne-kpis"></div>

				<div class="cima-ne-card">
					<div class="table-responsive">
						<table class="table table-bordered table-hover table-sm">
							<thead>
								<tr>
									<th>Nota de Entrega</th>
									<th>Fecha</th>
									<th>Cliente</th>
									<th>Vendedor</th>
									<th>Productos</th>
									<th class="text-right">Monto Base</th>
									<th>Comisión Vendedor</th>
									<th>Estado</th>
									<th>Registro Pago / Cancelación</th>
									<th>Acciones</th>
								</tr>
							</thead>
							<tbody id="ne-table-body">
								<tr><td colspan="10" class="text-center text-muted p-4">Cargando notas de entrega...</td></tr>
							</tbody>
						</table>
					</div>
				</div>
			</div>
		`;
		this.wrapper.find(".layout-main-section").html(html);
		this.filters.status = "Pendiente";
	}

	bindEvents() {
		const root = this.wrapper;
		root.on("click", "[data-action='go-pos']", () => frappe.set_route("venta-rapida"));
		root.on("click", "[data-action='calc-commission']", () => this.openCommissionCalculator());
		root.on("click", "[data-action='go-clients']", () => frappe.set_route("clientes-consumo"));
		root.on("click", "[data-action='refresh']", () => this.loadNotes());

		root.on("change", "#ne-filter-status, #ne-filter-seller, #ne-filter-from, #ne-filter-to", () => {
			this.filters.status = root.find("#ne-filter-status").val() || "";
			this.filters.seller = root.find("#ne-filter-seller").val() || "";
			this.filters.from_date = root.find("#ne-filter-from").val() || "";
			this.filters.to_date = root.find("#ne-filter-to").val() || "";
			this.loadNotes();
		});

		let timer = null;
		root.on("input", "#ne-filter-search", (e) => {
			clearTimeout(timer);
			timer = setTimeout(() => {
				this.filters.search = $(e.target).val() || "";
				this.loadNotes();
			}, 300);
		});

		root.on("click", "[data-pay-dn]", (e) => {
			const dnName = $(e.currentTarget).attr("data-pay-dn");
			const note = (this.data?.notes || []).find((n) => n.name === dnName);
			if (note) this.openPaidDialog(note);
		});

		root.on("click", "[data-cancel-dn]", (e) => {
			const dnName = $(e.currentTarget).attr("data-cancel-dn");
			const note = (this.data?.notes || []).find((n) => n.name === dnName);
			if (note) this.openCancelDialog(note);
		});
	}

	loadNotes() {
		frappe.call({
			method: "cima_ve.api.delivery_notes.get_delivery_notes",
			args: this.filters,
			callback: (r) => {
				if (!r.message) return;
				this.data = r.message;
				this.applyRoleUi();
				this.renderSellerFilter();
				this.renderKpis();
				this.renderTable();
			},
		});
	}

	applyRoleUi() {
		const isAdmin = Boolean(this.data?.config?.is_admin);
		this.wrapper.find("#ne-btn-clients").toggle(isAdmin);
		this.wrapper.find("#ne-btn-calc-commission").toggle(isAdmin);
		this.wrapper.find("#ne-seller-filter-wrap").toggle(isAdmin);
		if (isAdmin) {
			this.wrapper.find("#ne-hero-title").text("Control de Notas de Entrega — Cima Electronic");
			this.wrapper.find("#ne-hero-subtitle").text(
				"Seguimiento de despachos pendientes de pago: marca como Pagado (con método e impuestos) o Cancela para devolver el stock."
			);
		} else {
			this.wrapper.find("#ne-hero-title").text("Mis Notas de Entrega");
			this.wrapper.find("#ne-hero-subtitle").text(
				"Consulta las Notas de Entrega emitidas por tu usuario y registra tus pagos con comprobante."
			);
		}
	}

	renderSellerFilter() {
		const sel = this.wrapper.find("#ne-filter-seller");
		const cur = this.filters.seller || "";
		const sellers = this.data?.config?.sellers || [];
		const opts = [`<option value="">Todos</option>`].concat(
			sellers.map((s) => `<option value="${frappe.utils.escape_html(s.user)}">${frappe.utils.escape_html(s.fullname)}</option>`)
		);
		sel.html(opts.join("")).val(cur);
	}

	renderKpis() {
		const s = this.data?.summary || {};
		const fx = this.data?.config?.exchange_rate || {};
		const fxRate = Number(fx.adjusted_rate || fx.bcv_rate || 0);
		const fxCard =
			fxRate > 0
				? `<div class="cima-ne-kpi" style="border-left:3px solid #2563eb;">
					<div class="cima-ne-kpi-label">Tasa Ajustada (BCV + Brecha ${Number(fx.applied_brecha_pct || 0).toFixed(1)}%)</div>
					<div class="cima-ne-kpi-val" style="color:#1d4ed8;">Bs. ${fxRate.toFixed(2)}</div>
					<div class="cima-ne-kpi-sub">BCV ${Number(fx.bcv_rate || 0).toFixed(2)} · Binance ${Number(fx.binance_usdt_rate || 0).toFixed(2)}</div>
				</div>`
				: "";
		this.wrapper.find("#ne-kpis").html(`
			<div class="cima-ne-kpi">
				<div class="cima-ne-kpi-label">Pendientes por Cobrar</div>
				<div class="cima-ne-kpi-val" style="color:#b45309;">$${Number(s.pending_total || 0).toFixed(2)}</div>
				<div class="cima-ne-kpi-sub">${s.pending_count || 0} notas activas</div>
			</div>
			<div class="cima-ne-kpi">
				<div class="cima-ne-kpi-label">Pagadas</div>
				<div class="cima-ne-kpi-val" style="color:#15803d;">$${Number(s.paid_total || 0).toFixed(2)}</div>
				<div class="cima-ne-kpi-sub">${s.paid_count || 0} notas liquidadas</div>
			</div>
			<div class="cima-ne-kpi">
				<div class="cima-ne-kpi-label">Canceladas (Stock Devuelto)</div>
				<div class="cima-ne-kpi-val" style="color:#b91c1c;">$${Number(s.cancelled_total || 0).toFixed(2)}</div>
				<div class="cima-ne-kpi-sub">${s.cancelled_count || 0} notas anuladas</div>
			</div>
			<div class="cima-ne-kpi" style="border-left:3px solid #7c3aed;">
				<div class="cima-ne-kpi-label">Comisión Vendedor (Filtro)</div>
				<div class="cima-ne-kpi-val" style="color:#6d28d9;">$${Number(s.filtered_commission || 0).toFixed(2)}</div>
				<div class="cima-ne-kpi-sub">Pagadas: $${Number(s.filtered_paid_commission || 0).toFixed(2)} · Pend.: $${Number(s.filtered_pending_commission || 0).toFixed(2)}</div>
			</div>
			<div class="cima-ne-kpi">
				<div class="cima-ne-kpi-label">Total Notas</div>
				<div class="cima-ne-kpi-val">${s.total_count || 0}</div>
				<div class="cima-ne-kpi-sub">Margen filtro: $${Number(s.filtered_margin || 0).toFixed(2)}</div>
			</div>
			${fxCard}
		`);
	}

	renderTable() {
		const isAdmin = Boolean(this.data?.config?.is_admin);
		const notes = this.data?.notes || [];
		const tbody = this.wrapper.find("#ne-table-body");
		if (!notes.length) {
			tbody.html(`<tr><td colspan="10" class="text-center text-muted p-4">No hay Notas de Entrega para los filtros seleccionados.</td></tr>`);
			return;
		}

		tbody.html(
			notes
				.map((n) => {
					const itemsText = (n.items || [])
						.slice(0, 4)
						.map((it) => {
							const orig = Number(it.price_list_rate || 0);
							const rate = Number(it.rate || 0);
							const hasDisc = Boolean(it.has_discount || Number(it.discount_percentage || 0) > 0 || (orig > 0 && rate < orig - 0.0001));
							const discHtml = hasDisc
								? ` <del class="text-muted">$${orig.toFixed(2)}</del> <strong>$${rate.toFixed(2)}</strong> <span class="label" style="background:#fef3c7;color:#92400e;border:1px solid #fde68a;font-size:10px;">Descuento</span>`
								: ` <span class="text-muted">($${rate.toFixed(2)})</span>`;
							return `${Number(it.qty)}x ${frappe.utils.escape_html(it.item_name || it.item_code)}${discHtml}`;
						})
						.join("<br>");
					const moreItems = (n.items || []).length > 4 ? `<div class="text-muted small">+${n.items.length - 4} más</div>` : "";
					const globalDiscTags = [];
					if (Number(n.auto_discount_pct || 0) > 0 || Number(n.auto_discount_amount || 0) > 0) {
						globalDiscTags.push(
							`Auto -${Number(n.auto_discount_pct || 0).toFixed(2)}% (-$${Number(n.auto_discount_amount || 0).toFixed(2)})`
						);
					}
					if (Number(n.manual_discount_pct || 0) > 0 || Number(n.manual_discount_amount || 0) > 0) {
						globalDiscTags.push(
							`Manual -${Number(n.manual_discount_pct || 0).toFixed(2)}% (-$${Number(n.manual_discount_amount || 0).toFixed(2)})`
						);
					}
					const globalDiscBadge = globalDiscTags.length
						? `<div class="mt-1"><span class="label" style="background:#fef3c7;color:#92400e;border:1px solid #f59e0b;font-size:10px;display:inline-block;white-space:normal;">Descuento: ${frappe.utils.escape_html(globalDiscTags.join(" + "))}</span></div>`
						: "";
					const noteDiscountBadge =
						!globalDiscTags.length && n.has_discount
							? `<div class="mt-1"><span class="label" style="background:#fef3c7;color:#92400e;border:1px solid #fde68a;font-size:10px;">Con descuento (${Number(n.discounted_items_count || 1)})</span></div>`
							: "";
					const badgeClass =
						n.ve_ne_estado === "Pagada"
							? "cima-ne-badge-pagada"
							: n.ve_ne_estado === "Pago Parcial"
							? "cima-ne-badge-parcial"
							: n.ve_ne_estado === "Cancelada"
							? "cima-ne-badge-cancelada"
							: "cima-ne-badge-pendiente";

					const history = Array.isArray(n.payment_history) ? n.payment_history : [];
					const historyHtml = history.length
						? `<div class="mt-1 pt-1" style="border-top:1px dashed #cbd5e1;">` +
						  history
								.map(
									(h, idx) => {
										const proofLink = h.screenshot_url
											? ` · <a href="${encodeURI(h.screenshot_url)}" target="_blank" rel="noopener">📎 Ver captura</a>`
											: "";
										const hBs = Number(h.amount_bs || 0) > 0
											? ` (${this.formatBs(h.amount_bs)})`
											: "";
										return `<div class="text-muted" style="font-size:11px;">#${idx + 1}: <strong>$${Number(h.amount || 0).toFixed(2)}${hBs}</strong> · ${frappe.utils.escape_html(h.method || "")}${h.reference ? ` (Ref: ${frappe.utils.escape_html(h.reference)})` : ""}${proofLink} · ${frappe.utils.escape_html((h.paid_at || "").slice(0, 16))}</div>`;
									}
								)
								.join("") +
						  `</div>`
						: "";

					const reportedProofHtml = (n.ve_ne_metodo_pago || n.ve_ne_referencia_pago || n.ve_ne_comprobante_url)
						? `<div class="mt-1 p-1 small" style="background:#f8fafc;border:1px dashed #cbd5e1;border-radius:4px;">
							${n.ve_ne_metodo_pago ? `<div><strong>Reportado:</strong> ${frappe.utils.escape_html(n.ve_ne_metodo_pago)}</div>` : ""}
							${n.ve_ne_referencia_pago ? `<div><strong>Ref:</strong> ${frappe.utils.escape_html(n.ve_ne_referencia_pago)}${n.ve_ne_banco_pago ? ` (${frappe.utils.escape_html(n.ve_ne_banco_pago)})` : ""}</div>` : ""}
							${n.ve_ne_comprobante_url ? `<div><a href="${encodeURI(n.ve_ne_comprobante_url)}" target="_blank" rel="noopener">📎 Ver captura reportada</a></div>` : ""}
						</div>`
						: "";

					let resolutionHtml = `<span class="text-muted small">Sin procesar</span>${reportedProofHtml}`;
					if (n.ve_ne_estado === "Pagada" || n.ve_ne_estado === "Pago Parcial") {
						const taxTags = [
							n.ve_ne_aplica_iva ? "IVA" : "Sin IVA",
							n.ve_ne_aplica_igtf ? "IGTF" : "",
						]
							.filter(Boolean)
							.join(" + ");
						const paidBsText = Number(n.paid_bs || 0) > 0 ? ` (${this.formatBs(n.paid_bs)})` : "";
						const totalBsText = Number(n.total_bs || 0) > 0 ? ` (${this.formatBs(n.total_bs)})` : paidBsText;
						const balanceLine =
							n.ve_ne_estado === "Pago Parcial"
								? `<div style="color:#1e40af;font-weight:700;">Pagado: $${Number(n.paid_amount || 0).toFixed(2)}${paidBsText} · Resta: $${Number(n.remaining_amount || 0).toFixed(2)}</div>`
								: `<div>Total pagado: <strong>$${Number(n.paid_amount || n.total_to_pay || n.amount || 0).toFixed(2)}${totalBsText}</strong></div>`;
						resolutionHtml = `
							<div class="small">
								${balanceLine}
								<strong>${frappe.utils.escape_html(n.ve_ne_metodo_pago || "-")}</strong> (${frappe.utils.escape_html(taxTags)})<br>
								<span class="text-muted">${frappe.utils.escape_html(n.ve_ne_fecha_resolucion || "")}</span><br>
								<span class="text-muted">Por: ${frappe.utils.escape_html(n.ve_ne_usuario_resolucion || "")}</span>
								${n.ve_ne_factura && isAdmin ? `<br><a href="/app/sales-invoice/${encodeURIComponent(n.ve_ne_factura)}">${frappe.utils.escape_html(n.ve_ne_factura)}</a>` : ""}
								${n.ve_ne_comprobante_url && !history.length ? `<br><a href="${encodeURI(n.ve_ne_comprobante_url)}" target="_blank" rel="noopener">📎 Ver captura</a>` : ""}
								${historyHtml}
							</div>
						`;
					} else if (n.ve_ne_estado === "Cancelada") {
						resolutionHtml = `
							<div class="small text-danger">
								<strong>Anulada</strong> (${frappe.utils.escape_html(n.ve_ne_fecha_resolucion || "")})<br>
								<span class="text-muted">Por: ${frappe.utils.escape_html(n.ve_ne_usuario_resolucion || "")}</span>
								${n.ve_ne_motivo_cancelacion ? `<br><span class="text-muted">${frappe.utils.escape_html(n.ve_ne_motivo_cancelacion)}</span>` : ""}
							</div>
						`;
					}

					const isPayable = n.ve_ne_estado === "Pendiente" || n.ve_ne_estado === "Pago Parcial";
					const canCancel = isAdmin && n.ve_ne_estado === "Pendiente" && Number(n.paid_amount || 0) <= 0 && !n.ve_ne_factura;
					const actionsHtml = isPayable
						? `<div class="cima-ne-actions">
							<button type="button" class="btn btn-xs btn-success" data-pay-dn="${frappe.utils.escape_html(n.name)}">${n.ve_ne_estado === "Pago Parcial" ? "Abonar / Pagado" : "Pagado"}</button>
							${canCancel ? `<button type="button" class="btn btn-xs btn-danger" data-cancel-dn="${frappe.utils.escape_html(n.name)}">Cancelar</button>` : ""}
						</div>`
						: isAdmin
						? `<a class="btn btn-xs btn-default" href="/app/delivery-note/${encodeURIComponent(n.name)}">Ver</a>`
						: `<span class="text-muted small">Completada</span>`;

					const fx = this.data?.config?.exchange_rate || {};
					const fxRate = Number(fx.adjusted_rate || fx.bcv_rate || 0);
					const totalUsd = Number(n.total_to_pay || n.amount || 0);
					let bsLine = "";
					if (n.ve_ne_estado === "Pagada") {
						const frozenBs = Number(n.total_bs || n.paid_bs || 0);
						if (frozenBs > 0) {
							const frozenRate = Number(n.exchange_rate_used || 0);
							const rateTip = frozenRate > 0 ? ` title="Referencia histórica congelada @ Bs. ${frozenRate.toFixed(2)}/USD"` : "";
							bsLine = `<div class="small text-muted"${rateTip}>${this.formatBs(frozenBs)} <span style="font-size:10px;">(hist.)</span></div>`;
						}
					} else if (n.ve_ne_estado === "Pago Parcial") {
						const paidBs = Number(n.paid_bs || 0);
						const remBs = fxRate > 0 ? Number(n.remaining_amount || 0) * fxRate : 0;
						const paidBsHtml = paidBs > 0 ? `<div class="small text-muted">Pagado: ${this.formatBs(paidBs)}</div>` : "";
						const remBsHtml = remBs > 0 ? ` (${this.formatBs(remBs)})` : "";
						bsLine = paidBsHtml;
						n._remBsHtml = remBsHtml;
					} else if (n.ve_ne_estado !== "Cancelada" && fxRate > 0) {
						const liveBs = totalUsd * fxRate;
						if (liveBs > 0) {
							bsLine = `<div class="small text-muted">${this.formatBs(liveBs)}</div>`;
						}
					}

					const origSub = Number(n.subtotal_before_discount || 0);
					const baseDiscPrefix =
						n.has_global_discount && origSub > Number(n.amount || 0) + 0.01
							? `<div class="small text-muted"><del>$${origSub.toFixed(2)}</del></div>`
							: "";
					const amountCellHtml =
						n.ve_ne_estado === "Pago Parcial"
							? `${baseDiscPrefix}<div>$${totalUsd.toFixed(2)}</div>${bsLine}<div class="small text-primary">Resta: $${Number(n.remaining_amount || 0).toFixed(2)}${n._remBsHtml || ""}</div>`
							: `${baseDiscPrefix}$${totalUsd.toFixed(2)}${bsLine}`;

					const originBadge =
						n.ve_ne_origen === "Tienda Web"
							? `<div><span class="label" style="background:#dbeafe;color:#1e40af;font-size:10px;">Tienda Web</span></div>`
							: "";
					const shipInfo = n.ve_ne_envio_proveedor
						? `<div class="small text-muted">Envío: ${frappe.utils.escape_html(n.ve_ne_envio_proveedor)}${Number(n.ve_ne_envio_costo || 0) > 0 ? ` ($${Number(n.ve_ne_envio_costo).toFixed(2)})` : ""}</div>`
						: "";

					let commissionCellHtml = `<span class="text-muted small">Sin comisión</span>`;
					if (n.ve_ne_estado === "Cancelada") {
						commissionCellHtml = `<span class="text-muted small">Anulada ($0.00)</span>`;
					} else if (n.commission_option || Number(n.commission_pct || 0) > 0) {
						const optLabel = n.commission_option || `${Number(n.commission_pct || 0).toFixed(0)}%`;
						const marginLine = isAdmin
							? `<div class="text-muted" style="font-size:11px;">Margen: $${Number(n.margin_amount || 0).toFixed(2)} (Costo: $${Number(n.cost_total || 0).toFixed(2)})</div>`
							: "";
						commissionCellHtml = `
							<div class="small">
								<span class="label" style="background:#ede9fe;color:#5b21b6;border:1px solid #ddd6fe;font-size:10px;">${frappe.utils.escape_html(optLabel)}</span>
								<div style="color:#5b21b6;font-weight:700;margin-top:2px;">$${Number(n.commission_amount || 0).toFixed(2)}</div>
								${marginLine}
							</div>
						`;
					}

					return `
						<tr>
							<td><a href="/app/delivery-note/${encodeURIComponent(n.name)}"><strong>${frappe.utils.escape_html(n.name)}</strong></a>${originBadge}</td>
							<td>${frappe.utils.escape_html(n.posting_date || "")}</td>
							<td>${frappe.utils.escape_html(n.customer_name || n.customer || "")}${n.ve_ne_cliente_telefono ? `<div class="small text-muted">${frappe.utils.escape_html(n.ve_ne_cliente_telefono)}</div>` : ""}</td>
							<td>${frappe.utils.escape_html(n.seller_name || n.seller_user || "")}</td>
							<td class="small">${itemsText}${moreItems}${shipInfo}${globalDiscBadge}${noteDiscountBadge}</td>
							<td class="text-right font-weight-bold">${amountCellHtml}</td>
							<td>${commissionCellHtml}</td>
							<td><span class="cima-ne-badge ${badgeClass}">${frappe.utils.escape_html(n.ve_ne_estado)}</span></td>
							<td>${resolutionHtml}</td>
							<td>${actionsHtml}</td>
						</tr>
					`;
				})
				.join("")
		);
	}

	formatBs(amount) {
		return `Bs. ${Number(amount || 0).toLocaleString("es-VE", {
			minimumFractionDigits: 2,
			maximumFractionDigits: 2,
		})}`;
	}

	openPaidDialog(note) {
		const cfg = this.data?.config || {};
		const fx = cfg.exchange_rate || {};
		const fxRate = Number(fx.adjusted_rate || fx.bcv_rate || 0);
		const ivaRate = Number(cfg.iva_rate || 16);
		const igtfRate = Number(cfg.igtf_rate || 3);
		const methods = cfg.payment_methods || ["Contado USD", "Pago Móvil / Bs", "Cashea", "Punto de Venta"];
		const baseAmount = Number(note.net_total || note.amount || 0);
		const hasExistingInvoice = Boolean(note.ve_ne_factura);
		const alreadyPaid = Number(note.paid_amount || 0);
		const alreadyPaidBs = Number(note.paid_bs || 0);
		const existingTotal = Number(note.total_to_pay || baseAmount);
		const existingRemaining = hasExistingInvoice
			? Math.max(Number((existingTotal - alreadyPaid).toFixed(2)), 0)
			: baseAmount;
		const history = Array.isArray(note.payment_history) ? note.payment_history : [];

		const historyBanner = history.length
			? `<div class="mt-2 p-2 small" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;">
				<div><strong>Pagos anteriores:</strong> $${alreadyPaid.toFixed(2)}${alreadyPaidBs > 0 ? ` (${this.formatBs(alreadyPaidBs)})` : ""} de $${existingTotal.toFixed(2)} · <strong>Saldo pendiente: $${existingRemaining.toFixed(2)}</strong></div>
				${history
					.map(
						(h, idx) => {
							const proof = h.screenshot_url
								? ` · <a href="${encodeURI(h.screenshot_url)}" target="_blank" rel="noopener">📎 Ver captura</a>`
								: "";
							const hBs = Number(h.amount_bs || 0) > 0 ? ` (${this.formatBs(h.amount_bs)})` : "";
							return `<div class="text-muted">• Abono #${idx + 1}: $${Number(h.amount || 0).toFixed(2)}${hBs} (${frappe.utils.escape_html(h.method || "")}${h.reference ? ` · Ref: ${frappe.utils.escape_html(h.reference)}` : ""}${proof}) — ${frappe.utils.escape_html((h.paid_at || "").slice(0, 16))}</div>`;
						}
					)
					.join("")}
			</div>`
			: "";

		const d = new frappe.ui.Dialog({
			title: `Registrar Pago — ${note.name}`,
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "client_info",
					options: `<div class="mb-2"><strong>Cliente:</strong> ${frappe.utils.escape_html(note.customer_name || note.customer)} · <strong>Base:</strong> $${baseAmount.toFixed(2)}${historyBanner}</div>`,
				},
				{
					label: "Método de Pago",
					fieldname: "payment_method",
					fieldtype: "Select",
					options: methods.join("\n"),
					default: note.ve_ne_metodo_pago && methods.includes(note.ve_ne_metodo_pago) ? note.ve_ne_metodo_pago : methods[0],
					reqd: 1,
				},
				{
					label: `Aplica IVA (${ivaRate}%)`,
					fieldname: "apply_iva",
					fieldtype: "Check",
					default: hasExistingInvoice ? (note.ve_ne_aplica_iva ? 1 : 0) : 1,
					read_only: hasExistingInvoice ? 1 : 0,
				},
				{
					label: `Aplica IGTF (${igtfRate}% Divisas)`,
					fieldname: "apply_igtf",
					fieldtype: "Check",
					default: hasExistingInvoice ? (note.ve_ne_aplica_igtf ? 1 : 0) : 0,
					read_only: hasExistingInvoice ? 1 : 0,
				},
				{
					label: "Monto que pagó ($)",
					fieldname: "paid_amount",
					fieldtype: "Float",
					reqd: 1,
					default: hasExistingInvoice ? existingRemaining : Number((baseAmount * (1 + ivaRate / 100)).toFixed(2)),
				},
				{
					label: "Número de Referencia",
					fieldname: "reference",
					fieldtype: "Data",
					default: note.ve_ne_referencia_pago || "",
					description: "Número de referencia o confirmación del pago (no aplica para efectivo).",
				},
				{
					fieldtype: "HTML",
					fieldname: "screenshot_box",
					options: `
						<div class="form-group" id="ne-screenshot-group">
							<label class="control-label small">Captura de Pantalla / Comprobante</label>
							<input type="file" id="ne-payment-screenshot" class="form-control input-sm" accept="image/*" />
							<div id="ne-screenshot-preview" class="small text-muted mt-1"></div>
						</div>
					`,
				},
				{
					fieldtype: "HTML",
					fieldname: "totals_preview",
					options: "",
				},
			],
			primary_action_label: "Registrar Pago",
			primary_action: async (values) => {
				const payAmt = Number(values.paid_amount);
				if (isNaN(payAmt) || payAmt <= 0) {
					frappe.msgprint("Ingresa un monto válido mayor que 0.");
					return;
				}
				const isCash = isCashMethod(values.payment_method);
				let screenshotUrl = !isCash ? (note.ve_ne_comprobante_url || "") : "";
				if (!isCash) {
					const fileInput = d.$wrapper.find("#ne-payment-screenshot")[0];
					const file = fileInput && fileInput.files && fileInput.files[0];
					if (file) {
						try {
							const b64 = await new Promise((resolve, reject) => {
								const reader = new FileReader();
								reader.onload = () => resolve(String(reader.result || ""));
								reader.onerror = () => reject(new Error("read_error"));
								reader.readAsDataURL(file);
							});
							const up = await frappe.call({
								method: "cima_ve.api.delivery_notes.upload_delivery_note_payment_proof",
								args: {
									delivery_note: note.name,
									file_name: file.name,
									file_data_base64: b64,
								},
							});
							if (!up || !up.message || !up.message.file_url) {
								frappe.msgprint("No se pudo subir la captura de pantalla. Intenta nuevamente.");
								return;
							}
							screenshotUrl = up.message.file_url;
						} catch (err) {
							frappe.msgprint("Error al subir la captura de pantalla.");
							return;
						}
					}
				}
				frappe.call({
					method: "cima_ve.api.delivery_notes.mark_delivery_note_paid",
					args: {
						delivery_note: note.name,
						payment_method: values.payment_method,
						apply_iva: values.apply_iva ? 1 : 0,
						apply_igtf: values.apply_igtf ? 1 : 0,
						reference: isCash ? "" : values.reference || "",
						paid_amount: payAmt,
						screenshot_url: screenshotUrl,
					},
					freeze: true,
					freeze_message: "Registrando pago...",
					callback: (r) => {
						if (r.message && r.message.ok) {
							d.hide();
							const isDone = r.message.ve_ne_estado === "Pagada";
							frappe.show_alert({
								message: isDone
									? `Nota ${note.name} PAGADA en su totalidad ($${Number(r.message.paid_total).toFixed(2)})`
									: `Abono de $${Number(r.message.paid_now).toFixed(2)} registrado en ${note.name}. Resta: $${Number(r.message.remaining_amount).toFixed(2)}`,
								indicator: isDone ? "green" : "blue",
							});
							this.loadNotes();
						}
					},
				});
			},
		});

		const isCashMethod = (method) => {
			const lower = String(method || "").trim().toLowerCase();
			return lower.includes("efectivo") || /\bcash\b/.test(lower);
		};

		const toggleProofFields = () => {
			const method = d.get_value("payment_method");
			const cash = isCashMethod(method);
			d.set_df_property("reference", "hidden", cash ? 1 : 0);
			d.$wrapper.find("#ne-screenshot-group").toggle(!cash);
		};

		let userEditedAmount = hasExistingInvoice;
		const computeTargetTotal = () => {
			if (hasExistingInvoice) {
				return { iva: 0, igtf: 0, total: existingTotal, remainingBefore: existingRemaining };
			}
			const applyIva = !!d.get_value("apply_iva");
			const applyIgtf = !!d.get_value("apply_igtf");
			const iva = Number((applyIva ? baseAmount * (ivaRate / 100) : 0).toFixed(2));
			const subWithIva = baseAmount + iva;
			const igtf = Number((applyIgtf ? subWithIva * (igtfRate / 100) : 0).toFixed(2));
			const total = Number((subWithIva + igtf).toFixed(2));
			return { iva, igtf, total, remainingBefore: total };
		};

		const updatePreview = (syncAmount = false) => {
			const calc = computeTargetTotal();
			if (syncAmount && !userEditedAmount) {
				d.set_value("paid_amount", calc.remainingBefore);
			}
			const rawPay = parseFloat(d.get_value("paid_amount"));
			const payAmt = isNaN(rawPay) ? 0 : rawPay;
			const remainingAfter = Math.max(Number((calc.remainingBefore - payAmt).toFixed(2)), 0);
			const invalidAmt = payAmt <= 0 || payAmt > calc.remainingBefore + 0.01;
			const nextStateLabel = invalidAmt
				? `<span class="text-danger">Monto inválido (máximo $${calc.remainingBefore.toFixed(2)})</span>`
				: remainingAfter <= 0.01
				? `<span style="color:#15803d;font-weight:700;">Quedará PAGADA (saldrá de pendientes)</span>`
				: `<span style="color:#1e40af;font-weight:700;">Quedará PAGO PARCIAL (seguirá visible hasta pagar $${remainingAfter.toFixed(2)} restantes)</span>`;

			const remBeforeBs = fxRate > 0 ? ` <span class="text-primary">(${this.formatBs(calc.remainingBefore * fxRate)})</span>` : "";
			const payAmtBs = fxRate > 0 ? ` <span class="text-primary">(${this.formatBs(payAmt * fxRate)})</span>` : "";
			const remAfterBs = fxRate > 0 && remainingAfter > 0 ? ` (${this.formatBs(remainingAfter * fxRate)})` : "";
			const rateNote = fxRate > 0
				? `<div class="small text-muted mt-1">Tasa actual: <strong>Bs. ${fxRate.toFixed(2)} / USD</strong> · Al registrar el pago se guardará el monto en Bs como referencia histórica.</div>`
				: "";

			d.fields_dict.totals_preview.$wrapper.html(`
				<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;margin-top:6px;">
					${hasExistingInvoice ? `<div>Total Facturado: <strong>$${calc.total.toFixed(2)}</strong> · Ya Pagado: <strong>$${alreadyPaid.toFixed(2)}${alreadyPaidBs > 0 ? ` (${this.formatBs(alreadyPaidBs)})` : ""}</strong></div>` : `<div>Base: <strong>$${baseAmount.toFixed(2)}</strong> · IVA: <strong>$${calc.iva.toFixed(2)}</strong> · IGTF: <strong>$${calc.igtf.toFixed(2)}</strong></div>`}
					<div>Saldo pendiente actual: <strong>$${calc.remainingBefore.toFixed(2)}</strong>${remBeforeBs}</div>
					<div>Este pago: <strong>$${payAmt.toFixed(2)}</strong>${payAmtBs} · Saldo restante: <strong>$${remainingAfter.toFixed(2)}</strong>${remAfterBs}</div>
					${rateNote}
					<div class="mt-1 small">${nextStateLabel}</div>
				</div>
			`);
		};

		if (!hasExistingInvoice) {
			d.fields_dict.apply_iva.$input.on("change", () => updatePreview(true));
			d.fields_dict.apply_igtf.$input.on("change", () => updatePreview(true));
		}
		d.fields_dict.payment_method.$input.on("change", () => toggleProofFields());
		d.fields_dict.paid_amount.$input.on("input change", () => {
			userEditedAmount = true;
			updatePreview(false);
		});
		d.$wrapper.on("change", "#ne-payment-screenshot", (e) => {
			const file = e.target.files && e.target.files[0];
			d.$wrapper.find("#ne-screenshot-preview").text(file ? `Archivo seleccionado: ${file.name}` : "");
		});
		d.show();
		toggleProofFields();
		updatePreview(!hasExistingInvoice);
		setTimeout(() => d.fields_dict.paid_amount.$input.focus().select(), 80);
	}

	openCancelDialog(note) {
		const d = new frappe.ui.Dialog({
			title: `Cancelar Nota de Entrega — ${note.name}`,
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "warn",
					options: `<p>Al cancelar <strong>${frappe.utils.escape_html(note.name)}</strong>, todos los productos serán devueltos al inventario automáticamente.</p>`,
				},
				{
					label: "Motivo de Cancelación (Opcional)",
					fieldname: "reason",
					fieldtype: "Small Text",
				},
			],
			primary_action_label: "Confirmar Cancelación",
			primary_action: (values) => {
				frappe.call({
					method: "cima_ve.api.delivery_notes.cancel_delivery_note",
					args: {
						delivery_note: note.name,
						reason: values.reason || "",
					},
					freeze: true,
					freeze_message: "Cancelando y restaurando inventario...",
					callback: (r) => {
						if (r.message && r.message.ok) {
							d.hide();
							frappe.show_alert({
								message: `Nota ${note.name} cancelada e inventario restaurado.`,
								indicator: "orange",
							});
							this.loadNotes();
						}
					},
				});
			},
		});
		d.show();
	}

	openCommissionCalculator() {
		frappe.call({
			method: "cima_ve.api.delivery_notes.calculate_seller_commissions",
			args: {
				...this.filters,
				persist_missing: 1,
			},
			freeze: true,
			freeze_message: "Calculando comisiones de vendedores...",
			callback: (r) => {
				if (!r.message) return;
				const res = r.message;
				const bySeller = res.by_seller || [];
				if (res.persisted_count > 0) {
					this.loadNotes();
				}

				const sellerFilterLabel = this.filters.seller
					? frappe.utils.escape_html(this.wrapper.find("#ne-filter-seller option:selected").text() || this.filters.seller)
					: "Todos los vendedores";
				const dateRangeLabel =
					this.filters.from_date || this.filters.to_date
						? `${this.filters.from_date || "..."} → ${this.filters.to_date || "..."}`
						: "Todas las fechas";
				const statusLabel = this.filters.status || "Todos los estados";

				const rowsHtml = bySeller.length
					? bySeller
							.map(
								(b) => `
						<tr>
							<td><strong>${frappe.utils.escape_html(b.seller_name || b.seller_user)}</strong><div class="text-muted small">${frappe.utils.escape_html(b.seller_user)}</div></td>
							<td class="text-center">${b.notes_count} <div class="text-muted small">(${b.paid_notes_count} pag. / ${b.pending_notes_count} pend.)</div></td>
							<td class="text-right">$${Number(b.sales_total || 0).toFixed(2)}</td>
							<td class="text-right">$${Number(b.cost_total || 0).toFixed(2)}</td>
							<td class="text-right">$${Number(b.margin_total || 0).toFixed(2)}</td>
							<td class="text-right text-success">$${Number(b.paid_commission || 0).toFixed(2)}</td>
							<td class="text-right text-warning">$${Number(b.pending_commission || 0).toFixed(2)}</td>
							<td class="text-right" style="font-weight:700;color:#5b21b6;">$${Number(b.commission_total || 0).toFixed(2)}</td>
						</tr>`
							)
							.join("")
					: `<tr><td colspan="8" class="text-center text-muted p-3">No hay notas activas con comisión para los filtros seleccionados.</td></tr>`;

				const d = new frappe.ui.Dialog({
					title: "Cálculo de Comisiones por Vendedor",
					size: "large",
					fields: [
						{
							fieldtype: "HTML",
							fieldname: "commission_report",
							options: `
								<div class="mb-3 p-2 small" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;">
									<strong>Filtros aplicados:</strong> ${sellerFilterLabel} · ${frappe.utils.escape_html(statusLabel)} · ${frappe.utils.escape_html(dateRangeLabel)}
									${res.persisted_count > 0 ? `<span class="label label-info ml-2">${res.persisted_count} notas históricas actualizadas</span>` : ""}
								</div>
								<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px;">
									<div style="background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px;">
										<div class="small text-muted">Ventas Netas</div>
										<div style="font-size:16px;font-weight:700;">$${Number(res.total_sales || 0).toFixed(2)}</div>
									</div>
									<div style="background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px;">
										<div class="small text-muted">Costo Productos</div>
										<div style="font-size:16px;font-weight:700;">$${Number(res.total_cost || 0).toFixed(2)}</div>
									</div>
									<div style="background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px;">
										<div class="small text-muted">Margen de Ganancia</div>
										<div style="font-size:16px;font-weight:700;color:#0f766e;">$${Number(res.total_margin || 0).toFixed(2)}</div>
									</div>
									<div style="background:#f5f3ff;border:1px solid #ddd6fe;border-radius:6px;padding:10px;">
										<div class="small" style="color:#5b21b6;">Total Comisión a Pagar</div>
										<div style="font-size:18px;font-weight:800;color:#5b21b6;">$${Number(res.total_commission || 0).toFixed(2)}</div>
										<div class="small text-muted">Pagadas: $${Number(res.paid_commission || 0).toFixed(2)} · Pend: $${Number(res.pending_commission || 0).toFixed(2)}</div>
									</div>
								</div>
								<div class="table-responsive">
									<table class="table table-bordered table-sm">
										<thead>
											<tr>
												<th>Vendedor</th>
												<th class="text-center">Notas</th>
												<th class="text-right">Ventas Netas</th>
												<th class="text-right">Costo</th>
												<th class="text-right">Margen</th>
												<th class="text-right">Com. Pagadas</th>
												<th class="text-right">Com. Pendientes</th>
												<th class="text-right">Total Comisión</th>
											</tr>
										</thead>
										<tbody>${rowsHtml}</tbody>
									</table>
								</div>
							`,
						},
					],
					primary_action_label: "Cerrar",
					primary_action: () => d.hide(),
				});
				d.show();
			},
		});
	}
}
