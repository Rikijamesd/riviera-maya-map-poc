<#
Fast, standalone refresh of just the "Phases" sheet in the Zisla inventory
tracker workbook. Only needs the development listing (no per-unit fetch), so
it runs in seconds - handy for an on-demand refresh between monthly full runs.

Phase/delivery data comes from each development's "statusByPhase" field: one
or more construction phases, each with a status (e.g. AVAILABLE,
READY_TO_MOVE_IN) and a delivery date.

Appends a dated snapshot to the SAME workbook used by track-zisla-inventory.ps1
(default: G:\My Drive\zisla-tracker\zisla-inventory-tracker.xlsx), touching
only the "Phases" sheet - Units/Developments/Payment Plans are left untouched.

Usage:
  powershell -File download-zisla-phases.ps1
  powershell -File download-zisla-phases.ps1 -OutFile "D:\other\path.xlsx"
#>
param(
  [string]$OutFile = "G:\My Drive\zisla-tracker\zisla-inventory-tracker.xlsx"
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

Write-Host "Fetching developments from zisla.com ..."
$developments = Get-ZislaDevelopments
Write-Host "Total developments: $($developments.Count)"

Write-Host "Building phase/delivery rows..."
$phaseRows = foreach ($p in $developments) {
  if (-not $p.statusByPhase -or $p.statusByPhase.Count -eq 0) { continue }
  $phaseNum = 0
  foreach ($phase in $p.statusByPhase) {
    $phaseNum++
    [PSCustomObject]@{
      "Snapshot Date"  = $SnapshotDate
      "Development"    = $p.localized.title
      "Development ID" = $p._id
      "Province"       = $p.address.province
      "City"           = $p.address.city
      "Phase Number"   = $phaseNum
      "Phase ID"       = $phase._id
      "Status"         = $phase.status
      "Delivery Date"  = $phase.deliveryDate
    }
  }
}
Write-Host "Total phase rows: $($phaseRows.Count)"

if ($phaseRows.Count -eq 0) {
  Write-Host "No phase data found - nothing to write."
  return
}

function Get-OrCreateSheet {
  param($Workbook, [string]$Name, [string[]]$HeaderNames)
  foreach ($s in $Workbook.Worksheets) { if ($s.Name -eq $Name) { return $s } }

  $ws = $Workbook.Worksheets.Add([System.Reflection.Missing]::Value, $Workbook.Worksheets.Item($Workbook.Worksheets.Count))
  $ws.Name = $Name
  for ($c = 0; $c -lt $HeaderNames.Count; $c++) {
    $ws.Cells.Item(1, $c + 1) = $HeaderNames[$c]
    if ($HeaderNames[$c] -like "*ID*") {
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

if (-not (Test-Path $OutFile)) {
  Write-Error "Workbook not found at $OutFile - run track-zisla-inventory.ps1 first to create it."
  exit 1
}

Write-Host "Writing to workbook: $OutFile"
Add-Type -AssemblyName System.Drawing

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$excel.ScreenUpdating = $false

try {
  $wb = $excel.Workbooks.Open($OutFile)
  try { $excel.Calculation = -4135 } catch { }

  $phaseHeaders = $phaseRows[0].PSObject.Properties.Name
  $phaseSheet = Get-OrCreateSheet -Workbook $wb -Name "Phases" -HeaderNames $phaseHeaders

  Write-Host "Appending $($phaseRows.Count) phase rows..."
  Write-RowsToSheet -Sheet $phaseSheet -Rows $phaseRows
  $phaseSheet.UsedRange.Columns.AutoFit() | Out-Null

  $phaseTotalRows = $phaseSheet.UsedRange.Rows.Count - 1

  $wb.Save()
  $wb.Close($false)
  Write-Host "Saved snapshot dated $SnapshotDate to $OutFile"
  Write-Host "Phases sheet now has $phaseTotalRows total rows across all snapshots"
}
finally {
  $excel.Quit()
  [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}
