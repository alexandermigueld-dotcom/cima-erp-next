frappe.pages["gastos-cima"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Gastos y Facturas",
		single_column: true,
	});
	new CimaBillsPage(page, wrapper);
};

class CimaBillsPage {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = $(wrapper);
		this.state = {
			categories: [],
			groups: [],
			bills: [],
			summary: {},
		};
		this.renderShell();
		this.bindEvents();
		this.loadAll();
	}

	renderShell() {
		const today = frappe.datetime.get_today();
		const monthStart = frappe.datetime.month_start();
		this.wrapper.find(".layout-main-section").html(`
			<div class="cima-shell">
				<div class="cima-hero">
					<div class="cima-hero-brand">
						<img src="/assets/cima_ve/images/cima-logo-blanco.png" alt="CIMA" class="cima-hero-logo" />
						<div class="cima-hero-title">
							<h2>Módulo de Gastos y Facturas</h2>
							<p>Crea tipos de gasto como ítems de inventario, clasifícalos por grupo y registra pagos.</p>
						</div>
					</div>
					<div class="cima-hero-actions">
						<button type="button" class="cima-btn-primary" data-action="new-bill">+ Cargar Gasto / Factura</button>
						<button type="button" class="cima-btn-ghost" data-action="new-category">+ Nuevo Tipo de Gasto</button>
					</div>
				</div>

				<div class="cima-kpi-grid" id="bills-kpis"></div>

				<div class="row">
					<div class="col-md-8 mb-3">
						<div class="cima-card">
							<div class="cima-card-title">
								<span>Listado de Gastos Registrados</span>
							</div>
							<div class="d-flex flex-wrap mb-3" style="gap: 10px;">
								<input type="date" id="bills-from" class="form-control" style="max-width:160px;" value="${monthStart}" />
								<input type="date" id="bills-to" class="form-control" style="max-width:160px;" value="${today}" />
								<select id="bills-filter-group" class="form-control" style="max-width:200px;">
									<option value="">Todos los grupos</option>
								</select>
								<select id="bills-filter-status" class="form-control" style="max-width:150px;">
									<option value="">Todos los estados</option>
									<option value="Pagada">Pagada</option>
									<option value="Pendiente">Pendiente</option>
									<option value="Anulada">Anulada</option>
								</select>
								<button type="button" class="btn btn-default" id="bills-refresh-btn">Filtrar</button>
							</div>
							<div class="table-responsive">
								<table class="table table-bordered table-hover">
									<thead>
										<tr>
											<th>Fecha</th>
											<th>Concepto</th>
											<th>Tipo (Ítem)</th>
											<th>Grupo</th>
											<th>Estado</th>
											<th class="text-right">Monto</th>
											<th class="text-center">Acción</th>
										</tr>
									</thead>
									<tbody id="bills-table-body"></tbody>
								</table>
							</div>
						</div>
					</div>

					<div class="col-md-4 mb-3">
						<div class="cima-card mb-3">
							<div class="cima-card-title"><span>Resumen por Grupo</span></div>
							<div id="bills-group-summary"></div>
						</div>
						<div class="cima-card">
							<div class="cima-card-title">
								<span>Tipos de Gasto (Catálogo)</span>
								<button type="button" class="btn btn-xs btn-default" data-action="new-category">+ Agregar</button>
							</div>
							<div id="bills-categories-list"></div>
						</div>
					</div>
				</div>
			</div>
		`);
	}

	bindEvents() {
		const root = this.wrapper;
		root.on("click", "[data-action='new-category']", () => this.openCategoryDialog());
		root.on("click", "[data-action='new-bill']", () => this.openBillDialog());
		root.on("click", "#bills-refresh-btn", () => this.loadBills());
		root.on("click", "[data-mark-paid]", (e) => {
			const name = $(e.currentTarget).attr("data-mark-paid");
			frappe.call({
				method: "cima_ve.api.bills.update_bill_status",
				args: { bill_name: name, status: "Pagada" },
				callback: () => this.loadBills(),
			});
		});
	}

	loadAll() {
		this.loadCategories(() => this.loadBills());
	}

	loadCategories(cb) {
		frappe.call({
			method: "cima_ve.api.bills.get_bill_categories",
			callback: (r) => {
				if (!r.message) return;
				this.state.categories = r.message.categories || [];
				this.state.groups = r.message.groups || [];
				const grpOpts = `<option value="">Todos los grupos</option>` +
					this.state.groups.map((g) => `<option value="${frappe.utils.escape_html(g)}">${frappe.utils.escape_html(g)}</option>`).join("");
				this.wrapper.find("#bills-filter-group").html(grpOpts);
				this.renderCategories();
				if (cb) cb();
			},
		});
	}

	loadBills() {
		frappe.call({
			method: "cima_ve.api.bills.list_bills",
			args: {
				date_from: this.wrapper.find("#bills-from").val() || "",
				date_to: this.wrapper.find("#bills-to").val() || "",
				group: this.wrapper.find("#bills-filter-group").val() || "",
				status: this.wrapper.find("#bills-filter-status").val() || "",
			},
			callback: (r) => {
				if (!r.message) return;
				this.state.bills = r.message.bills || [];
				this.state.summary = r.message.summary || {};
				this.renderBills();
			},
		});
	}

	renderCategories() {
		const box = this.wrapper.find("#bills-categories-list");
		if (!this.state.categories.length) {
			box.html(`<div class="text-muted small">Crea tu primer tipo de gasto (ej: Alquiler, Meta Ads, Flete China).</div>`);
			return;
		}
		box.html(
			this.state.categories
				.map(
					(c) => `
					<div class="d-flex justify-content-between align-items-center py-2 border-bottom">
						<div><strong>${frappe.utils.escape_html(c.category_name)}</strong></div>
						<span class="cima-badge cima-badge-teal">${frappe.utils.escape_html(c.parent_group)}</span>
					</div>`
				)
				.join("")
		);
	}

	renderBills() {
		const s = this.state.summary || {};
		this.wrapper.find("#bills-kpis").html(`
			<div class="cima-kpi-card dark">
				<div class="cima-kpi-label">Total Gastos</div>
				<div class="cima-kpi-value">$${Number(s.total_spent || 0).toFixed(2)}</div>
				<div class="cima-kpi-sub">${s.total_count || 0} registros</div>
			</div>
			<div class="cima-kpi-card emerald">
				<div class="cima-kpi-label">Pagados</div>
				<div class="cima-kpi-value">$${Number(s.total_paid || 0).toFixed(2)}</div>
			</div>
			<div class="cima-kpi-card amber">
				<div class="cima-kpi-label">Pendientes por Pagar</div>
				<div class="cima-kpi-value">$${Number(s.total_pending || 0).toFixed(2)}</div>
			</div>
		`);

		const grpBox = this.wrapper.find("#bills-group-summary");
		const groups = s.by_group || [];
		grpBox.html(
			groups.length
				? groups
						.map(
							(g) => `
							<div class="d-flex justify-content-between py-2 border-bottom">
								<span>${frappe.utils.escape_html(g.group)} (${g.count})</span>
								<strong>$${Number(g.total).toFixed(2)}</strong>
							</div>`
						)
						.join("")
				: `<div class="text-muted small">Sin datos en el período.</div>`
		);

		const tbody = this.wrapper.find("#bills-table-body");
		if (!this.state.bills.length) {
			tbody.html(`<tr><td colspan="7" class="text-center text-muted">No hay gastos registrados en este rango.</td></tr>`);
			return;
		}
		tbody.html(
			this.state.bills
				.map((b) => {
					const badgeClass =
						b.status === "Pagada" ? "cima-badge-green" : b.status === "Pendiente" ? "cima-badge-amber" : "cima-badge-red";
					const actionBtn =
						b.status === "Pendiente"
							? `<button type="button" class="btn btn-xs btn-success" data-mark-paid="${frappe.utils.escape_html(b.name)}">Marcar Pagada</button>`
							: "-";
					return `
						<tr>
							<td>${frappe.utils.escape_html(b.bill_date)}</td>
							<td><strong>${frappe.utils.escape_html(b.bill_title)}</strong><div class="small text-muted">${frappe.utils.escape_html(b.supplier_name || "")}</div></td>
							<td>${frappe.utils.escape_html(b.bill_category)}</td>
							<td><span class="cima-badge cima-badge-teal">${frappe.utils.escape_html(b.bill_group || "Otros")}</span></td>
							<td><span class="cima-badge ${badgeClass}">${frappe.utils.escape_html(b.status)}</span></td>
							<td class="text-right"><strong>${frappe.utils.escape_html(b.currency)} ${Number(b.amount).toFixed(2)}</strong></td>
							<td class="text-center">${actionBtn}</td>
						</tr>
					`;
				})
				.join("")
		);
	}

	openCategoryDialog() {
		const d = new frappe.ui.Dialog({
			title: "Nuevo Tipo de Gasto (Ítem de Gasto)",
			fields: [
				{ label: "Nombre del Tipo de Gasto", fieldname: "category_name", fieldtype: "Data", reqd: 1 },
				{
					label: "Grupo de Clasificación",
					fieldname: "parent_group",
					fieldtype: "Select",
					options: this.state.groups.join("\n"),
					default: "Operativos",
					reqd: 1,
				},
				{ label: "Descripción", fieldname: "description", fieldtype: "Small Text" },
			],
			primary_action_label: "Guardar Tipo",
			primary_action: (values) => {
				frappe.call({
					method: "cima_ve.api.bills.create_bill_category",
					args: values,
					callback: () => {
						d.hide();
						this.loadCategories();
						frappe.show_alert({ message: "Tipo de gasto creado", indicator: "green" });
					},
				});
			},
		});
		d.show();
	}

	openBillDialog() {
		if (!this.state.categories.length) {
			frappe.msgprint("Primero crea al menos un Tipo de Gasto (ej: Alquiler, Servicios, Flete).");
			return;
		}
		const d = new frappe.ui.Dialog({
			title: "Cargar Nuevo Gasto / Factura",
			fields: [
				{ label: "Concepto / Descripción", fieldname: "bill_title", fieldtype: "Data", reqd: 1 },
				{
					label: "Tipo de Gasto",
					fieldname: "bill_category",
					fieldtype: "Select",
					options: this.state.categories.map((c) => c.category_name).join("\n"),
					reqd: 1,
				},
				{ label: "Fecha", fieldname: "bill_date", fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ label: "Monto", fieldname: "amount", fieldtype: "Currency", reqd: 1 },
				{ label: "Moneda", fieldname: "currency", fieldtype: "Select", options: "USD\nVES", default: "USD" },
				{
					label: "Método de Pago",
					fieldname: "payment_method",
					fieldtype: "Select",
					options: "Contado USD\nPago Móvil / Bs\nTransferencia\nZelle\nCashea\nOtro",
					default: "Contado USD",
				},
				{ label: "Estado", fieldname: "status", fieldtype: "Select", options: "Pagada\nPendiente", default: "Pagada" },
				{ label: "Proveedor / Beneficiario", fieldname: "supplier_name", fieldtype: "Data" },
				{ label: "Nro. Referencia / Factura", fieldname: "reference_number", fieldtype: "Data" },
			],
			primary_action_label: "Registrar Gasto",
			primary_action: (values) => {
				frappe.call({
					method: "cima_ve.api.bills.create_bill",
					args: values,
					callback: () => {
						d.hide();
						this.loadBills();
						frappe.show_alert({ message: "Gasto registrado", indicator: "green" });
					},
				});
			},
		});
		d.show();
	}
}
