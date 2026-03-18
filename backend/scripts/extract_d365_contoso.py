#!/usr/bin/env python3
"""
Extract supply chain data from D365 F&O Contoso (USMF) via OData.

Authenticates via Azure AD client credentials, queries all SC entities,
and writes CSV files to an output directory. These CSVs can then be
ingested via rebuild_d365_contoso_config.py.

Prerequisites:
    1. D365 F&O trial: https://www.microsoft.com/en-us/dynamics-365/free-trial
    2. Azure AD app registration with Dynamics ERP permissions
    3. App registered in D365: System Administration > Microsoft Entra Applications

Usage:
    export D365_BASE_URL="https://contoso.operations.dynamics.com"
    export D365_TENANT_ID="your-azure-tenant-id"
    export D365_CLIENT_ID="your-app-client-id"
    export D365_CLIENT_SECRET="your-app-client-secret"

    python scripts/extract_d365_contoso.py --output-dir /tmp/d365_csvs

    # Or pass inline:
    python scripts/extract_d365_contoso.py \
        --base-url https://contoso.operations.dynamics.com \
        --tenant-id abc-123 \
        --client-id def-456 \
        --client-secret xxx \
        --output-dir /tmp/d365_csvs
"""

import argparse
import csv
import json
import os
import sys
import time
from typing import Dict, List, Optional

import requests

# ── D365 OData entities to extract ──────────────────────────────────────────

ENTITIES = {
    # Master Data
    "Sites": {
        "select": "SiteId,SiteName",
    },
    "Warehouses": {
        "select": "WarehouseId,WarehouseName,SiteId,OperationalSiteId,IsInventoryManaged,WarehouseType",
    },
    "ReleasedProductsV2": {
        "select": "ItemNumber,ProductName,ProductType,ProductSubType,ProductGroupId,"
                  "InventoryUnitSymbol,SalesPrice,ProductionStandardCost,"
                  "NetWeight,GrossWeight,NetVolume,BarcodeId",
    },
    "VendorsV2": {
        "select": "VendorAccountNumber,VendorName,VendorGroupId,"
                  "AddressCountryRegionId,AddressCity,AddressZipCode,"
                  "PrimaryContactPhone,PrimaryContactEmail",
        "filename": "Vendors.csv",
    },
    "CustomersV3": {
        "select": "CustomerAccount,CustomerName,CustomerGroupId,"
                  "AddressCountryRegionId,AddressCity,AddressZipCode,"
                  "PrimaryContactPhone,PrimaryContactEmail",
    },
    "BillOfMaterialsHeaders": {
        "select": "BOMId,ProductNumber,SiteId,BOMName,IsActive,BOMQuantity,BOMUnitSymbol",
    },
    "BillOfMaterialsLines": {
        "select": "BOMId,LineNumber,ItemNumber,BOMLineQuantity,BOMLineQuantityUnitSymbol,ScrapPercentage",
    },
    # Transactions
    "PurchaseOrderHeadersV2": {
        "select": "PurchaseOrderNumber,VendorAccountNumber,OrderDate,"
                  "DeliveryDate,PurchaseOrderStatus,CurrencyCode,TotalOrderAmount",
    },
    "PurchaseOrderLinesV2": {
        "select": "PurchaseOrderNumber,LineNumber,ItemNumber,"
                  "PurchasedQuantity,ReceivedQuantity,PurchasePrice,DeliveryDate",
    },
    "SalesOrderHeadersV2": {
        "select": "SalesOrderNumber,CustomerAccountNumber,OrderDate,"
                  "RequestedShipDate,SalesOrderStatus,CurrencyCode,TotalOrderAmount",
    },
    "SalesOrderLinesV2": {
        "select": "SalesOrderNumber,LineNumber,ItemNumber,"
                  "OrderedSalesQuantity,DeliveredQuantity,SalesPrice",
    },
    # Inventory & Planning
    "InventWarehouseOnHandEntity": {
        "select": "ItemNumber,WarehouseId,SiteId,"
                  "PhysicalOnHandQuantity,ReservedQuantity,AvailableQuantity",
        "filename": "InventWarehouseOnHandEntity.csv",
    },
    "ItemCoverageSettings": {
        "select": "ItemNumber,SiteId,WarehouseId,"
                  "MinimumInventoryLevel,MaximumInventoryLevel,"
                  "SafetyStockQuantity,CoveragePlanGroupId",
    },
    # Production
    "ProductionOrderHeaders": {
        "select": "ProductionOrderNumber,ItemNumber,ProductionQuantity,"
                  "ProductionStatus,ScheduledStartDate,ScheduledEndDate,SiteId",
    },
    # Optional
    "VendorLeadTimes": {
        "select": "VendorAccountNumber,ItemNumber,SiteId,LeadTimeDays",
    },
    "DemandForecastEntries": {
        "select": "ItemNumber,SiteId,WarehouseId,ForecastQuantity,ForecastDate,ForecastModel",
        "filename": "DemandForecastEntries.csv",
    },
}


def get_token(tenant_id: str, client_id: str, client_secret: str, resource: str) -> str:
    """Get OAuth2 access token from Azure AD."""
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    resp = requests.post(url, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": f"{resource}/.default",
    })
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print(f"  Authenticated (token expires in {resp.json().get('expires_in', '?')}s)")
    return token


def odata_query_all(
    base_url: str,
    token: str,
    entity: str,
    select: str = "",
    data_area: str = "usmf",
    page_size: int = 5000,
) -> List[Dict]:
    """Query all records from a D365 OData entity with paging."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
    }

    url = f"{base_url}/data/{entity}"
    params = {
        "$filter": f"dataAreaId eq '{data_area}'",
        "$top": str(page_size),
    }
    if select:
        params["$select"] = select

    all_records = []
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=120)
        if resp.status_code == 401:
            raise RuntimeError("Authentication expired. Re-run with fresh credentials.")
        if resp.status_code != 200:
            print(f"    WARNING: {entity} returned {resp.status_code}: {resp.text[:200]}")
            break
        data = resp.json()
        records = data.get("value", [])
        all_records.extend(records)

        url = data.get("@odata.nextLink")
        params = {}  # nextLink contains all params

        if len(records) < page_size:
            break

    return all_records


def write_csv_file(filepath: str, records: List[Dict]) -> int:
    """Write records to CSV, stripping OData metadata fields."""
    if not records:
        return 0
    # Collect all field names, excluding OData metadata
    fieldnames = sorted(set(
        k for r in records for k in r.keys()
        if not k.startswith("@odata")
    ))
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Extract D365 F&O Contoso data via OData")
    parser.add_argument("--base-url", default=os.environ.get("D365_BASE_URL", ""),
                       help="D365 base URL (e.g. https://contoso.operations.dynamics.com)")
    parser.add_argument("--tenant-id", default=os.environ.get("D365_TENANT_ID", ""),
                       help="Azure AD tenant ID")
    parser.add_argument("--client-id", default=os.environ.get("D365_CLIENT_ID", ""),
                       help="Azure AD app client ID")
    parser.add_argument("--client-secret", default=os.environ.get("D365_CLIENT_SECRET", ""),
                       help="Azure AD app client secret")
    parser.add_argument("--data-area", default="usmf", help="D365 legal entity (default: usmf)")
    parser.add_argument("--output-dir", required=True, help="Directory for CSV output")
    args = parser.parse_args()

    if not all([args.base_url, args.tenant_id, args.client_id, args.client_secret]):
        print("ERROR: Missing credentials. Set D365_BASE_URL, D365_TENANT_ID, D365_CLIENT_ID, D365_CLIENT_SECRET")
        print("       or pass --base-url, --tenant-id, --client-id, --client-secret")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)
    base = args.base_url.rstrip("/")

    print(f"\n{'='*70}")
    print(f"  D365 Contoso OData Extraction")
    print(f"  Base URL:   {base}")
    print(f"  Data Area:  {args.data_area}")
    print(f"  Output:     {args.output_dir}")
    print(f"{'='*70}")

    # Authenticate
    print("\n  Authenticating...")
    token = get_token(args.tenant_id, args.client_id, args.client_secret, base)

    # Extract each entity
    total_records = 0
    for entity_name, config in ENTITIES.items():
        filename = config.get("filename", f"{entity_name}.csv")
        filepath = os.path.join(args.output_dir, filename)
        select = config.get("select", "")

        print(f"\n  Extracting {entity_name}...")
        start = time.time()

        try:
            records = odata_query_all(base, token, entity_name, select=select, data_area=args.data_area)
            count = write_csv_file(filepath, records)
            elapsed = time.time() - start
            print(f"    {count} records → {filename} ({elapsed:.1f}s)")
            total_records += count
        except Exception as e:
            print(f"    ERROR: {e}")

    print(f"\n{'='*70}")
    print(f"  Extraction complete: {total_records} total records")
    print(f"  CSV files in: {args.output_dir}")
    print(f"\n  Next step:")
    print(f"    python scripts/rebuild_d365_contoso_config.py \\")
    print(f"      --config-id <ID> --csv-dir {args.output_dir}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
