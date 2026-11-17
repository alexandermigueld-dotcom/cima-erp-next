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

permission_query_conditions = {
    "Delivery Note": "cima_ve.overrides.delivery_note_permissions.get_permission_query_conditions",
}

has_permission = {
    "Delivery Note": "cima_ve.overrides.delivery_note_permissions.has_permission",
}

scheduler_events = {
    "hourly": [
        "cima_ve.api.exchange_rates.sync_exchange_rates_job",
    ]
}
