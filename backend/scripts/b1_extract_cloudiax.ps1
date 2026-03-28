# SAP Business One — Cloudiax Local Extraction Script
# Run this from PowerShell INSIDE the Cloudiax RDP session.
# It connects to the local Service Layer and extracts all entities as JSON.
#
# Usage:
#   .\b1_extract_cloudiax.ps1
#   .\b1_extract_cloudiax.ps1 -CompanyDB "SBODemoUS" -User "c88888.28" -Pass "Autonomy@2026!"
#
# Output: C:\B1Export\*.json  (one file per entity)

param(
    [string]$BaseUrl   = "https://localhost:50000/b1s/v2",
    [string]$CompanyDB = "SBODemoUS",
    [string]$User      = "c88888.28",
    [string]$Pass      = "Autonomy@2026!",
    [string]$OutDir    = "C:\B1Export"
)

# Skip SSL validation (B1 uses self-signed certs locally)
Add-Type @"
using System.Net;
using System.Net.Security;
using System.Security.Cryptography.X509Certificates;
public class TrustAll {
    public static void Enable() {
        ServicePointManager.ServerCertificateValidationCallback =
            delegate { return true; };
    }
}
"@
[TrustAll]::Enable()
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Create output directory
if (!(Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

Write-Host "=== SAP B1 Extraction ===" -ForegroundColor Cyan
Write-Host "Server: $BaseUrl"
Write-Host "Company: $CompanyDB"
Write-Host "Output: $OutDir"
Write-Host ""

# --- Login ---
Write-Host "Logging in..." -ForegroundColor Yellow
$loginBody = @{
    CompanyDB = $CompanyDB
    UserName  = $User
    Password  = $Pass
} | ConvertTo-Json

try {
    $loginResp = Invoke-RestMethod -Uri "$BaseUrl/Login" -Method POST `
        -ContentType "application/json" -Body $loginBody -SessionVariable b1session
    $sessionId = $loginResp.SessionId
    Write-Host "  Logged in. SessionId: $sessionId" -ForegroundColor Green
} catch {
    Write-Host "  Login FAILED: $_" -ForegroundColor Red
    Write-Host "  Trying manager/manager..." -ForegroundColor Yellow
    $loginBody = @{ CompanyDB = $CompanyDB; UserName = "manager"; Password = "manager" } | ConvertTo-Json
    try {
        $loginResp = Invoke-RestMethod -Uri "$BaseUrl/Login" -Method POST `
            -ContentType "application/json" -Body $loginBody -SessionVariable b1session
        $sessionId = $loginResp.SessionId
        Write-Host "  Logged in as manager. SessionId: $sessionId" -ForegroundColor Green
    } catch {
        Write-Host "  manager login also FAILED: $_" -ForegroundColor Red
        Write-Host "  Trying with port 50000 on various hosts..." -ForegroundColor Yellow
        exit 1
    }
}

# --- Entity list (Service Layer entity names) ---
$entities = @(
    # Master
    "Companies",
    "Warehouses",
    "BinLocations",
    "BusinessPartners",
    "BusinessPartnerGroups",
    "Items",
    "ItemGroups",
    "UnitOfMeasurements",
    "UnitOfMeasurementGroups",
    "PriceLists",
    "SpecialPrices",
    "ProductTrees",
    "Resources",
    "ResourceCapacities",
    "BlanketAgreements",
    # Transaction
    "Orders",
    "DeliveryNotes",
    "Invoices",
    "Returns",
    "PurchaseOrders",
    "GoodsReturns",
    "PurchaseDeliveryNotes",
    "PurchaseInvoices",
    "PurchaseRequests",
    "ProductionOrders",
    "InventoryTransferRequests",
    "StockTransfers",
    # CDC
    "InventoryGenEntries",
    "InventoryGenExits",
    "StockTakings",
    "BatchNumberDetails",
    "SerialNumberDetails",
    "ServiceCalls"
)

# --- Extract each entity with pagination ---
$headers = @{
    "Cookie" = "B1SESSION=$sessionId"
    "Prefer" = "odata.maxpagesize=500"
}

$totalEntities = $entities.Count
$idx = 0
$summary = @()

foreach ($entity in $entities) {
    $idx++
    Write-Host "[$idx/$totalEntities] $entity..." -ForegroundColor Yellow -NoNewline

    $allRecords = @()
    $nextUrl = "$BaseUrl/$entity"
    $page = 0

    try {
        while ($nextUrl) {
            $page++
            $resp = Invoke-RestMethod -Uri $nextUrl -Method GET `
                -Headers $headers -WebSession $b1session -ContentType "application/json"

            if ($resp.value) {
                $allRecords += $resp.value
            } elseif ($resp -is [Array]) {
                $allRecords += $resp
            }

            # OData pagination
            $nextUrl = $resp.'odata.nextLink'
            if (!$nextUrl -and $resp.'@odata.nextLink') {
                $nextUrl = $resp.'@odata.nextLink'
            }
        }

        $count = $allRecords.Count
        Write-Host " $count records ($page pages)" -ForegroundColor Green

        # Save as JSON
        $outFile = Join-Path $OutDir "$entity.json"
        $allRecords | ConvertTo-Json -Depth 10 -Compress | Set-Content -Path $outFile -Encoding UTF8
        $summary += [PSCustomObject]@{ Entity = $entity; Records = $count; Status = "OK" }

    } catch {
        $errMsg = $_.Exception.Message
        # Some entities may not exist in the demo (QualityTests, ForecastReport, etc.)
        Write-Host " SKIP ($errMsg)" -ForegroundColor DarkYellow
        $summary += [PSCustomObject]@{ Entity = $entity; Records = 0; Status = "SKIP: $errMsg" }
    }
}

# --- Logout ---
try {
    Invoke-RestMethod -Uri "$BaseUrl/Logout" -Method POST -Headers $headers -WebSession $b1session | Out-Null
    Write-Host "`nLogged out." -ForegroundColor Green
} catch {}

# --- Summary ---
Write-Host "`n=== Extraction Summary ===" -ForegroundColor Cyan
$summary | Format-Table -AutoSize
$totalRecords = ($summary | Where-Object { $_.Status -eq "OK" } | Measure-Object -Property Records -Sum).Sum
$okCount = ($summary | Where-Object { $_.Status -eq "OK" }).Count
Write-Host "Extracted $totalRecords records from $okCount entities" -ForegroundColor Green
Write-Host "Files saved to: $OutDir" -ForegroundColor Cyan
Write-Host "`nCopy the C:\B1Export folder to your Linux machine and run:" -ForegroundColor Yellow
Write-Host "  python scripts/rebuild_b1_config.py --csv-dir /path/to/B1Export" -ForegroundColor White
