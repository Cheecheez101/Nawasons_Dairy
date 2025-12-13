ROLE_CONFIG = {
    'Milk Clerks': {
        'permissions': [
            'production.view_cow',
            'production.add_cow',
            'production.view_milkyield',
            'production.add_milkyield',
        ]
    },
    'Lab': {
        'permissions': [
            'production.view_milkyield',
            'production.change_milkyield',
            'production.approve_milk',
        ]
    },
    'Production Unit': {
        'permissions': [
            'production.view_milkyield',
            'inventory.view_inventoryitem',
            'inventory.change_inventoryitem',
            'inventory.add_inventorytransaction',
        ]
    },
    'Store': {
        'permissions': [
            'inventory.view_inventoryitem',
            'inventory.dispatch_product',
        ]
    },
    'Sales Person': {
        'permissions': [
            'sales.add_salestransaction',
            'sales.view_salestransaction',
            'customers.add_customer',
            'customers.view_customer',
        ]
    },
    'Accounts': {
        'permissions': [
            'sales.view_salestransaction',
            'inventory.view_inventoryitem',
            'reports.view_report',
            'customers.view_customer',
            'production.view_productprice',
            'production.add_productprice',
            'production.change_productprice',
        ]
    },
}
