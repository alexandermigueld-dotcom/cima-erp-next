frappe.pages["metricas-ventas"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Métricas de Ventas por Vendedor",
		single_column: true,
	});

	new CimaSalesMetrics(page, wrapper);
};

class CimaSalesMetrics {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = $(wrapper);

		const today = frappe.datetime.get_today();
		const monthStart = frappe.datetime.month_start(today);

		this.state = {
			preset: "month",
			from_date: monthStart,
			to_date: today,
			user: "",
			sales_channel: "",
			company: "",
			data: null,
		};

		this.renderShell();
		this.bindEvents();
		this.loadMetrics();
	}

	renderShell() {
		const html = `
			<div class="cima-metrics-shell">
				<div class="cima-metrics-hero">
					<div class="cima-hero-brand">
						<img src="/assets/cima_ve/images/cima-logo-blanco.png" alt="CIMA" class="cima-hero-logo" onerror="this.style.display='none'" />
						<div>
							<h2>Métricas de Ventas — Total y por Usuario</h2>
							<p>Resumen ejecutivo, ranking de vendedores, canales de venta, facturación fiscal e historial.</p>
						</div>
					</div>
					<div class="cima-metrics-actions">
						<button type="button" class="cima-btn-primary" data-action="go-pos">
							+ Facturación Rápida
						</button>
						<button type="button" class="cima-metrics-btn-ghost" data-action="export-csv">
							Exportar CSV (Vendedores)
						</button>
						<button type="button" class="cima-metrics-btn-ghost" data-action="refresh">
							Actualizar
						</button>
					</div>
				</div>

				<div class="cima-metrics-filters">
					<div class="cima-filter-group" style="flex: 1 1 280px;">
						<label>Período rápido</label>
						<div class="cima-preset-pills">
							<button type="button" class="cima-preset-btn" data-preset="today">Hoy</button>
							<button type="button" class="cima-preset-btn" data-preset="week">7 días</button>
							<button type="button" class="cima-preset-btn active" data-preset="month">Este Mes</button>
							<button type="button" class="cima-preset-btn" data-preset="30d">30 días</button>
							<button type="button" class="cima-preset-btn" data-preset="all">Todo</button>
						</div>
					</div>
					<div class="cima-filter-group">
						<label>Desde</label>
						<input type="date" id="cm-from-date" class="form-control input-sm" value="${this.state.from_date}" />
					</div>
					<div class="cima-filter-group">
						<label>Hasta</label>
						<input type="date" id="cm-to-date" class="form-control input-sm" value="${this.state.to_date}" />
					</div>
					<div class="cima-filter-group" style="min-width: 190px;">
						<label>Vendedor (Usuario)</label>
						<select id="cm-user-filter" class="form-control input-sm">
							<option value="">Todos los vendedores</option>
						</select>
					</div>
					<div class="cima-filter-group" style="min-width: 150px;">
						<label>Canal de Venta</label>
						<select id="cm-channel-filter" class="form-control input-sm">
							<option value="">Todos los canales</option>
						</select>
					</div>
					<div class="cima-filter-group" style="min-width: 160px;">
						<label>Empresa</label>
						<select id="cm-company-filter" class="form-control input-sm">
							<option value="">Todas</option>
						</select>
					</div>
				</div>

				<div id="cm-kpi-grid" class="cima-kpi-grid"></div>

				<div class="cima-metrics-card">
					<div class="cima-metrics-card-header">
						<div class="cima-metrics-card-title">Ventas Desglosadas por Usuario Vendedor</div>
						<div class="text-muted small" id="cm-user-hint">Haz clic en un vendedor para filtrar sus facturas y métricas</div>
					</div>
					<div class="table-responsive">
						<table class="table table-bordered table-hover">
							<thead>
								<tr>
									<th>Vendedor (Usuario)</th>
									<th class="text-right">Facturas</th>
									<th class="text-right">Ítems</th>
									<th class="text-right">Clientes</th>
									<th class="text-right">Total Vendido</th>
									<th>Participación</th>
									<th class="text-right">Ticket Prom.</th>
									<th class="text-right">Cobrado</th>
									<th class="text-right">Por Cobrar</th>
									<th class="text-right">Timbradas</th>
									<th class="text-right">Cashea</th>
								</tr>
							</thead>
							<tbody id="cm-by-user-body">
								<tr><td colspan="11" class="text-center text-muted">Cargando métricas...</td></tr>
							</tbody>
						</table>
					</div>
				</div>

				<div class="cima-metrics-grid-2">
					<div class="cima-metrics-card">
						<div class="cima-metrics-card-header">
							<div class="cima-metrics-card-title">Tendencia Diaria de Ventas</div>
						</div>
						<div id="cm-daily-trend"></div>
					</div>
					<div class="cima-metrics-card">
						<div class="cima-metrics-card-header">
							<div class="cima-metrics-card-title">Ventas por Canal</div>
						</div>
						<div id="cm-by-channel"></div>
					</div>
				</div>

				<div class="cima-metrics-grid-2">
					<div class="cima-metrics-card">
						<div class="cima-metrics-card-header">
							<div class="cima-metrics-card-title">Top 10 Productos Vendidos</div>
						</div>
						<div id="cm-top-items"></div>
					</div>
					<div class="cima-metrics-card">
						<div class="cima-metrics-card-header">
							<div class="cima-metrics-card-title">Top 10 Clientes</div>
						</div>
						<div id="cm-top-customers"></div>
					</div>
				</div>

				<div class="cima-metrics-card">
					<div class="cima-metrics-card-header">
						<div class="cima-metrics-card-title">Detalle de Facturas Emitidas</div>
						<div class="text-muted small" id="cm-invoices-count"></div>
					</div>
					<div class="table-responsive">
						<table class="table table-bordered table-hover">
							<thead>
								<tr>
									<th>Factura</th>
									<th>Fecha</th>
									<th>Vendedor</th>
									<th>Cliente</th>
									<th>Canal</th>
									<th>Estado Fiscal</th>
									<th>N° Control</th>
									<th>Cashea</th>
									<th class="text-right">Total</th>
									<th class="text-right">Pendiente</th>
								</tr>
							</thead>
							<tbody id="cm-invoices-body"></tbody>
						</table>
					</div>
				</div>
			</div>
		`;
		this.wrapper.find(".layout-main-section").html(html);
	}

	bindEvents() {
		const root = this.wrapper;

		root.on("click", "[data-action='go-pos']", () => {
			frappe.set_route("venta-rapida");
		});

		root.on("click", "[data-action='refresh']", () => {
			this.loadMetrics();
		});

		root.on("click", "[data-action='export-csv']", () => {
			this.exportByUserCsv();
		});

		root.on("click", "[data-preset]", (e) => {
			const preset = $(e.currentTarget).attr("data-preset");
			const today = frappe.datetime.get_today();
			let from = "";
			let to = today;

			if (preset === "today") {
				from = today;
			} else if (preset === "week") {
				from = frappe.datetime.add_days(today, -6);
			} else if (preset === "month") {
				from = frappe.datetime.month_start(today);
			} else if (preset === "30d") {
				from = frappe.datetime.add_days(today, -29);
			} else if (preset === "all") {
				from = "";
				to = "";
			}

			this.state.preset = preset;
			this.state.from_date = from;
			this.state.to_date = to;
			root.find("[data-preset]").removeClass("active");
			$(e.currentTarget).addClass("active");
			root.find("#cm-from-date").val(from);
			root.find("#cm-to-date").val(to);
			this.loadMetrics();
		});

		root.on("change", "#cm-from-date, #cm-to-date", () => {
			this.state.preset = "custom";
			root.find("[data-preset]").removeClass("active");
			this.state.from_date = root.find("#cm-from-date").val() || "";
			this.state.to_date = root.find("#cm-to-date").val() || "";
			this.loadMetrics();
		});

		root.on("change", "#cm-user-filter", (e) => {
			this.state.user = $(e.currentTarget).val() || "";
			this.loadMetrics();
		});

		root.on("change", "#cm-channel-filter", (e) => {
			this.state.sales_channel = $(e.currentTarget).val() || "";
			this.loadMetrics();
		});

		root.on("change", "#cm-company-filter", (e) => {
			this.state.company = $(e.currentTarget).val() || "";
			this.loadMetrics();
		});

		root.on("click", "[data-filter-user]", (e) => {
			const clickedUser = $(e.currentTarget).attr("data-filter-user");
			this.state.user = this.state.user === clickedUser ? "" : clickedUser;
			root.find("#cm-user-filter").val(this.state.user);
			this.loadMetrics();
		});
	}

	fmtMoney(amount, currency = "USD") {
		const num = Number(amount || 0).toLocaleString("en-US", {
			minimumFractionDigits: 2,
			maximumFractionDigits: 2,
		});
		return `${frappe.utils.escape_html(currency)} ${num}`;
	}

	loadMetrics() {
		frappe.call({
			method: "cima_ve.api.sales_metrics.get_sales_metrics",
			args: {
				from_date: this.state.from_date,
				to_date: this.state.to_date,
				user: this.state.user,
				sales_channel: this.state.sales_channel,
				company: this.state.company,
			},
			callback: (r) => {
				if (!r.message) return;
				this.state.data = r.message;
				this.populateFilterOptions(r.message.filter_options || {});
				this.renderAll();
			},
		});
	}

	populateFilterOptions(opts) {
		const userSel = this.wrapper.find("#cm-user-filter");
		const usersHtml =
			`<option value="">Todos los vendedores</option>` +
			(opts.users || [])
				.map(
					(u) =>
						`<option value="${frappe.utils.escape_html(u.user)}">${frappe.utils.escape_html(u.fullname)} (${frappe.utils.escape_html(u.user)})</option>`
				)
				.join("");
		userSel.html(usersHtml).val(this.state.user);

		const chSel = this.wrapper.find("#cm-channel-filter");
		const chHtml =
			`<option value="">Todos los canales</option>` +
			(opts.channels || [])
				.map((c) => `<option value="${frappe.utils.escape_html(c)}">${frappe.utils.escape_html(c)}</option>`)
				.join("");
		chSel.html(chHtml).val(this.state.sales_channel);

		const compSel = this.wrapper.find("#cm-company-filter");
		const compHtml =
			`<option value="">Todas</option>` +
			(opts.companies || [])
				.map((c) => `<option value="${frappe.utils.escape_html(c)}">${frappe.utils.escape_html(c)}</option>`)
				.join("");
		compSel.html(compHtml).val(this.state.company);
	}

	renderAll() {
		const data = this.state.data || {};
		const s = data.summary || {};
		const cur = s.currency || "USD";

		this.renderKpis(s, cur);
		this.renderByUser(data.by_user || [], cur);
		this.renderDailyTrend(data.daily_trend || [], cur);
		this.renderByChannel(data.by_channel || [], cur);
		this.renderTopItems(data.top_items || [], cur);
		this.renderTopCustomers(data.top_customers || [], cur);
		this.renderInvoices(data.invoices || [], cur);
	}

	renderKpis(s, cur) {
		const cards = [
			{
				label: "Total Vendido",
				value: this.fmtMoney(s.total_sales, cur),
				sub: `Neto: ${this.fmtMoney(s.net_sales, cur)} · IVA/Imp: ${this.fmtMoney(s.tax_total, cur)}`,
			},
			{
				label: "Facturas Emitidas",
				value: `${s.invoice_count || 0}`,
				sub: `Ticket promedio: ${this.fmtMoney(s.avg_ticket, cur)}`,
			},
			{
				label: "Vendedores Activos",
				value: `${s.unique_sellers || 0}`,
				sub: `Clientes atendidos: ${s.unique_customers || 0} · Ítems: ${Number(s.total_qty || 0)}`,
			},
			{
				label: "Cobrado vs Por Cobrar",
				value: this.fmtMoney(s.paid_amount, cur),
				sub: `Por cobrar: ${this.fmtMoney(s.outstanding_amount, cur)}`,
			},
			{
				label: "Facturación Fiscal & IGTF",
				value: `${s.fiscal_stamped_count || 0} timbradas`,
				sub: `IGTF (3%): ${this.fmtMoney(s.igtf_total, cur)}`,
			},
			{
				label: "Ventas con Cashea",
				value: this.fmtMoney(s.cashea_total, cur),
				sub: `${s.cashea_count || 0} órdenes Cashea`,
			},
		];

		this.wrapper.find("#cm-kpi-grid").html(
			cards
				.map(
					(c) => `
						<div class="cima-kpi-card">
							<div class="cima-kpi-label">${c.label}</div>
							<div class="cima-kpi-value">${c.value}</div>
							<div class="cima-kpi-sub">${c.sub}</div>
						</div>
					`
				)
				.join("")
		);
	}

	renderByUser(rows, cur) {
		const tbody = this.wrapper.find("#cm-by-user-body");
		if (!rows.length) {
			tbody.html(`<tr><td colspan="11" class="text-center text-muted">No hay facturas confirmadas para los filtros seleccionados.</td></tr>`);
			return;
		}
		tbody.html(
			rows
				.map((r) => {
					const isActive = this.state.user && this.state.user === r.user;
					const pct = Math.min(Math.max(Number(r.share_pct || 0), 0), 100);
					return `
						<tr class="cima-user-row ${isActive ? "active-seller" : ""}" data-filter-user="${frappe.utils.escape_html(r.user)}">
							<td>
								<div><strong>${frappe.utils.escape_html(r.fullname)}</strong></div>
								<div class="text-muted small">${frappe.utils.escape_html(r.user)}</div>
							</td>
							<td class="text-right"><strong>${r.invoice_count}</strong></td>
							<td class="text-right">${Number(r.total_qty || 0)}</td>
							<td class="text-right">${r.unique_customers}</td>
							<td class="text-right"><strong>${this.fmtMoney(r.total_sales, cur)}</strong></td>
							<td>
								<div class="cima-share-bar-wrap"><div class="cima-share-bar-fill" style="width: ${pct}%;"></div></div>
								<span>${pct.toFixed(1)}%</span>
							</td>
							<td class="text-right">${this.fmtMoney(r.avg_ticket, cur)}</td>
							<td class="text-right">${this.fmtMoney(r.paid_amount, cur)}</td>
							<td class="text-right">${this.fmtMoney(r.outstanding_amount, cur)}</td>
							<td class="text-right">${r.fiscal_stamped_count}</td>
							<td class="text-right">${r.cashea_count} (${this.fmtMoney(r.cashea_total, cur)})</td>
						</tr>
					`;
				})
				.join("")
		);
	}

	renderDailyTrend(rows, cur) {
		const container = this.wrapper.find("#cm-daily-trend");
		if (!rows.length) {
			container.html(`<div class="text-muted text-center p-4">Sin datos de tendencia en el período.</div>`);
			return;
		}
		const maxVal = Math.max(...rows.map((r) => Number(r.total_sales || 0)), 1);
		const barsHtml = rows
			.slice(-24)
			.map((r) => {
				const h = Math.max(Math.round((Number(r.total_sales || 0) / maxVal) * 120), 4);
				const label = (r.date || "").slice(5);
				const title = `${r.date}: ${this.fmtMoney(r.total_sales, cur)} (${r.invoice_count} facturas)`;
				return `
					<div class="cima-trend-col" title="${frappe.utils.escape_html(title)}">
						<div class="cima-trend-bar" style="height: ${h}px;"></div>
						<div class="cima-trend-date">${frappe.utils.escape_html(label)}</div>
					</div>
				`;
			})
			.join("");
		container.html(`<div class="cima-trend-bars">${barsHtml}</div>`);
	}

	renderByChannel(rows, cur) {
		const container = this.wrapper.find("#cm-by-channel");
		if (!rows.length) {
			container.html(`<div class="text-muted text-center p-4">Sin datos por canal.</div>`);
			return;
		}
		container.html(`
			<table class="table table-sm table-bordered mb-0">
				<thead>
					<tr>
						<th>Canal</th>
						<th class="text-right">Facturas</th>
						<th class="text-right">Total</th>
						<th>%</th>
					</tr>
				</thead>
				<tbody>
					${rows
						.map((r) => {
							const pct = Math.min(Math.max(Number(r.share_pct || 0), 0), 100);
							return `
								<tr>
									<td><strong>${frappe.utils.escape_html(r.channel)}</strong></td>
									<td class="text-right">${r.invoice_count}</td>
									<td class="text-right">${this.fmtMoney(r.total_sales, cur)}</td>
									<td>
										<div class="cima-share-bar-wrap" style="width: 70px;"><div class="cima-share-bar-fill" style="width: ${pct}%;"></div></div>
										${pct.toFixed(1)}%
									</td>
								</tr>
							`;
						})
						.join("")}
				</tbody>
			</table>
		`);
	}

	renderTopItems(rows, cur) {
		const container = this.wrapper.find("#cm-top-items");
		if (!rows.length) {
			container.html(`<div class="text-muted text-center p-4">Sin productos vendidos en el período.</div>`);
			return;
		}
		container.html(`
			<table class="table table-sm table-bordered mb-0">
				<thead>
					<tr>
						<th>Producto</th>
						<th class="text-right">Cant.</th>
						<th class="text-right">Facturas</th>
						<th class="text-right">Total</th>
					</tr>
				</thead>
				<tbody>
					${rows
						.map(
							(r) => `
								<tr>
									<td>
										<div><strong>${frappe.utils.escape_html(r.item_name)}</strong></div>
										<div class="text-muted small">${frappe.utils.escape_html(r.item_code)}</div>
									</td>
									<td class="text-right">${Number(r.qty || 0)}</td>
									<td class="text-right">${r.invoice_count}</td>
									<td class="text-right"><strong>${this.fmtMoney(r.amount, cur)}</strong></td>
								</tr>
							`
						)
						.join("")}
				</tbody>
			</table>
		`);
	}

	renderTopCustomers(rows, cur) {
		const container = this.wrapper.find("#cm-top-customers");
		if (!rows.length) {
			container.html(`<div class="text-muted text-center p-4">Sin clientes en el período.</div>`);
			return;
		}
		container.html(`
			<table class="table table-sm table-bordered mb-0">
				<thead>
					<tr>
						<th>Cliente</th>
						<th class="text-right">Facturas</th>
						<th class="text-right">Total</th>
					</tr>
				</thead>
				<tbody>
					${rows
						.map(
							(r) => `
								<tr>
									<td>
										<a href="/app/customer/${encodeURIComponent(r.customer)}"><strong>${frappe.utils.escape_html(r.customer_name)}</strong></a>
									</td>
									<td class="text-right">${r.invoice_count}</td>
									<td class="text-right"><strong>${this.fmtMoney(r.total_sales, cur)}</strong></td>
								</tr>
							`
						)
						.join("")}
				</tbody>
			</table>
		`);
	}

	renderInvoices(rows, cur) {
		this.wrapper.find("#cm-invoices-count").text(`Mostrando ${rows.length} facturas recientes`);
		const tbody = this.wrapper.find("#cm-invoices-body");
		if (!rows.length) {
			tbody.html(`<tr><td colspan="10" class="text-center text-muted">Sin facturas para mostrar.</td></tr>`);
			return;
		}
		tbody.html(
			rows
				.map((r) => {
					const invCur = r.currency || cur;
					const fiscalCls = r.ve_fiscal_status === "Timbrada" || r.ve_fiscal_status === "Simulada"
						? "cima-badge-ok"
						: "cima-badge-warn";
					const casheaText = r.cashea_order_id
						? `<span class="cima-badge-pill cima-badge-info">${frappe.utils.escape_html(r.cashea_status || "Cashea")}</span>`
						: "-";
					return `
						<tr>
							<td><a href="/app/sales-invoice/${encodeURIComponent(r.name)}"><strong>${frappe.utils.escape_html(r.name)}</strong></a></td>
							<td>${frappe.utils.escape_html(r.posting_date)}</td>
							<td>
								<div>${frappe.utils.escape_html(r.seller_name)}</div>
								<div class="text-muted small">${frappe.utils.escape_html(r.seller_user)}</div>
							</td>
							<td>${frappe.utils.escape_html(r.customer_name)}</td>
							<td>${frappe.utils.escape_html(r.canal_venta)}</td>
							<td><span class="cima-badge-pill ${fiscalCls}">${frappe.utils.escape_html(r.ve_fiscal_status)}</span></td>
							<td>${frappe.utils.escape_html(r.ve_numero_control || "-")}</td>
							<td>${casheaText}</td>
							<td class="text-right"><strong>${this.fmtMoney(r.grand_total, invCur)}</strong></td>
							<td class="text-right">${this.fmtMoney(r.outstanding_amount, invCur)}</td>
						</tr>
					`;
				})
				.join("")
		);
	}

	exportByUserCsv() {
		const rows = (this.state.data && this.state.data.by_user) || [];
		if (!rows.length) {
			frappe.msgprint("No hay datos de vendedores para exportar.");
			return;
		}
		const headers = [
			"Usuario",
			"Nombre",
			"Facturas",
			"Items",
			"Clientes Unicos",
			"Total Vendido",
			"Participacion %",
			"Ticket Promedio",
			"Cobrado",
			"Por Cobrar",
			"Timbradas",
			"Cashea Cantidad",
			"Cashea Total",
		];
		const lines = [headers.join(",")];
		rows.forEach((r) => {
			const cols = [
				r.user,
				r.fullname,
				r.invoice_count,
				r.total_qty,
				r.unique_customers,
				r.total_sales,
				r.share_pct,
				r.avg_ticket,
				r.paid_amount,
				r.outstanding_amount,
				r.fiscal_stamped_count,
				r.cashea_count,
				r.cashea_total,
			].map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`);
			lines.push(cols.join(","));
		});
		const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = `ventas_por_usuario_${this.state.from_date || "inicio"}_${this.state.to_date || "hoy"}.csv`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	}
}
