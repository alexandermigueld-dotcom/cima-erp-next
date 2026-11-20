frappe.pages["reportes-cima"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Reportes Ejecutivos — CIMA",
		single_column: true,
	});
	new CimaReportsPage(page, wrapper);
};

class CimaReportsPage {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = $(wrapper);
		this.data = null;
		this.renderShell();
		this.bindEvents();
		this.loadReport();
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
							<h2>Reporte Ejecutivo Gerencial</h2>
							<p>Ingresos vs Gastos, Detal / Mayor / Meta Ads, Vendedores, Métodos de Pago y Notas Pendientes.</p>
						</div>
					</div>
					<div class="cima-hero-actions cima-no-print">
						<button type="button" class="cima-btn-primary" id="rep-download-pdf">Descargar PDF</button>
						<button type="button" class="cima-btn-ghost" id="rep-print">Imprimir</button>
					</div>
				</div>

				<div class="cima-card mb-3 cima-no-print">
					<div class="d-flex flex-wrap align-items-end" style="gap: 12px;">
						<div>
							<label class="small font-weight-bold d-block">Desde</label>
							<input type="date" id="rep-from" class="form-control" value="${monthStart}" />
						</div>
						<div>
							<label class="small font-weight-bold d-block">Hasta</label>
							<input type="date" id="rep-to" class="form-control" value="${today}" />
						</div>
						<button type="button" class="cima-btn-primary" id="rep-refresh">Actualizar Reporte</button>
					</div>
				</div>

				<div class="cima-kpi-grid" id="rep-kpis"></div>

				<div class="row mb-3">
					<div class="col-md-6 mb-3">
						<div class="cima-card">
							<div class="cima-card-title"><span>Ingresos vs Gastos (Tendencia)</span></div>
							<div id="rep-chart-daily" style="min-height:240px;"></div>
						</div>
					</div>
					<div class="col-md-6 mb-3">
						<div class="cima-card">
							<div class="cima-card-title"><span>Ventas por Canal (Detal / Mayor / Meta Ads)</span></div>
							<div id="rep-chart-channels" style="min-height:240px;"></div>
						</div>
					</div>
				</div>

				<div class="row mb-3">
					<div class="col-md-6 mb-3">
						<div class="cima-card">
							<div class="cima-card-title"><span>Desglose por Canal de Venta</span></div>
							<div id="rep-table-channels"></div>
						</div>
					</div>
					<div class="col-md-6 mb-3">
						<div class="cima-card">
							<div class="cima-card-title"><span>Ventas por Método de Pago</span></div>
							<div id="rep-table-payments"></div>
						</div>
					</div>
				</div>

				<div class="cima-card mb-3">
					<div class="cima-card-title"><span>Hoja Resumen de Ventas por Vendedor</span></div>
					<div id="rep-table-sellers" class="table-responsive"></div>
				</div>

				<div class="cima-card mb-3">
					<div class="cima-card-title"><span>Notas de Entrega y Cuentas Pendientes por Pagar</span></div>
					<div id="rep-table-pending" class="table-responsive"></div>
				</div>

				<div class="row">
					<div class="col-md-6 mb-3">
						<div class="cima-card">
							<div class="cima-card-title"><span>Top 10 Productos Más Vendidos</span></div>
							<div id="rep-table-products"></div>
						</div>
					</div>
					<div class="col-md-6 mb-3">
						<div class="cima-card">
							<div class="cima-card-title"><span>Gastos por Grupo</span></div>
							<div id="rep-table-expenses"></div>
						</div>
					</div>
				</div>
			</div>
		`);
	}

	bindEvents() {
		const root = this.wrapper;
		root.on("click", "#rep-refresh", () => this.loadReport());
		root.on("click", "#rep-print", () => window.print());
		root.on("click", "#rep-download-pdf", () => {
			const from = root.find("#rep-from").val() || "";
			const to = root.find("#rep-to").val() || "";
			const url = `/api/method/cima_ve.api.reports.download_executive_report_pdf?date_from=${encodeURIComponent(from)}&date_to=${encodeURIComponent(to)}`;
			window.open(url, "_blank");
		});
	}

	loadReport() {
		frappe.call({
			method: "cima_ve.api.reports.get_executive_report",
			args: {
				date_from: this.wrapper.find("#rep-from").val() || "",
				date_to: this.wrapper.find("#rep-to").val() || "",
			},
			callback: (r) => {
				if (!r.message) return;
				this.data = r.message;
				this.renderAll();
			},
		});
	}

	renderAll() {
		const d = this.data;
		const k = d.kpis;
		this.wrapper.find("#rep-kpis").html(`
			<div class="cima-kpi-card emerald">
				<div class="cima-kpi-label">Ingresos (Ganado)</div>
				<div class="cima-kpi-value">$${Number(k.total_revenue).toFixed(2)}</div>
				<div class="cima-kpi-sub">${k.invoice_count} facturas · Ticket $${Number(k.avg_ticket).toFixed(2)}</div>
			</div>
			<div class="cima-kpi-card danger">
				<div class="cima-kpi-label">Gastos Totales</div>
				<div class="cima-kpi-value">$${Number(k.total_expenses).toFixed(2)}</div>
				<div class="cima-kpi-sub">Pendientes: $${Number(k.expenses_pending).toFixed(2)}</div>
			</div>
			<div class="cima-kpi-card">
				<div class="cima-kpi-label">Ganancia Neta</div>
				<div class="cima-kpi-value">$${Number(k.net_profit).toFixed(2)}</div>
				<div class="cima-kpi-sub">Margen: ${k.profit_margin_pct}% · IVA $${Number(k.total_iva).toFixed(2)}</div>
			</div>
			<div class="cima-kpi-card amber">
				<div class="cima-kpi-label">Notas / Cuentas Pendientes</div>
				<div class="cima-kpi-value">$${Number(k.pending_notes_total).toFixed(2)}</div>
				<div class="cima-kpi-sub">${k.pending_notes_count} documentos por cobrar</div>
			</div>
		`);

		this.renderCharts(d);
		this.renderTables(d);
	}

	renderCharts(d) {
		const dailyEl = this.wrapper.find("#rep-chart-daily")[0];
		const chanEl = this.wrapper.find("#rep-chart-channels")[0];
		if (typeof frappe.Chart !== "undefined") {
			const daily = d.daily_series || [];
			if (daily.length) {
				new frappe.Chart(dailyEl, {
					data: {
						labels: daily.map((x) => x.date),
						datasets: [
							{ name: "Ingresos", values: daily.map((x) => x.revenue) },
							{ name: "Gastos", values: daily.map((x) => x.expenses) },
						],
					},
					type: "bar",
					height: 230,
					colors: ["#06c686", "#1c2532"],
				});
			} else {
				$(dailyEl).html(`<div class="text-muted p-4 text-center">Sin movimientos en el período.</div>`);
			}

			const chans = (d.sales_by_channel || []).filter((c) => c.total > 0);
			if (chans.length) {
				new frappe.Chart(chanEl, {
					data: {
						labels: chans.map((c) => c.channel),
						datasets: [{ values: chans.map((c) => c.total) }],
					},
					type: "donut",
					height: 230,
					colors: ["#00ada4", "#1c2532", "#06c686", "#3d3d3d"],
				});
			} else {
				$(chanEl).html(`<div class="text-muted p-4 text-center">Sin ventas en el período.</div>`);
			}
		}
	}

	renderTables(d) {
		this.wrapper.find("#rep-table-channels").html(`
			<table class="table table-sm table-bordered">
				<thead><tr><th>Canal</th><th class="text-right">Facturas</th><th class="text-right">Total</th></tr></thead>
				<tbody>${(d.sales_by_channel || []).map((c) => `<tr><td><strong>${frappe.utils.escape_html(c.channel)}</strong></td><td class="text-right">${c.count}</td><td class="text-right"><strong>$${Number(c.total).toFixed(2)}</strong></td></tr>`).join("")}</tbody>
			</table>
		`);

		this.wrapper.find("#rep-table-payments").html(`
			<table class="table table-sm table-bordered">
				<thead><tr><th>Método de Pago</th><th class="text-right">Ops.</th><th class="text-right">Total</th></tr></thead>
				<tbody>${(d.sales_by_payment_method || []).map((p) => `<tr><td><strong>${frappe.utils.escape_html(p.payment_method)}</strong></td><td class="text-right">${p.count}</td><td class="text-right"><strong>$${Number(p.total).toFixed(2)}</strong></td></tr>`).join("") || `<tr><td colspan="3" class="text-muted text-center">Sin datos</td></tr>`}</tbody>
			</table>
		`);

		this.wrapper.find("#rep-table-sellers").html(`
			<table class="table table-sm table-bordered">
				<thead><tr><th>Vendedor</th><th class="text-right">Facturas</th><th class="text-right">Detal</th><th class="text-right">Mayor</th><th class="text-right">Meta Ads</th><th class="text-right">Ticket Prom.</th><th class="text-right">Total (%)</th></tr></thead>
				<tbody>${(d.sellers_summary || []).map((s) => `<tr><td><strong>${frappe.utils.escape_html(s.seller)}</strong></td><td class="text-right">${s.invoice_count}</td><td class="text-right">$${Number(s.detal_sales).toFixed(2)}</td><td class="text-right">$${Number(s.mayor_sales).toFixed(2)}</td><td class="text-right">$${Number(s.meta_ads_sales).toFixed(2)}</td><td class="text-right">$${Number(s.avg_ticket).toFixed(2)}</td><td class="text-right"><strong>$${Number(s.total_sales).toFixed(2)}</strong> (${s.share_pct}%)</td></tr>`).join("") || `<tr><td colspan="7" class="text-muted text-center">Sin ventas registradas</td></tr>`}</tbody>
			</table>
		`);

		this.wrapper.find("#rep-table-pending").html(`
			<table class="table table-sm table-bordered">
				<thead><tr><th>Tipo</th><th>Documento</th><th>Cliente</th><th>Fecha</th><th class="text-right">Total</th><th class="text-right">Pendiente</th></tr></thead>
				<tbody>${(d.pending_delivery_notes || []).map((n) => `<tr><td><span class="cima-badge cima-badge-amber">${frappe.utils.escape_html(n.doctype)}</span></td><td>${frappe.utils.escape_html(n.name)}</td><td>${frappe.utils.escape_html(n.customer)}</td><td>${frappe.utils.escape_html(n.date)}</td><td class="text-right">$${Number(n.grand_total).toFixed(2)}</td><td class="text-right text-danger"><strong>$${Number(n.pending_amount).toFixed(2)}</strong></td></tr>`).join("") || `<tr><td colspan="6" class="text-muted text-center">Sin notas o facturas pendientes</td></tr>`}</tbody>
			</table>
		`);

		this.wrapper.find("#rep-table-products").html(`
			<table class="table table-sm table-bordered">
				<thead><tr><th>Producto</th><th class="text-right">Uds.</th><th class="text-right">Ingresos</th></tr></thead>
				<tbody>${(d.top_products || []).map((p) => `<tr><td>${frappe.utils.escape_html(p.item_name)}</td><td class="text-right">${p.qty}</td><td class="text-right"><strong>$${Number(p.revenue).toFixed(2)}</strong></td></tr>`).join("") || `<tr><td colspan="3" class="text-muted text-center">Sin datos</td></tr>`}</tbody>
			</table>
		`);

		this.wrapper.find("#rep-table-expenses").html(`
			<table class="table table-sm table-bordered">
				<thead><tr><th>Grupo de Gasto</th><th class="text-right">Registros</th><th class="text-right">Total</th></tr></thead>
				<tbody>${(d.expenses_by_group || []).map((e) => `<tr><td>${frappe.utils.escape_html(e.group)}</td><td class="text-right">${e.count}</td><td class="text-right"><strong>$${Number(e.total).toFixed(2)}</strong></td></tr>`).join("") || `<tr><td colspan="3" class="text-muted text-center">Sin gastos registrados</td></tr>`}</tbody>
			</table>
		`);
	}
}
