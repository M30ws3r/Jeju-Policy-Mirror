# 제주데이터허브 614 · 일일 노선별 버스 이용자 정보 (API) — 월별 제공 건수 확인 (조건 없이 전체)
# 실행: powershell -ExecutionPolicy Bypass -File "Jeju Policy Mirror\backend\scripts\check_bus_coverage.ps1"
# 2016-01 ~ 2026-10 을 한 달씩 물어 건수만 기록한다 (약 130회 호출). 결과: data\real\bus_coverage.txt
$key = $env:JEJU_KEY
if (-not $key) { $key = (Read-Host "프로젝트 키를 붙여넣고 Enter").Trim() }
$base = "https://open.jejudatahub.net/api/proxy/1t4tbb16b4t1t11tt11tDt1ab6114a1t/$key"
$backend = Split-Path -Parent $PSScriptRoot
$out = Join-Path $backend "data\real\bus_coverage.txt"
function Get-Hub($u) {
    $r = Invoke-WebRequest $u -UseBasicParsing
    [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json
}
$lines = @()
$m = [datetime]"2016-01-01"
while ($m -le [datetime]"2026-10-01") {
    $s = $m.ToString("yyyyMMdd"); $e = $m.AddMonths(1).AddDays(-1).ToString("yyyyMMdd")
    try { $cnt = (Get-Hub "$base`?startDate=$s&endDate=$e&limit=1").totCnt }
    catch { Write-Host "중단: $s 에서 오류 → $($_.Exception.Message)"; break }
    $line = $m.ToString("yyyy-MM") + "," + $cnt
    $lines += $line; Write-Host $line
    $m = $m.AddMonths(1)
}
$lines | Set-Content $out -Encoding UTF8
"=== 끝 === 결과 파일: data\real\bus_coverage.txt"
