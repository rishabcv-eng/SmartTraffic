# Rebuild both decks end to end, in one command.
#
#   powershell -ExecutionPolicy Bypass -File docs\deck\build_all.ps1
#
# Generates the slides, injects transitions, and exports a PDF of each using the
# installed PowerPoint. Nothing here needs to be done by hand, so a changed
# result means re-running this rather than editing slides.

$ErrorActionPreference = 'Stop'
$deck = $PSScriptRoot
Set-Location $deck

# PowerPoint keeps an exclusive lock on an open file, so a rebuild fails while
# the deck is on screen. Close it first rather than failing halfway through.
Get-Process POWERPNT -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 800

$env:NODE_PATH = Join-Path $deck 'node_modules'

Write-Host '1/3  generating slides' -ForegroundColor Cyan
node build_deck_5min.js
node build_deck.js

Write-Host '2/3  adding transitions' -ForegroundColor Cyan
python add_motion.py SmartTraffic-5min.pptx
python add_motion.py SmartTraffic-full.pptx
Remove-Item *.bak -ErrorAction SilentlyContinue

Write-Host '3/3  exporting PDF' -ForegroundColor Cyan
$ppt = New-Object -ComObject PowerPoint.Application
try {
    foreach ($name in @('SmartTraffic-5min', 'SmartTraffic-full')) {
        $src = Join-Path $deck "$name.pptx"
        $out = Join-Path $deck "$name.pdf"
        if (Test-Path $out) { Remove-Item $out -Force }
        # ReadOnly, not Untitled, no window.
        $pres = $ppt.Presentations.Open($src, $true, $false, $false)
        $pres.SaveAs($out, 32)      # 32 = ppSaveAsPDF
        $pres.Close()
        Write-Host "     $name.pdf" -ForegroundColor Green
    }
}
finally {
    $ppt.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
}

Get-ChildItem *.pptx, *.pdf | Select-Object Name, @{N = 'KB'; E = { [int]($_.Length / 1KB) } }
Write-Host 'done' -ForegroundColor Cyan
