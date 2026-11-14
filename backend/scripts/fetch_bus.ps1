# 제주데이터허브 614 · 일일 노선별 버스 이용자 정보 (API) 수집 — 이어받기 지원
# 실행: powershell -ExecutionPolicy Bypass -File "Jeju Policy Mirror\backend\scripts\fetch_bus.ps1"
# - 승차·일반·카드 조건으로 하루씩 받아 노선별 합계만 data\real\bus_days\날짜.csv 로 저장한다.
# - 이미 받은 날짜는 건너뛴다. 쿼터가 끝나면 다음 날 같은 명령을 다시 실행하면 이어서 받는다.
# - 4일 간격으로 먼저 훑고 사이를 채우므로, 중간에 멈춰도 전 기간이 고르게 확보된다.
# - 프로젝트 키는 파일에 저장하지 않는다 (실행할 때 입력).
param([string]$Start = "20160901", [string]$End = "20171130", [int]$MaxCalls = 950)

$key = $env:JEJU_KEY
if (-not $key) { $key = (Read-Host "프로젝트 키를 붙여넣고 Enter").Trim() }
$base = "https://open.jejudatahub.net/api/proxy/1t4tbb16b4t1t11tt11tDt1ab6114a1t/$key"
$filter = "moveType=" + [uri]::EscapeDataString("승차") + "&priceType=" + [uri]::EscapeDataString("일반") + "&payType=" + [uri]::EscapeDataString("카드")
$backend = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $backend "data\real\bus_days"
New-Item -ItemType Directory -Force $dir | Out-Null

function Get-Hub($u) {
    $r = Invoke-WebRequest $u -UseBasicParsing
    [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json
}

$d0 = [datetime]::ParseExact($Start, "yyyyMMdd", $null)
$d1 = [datetime]::ParseExact($End, "yyyyMMdd", $null)
$days = @(); for ($d = $d0; $d -le $d1; $d = $d.AddDays(1)) { $days += $d }
$order = @(); foreach ($o in 0, 2, 1, 3) { for ($i = $o; $i -lt $days.Count; $i += 4) { $order += $days[$i] } }

$calls = 0
foreach ($d in $order) {
    $ds = $d.ToString("yyyyMMdd")
    $out = Join-Path $dir "$ds.csv"
    if (Test-Path $out) { continue }
    if ($calls -ge $MaxCalls) { Write-Host "오늘 호출 한도($MaxCalls)에 도달해 멈춥니다."; break }
    $rows = @(); $n = 1; $failed = $false
    try {
        while ($true) {
            $r = Get-Hub "$base`?startDate=$ds&endDate=$ds&limit=100&number=$n&$filter"
            $calls++
            if ($r.data) { $rows += $r.data }
            if (-not $r.hasMore) { break }
            $n++
        }
    } catch {
        Write-Host "중단: $ds 에서 오류 → $($_.Exception.Message)"
        $failed = $true
    }
    if ($failed) { break }
    $agg = @($rows | Group-Object routeName | ForEach-Object {
        [pscustomobject]@{ baseDate = $ds; routeName = $_.Name; userCount = ($_.Group | Measure-Object userCount -Sum).Sum }
    })
    if ($agg.Count -eq 0) { $agg = @([pscustomobject]@{ baseDate = $ds; routeName = ""; userCount = 0 }) }
    $agg | Export-Csv $out -NoTypeInformation -Encoding UTF8
    Write-Host "$ds  노선 $($agg.Count)개  (호출 누계 $calls)"
}

$files = @(Get-ChildItem $dir -Filter *.csv)
$all = $files | ForEach-Object { Import-Csv $_.FullName } | Where-Object { $_.routeName }
$all | Export-Csv (Join-Path $backend "data\real\bus.csv") -NoTypeInformation -Encoding UTF8
"=== 결과 ==="
"받은 날짜: $($files.Count) / $($days.Count)일"
"오늘 호출: $calls 회"
if ($files.Count -lt $days.Count) { "아직 남았습니다. 내일 같은 명령을 다시 실행하면 이어서 받습니다." } else { "전 기간 수집 완료." }
