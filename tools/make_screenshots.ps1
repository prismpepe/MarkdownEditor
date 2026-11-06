# README ... screenshots (light / dark) for this app, taken from docs\sample.
#
#   .\build.cmd                           # the exe must exist (dist\<App>.exe)
#   .\tools\make_screenshots.ps1          # writes docs\images\<App>-light.png / -dark.png
#
# - Runs the built exe with a temporary settings folder (your own settings are not touched).
# - The sample folder is shown as a throw-away drive letter (subst), so no local folder names appear.
# - Needs: Windows 11, Edge WebView2, PowerShell 7+.
# - Keep this file ASCII-only (Japanese text in a .ps1 needs a BOM). Japanese lives in docs\sample\*.md.
param([int]$Port = 9360, [int]$Width = 1400, [int]$Height = 860)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (Test-Path (Join-Path $root 'mdviewer.py')) { $app = 'MarkdownViewer'; $content = '#content'; $open = 'openFile' }
elseif (Test-Path (Join-Path $root 'mdeditor.py')) { $app = 'MarkdownEditor'; $content = '#preview'; $open = 'openPath' }
else { throw 'Run this from the repository (mdviewer.py or mdeditor.py not found).' }

$exe = Join-Path $root "dist\$app.exe"
if (-not (Test-Path $exe)) { throw "$exe not found. Run .\build.cmd first." }
if (Get-Process $app -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe }) { throw "$app.exe (dist) is running. Close it first." }

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("mdshot_" + [guid]::NewGuid().ToString('N').Substring(0, 8))
$sample = Join-Path $tmp 'sample'
New-Item -ItemType Directory $sample -Force | Out-Null
Copy-Item (Join-Path $root 'docs\sample\*.md') $sample
# the main sample document: the file whose name starts with U+306F (the hiragana letter HA: the introduction page)
$main = Get-ChildItem $sample -Filter *.md | Where-Object { $_.Name.StartsWith([string][char]0x306F) } | Select-Object -First 1
if (-not $main) { throw 'No sample file whose name starts with U+306F (docs\sample).' }

# a free drive letter (Z downwards), so the screenshot shows e.g. "Z:\" instead of a real path
$letter = (90..68 | ForEach-Object { [char]$_ } | Where-Object { -not (Test-Path "${_}:\") } | Select-Object -First 1)
if (-not $letter) { throw 'No free drive letter.' }
subst "${letter}:" $sample
$docPath = "${letter}:\" + $main.Name

$env:APPDATA = Join-Path $tmp 'appdata'
New-Item -ItemType Directory $env:APPDATA -Force | Out-Null
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$Port"
$proc = Start-Process $exe -ArgumentList "`"$docPath`"" -PassThru

$script:id = 0
function Send($ws, $method, $params) {
  $script:id++
  $msg = @{ id = $script:id; method = $method; params = $params } | ConvertTo-Json -Compress -Depth 8
  $b = [Text.Encoding]::UTF8.GetBytes($msg)
  $ws.SendAsync([ArraySegment[byte]]$b, 'Text', $true, [Threading.CancellationToken]::None).Wait()
  while ($true) {                                   # skip events, wait for our reply
    $ms = New-Object IO.MemoryStream
    do {
      $buf = New-Object byte[] 65536
      $r = $ws.ReceiveAsync([ArraySegment[byte]]$buf, [Threading.CancellationToken]::None).Result
      $ms.Write($buf, 0, $r.Count)
    } until ($r.EndOfMessage)
    $m = [Text.Encoding]::UTF8.GetString($ms.ToArray()) | ConvertFrom-Json
    if ($m.id -eq $script:id) { return $m }
  }
}
function Ev($ws, $expr) { (Send $ws 'Runtime.evaluate' @{ expression = $expr; returnByValue = $true; awaitPromise = $true }).result.result.value }
function WaitFor($ws, $expr, $seconds) {
  $until = (Get-Date).AddSeconds($seconds)
  while ((Get-Date) -lt $until) { if (Ev $ws $expr) { return $true }; Start-Sleep -Milliseconds 400 }
  return $false
}

try {
  $page = $null
  for ($i = 0; $i -lt 40 -and -not $page; $i++) {
    Start-Sleep -Milliseconds 500
    try { $page = (Invoke-RestMethod "http://127.0.0.1:$Port/json") | Where-Object { $_.type -eq 'page' } | Select-Object -First 1 } catch { }
  }
  if (-not $page) { throw 'Could not connect to the app (remote debugging).' }
  $ws = New-Object System.Net.WebSockets.ClientWebSocket
  $ws.ConnectAsync([Uri]$page.webSocketDebuggerUrl, [Threading.CancellationToken]::None).Wait()

  Send $ws 'Emulation.setDeviceMetricsOverride' @{ width = $Width; height = $Height; deviceScaleFactor = 1; mobile = $false } | Out-Null
  $pathJs = $docPath | ConvertTo-Json -Compress
  $imgDir = Join-Path $root 'docs\images'
  New-Item -ItemType Directory $imgDir -Force | Out-Null

  foreach ($scheme in 'light', 'dark') {
    Send $ws 'Emulation.setEmulatedMedia' @{ features = @(@{ name = 'prefers-color-scheme'; value = $scheme }) } | Out-Null
    # open the document again so that diagrams are drawn in this color scheme
    Ev $ws "$open($pathJs)" | Out-Null
    $ready = WaitFor $ws "document.querySelectorAll('$content .diagram svg, $content pre code.highlighted').length >= 2" 40
    if (-not $ready) { throw "The sample document did not finish rendering ($scheme)." }
    Start-Sleep -Milliseconds 1200
    Ev $ws "document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); 1" | Out-Null
    $shot = Send $ws 'Page.captureScreenshot' @{ format = 'png' }
    $out = Join-Path $imgDir "$app-$scheme.png"
    [IO.File]::WriteAllBytes($out, [Convert]::FromBase64String($shot.result.data))
    '{0}: {1:N0} KB' -f $out, ((Get-Item $out).Length / 1KB)
  }

  # Figures: a four-backtick markdown block in docs\sample\*.md holds the SOURCE of a diagram (mermaid, vega-lite ...).
  # Draw each one in the app (light) and save docs\images\sample-<language>.png, so that "source + image" always match.
  Send $ws 'Emulation.setEmulatedMedia' @{ features = @(@{ name = 'prefers-color-scheme'; value = 'light' }) } | Out-Null
  $bt3 = '`' * 3
  $bt4 = '`' * 4
  $pattern = '(?s)' + [regex]::Escape($bt4) + 'markdown\r?\n(.*?)\r?\n' + [regex]::Escape($bt4)
  foreach ($f in Get-ChildItem (Join-Path $root 'docs\sample') -Filter *.md) {
    $text = [IO.File]::ReadAllText($f.FullName, [Text.Encoding]::UTF8)
    foreach ($m in [regex]::Matches($text, $pattern)) {
      $inner = $m.Groups[1].Value
      $lang = [regex]::Match($inner, '^' + [regex]::Escape($bt3) + '([A-Za-z0-9_-]+)').Groups[1].Value
      if (-not $lang) { continue }
      [IO.File]::WriteAllText((Join-Path $sample "fig_$lang.md"), $inner + "`n", (New-Object Text.UTF8Encoding($false)))
      $figJs = ("${letter}:\fig_$lang.md") | ConvertTo-Json -Compress
      Ev $ws "$open($figJs)" | Out-Null
      if (-not (WaitFor $ws "document.querySelectorAll('$content .diagram svg').length >= 1" 40)) { throw "The figure ($lang) was not drawn." }
      Start-Sleep -Milliseconds 800
      $rect = (Ev $ws "(() => { const e = document.querySelector('$content .diagram svg'); e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect(); return JSON.stringify({x: r.x, y: r.y, w: r.width, h: r.height}); })()") | ConvertFrom-Json
      $pad = 14
      $clip = @{ x = [Math]::Max(0, $rect.x - $pad); y = [Math]::Max(0, $rect.y - $pad); width = $rect.w + 2 * $pad; height = $rect.h + 2 * $pad; scale = 1 }
      $shot = Send $ws 'Page.captureScreenshot' @{ format = 'png'; clip = $clip }
      $out = Join-Path $imgDir "sample-$lang.png"
      [IO.File]::WriteAllBytes($out, [Convert]::FromBase64String($shot.result.data))
      '{0}: {1:N0} KB' -f $out, ((Get-Item $out).Length / 1KB)
    }
  }
}
finally {
  Get-Process $app -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe } | Stop-Process -Force
  Start-Sleep -Seconds 2
  subst "${letter}:" /d | Out-Null
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
