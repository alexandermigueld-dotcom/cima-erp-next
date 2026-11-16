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
						<h2>Control de Notas de Entrega — Cima Electronic</h2>
						<p>Seguimiento de despachos pendientes de pago: marca como Pagado (con método e impuestos) o Cancela para devolver el stock.</p>
					</div>
					<div class="d-flex" style="gap:8px;flex-wrap:wrap;">
						<button type="button" class="btn btn-sm btn-primary" data-action="go-pos">+ Nueva Nota de Entrega</button>
						<button type="button" class="btn btn-sm btn-default" data-action="go-clients">Clientes y Consumo</button>
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
								<option value="Pagada">Pagada</option>
								<option value="Cancelada">Cancelada</option>
							</select>
						</div>
						<div>
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
									<th>Estado</th>
									<th>Registro Pago / Cancelación</th>
									<th>Acciones</th>
								</tr>
							</thead>
							<tbody id="ne-table-body">
								<tr><td colspan="9" class="text-center text-muted p-4">Cargando notas de entrega...</td></tr>
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
				this.renderSellerFilter();
				this.renderKpis();
				this.renderTable();
			},
		});
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
			<div class="cima-ne-kpi">
				<div class="cima-ne-kpi-label">Total Notas</div>
				<div class="cima-ne-kpi-val">${s.total_count || 0}</div>
				<div class="cima-ne-kpi-sub">Historial completo</div>
			</div>
		`);
	}

	renderTable() {
		const notes = this.data?.notes || [];
		const tbody = this.wrapper.find("#ne-table-body");
		if (!notes.length) {
			tbody.html(`<tr><td colspan="9" class="text-center text-muted p-4">No hay Notas de Entrega para los filtros seleccionados.</td></tr>`);
			return;
		}

		tbody.html(
			notes
				.map((n) => {
					const itemsText = (n.items || [])
						.slice(0, 3)
						.map((it) => `${Number(it.qty)}x ${frappe.utils.escape_html(it.item_name || it.item_code)}`)
						.join("<br>");
					const moreItems = (n.items || []).length > 3 ? `<div class="text-muted small">+${n.items.length - 3} más</div>` : "";
					const badgeClass =
						n.ve_ne_estado === "Pagada"
							? "cima-ne-badge-pagada"
							: n.ve_ne_estado === "Cancelada"
							? "cima-ne-badge-cancelada"
							: "cima-ne-badge-pendiente";

					let resolutionHtml = `<span class="text-muted small">Sin procesar</span>`;
					if (n.ve_ne_estado === "Pagada") {
						const taxTags = [
							n.ve_ne_aplica_iva ? "IVA" : "Sin IVA",
							n.ve_ne_aplica_igtf ? "IGTF" : "",
						]
							.filter(Boolean)
							.join(" + ");
						resolutionHtml = `
							<div class="small">
								<strong>${frappe.utils.escape_html(n.ve_ne_metodo_pago || "-")}</strong> (${frappe.utils.escape_html(taxTags)})<br>
								<span class="text-muted">${frappe.utils.escape_html(n.ve_ne_fecha_resolucion || "")}</span><br>
								<span class="text-muted">Por: ${frappe.utils.escape_html(n.ve_ne_usuario_resolucion || "")}</span>
								${n.ve_ne_factura ? `<br><a href="/app/sales-invoice/${encodeURIComponent(n.ve_ne_factura)}">${frappe.utils.escape_html(n.ve_ne_factura)}</a>` : ""}
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

					const actionsHtml =
						n.ve_ne_estado === "Pendiente"
							? `<div class="cima-ne-actions">
								<button type="button" class="btn btn-xs btn-success" data-pay-dn="${frappe.utils.escape_html(n.name)}">Pagado</button>
								<button type="button" class="btn btn-xs btn-danger" data-cancel-dn="${frappe.utils.escape_html(n.name)}">Cancelar</button>
							</div>`
							: `<a class="btn btn-xs btn-default" href="/app/delivery-note/${encodeURIComponent(n.name)}">Ver</a>`;

					return `
						<tr>
							<td><a href="/app/delivery-note/${encodeURIComponent(n.name)}"><strong>${frappe.utils.escape_html(n.name)}</strong></a></td>
							<td>${frappe.utils.escape_html(n.posting_date || "")}</td>
							<td>${frappe.utils.escape_html(n.customer_name || n.customer || "")}</td>
							<td>${frappe.utils.escape_html(n.seller_name || n.seller_user || "")}</td>
							<td class="small">${itemsText}${moreItems}</td>
							<td class="text-right font-weight-bold">$${Number(n.amount || 0).toFixed(2)}</td>
							<td><span class="cima-ne-badge ${badgeClass}">${frappe.utils.escape_html(n.ve_ne_estado)}</span></td>
							<td>${resolutionHtml}</td>
							<td>${actionsHtml}</td>
						</tr>
					`;
				})
				.join("")
		);
	}

	openPaidDialog(note) {
		const cfg = this.data?.config || {};
		const ivaRate = Number(cfg.iva_rate || 16);
		const igtfRate = Number(cfg.igtf_rate || 3);
		const methods = cfg.payment_methods || ["Contado USD", "Pago Móvil / Bs", "Cashea", "Punto de Venta"];
		const baseAmount = Number(note.net_total || note.amount || 0);

		const d = new frappe.ui.Dialog({
			title: `Registrar Pago — ${note.name}`,
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "client_info",
					options: `<div class="mb-2"><strong>Cliente:</strong> ${frappe.utils.escape_html(note.customer_name || note.customer)} · <strong>Base:</strong> $${baseAmount.toFixed(2)}</div>`,
				},
				{
					label: "Método de Pago",
					fieldname: "payment_method",
					fieldtype: "Select",
					options: methods.join("\n"),
					default: methods[0],
					reqd: 1,
				},
				{
					label: `Aplica IVA (${ivaRate}%)`,
					fieldname: "apply_iva",
					fieldtype: "Check",
					default: 1,
				},
				{
					label: `Aplica IGTF (${igtfRate}% Divisas)`,
					fieldname: "apply_igtf",
					fieldtype: "Check",
					default: 0,
				},
				{
					label: "Referencia / Comprobante (Opcional)",
					fieldname: "reference",
					fieldtype: "Data",
				},
				{
					fieldtype: "HTML",
					fieldname: "totals_preview",
					options: "",
				},
			],
			primary_action_label: "Confirmar Pagado",
			primary_action: (values) => {
				frappe.call({
					method: "cima_ve.api.delivery_notes.mark_delivery_note_paid",
					args: {
						delivery_note: note.name,
						payment_method: values.payment_method,
						apply_iva: values.apply_iva ? 1 : 0,
						apply_igtf: values.apply_igtf ? 1 : 0,
						reference: values.reference || "",
					},
					freeze: true,
					freeze_message: "Registrando pago y factura...",
					callback: (r) => {
						if (r.message && r.message.ok) {
							d.hide();
							frappe.show_alert({
								message: `Nota ${note.name} marcada como PAGADA ($${Number(r.message.grand_total).toFixed(2)})`,
								indicator: "green",
							});
							this.loadNotes();
						}
					},
				});
			},
		});

		const updatePreview = () => {
			const applyIva = !!d.get_value("apply_iva");
			const applyIgtf = !!d.get_value("apply_igtf");
			const iva = applyIva ? baseAmount * (ivaRate / 100) : 0;
			const subWithIva = baseAmount + iva;
			const igtf = applyIgtf ? subWithIva * (igtfRate / 100) : 0;
			const total = subWithIva + igtf;
			d.fields_dict.totals_preview.$wrapper.html(`
				<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;margin-top:6px;">
					<div>Base: <strong>$${baseAmount.toFixed(2)}</strong></div>
					<div>IVA (${applyIva ? ivaRate : 0}%): <strong>$${iva.toFixed(2)}</strong></div>
					<div>IGTF (${applyIgtf ? igtfRate : 0}%): <strong>$${igtf.toFixed(2)}</strong></div>
					<div style="font-size:16px;margin-top:4px;color:#15803d;"><strong>Total a cobrar: $${total.toFixed(2)}</strong></div>
				</div>
			`);
		};

		d.fields_dict.apply_iva.$input.on("change", updatePreview);
		d.fields_dict.apply_igtf.$input.on("change", updatePreview);
		d.show();
		updatePreview();
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
}
