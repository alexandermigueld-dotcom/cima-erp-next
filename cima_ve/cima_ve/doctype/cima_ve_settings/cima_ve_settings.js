frappe.ui.form.on("Cima VE Settings", {
	fx_sync_now(frm) {
		frappe.call({
			method: "cima_ve.api.exchange_rates.sync_exchange_rates_now",
			freeze: true,
			freeze_message: "Consultando BCV, Monitor y Binance P2P...",
			callback(r) {
				if (!r.message) return;
				const d = r.message;
				frm.reload_doc();
				frappe.show_alert({
					message: `Tasas actualizadas: BCV ${Number(d.bcv_rate || 0).toFixed(2)} Bs · Binance ${Number(d.binance_usdt_rate || 0).toFixed(2)} Bs · Brecha ${Number(d.applied_brecha_pct || 0).toFixed(2)}% · Ajustada ${Number(d.adjusted_rate || 0).toFixed(2)} Bs/USD`,
					indicator: d.errors && d.errors.length ? "orange" : "green",
				});
			},
		});
	},
});
