<#
Downloads every development photo from Zisla (zisla.com) and organizes them
so each photo is traceable back to its development.

Layout:
  <OutDir>\<urlAlias>\<urlAlias>_001.webp, _002.webp, ...
  <OutDir>\photo-manifest.csv   (Development, Development ID, urlAlias, Photo Index, Filename, Local Path, Source URL)

urlAlias is Zisla's own routing slug for the property (e.g. "quintana_roo-tulum-wamai")
and is guaranteed unique - it's what they use for the property's own URL - so it
doubles as a safe, human-readable folder name / unique identifier.

Resumable: re-running skips any photo file that's already on disk.

Usage:
  powershell -File download-zisla-photos.ps1
  powershell -File download-zisla-photos.ps1 -OutDir "D:\zisla-photos" -MaxConcurrency 8
  powershell -File download-zisla-photos.ps1 -Test          # only first 5 developments
  powershell -File download-zisla-photos.ps1 -Thumbnails    # smaller thumbnail images instead of full-res
#>
param(
  [string]$OutDir = "G:\My Drive\zisla-tracker\photos",
  [int]$MaxConcurrency = 8,
  [switch]$Test,
  [switch]$Thumbnails
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Headers = @{
  "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
  "Referer"    = "https://www.zisla.com/"
  "Accept"     = "application/json"
}

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

function Get-SafeFolderName {
  param([string]$Name)
  $invalid = [System.IO.Path]::GetInvalidFileNameChars() -join ''
  $pattern = "[{0}]" -f [regex]::Escape($invalid)
  return ($Name -replace $pattern, '_')
}

Write-Host "Fetching developments from zisla.com ..."
$developments = Get-ZislaDevelopments
Write-Host "Total developments: $($developments.Count)"

if ($Test) {
  Write-Host "TEST MODE: limiting to first 5 developments"
  $developments = $developments | Select-Object -First 5
}

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

Write-Host "Building download queue and manifest..."
$queue = New-Object System.Collections.Generic.List[object]
$manifest = New-Object System.Collections.Generic.List[object]

foreach ($p in $developments) {
  if (-not $p.photos -or $p.photos.Count -eq 0) { continue }
  $folder = Get-SafeFolderName $p.localized.urlAlias
  $devDir = Join-Path $OutDir $folder
  if (-not (Test-Path $devDir)) { New-Item -ItemType Directory -Path $devDir -Force | Out-Null }

  $idx = 0
  foreach ($photo in $p.photos) {
    $idx++
    $relUrl = if ($Thumbnails -and $photo.thumbnail) { $photo.thumbnail } else { $photo.url }
    if (-not $relUrl) { continue }
    $ext = [System.IO.Path]::GetExtension($relUrl)
    if (-not $ext) { $ext = ".webp" }
    $fileName = "{0}_{1:D3}{2}" -f $folder, $idx, $ext
    $localPath = Join-Path $devDir $fileName
    $fullUrl = "https://www.zisla.com$relUrl"

    $queue.Add([PSCustomObject]@{ Url = $fullUrl; Path = $localPath })
    $manifest.Add([PSCustomObject]@{
      "Development"    = $p.localized.title
      "Development ID" = $p._id
      "urlAlias"       = $p.localized.urlAlias
      "Photo Index"    = $idx
      "Filename"       = $fileName
      "Local Path"     = $localPath
      "Source URL"     = $fullUrl
    })
  }
}

Write-Host "Queued $($queue.Count) photos across $($developments.Count) developments"
$manifest | Export-Csv -Path (Join-Path $OutDir "photo-manifest.csv") -NoTypeInformation -Encoding UTF8
Write-Host "Wrote manifest: $(Join-Path $OutDir 'photo-manifest.csv')"

$toDownload = $queue | Where-Object { -not (Test-Path $_.Path) }
$alreadyHave = $queue.Count - $toDownload.Count
if ($alreadyHave -gt 0) { Write-Host "$alreadyHave already on disk, skipping" }
Write-Host "Downloading $($toDownload.Count) photos with $MaxConcurrency concurrent workers..."

if ($toDownload.Count -eq 0) {
  Write-Host "Nothing to download."
  return
}

$downloadScript = {
  param($Url, $Path)
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $wc = New-Object System.Net.WebClient
    $wc.Headers.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    $wc.DownloadFile($Url, $Path)
    $wc.Dispose()
    return "OK"
  } catch {
    return "FAIL: $($_.Exception.Message)"
  }
}

$pool = [runspacefactory]::CreateRunspacePool(1, $MaxConcurrency)
$pool.Open()

$handles = New-Object System.Collections.Generic.List[object]
foreach ($item in $toDownload) {
  $ps = [powershell]::Create()
  $ps.RunspacePool = $pool
  [void]$ps.AddScript($downloadScript).AddArgument($item.Url).AddArgument($item.Path)
  $handles.Add([PSCustomObject]@{ Pipe = $ps; Handle = $ps.BeginInvoke(); Item = $item })
}

$done = 0
$failed = New-Object System.Collections.Generic.List[object]
foreach ($h in $handles) {
  $result = $h.Pipe.EndInvoke($h.Handle)
  $h.Pipe.Dispose()
  $done++
  if ($result -notcontains "OK") {
    $failed.Add($h.Item)
  }
  if ($done % 250 -eq 0 -or $done -eq $handles.Count) {
    Write-Host "  $done / $($handles.Count) downloaded ($($failed.Count) failed so far)"
  }
}
$pool.Close()
$pool.Dispose()

Write-Host "Done. $($handles.Count - $failed.Count) succeeded, $($failed.Count) failed."
if ($failed.Count -gt 0) {
  $failedPath = Join-Path $OutDir "failed-downloads.csv"
  $failed | Export-Csv -Path $failedPath -NoTypeInformation -Encoding UTF8
  Write-Host "Failed downloads logged to $failedPath - re-run the script to retry them (existing files are skipped)."
}
