const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function setup() {
	const dialogs = [];
	const requests = [];
	const frappe = {
		pages: { "asistente-cima": {}, "carga-productos": {} },
		ui: { Dialog: class {
			constructor(options) { dialogs.push(options); }
			show() {}
			hide() {}
		} },
		utils: { escape_html: (text) => text.replaceAll("<", "&lt;") },
		call(options) { requests.push(options); },
	};
	const context = vm.createContext({ frappe });
	for (const page of ["asistente_cima", "carga_productos"]) {
		vm.runInContext(readFileSync(join(__dirname, "..", "cima_ve", "cima_ve", "page", page, `${page}.js`), "utf8"), context);
	}
	const assistant = vm.runInContext("Object.create(CimaAssistant.prototype)", context);
	const loader = vm.runInContext("Object.create(CimaProductLoader.prototype)", context);
	return { dialogs, requests, frappe, assistant, loader };
}

test("import confirms only the displayed preview, never on cancel or after it changes", () => {
	const { dialogs, assistant } = setup();
	const preview = { token: "reviewed", row_count: 1, rows: [{ item_name: "<Cable>", initial_qty: 2, warehouse: "WH" }] };
	const submitted = [];
	assistant.state = { importPreview: preview };
	assistant.createImportedProducts = (token) => { submitted.push(token); assistant.state.importPreview = null; };
	assistant.confirmImport();
	assert.match(dialogs[0].fields[0].options, /<table.*&lt;Cable>/s);
	dialogs[0].secondary_action();
	assert.deepEqual(submitted, []);
	assistant.confirmImport();
	assistant.state.importPreview = { ...preview, token: "other" };
	dialogs[1].primary_action();
	assert.deepEqual(submitted, []);
	assistant.state.importPreview = preview;
	assistant.confirmImport();
	dialogs[2].primary_action();
	dialogs[2].primary_action();
	assert.deepEqual(submitted, ["reviewed"]);
});

test("product draft handoff is consumed once and the review sends the displayed SKU on confirmation only", () => {
	const { dialogs, requests, frappe, loader } = setup();
	const draft = { item_name: "Cable" };
	const received = [];
	const wrapper = { cimaProductLoader: { offerAssistantDraft: (value) => received.push(value) } };
	frappe.cimaAssistantProductDraft = draft;
	frappe.pages["carga-productos"].on_page_show(wrapper);
	frappe.pages["carga-productos"].on_page_show(wrapper);
	assert.deepEqual(received, [draft]);
	assert.equal(requests.length, 0);

	loader.state = { bootstrap: {} };
	loader.wrapper = {};
	const product = { ...draft, item_code: "CABLE", initial_qty: 0, show_in_website: false };
	loader.reviewNewProduct(product, {});
	assert.match(dialogs[0].fields[0].options, /<table.*CABLE/s);
	dialogs[0].secondary_action();
	assert.equal(requests.length, 0);
	loader.reviewNewProduct(product, {});
	dialogs[1].primary_action();
	dialogs[1].primary_action();
	assert.equal(requests.length, 1);
	assert.equal(requests[0].method, "cima_ve.api.products.create_quick_product");
	assert.equal(requests[0].args.item_code, "CABLE");
	assert.equal(requests[0].args.show_in_website, 0);
});

test("reporting calls only the chat endpoint and does not open a confirmation", () => {
	const { dialogs, requests, assistant } = setup();
	assistant.state = { bootstrap: { enabled: true, configured: true }, messages: [] };
	assistant.wrapper = { find: (selector) => ({ val: () => selector === "#cima-ai-question" ? "Resume el inventario" : "", prop() {} }) };
	const messages = [];
	assistant.addMessage = (...args) => {
		messages.push(args);
		const message = { role: args[0], content: args[1], includeInHistory: args[3]?.includeInHistory !== false };
		assistant.state.messages.push(message);
		return message;
	};
	assistant.sendMessage();
	requests[0].callback({ message: { answer: "Informe", scope: {} } });
	assert.equal(requests.length, 1);
	assert.equal(requests[0].method, "cima_ve.api.ai_assistant.ask_assistant");
	assert.match(messages[1][1], /^Informe/);
	assert.equal(dialogs.length, 0);
});

test("chat shows pending state and keeps failed turns out of history until retry succeeds", () => {
	const { requests, assistant } = setup();
	const values = { "#cima-ai-question": "Resume inventario" };
	const properties = {};
	const element = (selector) => ({
		0: { scrollHeight: 40 },
		val(value) {
			if (arguments.length) values[selector] = value;
			return values[selector] || "";
		},
		prop(name, value) { properties[`${selector}:${name}`] = value; return this; },
		html() { return this; },
		scrollTop() { return this; },
	});
	assistant.wrapper = { find: element };
	assistant.state = { bootstrap: { enabled: true, configured: true }, messages: [], asking: false, retryRequest: null };
	assistant.sendMessage();
	assert.equal(assistant.state.asking, true);
	assert.equal(properties["#cima-ai-pending:hidden"], false);
	assert.equal(JSON.parse(requests[0].args.history).length, 0);

	requests[0].error({ message: "El proveedor está temporalmente saturado." });
	requests[0].always();
	assert.equal(assistant.state.asking, false);
	assert.equal(properties["#cima-ai-pending:hidden"], true);
	assert.equal(assistant.state.messages.every((message) => message.includeInHistory === false), true);

	assistant.retryLastQuestion();
	assert.equal(requests.length, 2);
	assert.equal(JSON.parse(requests[1].args.history).length, 0);
	requests[1].callback({ message: { answer: "Inventario estable", scope: {} } });
	requests[1].always();
	assert.equal(assistant.state.messages.find((message) => message.role === "user").includeInHistory, true);
	assert.equal(assistant.state.messages.filter((message) => message.error).every((message) => !message.includeInHistory), true);
});

test("dropping a spreadsheet starts preview only and never confirms an import", () => {
	const { requests, assistant } = setup();
	const handlers = {};
	const file = { name: "products.xlsx", size: 128 };
	const previewed = [];
	assistant.state = { importFile: null, importPreview: { token: "old-preview" }, previewing: false };
	assistant.wrapper = {
		on(event, selector, handler) {
			if (typeof selector === "string" && typeof handler === "function") handlers[`${event}:${selector}`] = handler;
		},
		find() { return { removeClass() {}, empty() { return this; }, text() { return this; }, html() { return this; }, val() { return this; } }; },
	};
	assistant.previewImport = (selectedFile) => previewed.push(selectedFile);
	assistant.bindEvents();
	let prevented = false;
	handlers["drop:#cima-ai-chat"]({
		preventDefault() { prevented = true; },
		originalEvent: { dataTransfer: { files: [file] } },
	});
	assert.equal(prevented, true);
	assert.deepEqual(previewed, [file]);
	assert.equal(assistant.state.importFile, file);
	assert.equal(assistant.state.importPreview, null);
	assert.equal(requests.length, 0);
});

test("price update preview renders current-to-new prices and AI chat updates staged preview without confirming", () => {
	const { dialogs, requests, assistant } = setup();
	assistant.escape = (value) => String(value ?? "").replaceAll("<", "&lt;");
	const preview = {
		token: "tok-1",
		row_count: 1,
		create_count: 0,
		update_count: 1,
		can_confirm: true,
		rows: [{
			row: 2,
			action: "update_price",
			item_code: "SKU-EX",
			item_name: "Router",
			current_detal_price: 20,
			detal_price: 25,
			current_mayor_price: 16,
			mayor_price: 20,
			errors: [],
		}],
	};
	const html = assistant.importTable(preview);
	assert.match(html, /Actualizar precio/);
	assert.match(html, /20.*→.*25/);

	const rendered = [];
	assistant.renderImportPreview = (p) => rendered.push(p);
	assistant.state = {
		bootstrap: { enabled: true, configured: true },
		messages: [],
		asking: false,
		retryRequest: null,
		importPreview: preview,
	};
	assistant.wrapper = { find: (selector) => ({ val: () => selector === "#cima-ai-question" ? "Sube 10% el detal" : "", prop() {}, html() { return this; }, scrollTop() { return this; } }) };
	assistant.addMessage = (...args) => {
		const msg = { role: args[0], content: args[1], includeInHistory: true };
		assistant.state.messages.push(msg);
		return msg;
	};
	assistant.sendMessage();
	assert.equal(requests[0].args.import_token, "tok-1");
	const updated = { ...preview, token: "tok-2" };
	requests[0].callback({ message: { answer: "Ajustado en vista previa.", scope: {}, updated_import_preview: updated } });
	assert.equal(assistant.state.importPreview.token, "tok-2");
	assert.deepEqual(rendered, [updated]);
	assert.equal(dialogs.length, 0);
});