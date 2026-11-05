$ErrorActionPreference = 'Stop'
$reportPath = Join-Path $PSScriptRoot 'reports\性能测试总报告-20261105\安全电商系统性能测试总报告.docx'
$qaPath = Join-Path $PSScriptRoot 'reports\overall-qa'
New-Item -ItemType Directory -Path $qaPath -Force | Out-Null
$pdfPath = Join-Path $qaPath 'report.pdf'
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $document = $word.Documents.Open($reportPath, $false, $true)
    $document.Repaginate()
    $pageCount = $document.ComputeStatistics(2)
    $document.ExportAsFixedFormat($pdfPath, 17)
    Write-Output "Rendered Word document: $pageCount pages"
} finally {
    if ($null -ne $document) { $document.Close(0) }
    if ($null -ne $word) { $word.Quit() }
    if ($null -ne $document) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) }
    if ($null -ne $word) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) }
}
