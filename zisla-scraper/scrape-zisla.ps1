<#
Scrapes all published property listings from Zisla (zisla.com) via its public
listing API and writes them to an Excel workbook.

Usage:
  powershell -File scrape-zisla.ps1
  powershell -File scrape-zisla.ps1 -OutFile "C:\path\to\output.xlsx"

Requires Microsoft Excel to be installed (used via COM automation to write a
real .xlsx file). No Python/Node dependency.
#>
param(
  [string]$OutFile = (Join-Path $PSScriptRoot "zisla-properties.xlsx")
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$ApiBase = "https://www.zisla.com/api/v1/properties/listing"
$PublishedFilter = '[{"id":"published","type":"boolean","value":true}]'
$PageSize = 200

function Get-ZislaListings {
  $all = New-Object System.Collections.Generic.List[object]
  $offset = 0
  while ($true) {
    $encodedFilters = [uri]::EscapeDataString($PublishedFilter)
    $uri = "$($ApiBase)?offset=$offset&limit=$PageSize&filters=$encodedFilters&lang=en"
    $headers = @{
      "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
      "Referer"    = "https://www.zisla.com/"
      "Accept"     = "application/json"
    }
    $resp = Invoke-RestMethod -Uri $uri -Headers $headers
    $items = $resp.items
    if (-not $items -or $items.Count -eq 0) { break }
    foreach ($i in $items) { $all.Add($i) }
    Write-Host "Fetched $($all.Count) properties..."
    if ($items.Count -lt $PageSize) { break }
    $offset += $PageSize
    Start-Sleep -Milliseconds 300
  }
  return $all
}

function ConvertTo-PlainText {
  param([string]$Html)
  if (-not $Html) { return "" }
  $t = $Html -replace '<[^>]+>', ' '
  $t = [System.Net.WebUtility]::HtmlDecode($t)
  return ($t -replace '\s+', ' ').Trim()
}

function Limit-CellLength {
  # Excel hard-caps a cell's text at 32,767 characters.
  param([string]$Text)
  if ($Text -and $Text.Length -gt 32000) {
    return $Text.Substring(0, 32000) + "...[truncated]"
  }
  return $Text
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

Write-Host "Fetching property listings from zisla.com ..."
$items = Get-ZislaListings
Write-Host "Total properties fetched: $($items.Count)"

if ($items.Count -eq 0) {
  Write-Error "No properties were fetched. Zisla's API may have changed."
  exit 1
}

Write-Host "Transforming records..."
$rows = foreach ($p in $items) {
  $priceMin = if ($null -ne $p.price.min) { [math]::Round($p.price.min / 100, 2) } else { $null }
  $priceMax = if ($null -ne $p.price.max) { [math]::Round($p.price.max / 100, 2) } else { $null }
  $pesosMin = if ($null -ne $p.priceInPesos.min) { [math]::Round($p.priceInPesos.min / 100, 2) } else { $null }
  $pesosMax = if ($null -ne $p.priceInPesos.max) { [math]::Round($p.priceInPesos.max / 100, 2) } else { $null }
  $photoCount = if ($p.photos) { $p.photos.Count } else { 0 }
  $firstPhoto = if ($p.photos -and $p.photos.Count -gt 0) { "https://www.zisla.com$($p.photos[0].url)" } else { "" }
  $lat = if ($p.location -and $p.location.coordinates) { $p.location.coordinates[1] } else { $null }
  $lon = if ($p.location -and $p.location.coordinates) { $p.location.coordinates[0] } else { $null }

  [PSCustomObject]@{
    "ID"                = $p._id
    "Title"             = $p.localized.title
    "URL"               = "https://www.zisla.com/en/properties/$($p.localized.urlAlias)"
    "Purpose"           = $p.purpose
    "Status"            = $p.status
    "Type"              = $p.type
    "Sub Type"          = $p.subType
    "Country"           = $p.address.country
    "Province"          = $p.address.province
    "City"              = $p.address.city
    "Neighbourhood"     = $p.address.neighbourhood
    "Street"            = $p.address.street
    "Postal Code"       = $p.address.postalCode
    "Price Min (USD)"   = $priceMin
    "Price Max (USD)"   = $priceMax
    "Price Min (MXN)"   = $pesosMin
    "Price Max (MXN)"   = $pesosMax
    "Price Hidden"      = $p.priceIsNotDisplayed
    "Bedrooms Min"      = $p.bedrooms.min
    "Bedrooms Max"      = $p.bedrooms.max
    "Bathrooms Min"     = $p.bathrooms.min
    "Bathrooms Max"     = $p.bathrooms.max
    "Sq Surface Min"    = $p.squareSurface.min
    "Sq Surface Max"    = $p.squareSurface.max
    "Measured In Sq Ft" = $p.isSquareFeet
    "Units Total"       = $p.nbOfUnits
    "Units Available"   = $p.nbOfUnitsAvailable
    "Levels"            = $p.nbOfLevels
    "Financing Offered" = $p.isFinancing
    "Latitude"          = $lat
    "Longitude"         = $lon
    "Amenities"         = Join-TrueKeys $p.amenities
    "Features"          = Join-TrueKeys $p.features
    "Developer ID"      = $p.developer
    "First Day On Site" = $p.firstDayOnSite
    "Last Update"       = $p.lastUpdate
    "Photo Count"       = $photoCount
    "First Photo URL"   = $firstPhoto
    "Description"       = ConvertTo-PlainText $p.localized.description
    "Raw JSON"          = Limit-CellLength ($p | ConvertTo-Json -Depth 10 -Compress)
  }
}

Write-Host "Writing Excel workbook to $OutFile ..."
Add-Type -AssemblyName System.Drawing

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

try {
  $wb = $excel.Workbooks.Add()
  $ws = $wb.Worksheets.Item(1)
  $ws.Name = "Zisla Properties"

  $headers = $rows[0].PSObject.Properties.Name
  $colCount = $headers.Count
  $rowCount = $rows.Count

  for ($c = 0; $c -lt $colCount; $c++) {
    $ws.Cells.Item(1, $c + 1) = $headers[$c]
  }

  # Write in small batches - a single huge Range.Value2 assignment can blow up
  # COM marshaling memory once string content (e.g. the Raw JSON column) gets large.
  $batchSize = 40
  for ($batchStart = 0; $batchStart -lt $rowCount; $batchStart += $batchSize) {
    $batchEnd = [Math]::Min($batchStart + $batchSize, $rowCount) - 1
    $batchRowCount = $batchEnd - $batchStart + 1

    $batchArray = New-Object 'object[,]' $batchRowCount, $colCount
    for ($r = 0; $r -lt $batchRowCount; $r++) {
      for ($c = 0; $c -lt $colCount; $c++) {
        $val = $rows[$batchStart + $r].($headers[$c])
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

    $startCell = $ws.Cells.Item(2 + $batchStart, 1)
    $endCell = $ws.Cells.Item(2 + $batchEnd, $colCount)
    $range = $ws.Range($startCell, $endCell)
    $range.Value2 = $batchArray
    Write-Host "Wrote rows $($batchStart + 1)-$($batchEnd + 1) of $rowCount"
  }

  $headerRange = $ws.Range($ws.Cells.Item(1, 1), $ws.Cells.Item(1, $colCount))
  $headerRange.Font.Bold = $true
  $headerRange.Font.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::White)
  $headerRange.Interior.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::FromArgb(31, 73, 125))
  $ws.Rows.Item(1).RowHeight = 20

  $ws.Application.ActiveWindow.SplitRow = 1
  $ws.Application.ActiveWindow.FreezePanes = $true

  $usedRange = $ws.UsedRange
  $usedRange.Columns.AutoFit() | Out-Null
  $headerRange.AutoFilter() | Out-Null

  if (Test-Path $OutFile) { Remove-Item $OutFile -Force }
  $wb.SaveAs($OutFile, 51)  # 51 = xlOpenXMLWorkbook (.xlsx)
  $wb.Close($false)
  Write-Host "Saved $rowCount properties to $OutFile"
}
finally {
  $excel.Quit()
  [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}
