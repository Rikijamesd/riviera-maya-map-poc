<#
Monthly inventory tracker for Zisla (zisla.com).

Fetches every published development plus every individual unit within it,
and APPENDS a dated snapshot to a persistent Excel workbook (rather than
overwriting), so you can see how availability, pricing, and inventory
change over time.

Sheets:
  - Units         : one row per unit per snapshot (Development + Unit columns)
  - Developments  : one row per development per snapshot (project-level info)
  - Payment Plans : one row per financing/payment plan option per development per snapshot
  - Phases        : one row per construction phase per development per snapshot (status + delivery date)

Default output: G:\My Drive\zisla-tracker\zisla-inventory-tracker.xlsx (synced via
Google Drive for Desktop).

Usage:
  powershell -File track-zisla-inventory.ps1
  powershell -File track-zisla-inventory.ps1 -OutFile "D:\other\path.xlsx"
  powershell -File track-zisla-inventory.ps1 -Test          # only first 5 developments, for a quick dry run
#>
param(
  [string]$OutFile = "G:\My Drive\zisla-tracker\zisla-inventory-tracker.xlsx",
  [switch]$Test
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Headers = @{
  "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
  "Referer"    = "https://www.zisla.com/"
  "Accept"     = "application/json"
}
$SnapshotDate = Get-Date -Format "yyyy-MM-dd"

function Get-ZislaDevelopments {
  $all = New-Object System.Collections.Generic.List[object]
  $offset = 0
  $pageSize = 200
  $filters = [uri]::EscapeDataString('[{"id":"published","type":"boolean","value":true}]')
  while ($true) {
    $uri = "https://www.zisla.com/api/v1/properties/listing?offset=$offset&limit=$pageSize&filters=$filters&lang=en"
    $resp = Invoke-RestMethod -Uri $uri -Headers $Headers
    $items = $resp.items
    if (-not $items -or $items.Count -eq 0) { break }
    foreach ($i in $items) { $all.Add($i) }
    if ($items.Count -lt $pageSize) { break }
    $offset += $pageSize
    Start-Sleep -Milliseconds 250
  }
  return $all
}

function Get-ZislaUnits {
  param([string]$PropertyId)
  $all = New-Object System.Collections.Generic.List[object]
  $offset = 0
  $pageSize = 1000
  $filters = [uri]::EscapeDataString("[{`"id`":`"propertyId`",`"type`":`"_id`",`"value`":`"$PropertyId`"}]")
  while ($true) {
    $uri = "https://www.zisla.com/api/v1/units/listing?offset=$offset&limit=$pageSize&filters=$filters&lang=en&browser=true"
    try {
      $resp = Invoke-RestMethod -Uri $uri -Headers $Headers
    } catch {
      Write-Warning "Failed to fetch units for property $PropertyId : $($_.Exception.Message)"
      break
    }
    $items = $resp.items
    if (-not $items -or $items.Count -eq 0) { break }
    foreach ($i in $items) { $all.Add($i) }
    if ($items.Count -lt $pageSize) { break }
    $offset += $pageSize
    Start-Sleep -Milliseconds 200
  }
  return $all
}

function Join-TrueKeys {
  param($Obj)
  if (-not $Obj) { return "" }
  $names = @()
  foreach ($p in $Obj.PSObject.Properties) {
    if ($p.Value -eq $true) { $names += $p.Name }
  }
  return ($names -join ", ")
}

function ConvertTo-PlainText {
  param([string]$Html)
  if (-not $Html) { return "" }
  $t = $Html -replace '<[^>]+>', ' '
  $t = [System.Net.WebUtility]::HtmlDecode($t)
  return ($t -replace '\s+', ' ').Trim()
}

Write-Host "Fetching developments from zisla.com ..."
$developments = Get-ZislaDevelopments
Write-Host "Total developments: $($developments.Count)"

if ($Test) {
  Write-Host "TEST MODE: limiting to first 5 developments"
  $developments = $developments | Select-Object -First 5
}

Write-Host "Building development rows..."
$devRows = foreach ($p in $developments) {
  $priceMin = if ($null -ne $p.price.min) { [math]::Round($p.price.min / 100, 2) } else { $null }
  $priceMax = if ($null -ne $p.price.max) { [math]::Round($p.price.max / 100, 2) } else { $null }
  [PSCustomObject]@{
    "Snapshot Date"     = $SnapshotDate
    "Development"       = $p.localized.title
    "Development ID"    = $p._id
    "URL"               = "https://www.zisla.com/en/properties/$($p.localized.urlAlias)"
    "Purpose"           = $p.purpose
    "Type"              = $p.type
    "Sub Type"          = $p.subType
    "Province"          = $p.address.province
    "City"              = $p.address.city
    "Price Min (USD)"   = $priceMin
    "Price Max (USD)"   = $priceMax
    "Units Total"       = $p.nbOfUnits
    "Units Available"   = $p.nbOfUnitsAvailable
    "Developer ID"      = $p.developer
    "Financing Offered" = $p.isFinancing
    "Amenities"         = Join-TrueKeys $p.amenities
    "Features"          = Join-TrueKeys $p.features
    "Description"       = ConvertTo-PlainText $p.localized.description
    "Last Update"       = $p.lastUpdate
  }
}

Write-Host "Building payment plan rows..."
$planRows = foreach ($p in $developments) {
  if (-not $p.financing -or $p.financing.Count -eq 0) { continue }
  $planNum = 0
  foreach ($plan in $p.financing) {
    $planNum++
    [PSCustomObject]@{
      "Snapshot Date"     = $SnapshotDate
      "Development"       = $p.localized.title
      "Development ID"    = $p._id
      "Province"          = $p.address.province
      "City"              = $p.address.city
      "Plan Number"       = $planNum
      "Plan ID"           = $plan._id
      "Signin %"          = $plan.signin
      "Building %"        = $plan.building
      "Delivery %"        = $plan.delivery
      "Deeding %"         = $plan.deeding
      "Discount %"        = $plan.discount
    }
  }
}
Write-Host "Total payment plan rows: $($planRows.Count)"

Write-Host "Building phase/delivery rows..."
$phaseRows = foreach ($p in $developments) {
  if (-not $p.statusByPhase -or $p.statusByPhase.Count -eq 0) { continue }
  $phaseNum = 0
  foreach ($phase in $p.statusByPhase) {
    $phaseNum++
    [PSCustomObject]@{
      "Snapshot Date"     = $SnapshotDate
      "Development"       = $p.localized.title
      "Development ID"    = $p._id
      "Province"          = $p.address.province
      "City"              = $p.address.city
      "Phase Number"      = $phaseNum
      "Phase ID"          = $phase._id
      "Status"            = $phase.status
      "Delivery Date"     = $phase.deliveryDate
    }
  }
}
Write-Host "Total phase rows: $($phaseRows.Count)"

Write-Host "Fetching units for each development (this takes a while)..."
$unitRows = New-Object System.Collections.Generic.List[object]
$i = 0
foreach ($p in $developments) {
  $i++
  $units = Get-ZislaUnits -PropertyId $p._id
  foreach ($u in $units) {
    $priceUsd = if ($null -ne $u.price) { [math]::Round($u.price / 100, 2) } else { $null }
    $priceMxn = if ($null -ne $u.priceInPesos) { [math]::Round($u.priceInPesos / 100, 2) } else { $null }
    $unitRows.Add([PSCustomObject]@{
      "Snapshot Date"       = $SnapshotDate
      "Development"         = $p.localized.title
      "Development ID"      = $p._id
      "Province"            = $p.address.province
      "City"                = $p.address.city
      "Unit"                = $u.name
      "Unit ID"             = $u._id
      "Status"              = $u.status
      "Bedrooms"            = $u.bedrooms
      "Bathrooms"           = $u.bathrooms
      "Construct Area (m2)" = $u.squareSurface
      "Price (USD)"         = $priceUsd
      "Price (MXN)"         = $priceMxn
      "Price per Area"      = $u.priceSurface
      "Floor Number"        = $u.floorNumber
      "Building ID"         = $u.buildingId
      "Phase Status"        = $u.phase.status
      "Phase Delivery Date" = $u.phase.deliveryDate
      "Discounted"          = $u.discount
      "Unit Last Updated"   = $u.updatedAt
    })
  }
  if ($i % 25 -eq 0 -or $i -eq $developments.Count) {
    Write-Host "  $i / $($developments.Count) developments processed, $($unitRows.Count) units collected so far"
  }
}
Write-Host "Total unit rows: $($unitRows.Count)"

function Get-OrCreateSheet {
  param($Workbook, [string]$Name, [string[]]$HeaderNames)
  foreach ($s in $Workbook.Worksheets) { if ($s.Name -eq $Name) { return $s } }

  $ws = $Workbook.Worksheets.Add([System.Reflection.Missing]::Value, $Workbook.Worksheets.Item($Workbook.Worksheets.Count))
  $ws.Name = $Name
  for ($c = 0; $c -lt $HeaderNames.Count; $c++) {
    $ws.Cells.Item(1, $c + 1) = $HeaderNames[$c]
    # ID-like / leading-zero-prone columns (e.g. Unit "01") - force text so Excel
    # doesn't silently reinterpret them as numbers.
    if ($HeaderNames[$c] -eq "Unit" -or $HeaderNames[$c] -like "*ID*") {
      $ws.Columns.Item($c + 1).NumberFormat = "@"
    }
  }
  $headerRange = $ws.Range($ws.Cells.Item(1, 1), $ws.Cells.Item(1, $HeaderNames.Count))
  $headerRange.Font.Bold = $true
  $headerRange.Font.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::White)
  $headerRange.Interior.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::FromArgb(31, 73, 125))
  $ws.Rows.Item(1).RowHeight = 20
  $headerRange.AutoFilter() | Out-Null
  $appWin = $Workbook.Application.Windows.Item(1)
  $ws.Activate()
  $appWin.SplitRow = 1
  $appWin.FreezePanes = $true
  return $ws
}

function Write-RowsToSheet {
  param($Sheet, [object[]]$Rows)
  if ($Rows.Count -eq 0) { return }
  $headers = $Rows[0].PSObject.Properties.Name
  $colCount = $headers.Count
  $startRow = $Sheet.UsedRange.Rows.Count + 1
  if ($startRow -eq 2 -and [string]::IsNullOrEmpty($Sheet.Cells.Item(2,1).Value2) -and $Sheet.UsedRange.Rows.Count -eq 1) {
    $startRow = 2
  }

  $batchSize = 25
  for ($batchStart = 0; $batchStart -lt $Rows.Count; $batchStart += $batchSize) {
    $batchEnd = [Math]::Min($batchStart + $batchSize, $Rows.Count) - 1
    $batchRowCount = $batchEnd - $batchStart + 1
    $batchArray = New-Object 'object[,]' $batchRowCount, $colCount
    for ($r = 0; $r -lt $batchRowCount; $r++) {
      for ($c = 0; $c -lt $colCount; $c++) {
        $val = $Rows[$batchStart + $r].($headers[$c])
        if ($null -eq $val) {
          $val = ""
        } elseif ($val -is [psobject]) {
          # Values from Invoke-RestMethod's JSON deserialization carry a PSObject
          # wrapper that breaks Excel COM's array marshaling (surfaces as a
          # misleading OutOfMemoryException) - unwrap to the raw .NET value.
          $val = $val.psobject.BaseObject
        }
        $batchArray[$r, $c] = $val
      }
    }
    $rangeStartRow = $startRow + $batchStart
    $rangeEndRow = $startRow + $batchEnd
    $range = $Sheet.Range($Sheet.Cells.Item($rangeStartRow, 1), $Sheet.Cells.Item($rangeEndRow, $colCount))
    $range.Value2 = $batchArray
  }
}

Write-Host "Writing to workbook: $OutFile"
Add-Type -AssemblyName System.Drawing
$outDir = Split-Path -Parent $OutFile
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$excel.ScreenUpdating = $false

try {
  if (Test-Path $OutFile) {
    $wb = $excel.Workbooks.Open($OutFile)
  } else {
    $wb = $excel.Workbooks.Add()
  }
  try { $excel.Calculation = -4135 } catch { }  # xlCalculationManual, best-effort

  $unitHeaders = $unitRows[0].PSObject.Properties.Name
  $devHeaders = $devRows[0].PSObject.Properties.Name

  $unitsSheet = Get-OrCreateSheet -Workbook $wb -Name "Units" -HeaderNames $unitHeaders
  $devSheet = Get-OrCreateSheet -Workbook $wb -Name "Developments" -HeaderNames $devHeaders
  $planSheet = $null
  if ($planRows.Count -gt 0) {
    $planHeaders = $planRows[0].PSObject.Properties.Name
    $planSheet = Get-OrCreateSheet -Workbook $wb -Name "Payment Plans" -HeaderNames $planHeaders
  }
  $phaseSheet = $null
  if ($phaseRows.Count -gt 0) {
    $phaseHeaders = $phaseRows[0].PSObject.Properties.Name
    $phaseSheet = Get-OrCreateSheet -Workbook $wb -Name "Phases" -HeaderNames $phaseHeaders
  }

  # Drop the blank default "Sheet1" Excel creates in a brand new workbook.
  $staleSheets = @($wb.Worksheets) | Where-Object {
    $_.Name -ne "Units" -and $_.Name -ne "Developments" -and $_.Name -ne "Payment Plans" -and $_.Name -ne "Phases" -and
    [string]::IsNullOrEmpty($_.Cells.Item(1, 1).Value2) -and $_.UsedRange.Address() -eq "`$A`$1"
  }
  foreach ($s in $staleSheets) { $s.Delete() }

  Write-Host "Appending $($unitRows.Count) unit rows..."
  Write-RowsToSheet -Sheet $unitsSheet -Rows $unitRows.ToArray()
  Write-Host "Appending $($devRows.Count) development rows..."
  Write-RowsToSheet -Sheet $devSheet -Rows $devRows
  if ($planSheet) {
    Write-Host "Appending $($planRows.Count) payment plan rows..."
    Write-RowsToSheet -Sheet $planSheet -Rows $planRows
  }
  if ($phaseSheet) {
    Write-Host "Appending $($phaseRows.Count) phase rows..."
    Write-RowsToSheet -Sheet $phaseSheet -Rows $phaseRows
  }

  $unitsSheet.UsedRange.Columns.AutoFit() | Out-Null
  $devSheet.UsedRange.Columns.AutoFit() | Out-Null
  if ($planSheet) { $planSheet.UsedRange.Columns.AutoFit() | Out-Null }
  if ($phaseSheet) { $phaseSheet.UsedRange.Columns.AutoFit() | Out-Null }

  $unitsTotalRows = $unitsSheet.UsedRange.Rows.Count - 1
  $devTotalRows = $devSheet.UsedRange.Rows.Count - 1
  $planTotalRows = if ($planSheet) { $planSheet.UsedRange.Rows.Count - 1 } else { 0 }
  $phaseTotalRows = if ($phaseSheet) { $phaseSheet.UsedRange.Rows.Count - 1 } else { 0 }

  if (Test-Path $OutFile) {
    $wb.Save()
  } else {
    $wb.SaveAs($OutFile, 51)
  }
  $wb.Close($false)
  Write-Host "Saved snapshot dated $SnapshotDate to $OutFile"
  Write-Host "Units sheet now has $unitsTotalRows total rows across all snapshots"
  Write-Host "Developments sheet now has $devTotalRows total rows across all snapshots"
  Write-Host "Payment Plans sheet now has $planTotalRows total rows across all snapshots"
  Write-Host "Phases sheet now has $phaseTotalRows total rows across all snapshots"
}
finally {
  $excel.Quit()
  [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}
