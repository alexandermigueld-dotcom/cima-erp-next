app_name = "cima_ve"
app_title = "Cima VE"
app_publisher = "Cima Electronic VE"
app_description = "Integración de Cashea y Facturación Fiscal Digital SENIAT para ERPNext Venezuela"
app_email = "cimaelectronic@gmail.com"
app_license = "MIT"

fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["module", "=", "Cima VE"]],
    },
    {
        "dt": "Workspace",
        "filters": [["module", "=", "Cima VE"]],
    },
]

doc_events = {
    "Sales Invoice": {
        "validate": "cima_ve.overrides.sales_invoice.validate_venezuela_fiscal",
        "on_submit": "cima_ve.overrides.sales_invoice.on_submit_fiscal_stamp",
    }
}
