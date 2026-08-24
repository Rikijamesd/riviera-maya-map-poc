<#
Scrapes the title + metadata (not body text) of every published blog article
on zisla.com/en/blog.

Deliberately excludes the article body: only title, URL, category, publish
date, and the short (~150-char) SEO meta description are collected. The full
article HTML lives in each item's "component" field and is not touched here -
downloading full article text at scale would mean reproducing Zisla's
copyrighted editorial writing, which is a different thing from collecting
factual/structured data (titles, dates, categories are not creative content).

Usage:
  powershell -File download-zisla-blog-titles.ps1
  powershell -File download-zisla-blog-titles.ps1 -OutFile "D:\other\path.xlsx"
#>
param(
  [string]$OutFile = "G:\My Drive\zisla-tracker\zisla-blog-titles.xlsx"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Headers = @{
  "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
  "Referer"    = "https://www.zisla.com/"
  "Accept"     = "application/json"
}

function Get-ZislaBlogArticles {
  $all = New-Object System.Collections.Generic.List[object]
  $offset = 0
  $pageSize = 100
  $filters = [uri]::EscapeDataString('[{"type":"string","id":"type","value":"ARTICLE"},{"type":"boolean","id":"localized.en.published","value":true}]')
  while ($true) {
    $uri = "https://www.zisla.com/api/v1/pages?offset=$offset&limit=$pageSize&filters=$filters"
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

Write-Host "Fetching blog article list from zisla.com ..."
$articles = Get-ZislaBlogArticles
Write-Host "Total articles: $($articles.Count)"

$rows = foreach ($a in $articles) {
  [PSCustomObject]@{
    "Title"        = $a.localized.en.title
    "URL"          = "https://www.zisla.com/en/blog$($a.localized.en.url)"
    "Category"     = $a.blogType
    "Published At" = $a.localized.en.publishedAt
    "Created At"   = $a.createdAt
    "Updated At"   = $a.updatedAt
    "Meta Description" = $a.localized.en.description
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
  if (Test-Path $OutFile) { Remove-Item $OutFile -Force }
  $wb = $excel.Workbooks.Add()
  $ws = $wb.Worksheets.Item(1)
  $ws.Name = "Blog Articles"

  $headers = $rows[0].PSObject.Properties.Name
  $colCount = $headers.Count
  for ($c = 0; $c -lt $colCount; $c++) { $ws.Cells.Item(1, $c + 1) = $headers[$c] }

  $headerRange = $ws.Range($ws.Cells.Item(1, 1), $ws.Cells.Item(1, $colCount))
  $headerRange.Font.Bold = $true
  $headerRange.Font.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::White)
  $headerRange.Interior.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::FromArgb(31, 73, 125))
  $ws.Rows.Item(1).RowHeight = 20
  $headerRange.AutoFilter() | Out-Null
  $ws.Application.ActiveWindow.SplitRow = 1
  $ws.Application.ActiveWindow.FreezePanes = $true

  $batchSize = 25
  for ($batchStart = 0; $batchStart -lt $rows.Count; $batchStart += $batchSize) {
    $batchEnd = [Math]::Min($batchStart + $batchSize, $rows.Count) - 1
    $batchRowCount = $batchEnd - $batchStart + 1
    $batchArray = New-Object 'object[,]' $batchRowCount, $colCount
    for ($r = 0; $r -lt $batchRowCount; $r++) {
      for ($c = 0; $c -lt $colCount; $c++) {
        $val = $rows[$batchStart + $r].($headers[$c])
        if ($null -eq $val) {
          $val = ""
        } elseif ($val -is [psobject]) {
          $val = $val.psobject.BaseObject
        }
        $batchArray[$r, $c] = $val
      }
    }
    $range = $ws.Range($ws.Cells.Item(2 + $batchStart, 1), $ws.Cells.Item(2 + $batchEnd, $colCount))
    $range.Value2 = $batchArray
  }

  $ws.UsedRange.Columns.AutoFit() | Out-Null
  $wb.SaveAs($OutFile, 51)
  $wb.Close($false)
  Write-Host "Saved $($rows.Count) blog article titles to $OutFile"
}
finally {
  $excel.Quit()
  [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}
