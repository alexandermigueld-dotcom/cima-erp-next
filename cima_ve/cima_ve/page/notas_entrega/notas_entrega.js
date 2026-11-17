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
								<option value="Pago Parcial">Pago Parcial</option>
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
					const noteDiscountBadge = n.has_discount
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
									(h, idx) =>
										`<div class="text-muted" style="font-size:11px;">#${idx + 1}: <strong>$${Number(h.amount || 0).toFixed(2)}</strong> · ${frappe.utils.escape_html(h.method || "")}${h.reference ? ` (${frappe.utils.escape_html(h.reference)})` : ""} · ${frappe.utils.escape_html((h.paid_at || "").slice(0, 16))}</div>`
								)
								.join("") +
						  `</div>`
						: "";

					let resolutionHtml = `<span class="text-muted small">Sin procesar</span>`;
					if (n.ve_ne_estado === "Pagada" || n.ve_ne_estado === "Pago Parcial") {
						const taxTags = [
							n.ve_ne_aplica_iva ? "IVA" : "Sin IVA",
							n.ve_ne_aplica_igtf ? "IGTF" : "",
						]
							.filter(Boolean)
							.join(" + ");
						const balanceLine =
							n.ve_ne_estado === "Pago Parcial"
								? `<div style="color:#1e40af;font-weight:700;">Pagado: $${Number(n.paid_amount || 0).toFixed(2)} · Resta: $${Number(n.remaining_amount || 0).toFixed(2)}</div>`
								: `<div>Total pagado: <strong>$${Number(n.paid_amount || n.total_to_pay || n.amount || 0).toFixed(2)}</strong></div>`;
						resolutionHtml = `
							<div class="small">
								${balanceLine}
								<strong>${frappe.utils.escape_html(n.ve_ne_metodo_pago || "-")}</strong> (${frappe.utils.escape_html(taxTags)})<br>
								<span class="text-muted">${frappe.utils.escape_html(n.ve_ne_fecha_resolucion || "")}</span><br>
								<span class="text-muted">Por: ${frappe.utils.escape_html(n.ve_ne_usuario_resolucion || "")}</span>
								${n.ve_ne_factura ? `<br><a href="/app/sales-invoice/${encodeURIComponent(n.ve_ne_factura)}">${frappe.utils.escape_html(n.ve_ne_factura)}</a>` : ""}
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
					const canCancel = n.ve_ne_estado === "Pendiente" && Number(n.paid_amount || 0) <= 0 && !n.ve_ne_factura;
					const actionsHtml = isPayable
						? `<div class="cima-ne-actions">
							<button type="button" class="btn btn-xs btn-success" data-pay-dn="${frappe.utils.escape_html(n.name)}">${n.ve_ne_estado === "Pago Parcial" ? "Abonar / Pagado" : "Pagado"}</button>
							${canCancel ? `<button type="button" class="btn btn-xs btn-danger" data-cancel-dn="${frappe.utils.escape_html(n.name)}">Cancelar</button>` : ""}
						</div>`
						: `<a class="btn btn-xs btn-default" href="/app/delivery-note/${encodeURIComponent(n.name)}">Ver</a>`;

					const amountCellHtml =
						n.ve_ne_estado === "Pago Parcial"
							? `<div>$${Number(n.total_to_pay || n.amount || 0).toFixed(2)}</div><div class="small text-primary">Resta: $${Number(n.remaining_amount || 0).toFixed(2)}</div>`
							: `$${Number(n.total_to_pay || n.amount || 0).toFixed(2)}`;

					return `
						<tr>
							<td><a href="/app/delivery-note/${encodeURIComponent(n.name)}"><strong>${frappe.utils.escape_html(n.name)}</strong></a></td>
							<td>${frappe.utils.escape_html(n.posting_date || "")}</td>
							<td>${frappe.utils.escape_html(n.customer_name || n.customer || "")}</td>
							<td>${frappe.utils.escape_html(n.seller_name || n.seller_user || "")}</td>
							<td class="small">${itemsText}${moreItems}${noteDiscountBadge}</td>
							<td class="text-right font-weight-bold">${amountCellHtml}</td>
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
		const hasExistingInvoice = Boolean(note.ve_ne_factura);
		const alreadyPaid = Number(note.paid_amount || 0);
		const existingTotal = Number(note.total_to_pay || baseAmount);
		const existingRemaining = hasExistingInvoice
			? Math.max(Number((existingTotal - alreadyPaid).toFixed(2)), 0)
			: baseAmount;
		const history = Array.isArray(note.payment_history) ? note.payment_history : [];

		const historyBanner = history.length
			? `<div class="mt-2 p-2 small" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;">
				<div><strong>Pagos anteriores:</strong> $${alreadyPaid.toFixed(2)} de $${existingTotal.toFixed(2)} · <strong>Saldo pendiente: $${existingRemaining.toFixed(2)}</strong></div>
				${history
					.map(
						(h, idx) =>
							`<div class="text-muted">• Abono #${idx + 1}: $${Number(h.amount || 0).toFixed(2)} (${frappe.utils.escape_html(h.method || "")}${h.reference ? ` · Ref: ${frappe.utils.escape_html(h.reference)}` : ""}) — ${frappe.utils.escape_html((h.paid_at || "").slice(0, 16))}</div>`
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
			primary_action_label: "Registrar Pago",
			primary_action: (values) => {
				const payAmt = Number(values.paid_amount);
				if (isNaN(payAmt) || payAmt <= 0) {
					frappe.msgprint("Ingresa un monto válido mayor que 0.");
					return;
				}
				frappe.call({
					method: "cima_ve.api.delivery_notes.mark_delivery_note_paid",
					args: {
						delivery_note: note.name,
						payment_method: values.payment_method,
						apply_iva: values.apply_iva ? 1 : 0,
						apply_igtf: values.apply_igtf ? 1 : 0,
						reference: values.reference || "",
						paid_amount: payAmt,
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

			d.fields_dict.totals_preview.$wrapper.html(`
				<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;margin-top:6px;">
					${hasExistingInvoice ? `<div>Total Facturado: <strong>$${calc.total.toFixed(2)}</strong> · Ya Pagado: <strong>$${alreadyPaid.toFixed(2)}</strong></div>` : `<div>Base: <strong>$${baseAmount.toFixed(2)}</strong> · IVA: <strong>$${calc.iva.toFixed(2)}</strong> · IGTF: <strong>$${calc.igtf.toFixed(2)}</strong></div>`}
					<div>Saldo pendiente actual: <strong>$${calc.remainingBefore.toFixed(2)}</strong></div>
					<div>Este pago: <strong>$${payAmt.toFixed(2)}</strong> · Saldo restante: <strong>$${remainingAfter.toFixed(2)}</strong></div>
					<div class="mt-1 small">${nextStateLabel}</div>
				</div>
			`);
		};

		if (!hasExistingInvoice) {
			d.fields_dict.apply_iva.$input.on("change", () => updatePreview(true));
			d.fields_dict.apply_igtf.$input.on("change", () => updatePreview(true));
		}
		d.fields_dict.paid_amount.$input.on("input change", () => {
			userEditedAmount = true;
			updatePreview(false);
		});
		d.show();
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
}
