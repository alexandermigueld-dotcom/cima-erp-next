frappe.pages["asistente-cima"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Asistente CIMA",
		single_column: true,
	});

	new CimaAssistant(page, wrapper);
};

class CimaAssistant {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = $(wrapper);
		this.state = {
			bootstrap: {},
			messages: [],
			importPreview: null,
			importFile: null,
			previewing: false,
			asking: false,
			retryRequest: null,
		};
		this.dragDepth = 0;
		this.renderShell();
		this.bindEvents();
		this.loadBootstrap();
	}

	escape(value) {
		return frappe.utils.escape_html(String(value == null ? "" : value));
	}

	renderShell() {
		this.wrapper.find(".layout-main-section").html(`
			<div class="cima-ai-shell">
				<div class="cima-ai-topbar">
					<div class="cima-ai-topbar-title">
						<h2>Asistente CIMA</h2>
						<span class="cima-ai-badge">IA + Inventario</span>
					</div>
					<div class="cima-ai-topbar-actions">
						<button type="button" id="cima-ai-toggle-filters" class="btn btn-default btn-xs" aria-expanded="false">Filtros</button>
						<button type="button" class="btn btn-default btn-xs" data-action="product-loader">Carga de Productos</button>
						<button type="button" class="btn btn-default btn-xs" data-action="settings">Configuración IA</button>
					</div>
				</div>
				<div id="cima-ai-config-alert"></div>
				<section id="cima-ai-chat" class="cima-ai-chat-card" aria-label="Chat del asistente y carga de archivos CSV o Excel">
					<div class="cima-ai-drag-overlay" aria-hidden="true">
						<div class="cima-ai-drag-overlay-box">
							<strong>Suelta tu archivo CSV o Excel (.xlsx)</strong>
							<span>Se validará en una tabla antes de crear productos o actualizar precios.</span>
						</div>
					</div>
					<div id="cima-ai-filter-panel" class="cima-ai-filter-panel" hidden>
						<div class="cima-ai-scope">
							<div><label>Desde</label><input id="cima-ai-from" type="date" class="form-control input-sm" /></div>
							<div><label>Hasta</label><input id="cima-ai-to" type="date" class="form-control input-sm" /></div>
							<div><label>Vendedor</label><select id="cima-ai-seller" class="form-control input-sm"><option value="">Todos</option></select></div>
							<div><label>Compañía</label><select id="cima-ai-company" class="form-control input-sm"><option value="">Todas</option></select></div>
							<div><label>Almacén consulta</label><select id="cima-ai-warehouse" class="form-control input-sm"><option value="">Todos</option></select></div>
							<div><label>Almacén carga</label><select id="cima-ai-import-warehouse" class="form-control input-sm"><option value="">Si hay cantidades</option></select></div>
						</div>
					</div>
					<div id="cima-ai-messages" class="cima-ai-messages" aria-live="polite"></div>
					<div id="cima-ai-pending" class="cima-ai-pending" role="status" aria-live="polite" hidden>
						<span class="cima-ai-spinner" aria-hidden="true"></span>Pensando…
					</div>
					<div id="cima-ai-import-preview" class="cima-ai-import-preview-slot"></div>
					<div class="cima-ai-composer-wrap">
						<div class="cima-ai-suggestions">
							<button type="button" data-prompt="Resume el inventario actual y destaca los productos con menor existencia.">Inventario bajo</button>
							<button type="button" data-prompt="Resume las Notas de Entrega despachadas y sus estados.">Notas de Entrega</button>
							<button type="button" data-prompt="Compara ventas facturadas, cobros registrados y despacho por vendedor en el período seleccionado.">Ventas y vendedores</button>
							<button type="button" data-template="Prepara un borrador para crear este producto: ">Preparar producto</button>
						</div>
						<div class="cima-ai-compose">
							<input id="cima-ai-file" type="file" class="cima-ai-file-input" accept=".csv,.xlsx" aria-label="Seleccionar archivo CSV o Excel" />
							<label for="cima-ai-file" class="cima-ai-attach-btn" title="Adjuntar CSV o Excel (.xlsx)">
								<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
							</label>
							<textarea id="cima-ai-question" rows="1" class="form-control" placeholder="Pregunta sobre inventario, ventas, cobros o arrastra un CSV/XLSX aquí..." aria-label="Escribe tu pregunta"></textarea>
							<button type="button" id="cima-ai-send" class="btn btn-primary btn-sm cima-ai-send-btn" disabled>Enviar</button>
						</div>
						<div class="cima-ai-compose-hint">
							<span>Enter para enviar · Shift+Enter nueva línea · Arrastra CSV/XLSX al chat (máx. 4 MB, 250 filas)</span>
							<span>Solo datos resumidos</span>
						</div>
					</div>
				</section>
			</div>
		`);
		this.addMessage("assistant", "Hola. Puedo resumir inventario, ventas facturadas, cobros y Notas de Entrega, o preparar borradores de productos. También puedes arrastrar un archivo CSV o Excel (.xlsx) directamente al chat para crear productos nuevos o actualizar precios de existentes (e incluso pedirme en el chat que ajuste los precios del archivo antes de confirmar).");
	}

	bindEvents() {
		this.wrapper.on("click", "#cima-ai-send", () => this.sendMessage());
		this.wrapper.on("keydown", "#cima-ai-question", (event) => {
			if (event.key === "Enter" && !event.shiftKey) {
				event.preventDefault();
				this.sendMessage();
			}
		});
		this.wrapper.on("input", "#cima-ai-question", (event) => {
			const el = event.currentTarget;
			if (!el || !el.style) return;
			el.style.height = "auto";
			el.style.height = `${Math.min(el.scrollHeight || 32, 110)}px`;
		});
		this.wrapper.on("click", "#cima-ai-toggle-filters", (event) => {
			const panel = this.wrapper.find("#cima-ai-filter-panel");
			const isHidden = Boolean(panel.prop("hidden"));
			panel.prop("hidden", !isHidden);
			$(event.currentTarget).attr("aria-expanded", String(isHidden));
		});
		this.wrapper.on("click", ".cima-ai-suggestions [data-prompt]", (event) => {
			this.wrapper.find("#cima-ai-question").val($(event.currentTarget).data("prompt"));
			this.sendMessage();
		});
		this.wrapper.on("click", "[data-template]", (event) => {
			this.wrapper.find("#cima-ai-question").val($(event.currentTarget).data("template")).trigger("focus");
		});
		this.wrapper.on("click", "[data-draft-index]", (event) => {
			const draft = this.state.messages[$(event.currentTarget).data("draft-index")]?.draft;
			if (!draft) return;
			frappe.cimaAssistantProductDraft = draft;
			frappe.set_route("carga-productos");
		});
		this.wrapper.on("click", "[data-retry-index]", () => this.retryLastQuestion());
		this.wrapper.on("click", "[data-action='settings']", () => frappe.set_route("Form", "Cima VE Settings", "Cima VE Settings"));
		this.wrapper.on("click", "[data-action='product-loader']", () => frappe.set_route("carga-productos"));
		this.wrapper.on("click", "[data-action='close-preview']", () => this.clearImportPreview());
		this.wrapper.on("click", "#cima-ai-preview", () => this.previewImport());
		this.wrapper.on("click", "#cima-ai-confirm-import", () => this.confirmImport());
		this.wrapper.on("change", "#cima-ai-file", (event) => this.handleFileSelection(event.currentTarget.files[0]));
		this.wrapper.on("change", "#cima-ai-import-warehouse", () => this.invalidateImportPreview());
		this.wrapper.on("dragenter", "#cima-ai-chat", (event) => {
			event.preventDefault();
			this.dragDepth = (this.dragDepth || 0) + 1;
			this.wrapper.find("#cima-ai-chat").addClass("is-dragging");
		});
		this.wrapper.on("dragover", "#cima-ai-chat", (event) => {
			event.preventDefault();
			this.wrapper.find("#cima-ai-chat").addClass("is-dragging");
		});
		this.wrapper.on("dragleave", "#cima-ai-chat", (event) => {
			event.preventDefault();
			this.dragDepth = Math.max(0, (this.dragDepth || 0) - 1);
			if (this.dragDepth === 0) {
				this.wrapper.find("#cima-ai-chat").removeClass("is-dragging");
			}
		});
		this.wrapper.on("drop", "#cima-ai-chat", (event) => {
			event.preventDefault();
			this.dragDepth = 0;
			this.wrapper.find("#cima-ai-chat").removeClass("is-dragging");
			const transfer = (event.originalEvent || event).dataTransfer;
			if (transfer && transfer.files && transfer.files[0]) this.handleFileSelection(transfer.files[0]);
		});
		this.wrapper.on("click", "a[data-item-code]", (event) => {
			event.preventDefault();
			frappe.set_route("Form", "Item", $(event.currentTarget).data("item-code"));
		});
	}

	loadBootstrap() {
		frappe.call({
			method: "cima_ve.api.ai_assistant.get_assistant_bootstrap",
			callback: (r) => {
				if (!r.message) return;
				this.state.bootstrap = r.message;
				this.renderBootstrap();
			},
		});
	}

	renderBootstrap() {
		const b = this.state.bootstrap;
		const selectOptions = (values, getValue, getLabel) => values
			.map((value) => `<option value="${this.escape(getValue(value))}">${this.escape(getLabel(value))}</option>`)
			.join("");
		this.wrapper.find("#cima-ai-seller").append(selectOptions(b.users || [], (u) => u.name, (u) => u.full_name || u.name));
		this.wrapper.find("#cima-ai-company").append(selectOptions(b.companies || [], (c) => c, (c) => c));
		const warehouseOptions = selectOptions(b.warehouses || [], (w) => w.name, (w) => w.warehouse_name || w.name);
		this.wrapper.find("#cima-ai-warehouse").append(warehouseOptions);
		this.wrapper.find("#cima-ai-import-warehouse").append(warehouseOptions).val(b.default_warehouse || "");
		if (!b.enabled || !b.configured) {
			const reason = !b.enabled ? "Habilita el asistente en Cima VE Settings para usar el chat." : "Configura la clave API del proveedor seleccionado para usar el chat.";
			this.wrapper.find("#cima-ai-config-alert").html(`<div class="alert alert-warning">${this.escape(reason)} El cargador de inventario permanece disponible.</div>`);
		}
		this.wrapper.find("#cima-ai-send").prop("disabled", !b.enabled || !b.configured);
	}

	addMessage(role, text, draft = null, options = {}) {
		const message = {
			role,
			content: String(text || ""),
			meta: options.meta ? String(options.meta) : "",
			draft,
			includeInHistory: options.includeInHistory !== false,
			error: Boolean(options.error),
			retry: Boolean(options.retry),
		};
		this.state.messages.push(message);
		this.renderMessages();
		return message;
	}

	renderMessages() {
		const messageHtml = this.state.messages
			.map((message, index) => `<div class="cima-ai-message-row cima-ai-message-row-${message.role}">
				<div class="cima-ai-message cima-ai-message-${message.role}${message.error ? " cima-ai-message-error" : ""}">
					<div class="cima-ai-message-body">${this.escape(message.content)}</div>${message.meta
						? `<div class="cima-ai-message-meta">${this.escape(message.meta)}</div>` : ""}${message.draft
						? `<div class="cima-ai-message-actions"><button type="button" class="btn btn-default btn-xs" data-draft-index="${index}">Editar borrador en Carga de Productos</button></div>` : ""}${message.retry
						? `<div class="cima-ai-message-actions"><button type="button" class="btn btn-default btn-xs" data-retry-index="${index}">Reintentar</button></div>` : ""}
				</div>
			</div>`)
			.join("");
		const container = this.wrapper.find("#cima-ai-messages").html(messageHtml);
		if (container[0]) container.scrollTop(container[0].scrollHeight);
	}

	setPending(pending) {
		this.wrapper.find("#cima-ai-pending").prop("hidden", !pending);
	}

	sendMessage() {
		if (this.state.asking || !this.state.bootstrap.enabled || !this.state.bootstrap.configured) return;
		const input = this.wrapper.find("#cima-ai-question");
		const question = String(input.val() || "").trim();
		if (!question) return;
		if (question.length > 2000) {
			frappe.msgprint("La pregunta no puede superar 2.000 caracteres.");
			return;
		}
		this.state.retryRequest = null;
		const hadRetry = this.state.messages.some((message) => message.retry);
		this.state.messages.forEach((message) => { message.retry = false; });
		if (hadRetry) this.renderMessages();
		input.val("");
		if (typeof input.css === "function") input.css("height", "auto");
		this.requestAnswer(question);
	}

	requestAnswer(question, userTurn = null) {
		if (this.state.asking) return;
		const history = this.state.messages
			.filter((message) => message.includeInHistory !== false)
			.slice(-8)
			.map(({ role, content }) => ({ role, content }));
		userTurn = userTurn || this.addMessage("user", question, null, { includeInHistory: false });
		this.state.asking = true;
		this.setPending(true);
		this.wrapper.find("#cima-ai-send").prop("disabled", true);
		frappe.call({
			method: "cima_ve.api.ai_assistant.ask_assistant",
			args: {
				message: question,
				history: JSON.stringify(history),
				from_date: this.wrapper.find("#cima-ai-from").val() || "",
				to_date: this.wrapper.find("#cima-ai-to").val() || "",
				seller: this.wrapper.find("#cima-ai-seller").val() || "",
				company: this.wrapper.find("#cima-ai-company").val() || "",
				warehouse: this.wrapper.find("#cima-ai-warehouse").val() || "",
				import_token: this.state.importPreview?.token || "",
			},
			callback: (r) => {
				if (r.message && r.message.answer) {
					userTurn.includeInHistory = true;
					this.state.retryRequest = null;
					const scope = r.message.scope || {};
					const model = r.message.model ? ` · ${r.message.model}` : "";
					const meta = `Alcance: ${scope.from_date} a ${scope.to_date} · ${scope.seller} · ${scope.warehouse} · ${scope.company}${model}`;
					this.addMessage("assistant", r.message.answer, r.message.product_draft, { meta });
					if (r.message.updated_import_preview) {
						this.state.importPreview = r.message.updated_import_preview;
						this.renderImportPreview(r.message.updated_import_preview);
					}
				} else {
					this.showRequestError(question, userTurn, r);
				}
			},
			error: (r) => this.showRequestError(question, userTurn, r),
			always: () => {
				this.state.asking = false;
				this.setPending(false);
				this.wrapper.find("#cima-ai-send").prop("disabled", !this.state.bootstrap.enabled || !this.state.bootstrap.configured);
			},
		});
	}

	showRequestError(question, userTurn, response) {
		const detail = typeof response?.message === "string" && response.message.length < 700
			? response.message
			: "No se pudo completar la consulta. Revisa la disponibilidad y configuración del proveedor e inténtalo de nuevo.";
		this.state.retryRequest = { question, userTurn };
		this.addMessage("assistant", detail, null, { includeInHistory: false, error: true, retry: true });
	}

	retryLastQuestion() {
		const retry = this.state.retryRequest;
		if (!retry || this.state.asking) return;
		this.state.retryRequest = null;
		this.state.messages.forEach((message) => { message.retry = false; });
		this.renderMessages();
		this.requestAnswer(retry.question, retry.userTurn);
	}

	handleFileSelection(file) {
		if (!file) return;
		this.state.importFile = file;
		this.wrapper.find("#cima-ai-file").val("");
		this.invalidateImportPreview();
		this.previewImport(file);
	}

	clearImportPreview() {
		this.state.importPreview = null;
		this.state.importFile = null;
		this.wrapper.find("#cima-ai-file").val("");
		this.wrapper.find("#cima-ai-import-preview").empty();
	}

	invalidateImportPreview() {
		this.state.importPreview = null;
		const output = this.wrapper.find("#cima-ai-import-preview").empty();
		if (this.state.importFile) {
			output.html(`<div class="cima-ai-import-card"><div class="cima-ai-import-header"><span>Cambió el archivo o el almacén.</span><div class="cima-ai-import-actions"><button type="button" id="cima-ai-preview" class="btn btn-primary btn-xs">Revalidar</button><button type="button" class="btn btn-default btn-xs" data-action="close-preview">Cerrar</button></div></div></div>`);
		}
	}

	readFile(file) {
		return new Promise((resolve, reject) => {
			const reader = new FileReader();
			reader.onload = () => resolve(String(reader.result || ""));
			reader.onerror = () => reject(new Error("No se pudo leer el archivo."));
			reader.readAsDataURL(file);
		});
	}

	async previewImport(fileOverride = null) {
		if (this.state.previewing) return;
		const fileInput = this.wrapper.find("#cima-ai-file");
		const warehouseInput = this.wrapper.find("#cima-ai-import-warehouse");
		const file = fileOverride || this.state.importFile || fileInput[0].files[0];
		if (!file) {
			frappe.msgprint("Selecciona un archivo CSV o XLSX.");
			return;
		}
		if (file.size > 4 * 1024 * 1024) {
			frappe.msgprint("El archivo supera el límite de 4 MB.");
			return;
		}
		const controls = fileInput.add(warehouseInput).add(this.wrapper.find("#cima-ai-preview"));
		const output = this.wrapper.find("#cima-ai-import-preview");
		this.state.importPreview = null;
		this.state.previewing = true;
		controls.prop("disabled", true);
		output.text("Validando archivo...");
		try {
			const fileData = await this.readFile(file);
			const r = await frappe.call({
				method: "cima_ve.api.ai_assistant.preview_inventory_import",
				args: {
					filename: file.name,
					file_data_base64: fileData,
					warehouse: warehouseInput.val() || "",
				},
				freeze: true,
				freeze_message: "Validando productos y códigos duplicados...",
			});
			if (!r.message) throw new Error("No se pudo validar el archivo.");
			this.state.importPreview = r.message;
			this.renderImportPreview(r.message);
		} catch (error) {
			output.text(error.message || "No se pudo validar el archivo.");
		} finally {
			controls.prop("disabled", false);
			this.state.previewing = false;
		}
	}

	formatPriceCell(row, field, currentField) {
		const nextVal = row[field];
		if (row.action === "update_price") {
			if (nextVal === null || nextVal === undefined || nextVal === "") return "—";
			const curVal = row[currentField];
			if (curVal !== null && curVal !== undefined && curVal !== "") {
				return `<span class="text-muted">${this.escape(curVal)}</span> → <strong>${this.escape(nextVal)}</strong>`;
			}
			return `<strong>${this.escape(nextVal)}</strong>`;
		}
		return this.escape(nextVal);
	}

	importTable(preview) {
		const rows = (preview.rows || []).map((row) => {
			const errors = (row.errors || []).join(" ");
			const isUpdate = row.action === "update_price";
			const actionBadge = isUpdate
				? '<span class="cima-ai-action-badge is-update">Actualizar precio</span>'
				: '<span class="cima-ai-action-badge is-create">Crear</span>';
			const readyLabel = isUpdate ? "Listo para actualizar" : "Lista para crear";
			return `<tr>
				<td>${this.escape(row.row)}</td>
				<td>${actionBadge}</td>
				<td>${this.escape(row.item_code)}</td>
				<td>${this.escape(row.item_name)}</td>
				<td>${this.escape(row.description)}</td>
				<td>${this.escape(row.item_group || "—")}</td>
				<td>${this.escape(row.stock_uom || "—")}</td>
				<td>${this.formatPriceCell(row, "cost_rate", "current_cost_rate")}</td>
				<td>${this.formatPriceCell(row, "detal_price", "current_detal_price")}</td>
				<td>${this.formatPriceCell(row, "mayor_price", "current_mayor_price")}</td>
				<td>${isUpdate ? "—" : this.escape(row.initial_qty)}</td>
				<td>${!isUpdate && Number(row.initial_qty) > 0 ? this.escape(row.warehouse) : "—"}</td>
				<td>${isUpdate ? "—" : (row.show_in_website ? "Sí" : "No")}</td>
				<td class="${errors ? "cima-ai-error" : "cima-ai-ready"}">${this.escape(errors || readyLabel)}</td>
			</tr>`;
		}).join("");
		return `<div class="cima-ai-preview-table-wrap" tabindex="0" style="overflow: auto; max-height: 55vh;">
			<table class="cima-ai-preview-table table table-bordered table-sm"><thead><tr><th>Fila</th><th>Acción</th><th>SKU</th><th>Producto</th><th>Descripción</th><th>Categoría</th><th>Unidad</th><th>Costo</th><th>Detal</th><th>Mayor</th><th>Cantidad inicial</th><th>Almacén</th><th>Web</th><th>Validación</th></tr></thead><tbody>${rows}</tbody></table>
		</div>`;
	}

	renderImportPreview(preview) {
		const button = preview.can_confirm
			? '<button type="button" id="cima-ai-confirm-import" class="btn btn-primary btn-xs">Revisar y confirmar…</button>'
			: '<span class="cima-ai-error small">Corrige las filas con errores y vuelve a cargar el archivo.</span>';
		const createCount = Number(preview.create_count || 0);
		const updateCount = Number(preview.update_count || 0);
		const summaryParts = [];
		if (createCount) summaryParts.push(`${createCount} nuevos`);
		if (updateCount) summaryParts.push(`${updateCount} precios por actualizar`);
		const summaryText = summaryParts.length ? ` (${summaryParts.join(" · ")})` : "";
		const aiCols = preview.ai_mapped_columns && Object.keys(preview.ai_mapped_columns).length
			? `<div class="text-muted small" style="margin-bottom:6px;">Columnas interpretadas con IA: ${this.escape(Object.entries(preview.ai_mapped_columns).map(([k, v]) => `${k} → ${v}`).join(", "))}</div>`
			: "";
		this.wrapper.find("#cima-ai-import-preview").html(`
			<div class="cima-ai-import-card">
				<div class="cima-ai-import-header">
					<div>
						<strong>${this.escape(preview.row_count)} filas${this.escape(summaryText)}</strong>
						<span class="text-muted small"> · Vista previa válida 10 min (puedes pedirle ajustes de precio a la IA antes de confirmar).</span>
					</div>
					<div class="cima-ai-import-actions">
						${button}
						<button type="button" class="btn btn-default btn-xs" data-action="close-preview" aria-label="Cerrar vista previa">Cerrar</button>
					</div>
				</div>
				${aiCols}
				${this.importTable(preview)}
			</div>
		`);
	}

	confirmImport() {
		const preview = this.state.importPreview;
		if (!preview?.token) return;
		const rows = preview.rows || [];
		const createRows = rows.filter((row) => row.action !== "update_price");
		const updateRows = rows.filter((row) => row.action === "update_price");
		const stockCount = createRows.filter((row) => Number(row.initial_qty) > 0).length;
		const webCount = createRows.filter((row) => row.show_in_website).length;
		const parts = [];
		if (createRows.length) parts.push(`se crearán <strong>${createRows.length} productos nuevos</strong> (${stockCount} con entrada de stock y ${webCount} marcados para la web)`);
		if (updateRows.length) parts.push(`se actualizarán precios de <strong>${updateRows.length} productos existentes</strong>`);
		const summarySentence = parts.length ? `En esta operación ${parts.join(" y ")}. Revisa las filas antes de confirmar.` : "Revisa las filas antes de confirmar.";
		const dialog = new frappe.ui.Dialog({
			title: updateRows.length && !createRows.length ? "Confirmar actualización de precios" : "Confirmar carga y actualización de productos",
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "review", options: `
				<p>${summarySentence}</p>
				${this.importTable(preview)}` }],
			secondary_action_label: "Cancelar",
			secondary_action: () => dialog.hide(),
			primary_action_label: updateRows.length && !createRows.length ? "Confirmar y actualizar precios" : "Confirmar y aplicar cambios",
			primary_action: () => {
				dialog.hide();
				if (this.state.importPreview !== preview) return;
				return this.createImportedProducts(preview.token);
			},
		});
		dialog.show();
	}

	async createImportedProducts(token) {
		this.state.importPreview = null;
		this.state.importFile = null;
		const output = this.wrapper.find("#cima-ai-import-preview").text("Aplicando cambios en ERPNext...");
		try {
			const r = await frappe.call({
				method: "cima_ve.api.ai_assistant.confirm_inventory_import",
				args: { token },
				freeze: true,
				freeze_message: "Aplicando productos y precios aprobados...",
			});
			if (!r.message?.ok) throw new Error("No se recibió la confirmación de la operación.");
			const created = (r.message.items || []).map((item) => {
				const tag = item.action === "update_price" ? "Precio actualizado" : "Creado";
				const stockNote = item.stock_entry ? ` — Entrada ${this.escape(item.stock_entry)}` : "";
				return `<li><a href="#" data-item-code="${this.escape(item.item_code)}">${this.escape(item.item_name)} (${this.escape(item.item_code)})</a> — ${tag}${stockNote}</li>`;
			}).join("");
			const counts = [];
			if (r.message.created_count) counts.push(`${this.escape(r.message.created_count)} creados`);
			if (r.message.updated_count) counts.push(`${this.escape(r.message.updated_count)} precios actualizados`);
			const summary = counts.length ? counts.join(" · ") : `${this.escape(r.message.items_count)} procesados`;
			output.html(`<div class="alert alert-success">Operación completada (${summary}).<ul>${created}</ul></div>`);
		} catch {
			output.text("No se pudo confirmar la importación. Vuelve a validar el archivo para comprobar los códigos.");
		}
	}
}