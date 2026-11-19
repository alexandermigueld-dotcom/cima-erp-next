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
	assistant.addMessage = (...args) => messages.push(args);
	assistant.sendMessage();
	requests[0].callback({ message: { answer: "Informe", scope: {} } });
	assert.equal(requests.length, 1);
	assert.equal(requests[0].method, "cima_ve.api.ai_assistant.ask_assistant");
	assert.match(messages[1][1], /^Informe/);
	assert.equal(dialogs.length, 0);
});