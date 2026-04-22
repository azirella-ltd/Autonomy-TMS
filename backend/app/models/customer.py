"""Customer model — re-exports from canonical azirella-data-model.

The SQLAlchemy Customer class is defined in azirella-data-model and
re-exported here so existing-style imports
(`from app.models.customer import Customer`) work unchanged across TMS.

Customer is the commercial-account entity that owns one or more Tenants
and carries the `purchased_solutions` list that gates ERP/APS connector
extraction. See azirella_data_model/tenant/customer.py for the full
contract.
"""
from azirella_data_model.tenant import Customer, CustomerStatus  # noqa: F401
