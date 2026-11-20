frappe.pages["bi-cima"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Inteligencia de Negocios",
		single_column: true,
	});
	new CimaBiPage(page, wrapper);
};

class CimaBiPage {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = $(wrapper);
		this.renderShell();
		this.bindEvents();
		this.loadBi();
	}

	renderShell() {
		this.wrapper.find(".layout-main-section").html(`
			<div class="cima-shell">
				<div class="cima-hero">
					<div class="cima-hero-brand">
						<img src="/assets/cima_ve/images/cima-logo-blanco.png" alt="CIMA" class="cima-hero-logo" />
						<div class="cima-hero-title">
							<h2>Inteligencia de Negocios e Importación China</h2>
							<p>Predicción de agotamiento, clasificación ABC, rotación rápida y plan óptimo de compra.</p>
						</div>
					</div>
					<div class="cima-hero-actions">
						<button type="button" class="cima-btn-primary" id="bi-send-alert">Enviar Alerta Semanal Ahora</button>
						<button type="button" class="cima-btn-ghost" id="bi-open-settings">Configurar Días China</button>
					</div>
				</div>

				<div class="cima-kpi-grid" id="bi-kpis"></div>

				<div class="cima-card mb-3">
					<div class="cima-card-title">
						<span>Alertas Críticas: Stock se agota antes de llegar de China</span>
						<span class="cima-badge cima-badge-red" id="bi-lead-badge">Lead time China: 45 días</span>
					</div>
					<div id="bi-table-critical" class="table-responsive"></div>
				</div>

				<div class="row mb-3">
					<div class="col-md-6 mb-3">
						<div class="cima-card">
							<div class="cima-card-title"><span>Top Productos por Ingresos (ABC)</span></div>
							<div id="bi-table-revenue" class="table-responsive"></div>
						</div>
					</div>
					<div class="col-md-6 mb-3">
						<div class="cima-card">
							<div class="cima-card-title"><span>Productos de Rotación Más Rápida</span></div>
							<div id="bi-table-fastest" class="table-responsive"></div>
						</div>
					</div>
				</div>

				<div class="cima-card mb-3">
					<div class="cima-card-title"><span>Plan Recomendado de Compra a China</span></div>
					<div id="bi-table-purchase" class="table-responsive"></div>
				</div>

				<div class="cima-card">
					<div class="cima-card-title"><span>Inventario Sin Movimiento (Capital Inmovilizado)</span></div>
					<div id="bi-table-dead" class="table-responsive"></div>
				</div>
			</div>
		`);
	}

	bindEvents() {
		const root = this.wrapper;
		root.on("click", "#bi-open-settings", () => frappe.set_route("Form", "Cima VE Settings"));
		root.on("click", "#bi-send-alert", () => {
			frappe.call({
				method: "cima_ve.api.bi.send_bi_stockout_alert_now",
				callback: (r) => {
					if (r.message && r.message.sent) {
						frappe.msgprint(`Alerta enviada a: ${(r.message.recipients || []).join(", ")}`);
					} else {
						frappe.msgprint((r.message && r.message.message) || "No hay productos críticos para alertar.");
					}
				},
			});
		});
	}

	loadBi() {
		frappe.call({
			method: "cima_ve.api.bi.get_bi_dashboard",
			callback: (r) => {
				if (!r.message) return;
				this.renderBi(r.message);
			},
		});
	}

	renderBi(data) {
		const k = data.kpis;
		const cfg = data.config;
		this.wrapper.find("#bi-lead-badge").text(`Lead time China: ${cfg.china_lead_time_days} días · Seguridad: ${cfg.safety_stock_days}d`);
		this.wrapper.find("#bi-kpis").html(`
			<div class="cima-kpi-card danger">
				<div class="cima-kpi-label">Críticos (&lt; ${cfg.china_lead_time_days}d China)</div>
				<div class="cima-kpi-value">${k.critical_count}</div>
				<div class="cima-kpi-sub">${k.warning_count} en alerta preventiva</div>
			</div>
			<div class="cima-kpi-card emerald">
				<div class="cima-kpi-label">Ventas Ventana (${cfg.analysis_window_days}d)</div>
				<div class="cima-kpi-value">$${Number(k.total_revenue_window).toFixed(2)}</div>
				<div class="cima-kpi-sub">${k.total_items_analyzed} ítems analizados</div>
			</div>
			<div class="cima-kpi-card">
				<div class="cima-kpi-label">Inversión Sugerida China</div>
				<div class="cima-kpi-value">$${Number(k.total_recommended_investment).toFixed(2)}</div>
				<div class="cima-kpi-sub">Valor stock actual: $${Number(k.total_inventory_value).toFixed(2)}</div>
			</div>
			<div class="cima-kpi-card amber">
				<div class="cima-kpi-label">Stock Sin Movimiento</div>
				<div class="cima-kpi-value">${k.dead_stock_count}</div>
				<div class="cima-kpi-sub">Candidatos a promoción / Meta Ads</div>
			</div>
		`);

		this.wrapper.find("#bi-table-critical").html(`
			<table class="table table-sm table-bordered">
				<thead><tr><th>Código</th><th>Producto</th><th class="text-right">Stock</th><th class="text-right">Vel./Día</th><th class="text-right">Días Rest.</th><th>Agotamiento Est.</th><th class="text-right">Pedir (China)</th></tr></thead>
				<tbody>${(data.critical_items || []).map((i) => `<tr><td><code>${frappe.utils.escape_html(i.item_code)}</code></td><td><strong>${frappe.utils.escape_html(i.item_name)}</strong></td><td class="text-right">${i.current_stock}</td><td class="text-right">${i.daily_velocity.toFixed(2)}</td><td class="text-right text-danger"><strong>${i.days_until_stockout} d</strong></td><td>${frappe.utils.escape_html(i.est_stockout_date || "-")}</td><td class="text-right"><strong>${i.recommended_order_qty} uds</strong></td></tr>`).join("") || `<tr><td colspan="7" class="text-muted text-center">Ningún producto se agota antes del tiempo de llegada desde China.</td></tr>`}</tbody>
			</table>
		`);

		this.wrapper.find("#bi-table-revenue").html(`
			<table class="table table-sm table-bordered">
				<thead><tr><th>ABC</th><th>Producto</th><th class="text-right">Uds.</th><th class="text-right">Ingresos</th></tr></thead>
				<tbody>${(data.top_revenue_items || []).map((i) => `<tr><td><span class="cima-badge cima-badge-teal">${i.abc_class}</span></td><td>${frappe.utils.escape_html(i.item_name)}</td><td class="text-right">${i.units_sold_window}</td><td class="text-right"><strong>$${Number(i.revenue_window).toFixed(2)}</strong></td></tr>`).join("") || `<tr><td colspan="4" class="text-muted text-center">Sin ventas</td></tr>`}</tbody>
			</table>
		`);

		this.wrapper.find("#bi-table-fastest").html(`
			<table class="table table-sm table-bordered">
				<thead><tr><th>Producto</th><th class="text-right">Uds./Día</th><th class="text-right">Uds./Mes</th><th class="text-right">Días Stock</th></tr></thead>
				<tbody>${(data.fastest_selling_items || []).map((i) => `<tr><td>${frappe.utils.escape_html(i.item_name)}</td><td class="text-right"><strong>${i.daily_velocity.toFixed(2)}</strong></td><td class="text-right">${i.monthly_velocity}</td><td class="text-right">${i.days_until_stockout ?? "∞"}</td></tr>`).join("") || `<tr><td colspan="4" class="text-muted text-center">Sin datos</td></tr>`}</tbody>
			</table>
		`);

		this.wrapper.find("#bi-table-purchase").html(`
			<table class="table table-sm table-bordered">
				<thead><tr><th>Estado</th><th>Código</th><th>Producto</th><th class="text-right">Stock + Tránsito</th><th class="text-right">Cant. Sugerida</th><th class="text-right">Costo Est.</th></tr></thead>
				<tbody>${(data.purchase_plan || []).slice(0, 30).map((i) => {
					const badge = i.alert_level === "CRÍTICO" ? "cima-badge-red" : i.alert_level === "ALERTA" ? "cima-badge-amber" : "cima-badge-green";
					return `<tr><td><span class="cima-badge ${badge}">${i.alert_level}</span></td><td><code>${frappe.utils.escape_html(i.item_code)}</code></td><td>${frappe.utils.escape_html(i.item_name)}</td><td class="text-right">${i.current_stock + i.incoming_qty}</td><td class="text-right"><strong>${i.recommended_order_qty}</strong></td><td class="text-right">$${Number(i.est_order_cost).toFixed(2)}</td></tr>`;
				}).join("") || `<tr><td colspan="6" class="text-muted text-center">Inventario cubierto</td></tr>`}</tbody>
			</table>
		`);

		this.wrapper.find("#bi-table-dead").html(`
			<table class="table table-sm table-bordered">
				<thead><tr><th>Código</th><th>Producto</th><th class="text-right">Stock</th><th class="text-right">Capital Inmovilizado</th></tr></thead>
				<tbody>${(data.slow_dead_stock || []).map((i) => `<tr><td><code>${frappe.utils.escape_html(i.item_code)}</code></td><td>${frappe.utils.escape_html(i.item_name)}</td><td class="text-right">${i.current_stock}</td><td class="text-right">$${Number(i.stock_value).toFixed(2)}</td></tr>`).join("") || `<tr><td colspan="4" class="text-muted text-center">Todo el inventario tiene rotación</td></tr>`}</tbody>
			</table>
		`);
	}
}
