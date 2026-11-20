frappe.pages["clientes-consumo"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Consumo por Cliente",
		single_column: true,
	});
	new CimaClientConsumption(page, wrapper);
};

class CimaClientConsumption {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = $(wrapper);
		this.data = null;
		this.filters = {
			from_date: "",
			to_date: "",
			seller: "",
			search: "",
		};
		this.renderShell();
		this.bindEvents();
		this.loadData();
	}

	renderShell() {
		const html = `
			<div class="cima-cc-shell">
				<div class="cima-cc-hero">
					<div class="cima-hero-brand">
						<img src="/assets/cima_ve/images/cima-logo-blanco.png" alt="CIMA" class="cima-hero-logo" onerror="this.style.display='none'" />
						<div>
							<h2>Consumo por Cliente y Desglose por Vendedor</h2>
							<p>Visualiza cuánto ha consumido cada cliente en total y el detalle exacto de sus compras con cada vendedor.</p>
						</div>
					</div>
					<div class="d-flex" style="gap:8px;flex-wrap:wrap;align-items:center;">
						<button type="button" class="cima-btn-primary" data-action="export-csv">Exportar CSV</button>
						<button type="button" class="cima-btn-ghost" data-action="go-notes">Notas de Entrega</button>
						<button type="button" class="cima-btn-ghost" data-action="go-metrics">Métricas de Ventas</button>
						<button type="button" class="cima-btn-ghost" data-action="refresh">Actualizar</button>
					</div>
				</div>

				<div class="cima-cc-card">
					<div class="cima-cc-filters">
						<div>
							<label class="small text-muted">Desde</label>
							<input type="date" id="cc-from-date" class="form-control input-sm" />
						</div>
						<div>
							<label class="small text-muted">Hasta</label>
							<input type="date" id="cc-to-date" class="form-control input-sm" />
						</div>
						<div>
							<label class="small text-muted">Vendedor</label>
							<select id="cc-seller" class="form-control input-sm">
								<option value="">Todos los vendedores</option>
							</select>
						</div>
						<div>
							<label class="small text-muted">Buscar Cliente</label>
							<input type="text" id="cc-search" class="form-control input-sm" placeholder="Nombre o RIF..." />
						</div>
					</div>
				</div>

				<div class="cima-cc-kpis" id="cc-kpis"></div>

				<div class="cima-cc-card">
					<div class="table-responsive">
						<table class="table table-bordered table-hover table-sm">
							<thead>
								<tr>
									<th>Cliente</th>
									<th>RIF / Cédula</th>
									<th class="text-right">Facturas</th>
									<th class="text-right">Total Consumido</th>
									<th class="text-right">Notas Entrega Pend.</th>
									<th>Última Compra</th>
									<th>Compras por Vendedor</th>
									<th class="text-center">Detalle</th>
								</tr>
							</thead>
							<tbody id="cc-table-body">
								<tr><td colspan="8" class="text-center text-muted p-4">Cargando consumo de clientes...</td></tr>
							</tbody>
						</table>
					</div>
				</div>
			</div>
		`;
		this.wrapper.find(".layout-main-section").html(html);
	}

	bindEvents() {
		const root = this.wrapper;
		root.on("click", "[data-action='refresh']", () => this.loadData());
		root.on("click", "[data-action='go-notes']", () => frappe.set_route("notas-entrega"));
		root.on("click", "[data-action='go-metrics']", () => frappe.set_route("metricas-ventas"));
		root.on("click", "[data-action='export-csv']", () => this.exportCsv());

		root.on("change", "#cc-from-date, #cc-to-date, #cc-seller", () => {
			this.filters.from_date = root.find("#cc-from-date").val() || "";
			this.filters.to_date = root.find("#cc-to-date").val() || "";
			this.filters.seller = root.find("#cc-seller").val() || "";
			this.loadData();
		});

		let timer = null;
		root.on("input", "#cc-search", (e) => {
			clearTimeout(timer);
			timer = setTimeout(() => {
				this.filters.search = $(e.target).val() || "";
				this.loadData();
			}, 300);
		});

		root.on("click", "[data-client-detail]", (e) => {
			const custId = $(e.currentTarget).attr("data-client-detail");
			const client = (this.data?.clients || []).find((c) => c.customer === custId);
			if (client) this.openClientDialog(client);
		});
	}

	loadData() {
		frappe.call({
			method: "cima_ve.api.client_consumption.get_client_consumption",
			args: this.filters,
			callback: (r) => {
				if (!r.message) return;
				this.data = r.message;
				this.renderSellerOptions();
				this.renderKpis();
				this.renderTable();
			},
		});
	}

	renderSellerOptions() {
		const sel = this.wrapper.find("#cc-seller");
		const cur = this.filters.seller || "";
		const sellers = this.data?.filter_options?.sellers || [];
		const opts = [`<option value="">Todos los vendedores</option>`].concat(
			sellers.map((s) => `<option value="${frappe.utils.escape_html(s.user)}">${frappe.utils.escape_html(s.fullname)}</option>`)
		);
		sel.html(opts.join("")).val(cur);
	}

	renderKpis() {
		const s = this.data?.summary || {};
		const cur = s.currency || "USD";
		this.wrapper.find("#cc-kpis").html(`
			<div class="cima-cc-kpi">
				<div class="cima-cc-kpi-label">Clientes Activos</div>
				<div class="cima-cc-kpi-val">${s.total_customers || 0}</div>
			</div>
			<div class="cima-cc-kpi">
				<div class="cima-cc-kpi-label">Total Consumido (Facturado)</div>
				<div class="cima-cc-kpi-val" style="color:#15803d;">${cur} ${Number(s.total_consumed || 0).toFixed(2)}</div>
			</div>
			<div class="cima-cc-kpi">
				<div class="cima-cc-kpi-label">Notas Entrega Pendientes</div>
				<div class="cima-cc-kpi-val" style="color:#b45309;">${cur} ${Number(s.total_pending_dn || 0).toFixed(2)}</div>
			</div>
			<div class="cima-cc-kpi">
				<div class="cima-cc-kpi-label">Promedio por Cliente</div>
				<div class="cima-cc-kpi-val">${cur} ${Number(s.avg_per_customer || 0).toFixed(2)}</div>
			</div>
			<div class="cima-cc-kpi">
				<div class="cima-cc-kpi-label">Cliente Principal</div>
				<div class="cima-cc-kpi-val" style="font-size:16px;">${frappe.utils.escape_html(s.top_customer || "-")}</div>
			</div>
		`);
	}

	renderTable() {
		const clients = this.data?.clients || [];
		const tbody = this.wrapper.find("#cc-table-body");
		if (!clients.length) {
			tbody.html(`<tr><td colspan="8" class="text-center text-muted p-4">No hay consumo registrado para los filtros seleccionados.</td></tr>`);
			return;
		}

		tbody.html(
			clients
				.map((c) => {
					const sellerPills = (c.by_seller || [])
						.map((sb) => {
							const mainTxt = `${frappe.utils.escape_html(sb.seller_name)}: $${Number(sb.total_amount || 0).toFixed(2)} (${sb.share_pct}%)`;
							const pendTxt = sb.pending_dn_amount > 0 ? ` + $${Number(sb.pending_dn_amount).toFixed(2)} NE` : "";
							return `<span class="cima-seller-pill">${mainTxt}${pendTxt}</span>`;
						})
						.join("");

					return `
						<tr>
							<td><a href="/app/customer/${encodeURIComponent(c.customer)}"><strong>${frappe.utils.escape_html(c.customer_name)}</strong></a></td>
							<td>${frappe.utils.escape_html(c.rif_cedula || "-")}</td>
							<td class="text-right">${c.invoice_count || 0}</td>
							<td class="text-right font-weight-bold">$${Number(c.total_consumed || 0).toFixed(2)}</td>
							<td class="text-right">${c.pending_dn_count ? `$${Number(c.pending_dn_amount).toFixed(2)} (${c.pending_dn_count})` : "-"}</td>
							<td>${frappe.utils.escape_html(c.last_purchase_date || "-")}</td>
							<td>${sellerPills || "<span class='text-muted small'>-</span>"}</td>
							<td class="text-center">
								<button type="button" class="btn btn-xs btn-default" data-client-detail="${frappe.utils.escape_html(c.customer)}">
									Ver Desglose
								</button>
							</td>
						</tr>
					`;
				})
				.join("")
		);
	}

	openClientDialog(client) {
		const rows = (client.by_seller || [])
			.map(
				(sb) => `
				<tr>
					<td><strong>${frappe.utils.escape_html(sb.seller_name)}</strong><br><span class="text-muted small">${frappe.utils.escape_html(sb.seller_user)}</span></td>
					<td class="text-right">${sb.invoice_count}</td>
					<td class="text-right font-weight-bold">$${Number(sb.total_amount || 0).toFixed(2)}</td>
					<td class="text-right">${sb.share_pct}%</td>
					<td class="text-right">${sb.pending_dn_count ? `$${Number(sb.pending_dn_amount).toFixed(2)} (${sb.pending_dn_count})` : "-"}</td>
				</tr>`
			)
			.join("");

		const d = new frappe.ui.Dialog({
			title: `Desglose por Vendedor — ${client.customer_name}`,
			size: "large",
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "detail_html",
					options: `
						<div class="mb-3">
							<strong>RIF / Cédula:</strong> ${frappe.utils.escape_html(client.rif_cedula || "N/A")} ·
							<strong>Total Consumido:</strong> $${Number(client.total_consumed || 0).toFixed(2)} ·
							<strong>Pendiente en Notas de Entrega:</strong> $${Number(client.pending_dn_amount || 0).toFixed(2)}
						</div>
						<table class="table table-bordered table-sm">
							<thead>
								<tr>
									<th>Vendedor</th>
									<th class="text-right">Facturas</th>
									<th class="text-right">Monto Comprado</th>
									<th class="text-right">% del Cliente</th>
									<th class="text-right">Notas Entrega Pend.</th>
								</tr>
							</thead>
							<tbody>${rows || "<tr><td colspan='5' class='text-center'>Sin datos</td></tr>"}</tbody>
						</table>
					`,
				},
			],
		});
		d.show();
	}

	exportCsv() {
		const clients = this.data?.clients || [];
		if (!clients.length) {
			frappe.msgprint("No hay datos para exportar.");
			return;
		}
		const headers = ["Cliente", "RIF/Cedula", "Facturas", "Total Consumido", "Notas Entrega Pend.", "Vendedor", "Monto por Vendedor", "% Cliente"];
		const lines = [headers.join(",")];
		clients.forEach((c) => {
			(c.by_seller || [{}]).forEach((sb) => {
				lines.push(
					[
						`"${String(c.customer_name || "").replace(/"/g, '""')}"`,
						`"${String(c.rif_cedula || "").replace(/"/g, '""')}"`,
						c.invoice_count || 0,
						Number(c.total_consumed || 0).toFixed(2),
						Number(c.pending_dn_amount || 0).toFixed(2),
						`"${String(sb.seller_name || "").replace(/"/g, '""')}"`,
						Number(sb.total_amount || 0).toFixed(2),
						sb.share_pct || 0,
					].join(",")
				);
			});
		});
		const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = "consumo_clientes_por_vendedor.csv";
		a.click();
		URL.revokeObjectURL(url);
	}
}
