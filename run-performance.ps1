param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('order', 'login')]
    [string]$Scenario,
    [ValidateSet('smoke', 'load')]
    [string]$Mode = 'smoke',
    [ValidateRange(1, 9)]
    [int]$Users = 9,
    [ValidateRange(1, 100)]
    [int]$Quantity = 1
)

$ErrorActionPreference = 'Stop'
$perfRoot = $PSScriptRoot
$projectRoot = Split-Path -Parent $perfRoot
$planName = if ($Scenario -eq 'order') { '下单性能测试.jmx' } else { '登录性能测试.jmx' }
$label = if ($Scenario -eq 'order') { '03_创建订单' } else { '01_普通用户登录' }
$delay = if ($Scenario -eq 'order') { 500 } else { 1000 }
$loops = if ($Mode -eq 'load') { -1 } else { 1 }
$ramp = if ($Mode -eq 'load') { 10 } else { $Users }
$runId = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$runDir = Join-Path $perfRoot "results\$Scenario\$Mode-$runId"
New-Item -ItemType Directory -Path $runDir | Out-Null

# Disable visual listeners for the CLI copy, while keeping the editable source.
$sourcePlan = Join-Path $perfRoot "plans\$planName"
[xml]$plan = [System.IO.File]::ReadAllText($sourcePlan)
foreach ($listener in $plan.SelectNodes('//ResultCollector')) {
    $listener.SetAttribute('enabled', 'false')
}
$snapshot = Join-Path $runDir 'plan-used.jmx'
$plan.Save($snapshot)
@{
    scenario = $Scenario; mode = $Mode; users = $Users; loops = $loops;
    ramp_seconds = $ramp; duration_seconds = 390; delay_ms = $delay;
    quantity = $Quantity; measured_label = $label;
    required_backend_environment = 'PERF_TEST_MODE=1';
    source_plan = $sourcePlan;
    measurement = 'Skip first 70 seconds; select starts in following 300 seconds; retain failures'
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runDir 'settings.json') -Encoding UTF8

Write-Host "Scenario=$Scenario Mode=$Mode Users=$Users Loops=$loops"
Write-Host "Backend must already be running with PERF_TEST_MODE=1."
if ($Scenario -eq 'order') {
    Write-Host 'This creates real orders and consumes stock. All selected test accounts must start with empty carts.'
}
$launcher = Join-Path $perfRoot 'jmeter\start-jmeter-java21.bat'
& $launcher -n -t $snapshot "-Jusers=$Users" "-Jramp=$ramp" "-Jloops=$loops" `
    '-Jduration=390' "-Jdelay_ms=$delay" "-Jquantity=$Quantity" `
    '-Jjmeter.save.saveservice.output_format=csv' `
    '-Jjmeter.save.saveservice.timestamp_format=ms' `
    '-Jjmeter.save.saveservice.print_field_names=true' `
    -l (Join-Path $runDir 'raw.jtl') -j (Join-Path $runDir 'jmeter.log')

$raw = Join-Path $runDir 'raw.jtl'
if (-not (Test-Path -LiteralPath $raw)) { throw "No JTL produced. Check $runDir\jmeter.log" }
$samples = @(Import-Csv -LiteralPath $raw -Encoding UTF8)
if ($samples.Count -eq 0) { throw "No HTTP samples. Check CSV initialization and $runDir\jmeter.log" }
$failed = @($samples | Where-Object { $_.success -ne 'true' })
Write-Host "HTTP samples=$($samples.Count) Failed=$($failed.Count)"
& $launcher -g $raw -o (Join-Path $runDir 'full-html')
if ($LASTEXITCODE -ne 0) { throw 'Full report generation failed. Inspect the JMeter log.' }

if ($Mode -eq 'load') {
    $python = Join-Path $projectRoot 'venv\Scripts\python.exe'
    $extractor = Join-Path $perfRoot 'extract_measurement.py'
    $measurement = Join-Path $runDir 'measurement.jtl'
    & $python $extractor $raw --label $label --skip-seconds 70 --seconds 300 --output $measurement
    if ($LASTEXITCODE -ne 0) { throw 'Measurement extraction failed; retain raw results and inspect initialization failures.' }
    & $launcher -g $measurement -o (Join-Path $runDir 'measurement-html')
    if ($LASTEXITCODE -ne 0) { throw 'Measurement report generation failed.' }
}
Write-Host "Results saved to: $runDir"
if ($failed.Count -gt 0) {
    Write-Warning 'This run has failures. Inspect status codes and active thread counts before using it as a baseline.'
}
