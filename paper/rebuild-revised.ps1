# Regenerate every number, table and figure of the revised paper from results/,
# then lay it out as Word and export the PDF through Word itself.
#   powershell -ExecutionPolicy Bypass -File paper\rebuild-revised.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"

$parts = Get-ChildItem results\corpus-v2 -Directory | Where-Object { Test-Path (Join-Path $_.FullName "runs.csv") } | ForEach-Object { $_.FullName }
python research\merge_results.py --out results\v2 @parts
python research\analyze_statistics.py --runs results\v2\runs.csv --out results\v2 | Out-Null
python research\corpus_table.py --manifest research\corpus-v2.json --results results\corpus-v2 --out results\v2\corpus_table.json
python research\paper_numbers.py --results results\v2 | Out-File -Encoding utf8 results\v2\paper_numbers.md
python research\live_numbers.py --live results\live | Out-File -Encoding utf8 results\v2\live_numbers.md
python research\make_figures.py --results results\v2 --out paper\figures-v2
Copy-Item paper\figures\fig-pipeline.* paper\figures-v2\ -Force
python research\fill_paper.py --v2 results\v2 --live results\live --template paper\paper-revised.template.md --out paper\paper-revised.md

Push-Location paper
node build-paper-docx.js paper-revised.md paper-revised.docx
Pop-Location

$doc = Join-Path $root "paper\paper-revised.docx"
$pdf = Join-Path $root "paper\paper-revised.pdf"
# Word may hand back the user's already-running instance. Close only the
# document opened here, and afterwards stop only Word processes this script
# started -- a stray instance left holding the file makes the next export hang
# on an invisible "file in use" prompt.
$before = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$word = New-Object -ComObject Word.Application
$word.DisplayAlerts = 0
$d = $word.Documents.Open($doc, $false, $true)
try {
    $d.ExportAsFixedFormat($pdf, 17)
} finally {
    $d.Close(0)
    if ($word.Documents.Count -eq 0) { $word.Quit() }
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    Start-Sleep -Seconds 2
    Get-Process WINWORD -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id } | Stop-Process -Force
}
"wrote $doc and $pdf"
