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
			previewing: false,
			asking: false,
		};
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
				<div class="cima-ai-hero">
					<div>
					<h2>Asistente CIMA</h2>
					<p>Consultas con datos resumidos de ERPNext y carga revisada de productos desde CSV/XLSX.</p>
				</div>
				<div>
					<button type="button" class="btn btn-default" data-action="settings">Configuración IA</button>
					<button type="button" class="btn btn-default" data-action="product-loader">Carga de Productos</button>
				</div>
			</div>
			<div id="cima-ai-config-alert"></div>
			<div class="cima-ai-layout">
				<section class="cima-ai-card">
					<h3>Consulta al asistente</h3>
					<div class="text-muted small">Tu pregunta y los resúmenes seleccionados se envían al proveedor IA configurado. Se separan facturas por fecha de emisión, cobros por fecha de pago y Notas de Entrega por fecha de despacho; no se envían nombres de clientes ni comprobantes.</div>
					<div class="cima-ai-scope">
						<div><label>Desde</label><input id="cima-ai-from" type="date" class="form-control" /></div>
						<div><label>Hasta</label><input id="cima-ai-to" type="date" class="form-control" /></div>
						<div><label>Vendedor</label><select id="cima-ai-seller" class="form-control"><option value="">Todos</option></select></div>
						<div><label>Compañía</label><select id="cima-ai-company" class="form-control"><option value="">Todas</option></select></div>
						<div><label>Almacén</label><select id="cima-ai-warehouse" class="form-control"><option value="">Todos</option></select></div>
					</div>
					<div class="cima-ai-suggestions">
						<button type="button" data-prompt="Resume el inventario actual y destaca los productos con menor existencia.">Inventario bajo</button>
						<button type="button" data-prompt="Resume las Notas de Entrega despachadas y sus estados.">Notas de Entrega</button>
						<button type="button" data-prompt="Compara ventas facturadas, cobros registrados y despacho por vendedor en el período seleccionado.">Ventas y vendedores</button>
						<button type="button" data-template="Prepara un borrador para crear este producto: ">Preparar producto</button>
					</div>
					<div id="cima-ai-messages" class="cima-ai-messages" aria-live="polite"></div>
					<div class="cima-ai-compose">
						<textarea id="cima-ai-question" class="form-control" placeholder="Pregunta sobre inventario, ventas, cobros o vendedores..."></textarea>
						<button type="button" id="cima-ai-send" class="btn btn-primary">Enviar</button>
					</div>
				</section>

				<section class="cima-ai-card">
					<h3>Agregar productos desde archivo</h3>
					<div class="cima-ai-import-help">
						Carga un CSV UTF-8 o XLSX de hasta 4 MB y 250 filas. Encabezados admitidos: nombre/<code>item_name</code> (obligatorio), SKU, categoría, unidad, costo, precio Detal, precio Mayor, cantidad inicial, descripción y publicar/web. Los precios/costos/cantidades vacíos quedan en cero; no se publica en la tienda ni se agrega stock salvo que lo indiques y confirmes aquí.
					</div>
					<div class="form-group">
						<label>Almacén para cantidades iniciales</label>
						<select id="cima-ai-import-warehouse" class="form-control"><option value="">Selecciona almacén (si hay cantidades)</option></select>
					</div>
					<div class="form-group">
						<label>Archivo de productos</label>
						<input id="cima-ai-file" type="file" class="form-control" accept=".csv,.xlsx" />
					</div>
					<button type="button" id="cima-ai-preview" class="btn btn-default">Validar y revisar</button>
					<div id="cima-ai-import-preview"></div>
				</section>
			</div>
		`);
		this.addMessage("assistant", "Hola. Puedo resumir inventario, ventas facturadas, cobros y Notas de Entrega. También puedo preparar un borrador de producto; para varios productos, carga un archivo y revisa todas las filas antes de confirmar.");
	}

	bindEvents() {
		this.wrapper.on("click", "#cima-ai-send", () => this.sendMessage());
		this.wrapper.on("keydown", "#cima-ai-question", (event) => {
			if (event.key === "Enter" && !event.shiftKey) {
				event.preventDefault();
				this.sendMessage();
			}
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
		this.wrapper.on("click", "[data-action='settings']", () => frappe.set_route("Form", "Cima VE Settings", "Cima VE Settings"));
		this.wrapper.on("click", "[data-action='product-loader']", () => frappe.set_route("carga-productos"));
		this.wrapper.on("click", "#cima-ai-preview", () => this.previewImport());
		this.wrapper.on("click", "#cima-ai-confirm-import", () => this.confirmImport());
		this.wrapper.on("change", "#cima-ai-file, #cima-ai-import-warehouse", () => {
			this.state.importPreview = null;
			this.wrapper.find("#cima-ai-import-preview").empty();
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
			this.wrapper.find("#cima-ai-send").prop("disabled", true);
		}
	}

	addMessage(role, text, draft = null) {
		this.state.messages.push({ role, content: String(text || ""), draft });
		const messageHtml = this.state.messages
			.map((message, index) => `<div class="cima-ai-message cima-ai-message-${message.role}">${this.escape(message.content)}${message.draft
				? `<div class="mt-2"><button type="button" class="btn btn-default btn-sm" data-draft-index="${index}">Editar borrador en Carga de Productos</button></div>` : ""}</div>`)
			.join("");
		const container = this.wrapper.find("#cima-ai-messages").html(messageHtml);
		container.scrollTop(container[0].scrollHeight);
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
		const history = this.state.messages.slice(-8).map(({ role, content }) => ({ role, content }));
		this.addMessage("user", question);
		input.val("");
		this.state.asking = true;
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
			},
			callback: (r) => {
				if (r.message && r.message.answer) {
					const scope = r.message.scope || {};
					this.addMessage("assistant", `${r.message.answer}\n\nAlcance: ${scope.from_date} a ${scope.to_date}; ${scope.seller}; ${scope.warehouse}; ${scope.company}.`, r.message.product_draft);
				} else {
					this.addMessage("assistant", "No pude completar la consulta. Revisa la configuración del proveedor y vuelve a intentarlo.");
				}
			},
			always: () => {
				this.state.asking = false;
				this.wrapper.find("#cima-ai-send").prop("disabled", false);
			},
		});
	}

	readFile(file) {
		return new Promise((resolve, reject) => {
			const reader = new FileReader();
			reader.onload = () => resolve(String(reader.result || ""));
			reader.onerror = () => reject(new Error("No se pudo leer el archivo."));
			reader.readAsDataURL(file);
		});
	}

	async previewImport() {
		if (this.state.previewing) return;
		const fileInput = this.wrapper.find("#cima-ai-file");
		const warehouseInput = this.wrapper.find("#cima-ai-import-warehouse");
		const file = fileInput[0].files[0];
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

	importTable(preview) {
		const rows = (preview.rows || []).map((row) => {
			const errors = (row.errors || []).join(" ");
			return `<tr>
				<td>${this.escape(row.row)}</td>
				<td>${this.escape(row.item_code)}</td>
				<td>${this.escape(row.item_name)}</td>
				<td>${this.escape(row.description)}</td>
				<td>${this.escape(row.item_group)}</td>
				<td>${this.escape(row.stock_uom)}</td>
				<td>${this.escape(row.cost_rate)}</td>
				<td>${this.escape(row.detal_price)}</td>
				<td>${this.escape(row.mayor_price)}</td>
				<td>${this.escape(row.initial_qty)}</td>
				<td>${Number(row.initial_qty) > 0 ? this.escape(row.warehouse) : "—"}</td>
				<td>${row.show_in_website ? "Sí" : "No"}</td>
				<td class="${errors ? "cima-ai-error" : "cima-ai-ready"}">${this.escape(errors || "Lista para crear")}</td>
			</tr>`;
		}).join("");
		return `<div class="cima-ai-preview-table-wrap" tabindex="0" style="overflow: auto; max-height: 55vh;">
			<table class="cima-ai-preview-table table table-bordered table-sm"><thead><tr><th>Fila</th><th>SKU</th><th>Producto</th><th>Descripción</th><th>Categoría</th><th>Unidad</th><th>Costo</th><th>Detal</th><th>Mayor</th><th>Cantidad inicial</th><th>Almacén</th><th>Web</th><th>Validación</th></tr></thead><tbody>${rows}</tbody></table>
		</div>`;
	}

	renderImportPreview(preview) {
		const button = preview.can_confirm
			? '<button type="button" id="cima-ai-confirm-import" class="btn btn-primary">Revisar y confirmar…</button>'
			: '<div class="alert alert-danger">Corrige las filas con errores y vuelve a cargar el archivo. No se creará ningún producto.</div>';
		this.wrapper.find("#cima-ai-import-preview").html(`
			<p class="mt-2"><strong>${this.escape(preview.row_count)} filas</strong>. La vista previa expira en 10 minutos y solo puede confirmarse una vez.</p>
			${this.importTable(preview)}
			<div class="mt-3">${button}</div>
		`);
	}

	confirmImport() {
		const preview = this.state.importPreview;
		if (!preview?.token) return;
		const stockCount = preview.rows.filter((row) => Number(row.initial_qty) > 0).length;
		const webCount = preview.rows.filter((row) => row.show_in_website).length;
		const dialog = new frappe.ui.Dialog({
			title: "Confirmar creación de productos",
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "review", options: `
				<p>Se crearán <strong>${this.escape(preview.row_count)} productos</strong>: ${stockCount} con entrada de stock y ${webCount} marcados para la web. Revisa las filas antes de confirmar.</p>
				${this.importTable(preview)}` }],
			secondary_action_label: "Cancelar",
			secondary_action: () => dialog.hide(),
			primary_action_label: "Confirmar y crear productos",
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
		const output = this.wrapper.find("#cima-ai-import-preview").text("Creando productos...");
		try {
			const r = await frappe.call({
				method: "cima_ve.api.ai_assistant.confirm_inventory_import",
				args: { token },
				freeze: true,
				freeze_message: "Creando productos e inventario inicial aprobado...",
			});
			if (!r.message?.ok) throw new Error("No se recibió la confirmación de la operación.");
			const created = (r.message.items || []).map((item) =>
				`<li><a href="#" data-item-code="${this.escape(item.item_code)}">${this.escape(item.item_name)} (${this.escape(item.item_code)})</a>${item.stock_entry ? ` — Entrada ${this.escape(item.stock_entry)}` : ""}</li>`
			).join("");
			output.html(`<div class="alert alert-success">Se crearon ${this.escape(r.message.items_count)} productos.<ul>${created}</ul></div>`);
		} catch {
			output.text("No se pudo confirmar la importación. Vuelve a validar el archivo para comprobar qué códigos ya existen.");
		}
	}
}