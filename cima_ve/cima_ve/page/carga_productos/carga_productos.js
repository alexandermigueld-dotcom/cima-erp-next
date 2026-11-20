frappe.pages["carga-productos"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Carga de Productos y Lotes",
		single_column: true,
	});

	wrapper.cimaProductLoader = new CimaProductLoader(page, wrapper);
};

frappe.pages["carga-productos"].on_page_show = function (wrapper) {
	const draft = frappe.cimaAssistantProductDraft;
	if (!draft) return;
	delete frappe.cimaAssistantProductDraft;
	wrapper.cimaProductLoader.offerAssistantDraft(draft);
};

class CimaProductLoader {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = $(wrapper);
		this.state = {
			activeTab: "nuevo",
			bootstrap: {
				warehouses: [],
				item_groups: [],
				uoms: [],
				default_warehouse: "",
				default_item_group: "Products",
				default_uom: "Nos",
				detal_price_list: "",
				mayor_price_list: "",
				exchange_rate: {},
			},
			newImage: { fileName: "", base64: "" },
			reviewingProduct: false,
			products: [],
			batchItems: [],
		};

		this.renderShell();
		this.bindEvents();
		this.loadBootstrap();
	}

	offerAssistantDraft(draft) {
		const root = this.wrapper;
		this.switchTab("nuevo");
		const alert = root.find("#cp-alert-area");
		const fields = root.find("#cp-new-name, #cp-new-code, #cp-new-desc, #cp-new-cost, #cp-new-detal, #cp-new-mayor, #cp-new-image");
		const applyDraft = () => {
			root.find("#cp-new-name").val(draft.item_name);
			root.find("#cp-new-code").val(draft.item_code || "");
			root.find("#cp-new-desc").val(draft.description || "");
			root.find("#cp-new-cost, #cp-new-detal, #cp-new-mayor, #cp-new-image").val("");
			root.find("#cp-new-qty").val("0");
			root.find("#cp-new-web").prop("checked", false);
			root.find("#cp-new-detal-bs, #cp-new-mayor-bs").text("");
			root.find("#cp-new-img-preview").text("Sin imagen");
			this.state.newImage = { fileName: "", base64: "" };
			alert.html('<div class="alert alert-info">Borrador de Asistente CIMA. Revisa y completa los campos; aún no se ha creado ningún producto.</div>');
		};
		if (fields.toArray().some((field) => field.value) || Number(root.find("#cp-new-qty").val()) > 0) {
			alert.html('<div class="alert alert-info">Hay un formulario en curso. <button type="button" class="btn btn-default btn-sm">Reemplazar con el borrador de Asistente CIMA</button></div>');
			alert.find("button").one("click", applyDraft);
		} else {
			applyDraft();
		}
	}

	getBsRate() {
		const fx = this.state.bootstrap?.exchange_rate || {};
		return Number(fx.adjusted_rate || fx.bcv_rate || 0);
	}

	formatBs(usd) {
		const rate = this.getBsRate();
		if (rate <= 0 || !usd) return "";
		const bs = Number(usd || 0) * rate;
		return `≈ Bs. ${bs.toLocaleString("es-VE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
	}

	renderShell() {
		const html = `
			<div class="cima-cp-shell">
				<div class="cima-cp-hero">
					<div class="cima-hero-brand">
						<img src="/assets/cima_ve/images/cima-logo-blanco.png" alt="CIMA" class="cima-hero-logo" onerror="this.style.display='none'" />
						<div>
							<h2>Carga de Productos y Lotes</h2>
							<p>Crea productos nuevos con foto y precios, o agrega lotes de inventario de forma rápida.</p>
						</div>
					</div>
					<div class="cima-cp-hero-actions">
						<button type="button" class="cima-cp-btn-nav" data-nav="venta-rapida">Facturación Rápida</button>
						<button type="button" class="cima-cp-btn-nav" data-nav="notas-entrega">Notas de Entrega</button>
					</div>
				</div>

				<div id="cp-alert-area"></div>

				<div class="cima-cp-tabs">
					<button type="button" class="cima-cp-tab active" data-tab="nuevo">+ Nuevo Producto</button>
					<button type="button" class="cima-cp-tab" data-tab="lote">Agregar Lote / Entrada de Stock</button>
					<button type="button" class="cima-cp-tab" data-tab="catalogo">Catálogo Rápido (Precios e Imágenes)</button>
				</div>

				<div id="cp-view-nuevo" class="cima-cp-card">
					<div class="cima-cp-card-title">
						<span>Registrar Nuevo Producto</span>
						<span class="small text-muted" id="cp-fx-badge"></span>
					</div>

					<div class="cima-cp-grid-2">
						<div class="form-group">
							<label class="control-label">Nombre del Producto *</label>
							<input type="text" id="cp-new-name" class="form-control" placeholder="Ej. Cargador USB-C 20W Original" />
						</div>
						<div class="form-group">
							<label class="control-label">Código / SKU (opcional — se autogenera si lo dejas vacío)</label>
							<input type="text" id="cp-new-code" class="form-control" placeholder="Ej. CARG-USBC-20W" />
						</div>
					</div>

					<div class="cima-cp-grid-3">
						<div class="form-group">
							<label class="control-label">Categoría</label>
							<select id="cp-new-group" class="form-control"></select>
						</div>
						<div class="form-group">
							<label class="control-label">Unidad de Medida</label>
							<select id="cp-new-uom" class="form-control"></select>
						</div>
						<div class="form-group">
							<label class="control-label">Almacén Inicial</label>
							<select id="cp-new-warehouse" class="form-control"></select>
						</div>
					</div>

					<div class="cima-cp-grid-3">
						<div class="form-group">
							<label class="control-label">Costo Unitario ($ USD)</label>
							<input type="number" step="0.01" min="0" id="cp-new-cost" class="form-control" placeholder="0.00" />
						</div>
						<div class="form-group">
							<label class="control-label">Precio Detal ($ USD)</label>
							<input type="number" step="0.01" min="0" id="cp-new-detal" class="form-control" placeholder="0.00" />
							<div class="small text-muted mt-1" id="cp-new-detal-bs"></div>
						</div>
						<div class="form-group">
							<label class="control-label">Precio Mayor ($ USD)</label>
							<input type="number" step="0.01" min="0" id="cp-new-mayor" class="form-control" placeholder="0.00" />
							<div class="small text-muted mt-1" id="cp-new-mayor-bs"></div>
						</div>
					</div>

					<div class="cima-cp-grid-2">
						<div class="form-group">
							<label class="control-label">Cantidad Inicial en Stock</label>
							<input type="number" step="1" min="0" id="cp-new-qty" class="form-control" value="0" />
							<div class="small text-muted mt-1">Si es mayor a 0, se crea automáticamente la entrada de inventario.</div>
						</div>
						<div class="form-group">
							<label class="control-label">Descripción breve (opcional)</label>
							<input type="text" id="cp-new-desc" class="form-control" placeholder="Detalles para vendedores y Tienda Web" />
						</div>
					</div>

					<div class="cima-cp-grid-2" style="align-items:center;">
						<div class="form-group">
							<label class="control-label">Imagen del Producto (para /tienda y catálogo)</label>
							<div style="display:flex;gap:12px;align-items:center;">
								<div class="cima-cp-img-preview" id="cp-new-img-preview">Sin imagen</div>
								<div>
									<input type="file" id="cp-new-image" class="form-control input-sm" accept="image/*" />
									<div class="small text-muted mt-1">PNG, JPG o WEBP (máx. 5 MB).</div>
								</div>
							</div>
						</div>
						<div class="form-group">
							<label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-top:14px;">
								<input type="checkbox" id="cp-new-web" checked />
								<span>Habilitar para venta y Tienda Web (/tienda)</span>
							</label>
						</div>
					</div>

					<div class="mt-3">
						<button type="button" class="btn btn-primary" id="cp-btn-create-product">
							Guardar Producto
						</button>
					</div>
				</div>

				<div id="cp-view-lote" style="display:none;">
					<div class="cima-cp-batch-layout">
						<div class="cima-cp-card">
							<div class="cima-cp-card-title">
								<span>1. Buscar Producto Existente</span>
							</div>
							<div class="form-group">
								<input type="text" id="cp-batch-search" class="form-control" placeholder="Buscar por nombre, SKU o categoría..." />
							</div>
							<div id="cp-batch-search-results" style="max-height:460px;overflow:auto;"></div>
						</div>

						<div class="cima-cp-card">
							<div class="cima-cp-card-title">
								<span>2. Lote de Entrada de Inventario</span>
								<button type="button" class="btn btn-xs btn-default" id="cp-btn-clear-batch">Limpiar</button>
							</div>
							<div class="cima-cp-grid-2">
								<div class="form-group">
									<label class="control-label">Almacén Destino *</label>
									<select id="cp-batch-warehouse" class="form-control"></select>
								</div>
								<div class="form-group">
									<label class="control-label">Referencia / Proveedor del Lote</label>
									<input type="text" id="cp-batch-ref" class="form-control" placeholder="Ej. Lote Noviembre - Pantallas y Cargadores" />
								</div>
							</div>
							<div class="table-responsive">
								<table class="table table-bordered table-sm">
									<thead>
										<tr>
											<th>Producto</th>
											<th style="width:85px;">Cant.</th>
											<th style="width:95px;">Costo ($)</th>
											<th style="width:95px;">Detal ($)</th>
											<th style="width:95px;">Mayor ($)</th>
											<th style="width:36px;"></th>
										</tr>
									</thead>
									<tbody id="cp-batch-tbody"></tbody>
								</table>
							</div>
							<div class="d-flex justify-content-between align-items-center mt-2" style="display:flex;justify-content:space-between;align-items:center;">
								<div class="small text-muted" id="cp-batch-summary">0 productos en el lote</div>
								<button type="button" class="btn btn-success" id="cp-btn-submit-batch">
									Confirmar Entrada de Lote
								</button>
							</div>
						</div>
					</div>
				</div>

				<div id="cp-view-catalogo" class="cima-cp-card" style="display:none;">
					<div class="cima-cp-card-title">
						<span>Catálogo Rápido — Editar Precios e Imágenes</span>
						<div style="display:flex;gap:8px;align-items:center;">
							<input type="text" id="cp-cat-search" class="form-control input-sm" style="width:260px;" placeholder="Buscar producto..." />
							<button type="button" class="btn btn-sm btn-default" id="cp-cat-refresh">Actualizar</button>
						</div>
					</div>
					<div class="table-responsive">
						<table class="table table-bordered table-hover table-sm">
							<thead>
								<tr>
									<th style="width:54px;">Foto</th>
									<th>Producto / SKU</th>
									<th>Categoría</th>
									<th class="text-right">Stock</th>
									<th class="text-right">Costo ($)</th>
									<th class="text-right">Detal ($)</th>
									<th class="text-right">Mayor ($)</th>
									<th style="width:100px;">Acción</th>
								</tr>
							</thead>
							<tbody id="cp-cat-tbody"></tbody>
						</table>
					</div>
				</div>
			</div>
		`;
		this.wrapper.find(".layout-main-section").html(html);
	}

	bindEvents() {
		const root = this.wrapper;

		root.on("click", "[data-nav]", (e) => {
			frappe.set_route($(e.currentTarget).attr("data-nav"));
		});

		root.on("click", ".cima-cp-tab", (e) => {
			const tab = $(e.currentTarget).attr("data-tab");
			this.switchTab(tab);
		});

		root.on("input", "#cp-new-detal", (e) => {
			const val = parseFloat($(e.target).val() || 0);
			root.find("#cp-new-detal-bs").text(this.formatBs(val));
		});

		root.on("input", "#cp-new-mayor", (e) => {
			const val = parseFloat($(e.target).val() || 0);
			root.find("#cp-new-mayor-bs").text(this.formatBs(val));
		});

		root.on("change", "#cp-new-image", async (e) => {
			const file = e.target.files && e.target.files[0];
			if (!file) {
				this.state.newImage = { fileName: "", base64: "" };
				root.find("#cp-new-img-preview").html("Sin imagen");
				return;
			}
			const b64 = await this.readFileAsDataUrl(file);
			this.state.newImage = { fileName: file.name, base64: b64 };
			root.find("#cp-new-img-preview").html(`<img src="${b64}" alt="Vista previa" />`);
		});

		root.on("click", "#cp-btn-create-product", () => this.submitNewProduct());

		let batchTimer = null;
		root.on("input", "#cp-batch-search", (e) => {
			clearTimeout(batchTimer);
			const q = $(e.target).val();
			batchTimer = setTimeout(() => this.loadProducts(q), 220);
		});

		root.on("change", "#cp-batch-warehouse", () => {
			this.loadProducts(root.find("#cp-batch-search").val() || "");
		});

		root.on("click", "[data-add-batch]", (e) => {
			const code = $(e.currentTarget).attr("data-add-batch");
			const prod = this.state.products.find((p) => p.item_code === code);
			if (prod) this.addProductToBatch(prod);
		});

		root.on("input change", "[data-batch-field]", (e) => {
			const idx = parseInt($(e.currentTarget).attr("data-batch-idx"), 10);
			const field = $(e.currentTarget).attr("data-batch-field");
			if (!this.state.batchItems[idx]) return;
			const raw = $(e.currentTarget).val();
			this.state.batchItems[idx][field] = raw === "" ? "" : parseFloat(raw);
			this.updateBatchSummary();
		});

		root.on("click", "[data-remove-batch]", (e) => {
			const idx = parseInt($(e.currentTarget).attr("data-remove-batch"), 10);
			this.state.batchItems.splice(idx, 1);
			this.renderBatchTable();
		});

		root.on("click", "#cp-btn-clear-batch", () => {
			this.state.batchItems = [];
			this.renderBatchTable();
		});

		root.on("click", "#cp-btn-submit-batch", () => this.submitBatch());

		let catTimer = null;
		root.on("input", "#cp-cat-search", (e) => {
			clearTimeout(catTimer);
			const q = $(e.target).val();
			catTimer = setTimeout(() => this.loadProducts(q), 220);
		});

		root.on("click", "#cp-cat-refresh", () => {
			this.loadProducts(root.find("#cp-cat-search").val() || "");
		});

		root.on("click", "[data-edit-product]", (e) => {
			const code = $(e.currentTarget).attr("data-edit-product");
			const prod = this.state.products.find((p) => p.item_code === code);
			if (prod) this.openQuickEditDialog(prod);
		});
	}

	switchTab(tab) {
		this.state.activeTab = tab;
		this.wrapper.find(".cima-cp-tab").removeClass("active");
		this.wrapper.find(`.cima-cp-tab[data-tab="${tab}"]`).addClass("active");
		this.wrapper.find("#cp-view-nuevo").toggle(tab === "nuevo");
		this.wrapper.find("#cp-view-lote").toggle(tab === "lote");
		this.wrapper.find("#cp-view-catalogo").toggle(tab === "catalogo");
		if (tab === "lote" || tab === "catalogo") {
			const q = tab === "lote"
				? this.wrapper.find("#cp-batch-search").val()
				: this.wrapper.find("#cp-cat-search").val();
			this.loadProducts(q || "");
		}
	}

	readFileAsDataUrl(file) {
		return new Promise((resolve, reject) => {
			const reader = new FileReader();
			reader.onload = () => resolve(String(reader.result || ""));
			reader.onerror = () => reject(new Error("read_error"));
			reader.readAsDataURL(file);
		});
	}

	loadBootstrap() {
		frappe.call({
			method: "cima_ve.api.products.get_product_loader_bootstrap",
			callback: (r) => {
				if (!r.message) return;
				this.state.bootstrap = r.message;
				const b = r.message;

				const whHtml = (b.warehouses || [])
					.map((w) => `<option value="${frappe.utils.escape_html(w.name)}">${frappe.utils.escape_html(w.warehouse_name || w.name)}</option>`)
					.join("");
				const grpHtml = (b.item_groups || [])
					.map((g) => `<option value="${frappe.utils.escape_html(g)}">${frappe.utils.escape_html(g)}</option>`)
					.join("");
				const uomHtml = (b.uoms || [])
					.map((u) => `<option value="${frappe.utils.escape_html(u)}">${frappe.utils.escape_html(u)}</option>`)
					.join("");

				this.wrapper.find("#cp-new-warehouse, #cp-batch-warehouse").html(whHtml).val(b.default_warehouse || "");
				this.wrapper.find("#cp-new-group").html(grpHtml).val(b.default_item_group || "");
				this.wrapper.find("#cp-new-uom").html(uomHtml).val(b.default_uom || "");

				const fxRate = this.getBsRate();
				if (fxRate > 0) {
					this.wrapper.find("#cp-fx-badge").text(`Tasa referencia: Bs. ${fxRate.toFixed(2)} / USD`);
				}
				this.renderBatchTable();
			},
		});
	}

	loadProducts(query) {
		const warehouse = this.wrapper.find("#cp-batch-warehouse").val() || this.state.bootstrap.default_warehouse || "";
		frappe.call({
			method: "cima_ve.api.products.search_products_for_batch",
			args: { query: query || "", warehouse, limit: 80 },
			callback: (r) => {
				this.state.products = r.message || [];
				this.renderBatchSearchResults();
				this.renderCatalogTable();
			},
		});
	}

	async submitNewProduct() {
		if (this.state.reviewingProduct) return;
		const root = this.wrapper;
		const itemName = (root.find("#cp-new-name").val() || "").trim();
		if (!itemName) {
			frappe.msgprint("Ingresa el nombre del producto.");
			return;
		}
		const payload = {
			item_name: itemName,
			item_code: (root.find("#cp-new-code").val() || "").trim(),
			item_group: root.find("#cp-new-group").val() || "Products",
			stock_uom: root.find("#cp-new-uom").val() || "Nos",
			warehouse: root.find("#cp-new-warehouse").val() || "",
			cost_rate: root.find("#cp-new-cost").val() || 0,
			detal_price: root.find("#cp-new-detal").val() || 0,
			mayor_price: root.find("#cp-new-mayor").val() || 0,
			initial_qty: root.find("#cp-new-qty").val() || 0,
			description: (root.find("#cp-new-desc").val() || "").trim(),
			show_in_website: root.find("#cp-new-web").is(":checked") ? 1 : 0,
		};
		const image = this.state.newImage;
		this.state.reviewingProduct = true;
		try {
			const r = await frappe.call({
				method: "cima_ve.api.products.preview_quick_product",
				args: { product: JSON.stringify(payload) },
				freeze: true,
				freeze_message: "Validando producto y código SKU...",
			});
			if (r.message) this.reviewNewProduct(r.message, image);
		} catch {
			// Frappe muestra los errores de validación del servidor.
		} finally {
			this.state.reviewingProduct = false;
		}
	}

	reviewNewProduct(product, image) {
		const b = this.state.bootstrap;
		const rows = [
			["Producto", product.item_name], ["SKU", product.item_code], ["Descripción", product.description],
			["Categoría", product.item_group], ["Unidad", product.stock_uom], ["Costo unitario (USD)", product.cost_rate],
			["Precio Detal (USD)", product.detal_price > 0 && b.detal_price_list ? product.detal_price : "Sin registro de precio"],
			["Precio Mayor (USD)", product.mayor_price > 0 && b.mayor_price_list ? product.mayor_price : "Sin registro de precio"],
			["Cantidad inicial", product.initial_qty], ["Almacén", product.initial_qty > 0 ? product.warehouse : "Sin entrada de stock"],
			["Marcado para la web", product.show_in_website ? "Sí" : "No"], ["Imagen", image.fileName || "Sin imagen"],
		].map(([label, value]) => `<tr><th scope="row">${label}</th><td>${frappe.utils.escape_html(String(value))}</td></tr>`).join("");
		let approved = false;
		const dialog = new frappe.ui.Dialog({
			title: "Confirmar nuevo producto",
			fields: [{ fieldtype: "HTML", fieldname: "review", options: `
				<p>Revisa los valores que se guardarán en ERPNext.</p>
				<div style="overflow:auto; max-height:55vh;" tabindex="0">
					<table class="table table-bordered table-sm"><thead><tr><th>Campo</th><th>Valor</th></tr></thead><tbody>${rows}</tbody></table>
				</div>` }],
			secondary_action_label: "Cancelar",
			secondary_action: () => dialog.hide(),
			primary_action_label: "Confirmar y crear producto",
			primary_action: () => {
				if (approved) return;
				approved = true;
				dialog.hide();
				this.createNewProduct({
					...product,
					show_in_website: Number(product.show_in_website),
					image_file_name: image.fileName || "",
					image_data_base64: image.base64 || "",
				});
			},
		});
		dialog.show();
	}

	createNewProduct(payload) {
		const root = this.wrapper;
		frappe.call({
			method: "cima_ve.api.products.create_quick_product",
			args: payload,
			freeze: true,
			freeze_message: "Guardando producto...",
			callback: (r) => {
				if (!r.message || !r.message.ok) return;
				const res = r.message;
				root.find("#cp-alert-area").html(`
					<div class="alert alert-success">
						Producto <strong>${frappe.utils.escape_html(res.item_name)}</strong> (${frappe.utils.escape_html(res.item_code)}) creado correctamente.
						${res.stock_entry ? ` Entrada de inventario: <strong>${frappe.utils.escape_html(res.stock_entry)}</strong>.` : ""}
					</div>
				`);
				root.find("#cp-new-name, #cp-new-code, #cp-new-cost, #cp-new-detal, #cp-new-mayor, #cp-new-desc, #cp-new-image").val("");
				root.find("#cp-new-qty").val("0");
				root.find("#cp-new-detal-bs, #cp-new-mayor-bs").text("");
				root.find("#cp-new-img-preview").html("Sin imagen");
				this.state.newImage = { fileName: "", base64: "" };
			},
		});
	}

	renderBatchSearchResults() {
		const container = this.wrapper.find("#cp-batch-search-results");
		if (!this.state.products.length) {
			container.html(`<div class="text-muted text-center p-3">No se encontraron productos.</div>`);
			return;
		}
		container.html(
			this.state.products
				.map(
					(p) => `
				<div style="display:flex;justify-content:space-between;align-items:center;padding:8px;border-bottom:1px solid #e2e8f0;gap:8px;">
					<div>
						<div><strong>${frappe.utils.escape_html(p.item_name)}</strong></div>
						<div class="small text-muted">${frappe.utils.escape_html(p.item_code)} · Stock: <strong>${Number(p.stock_qty || 0)}</strong> · Detal: $${Number(p.detal_price || 0).toFixed(2)}</div>
					</div>
					<button type="button" class="btn btn-xs btn-primary" data-add-batch="${frappe.utils.escape_html(p.item_code)}">+ Agregar</button>
				</div>`
				)
				.join("")
		);
	}

	addProductToBatch(prod) {
		const existing = this.state.batchItems.find((b) => b.item_code === prod.item_code);
		if (existing) {
			existing.qty = Number(existing.qty || 0) + 1;
		} else {
			const baseCost = Number(prod.valuation_rate || prod.last_purchase_rate || 0);
			this.state.batchItems.push({
				item_code: prod.item_code,
				item_name: prod.item_name,
				qty: 1,
				incoming_rate: baseCost,
				detal_price: Number(prod.detal_price || 0) || "",
				mayor_price: Number(prod.mayor_price || 0) || "",
			});
		}
		this.renderBatchTable();
	}

	renderBatchTable() {
		const tbody = this.wrapper.find("#cp-batch-tbody");
		if (!this.state.batchItems.length) {
			tbody.html(`<tr><td colspan="6" class="text-center text-muted p-3">Busca y agrega productos desde la columna izquierda.</td></tr>`);
			this.updateBatchSummary();
			return;
		}
		tbody.html(
			this.state.batchItems
				.map(
					(row, idx) => `
				<tr>
					<td>
						<strong>${frappe.utils.escape_html(row.item_name)}</strong>
						<div class="small text-muted">${frappe.utils.escape_html(row.item_code)}</div>
					</td>
					<td><input type="number" min="1" step="1" class="form-control input-sm" data-batch-idx="${idx}" data-batch-field="qty" value="${row.qty}" /></td>
					<td><input type="number" min="0" step="0.01" class="form-control input-sm" data-batch-idx="${idx}" data-batch-field="incoming_rate" value="${row.incoming_rate}" /></td>
					<td><input type="number" min="0" step="0.01" class="form-control input-sm" data-batch-idx="${idx}" data-batch-field="detal_price" value="${row.detal_price}" /></td>
					<td><input type="number" min="0" step="0.01" class="form-control input-sm" data-batch-idx="${idx}" data-batch-field="mayor_price" value="${row.mayor_price}" /></td>
					<td class="text-center"><button type="button" class="btn btn-xs btn-danger" data-remove-batch="${idx}">✕</button></td>
				</tr>`
				)
				.join("")
		);
		this.updateBatchSummary();
	}

	updateBatchSummary() {
		const count = this.state.batchItems.length;
		const totalQty = this.state.batchItems.reduce((acc, r) => acc + Number(r.qty || 0), 0);
		const totalCost = this.state.batchItems.reduce((acc, r) => acc + Number(r.qty || 0) * Number(r.incoming_rate || 0), 0);
		this.wrapper.find("#cp-batch-summary").text(
			`${count} producto(s) · ${totalQty} unidades · Costo total lote: $${totalCost.toFixed(2)}`
		);
	}

	submitBatch() {
		if (!this.state.batchItems.length) {
			frappe.msgprint("Agrega al menos un producto al lote.");
			return;
		}
		const warehouse = this.wrapper.find("#cp-batch-warehouse").val() || "";
		const reference = (this.wrapper.find("#cp-batch-ref").val() || "").trim();
		frappe.call({
			method: "cima_ve.api.products.add_stock_batch",
			args: {
				items: JSON.stringify(this.state.batchItems),
				warehouse,
				reference,
			},
			freeze: true,
			freeze_message: "Registrando entrada de lote...",
			callback: (r) => {
				if (!r.message || !r.message.ok) return;
				const res = r.message;
				this.wrapper.find("#cp-alert-area").html(`
					<div class="alert alert-success">
						Lote registrado correctamente (<strong>${frappe.utils.escape_html(res.stock_entry)}</strong>):
						${res.items_count} producto(s), ${res.total_qty} unidades, costo total $${Number(res.total_cost || 0).toFixed(2)}.
					</div>
				`);
				this.state.batchItems = [];
				this.wrapper.find("#cp-batch-ref").val("");
				this.renderBatchTable();
				this.loadProducts(this.wrapper.find("#cp-batch-search").val() || "");
			},
		});
	}

	renderCatalogTable() {
		const tbody = this.wrapper.find("#cp-cat-tbody");
		if (!this.state.products.length) {
			tbody.html(`<tr><td colspan="8" class="text-center text-muted p-3">Sin productos para mostrar.</td></tr>`);
			return;
		}
		tbody.html(
			this.state.products
				.map((p) => {
					const imgCell = p.website_image
						? `<img src="${encodeURI(p.website_image)}" class="cima-cp-thumb" alt="Foto" />`
						: `<span class="label label-default" style="font-size:10px;">Sin foto</span>`;
					return `
						<tr>
							<td class="text-center">${imgCell}</td>
							<td><strong>${frappe.utils.escape_html(p.item_name)}</strong><div class="small text-muted">${frappe.utils.escape_html(p.item_code)}</div></td>
							<td class="small">${frappe.utils.escape_html(p.item_group || "")}</td>
							<td class="text-right"><strong>${Number(p.stock_qty || 0)}</strong></td>
							<td class="text-right">$${Number(p.valuation_rate || 0).toFixed(2)}</td>
							<td class="text-right">$${Number(p.detal_price || 0).toFixed(2)}</td>
							<td class="text-right">$${Number(p.mayor_price || 0).toFixed(2)}</td>
							<td><button type="button" class="btn btn-xs btn-primary" data-edit-product="${frappe.utils.escape_html(p.item_code)}">Editar</button></td>
						</tr>
					`;
				})
				.join("")
		);
	}

	openQuickEditDialog(prod) {
		const d = new frappe.ui.Dialog({
			title: `Editar ${prod.item_name}`,
			fields: [
				{
					label: "Costo Unitario ($ USD)",
					fieldname: "cost_rate",
					fieldtype: "Float",
					default: Number(prod.valuation_rate || 0),
				},
				{
					label: "Precio Detal ($ USD)",
					fieldname: "detal_price",
					fieldtype: "Float",
					default: Number(prod.detal_price || 0),
				},
				{
					label: "Precio Mayor ($ USD)",
					fieldname: "mayor_price",
					fieldtype: "Float",
					default: Number(prod.mayor_price || 0),
				},
				{
					fieldtype: "HTML",
					fieldname: "img_box",
					options: `
						<div class="form-group">
							<label class="control-label small">Nueva Imagen (opcional)</label>
							<input type="file" id="cp-edit-image" class="form-control input-sm" accept="image/*" />
						</div>
					`,
				},
			],
			primary_action_label: "Guardar Cambios",
			primary_action: async (values) => {
				const fileInput = d.$wrapper.find("#cp-edit-image")[0];
				const file = fileInput && fileInput.files && fileInput.files[0];
				let fileName = "";
				let b64 = "";
				if (file) {
					fileName = file.name;
					b64 = await this.readFileAsDataUrl(file);
				}
				frappe.call({
					method: "cima_ve.api.products.update_product_quick_details",
					args: {
						item_code: prod.item_code,
						cost_rate: values.cost_rate,
						detal_price: values.detal_price,
						mayor_price: values.mayor_price,
						image_file_name: fileName,
						image_data_base64: b64,
					},
					freeze: true,
					freeze_message: "Actualizando producto...",
					callback: (r) => {
						if (r.message && r.message.ok) {
							d.hide();
							frappe.show_alert({ message: "Producto actualizado", indicator: "green" });
							this.loadProducts(this.wrapper.find("#cp-cat-search").val() || "");
						}
					},
				});
			},
		});
		d.show();
	}
}
