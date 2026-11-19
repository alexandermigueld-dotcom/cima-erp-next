frappe.ui.form.on("Cima VE Settings", {
	assistant_provider(frm) {
		const defaultModels = {
			OpenAI: "gpt-4o-mini",
			Anthropic: "claude-3-5-haiku-latest",
			Gemini: "gemini-2.0-flash",
		};
		if (defaultModels[frm.doc.assistant_provider]) {
			frm.set_value("assistant_model", defaultModels[frm.doc.assistant_provider]);
		}
	},
	refresh(frm) {
		frm.add_custom_button("Probar conexión IA", () => {
			const testConnection = () => {
				frappe.call({
					method: "cima_ve.api.ai_assistant.test_assistant_connection",
					freeze: true,
					freeze_message: "Probando conexión con el proveedor de IA...",
					callback(r) {
						if (r.message && r.message.ok) {
							frappe.show_alert({ message: `Conexión correcta con ${r.message.provider} (${r.message.model}).`, indicator: "green" });
						}
					},
				});
			};
			if (frm.is_dirty()) {
				frm.save().then(testConnection);
			} else {
				testConnection();
			}
		});
	},
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
