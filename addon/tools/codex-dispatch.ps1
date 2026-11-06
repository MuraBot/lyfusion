# 把简报派给 Codex 助手,并当监工:缺最终报告就要求补,阶段证据不全又没停下就续跑,验收命令不过就让助手接着修。
# 每次运行自动记台账;运行结束后由脚本提交助手的改动,打交接包 bundle.md。用法见 prompts/dispatch.md:
#   .\tools\codex-dispatch.ps1 -Task T5 -Model gpt-6-luna -Explore -AskFile dispatch-logs\asks\T5-ask.md   只读探索,产出探索包
#   .\tools\codex-dispatch.ps1 -Task T5 -Model gpt-6-luna                                    派工:检查简报、登记、记起点、启动
#   .\tools\codex-dispatch.ps1 -Task T5 -Model gpt-6-luna -Resume 探索会话编号                派工,续用本任务的探索会话(它读过代码)
#   .\tools\codex-dispatch.ps1 -Task T5 -Model gpt-6-luna -Resume 会话编号 -MessageFile 文件 [-Contract]   修改请求、回答问题
#   .\tools\codex-dispatch.ps1 -Task T5 -Accept -Session lead的会话编号 [-Note "看了哪些"]   跑验收命令、核对修改请求、记结论、提交
#   .\tools\codex-dispatch.ps1 -Task T5 -Rollback -Session lead的会话编号                   退回派工前的起点(台账和简报不退)
#   .\tools\codex-dispatch.ps1 -Task 预检 -Model 模型名 -Effort low -Preflight "构建命令"
# 同时开着前端子代理时才用工作目录:派工加 -Worktree [-From task/T4];收尾用 ledger.py review、-Merge [-Playtest]、-Cleanup。
# 可选参数:
#   -Effort low/medium/high 等      推理强度;不加就用"项目设置"里的 $DefaultEffort
#   -Sandbox workspace-write 或 danger-full-access   不加就用下面"项目设置"里的默认值
#   -Message "……"                   续用时的短消息;长的、带引号的用 -MessageFile
#   -Contract                       消息是改变契约的决定:先写进简报的"已定",再交给助手
#   -Playtest                       验收或合并后要 Lily 试玩:状态改成 verify,不改成 done
#   -NoSupervise                    不自动续跑
# 本文件保存为带 BOM 的 UTF-8,Windows PowerShell 5.1 才能正确读取中文。
param(
    [Parameter(Mandatory = $true)][string]$Task,
    [string]$Model,
    [string]$Resume,
    [string]$Message,
    [string]$MessageFile,
    [switch]$Contract,
    [switch]$Explore,
    [string]$AskFile,
    [string]$Base = "main",
    [string]$Effort,
    [ValidateSet("", "workspace-write", "danger-full-access")][string]$Sandbox = "",
    [switch]$Worktree,
    [string]$From,
    [string]$Preflight,
    [switch]$Accept,
    [switch]$Rollback,
    [string]$Session,
    [string]$Note = "",
    [switch]$Merge,
    [switch]$Playtest,
    [switch]$Cleanup,
    [switch]$NoSupervise
)

# ---- 项目设置:每个项目只改这里 ----
# lead 可以直接改这一块,在提交说明里写明。沙箱模式除外,改它要 Lily 同意(Lily 2026-10-28)
# 沙箱默认值。只有环境预检证明沙箱里跑不通、并且 Lily 同意后,才改成 danger-full-access
$DefaultSandbox = "workspace-write"
# 助手要用的命令。派工前检查,缺的写进提示词开头,例如 @("git", "python", "rg")
$NeedCommands = @("git", "python")
# 传给 agent 的环境变量,例如 @{ GRADLE_USER_HOME = "D:\gradle-cache" }
$ProjectEnv = @{}
# 建工作目录时从主目录复制过去的文件。只写 Lily 已授权的,例如 @("run/eula.txt")
$CopyIntoWorktree = @()
# 一次派工最多自动续跑几次
$MaxContinue = 3
# 验收命令:助手做完后脚本跑,不通过就让助手接着修;-Accept 和 -Merge 前再跑。留空就跳过
# 测试命令,例如 "gradlew.bat test"
$TestCommand = ""
# lint 命令,例如 "python -m ruff check --fix ."。各语言的推荐命令见 lyfusion 的 README「lint」
$LintCommand = ""
# 验收命令不通过时,最多让助手修几次
$MaxGateFix = 2
# 验收命令输出里有这些,算环境错误(证书、网络):脚本原样重跑 1 次,不交给助手修
$EnvFailurePattern = 'certificate|PKIX|SSLHandshake|Could not resolve host|UnknownHost|Connection (timed out|refused|reset)|Read timed out'
# 助手跑过的命令里有这些,算禁止的操作:写进交接包,-Accept 拒绝验收,先问 Lily。按项目的禁令补充
$ForbiddenPattern = 'check\.certs=false|--no-verify|commit\.gpgsign=false|git push'
# 助手会话的累计输入超过这个数,提醒下个任务不要再续用它
$BigSession = 30000000
# 交接包里"关键改动"一共大约放多少行 diff,平分给每个改动的文件
$BundleDiffLines = 600
# 助手的推理强度,派工不加 -Effort 时用它。Lily 2026-11-06:gpt-6-luna 统一用 high(依据 Cognition 的文章);留空就用 Codex 的默认配置
$DefaultEffort = "high"
# lead 用 -Accept、-Rollback 提交时,追溯信息里的模型和推理强度
$LeadModel = "claude-opus-5-5"
$LeadEffort = "high"
# ---- 项目设置结束 ----

$ErrorActionPreference = "Continue"
if (-not $Sandbox) { $Sandbox = $DefaultSandbox }
$root = Split-Path $PSScriptRoot -Parent
$PSDefaultParameterValues["Out-File:Encoding"] = "utf8"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$work = $root
$branch = "task/$Task"
$wtPath = Join-Path (Split-Path $root -Parent) ((Split-Path $root -Leaf) + "-" + $Task)
if ($Worktree -or (Test-Path $wtPath)) { $work = $wtPath }
$logDir = Join-Path $root "dispatch-logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$evidence = "dispatch-logs/evidence/$Task"
$stem = Join-Path $logDir ("{0}-{1}" -f $Task, (Get-Date -Format "yyyyMMdd-HHmmss"))
if (-not $Effort -and $DefaultEffort) { $Effort = $DefaultEffort }
$effortName = if ($Effort) { $Effort } else { "default" }

# Codex 和验收命令交给 run_logged.py 运行,不用 &:后台的 git 会占着输出管道让 & 挂住,原因见 run_logged.py
function Invoke-Logged([hashtable]$Spec, [string]$SpecFile) {
    $Spec | ConvertTo-Json | Out-File $SpecFile -Encoding UTF8
    python (Join-Path $root "tools\run_logged.py") $SpecFile | Out-Host
    return $LASTEXITCODE
}

function Get-Tail([string]$Path, [int]$N) { @(Get-Content $Path -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last $N) }
function Test-EnvFailure([string]$Path) { [bool](Select-String -Path $Path -Encoding UTF8 -Pattern $EnvFailurePattern -Quiet -ErrorAction SilentlyContinue) }
# 失败相关的行(断言、异常、失败的用例),最多 30 行:只给最后 40 行时,断言常在更前面(HEX T12)
function Get-FailLines([string]$Path) {
    @(Select-String -Path $Path -Encoding UTF8 -Pattern '(?i)fail|error|expected|exception|assert' -ErrorAction SilentlyContinue | Select-Object -First 30 | ForEach-Object { $_.Line })
}
# 测试结果的汇总行,例如 "All 46 required tests passed"
function Get-TestSummary([string]$Path) {
    @(Select-String -Path $Path -Encoding UTF8 -Pattern '(?i)tests? (passed|failed)|required tests|Tests run:|\d+ (passed|failed)' -ErrorAction SilentlyContinue | Select-Object -Last 5 | ForEach-Object { $_.Line })
}

# 临时目录放进工作目录,每次运行一个:沙箱只能写工作目录;pytest 清理上次的临时目录会报权限错误(fusion-bench C1-H2、C2-H2)
function Set-WorkTemp {
    $t = Join-Path $work ("dispatch-logs\tmp\" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Force $t | Out-Null
    $env:TEMP = $t; $env:TMP = $t
}

# 跑测试和 lint 命令,返回每条的结果
function Invoke-Gates([string]$Tag) {
    $res = @()
    foreach ($g in @(@("测试", $TestCommand, "test"), @("lint", $LintCommand, "lint"))) {
        if (-not $g[1]) { continue }
        $out = "$stem-$Tag-$($g[2]).out.txt"
        $code = Invoke-Logged @{ shell = $g[1]; cwd = $work; out = $out } "$out.json"
        $res += , @{ Name = $g[0]; Cmd = $g[1]; Code = $code; Out = $out }
    }
    return , $res
}

# 模型备注:prompts/models/模型名.md 里「## 备注」下的条目。「## 待观察」的不用
function Get-ModelNotes {
    $f = Join-Path $root "prompts\models\$Model.md"
    $out = @()
    if (-not ($Model -and (Test-Path $f))) { return , $out }
    $on = $false
    foreach ($l in Get-Content $f -Encoding UTF8) {
        if ($l -match '^## ') { $on = $l -match '^## 备注'; continue }
        if ($on -and $l -match '^\s*- ') { $out += $l.Trim() }
    }
    return , $out
}

# lead 的提交(-Accept、-Rollback):追溯信息写 lead 的
function Save-LeadCommit([string]$Title) {
    if (-not (git -C $root status --porcelain)) { return }
    $msgFile = "$stem.lead-commit.txt"
    $msg = "$Title`n`nTask: $Task`nAgent: Claude Code`nModel: $LeadModel`nEffort: $LeadEffort`nSession: $Session`n"
    [IO.File]::WriteAllText($msgFile, $msg, (New-Object Text.UTF8Encoding $false))
    git -C $root add -A
    git -C $root commit -q -F $msgFile
    if ($LASTEXITCODE -ne 0) { Write-Warning "提交失败,改动还在:$root" }
}

# 修改请求的编号,例如 R1、R2:只认行首的。正文里顺带提到的"T7 的 R3"不算(HEX T8、T11 被记成了修改请求)
function Get-RequestIds([string]$Text) {
    @([regex]::Matches($Text, '(?m)^[ \t]*(?:[-*][ \t]*)?(?:\*\*)?(R\d+)(?!\d)') | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique)
}
# 报告「修改请求的回应」一节里带本任务前缀的编号,例如 T5-R1。别的任务的 R1 不算(HEX 的长会话把 T2 的回应带进了 T3~T12)
# -Session 要写 lead 的会话编号。台账里记过的助手会话就拒绝(HEX 的验收提交全写成了助手的)
function Test-SidekickSession([string]$S) {
    $lf = Join-Path $root "ledger.jsonl"
    if (-not (Test-Path $lf)) { return $false }
    [bool]@(Get-Content $lf -Encoding UTF8 | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.kind -eq "run" -and $_.session -eq $S }).Count
}
# 报告里某一节的条目,不算"无"
function Get-ReportItems([string]$Path, [string]$Title) {
    if (-not (Test-Path $Path)) { return @() }
    $sec = ([regex]::Match((Get-Content $Path -Encoding UTF8 -Raw), '(?ms)^## ' + [regex]::Escape($Title) + '\s*$(.*?)(?=^## |\z)')).Groups[1].Value
    @($sec -split "`n" | Where-Object { $_ -match '^- ' -and $_.Trim() -ne "- 无" } | ForEach-Object { $_.Trim() })
}
function Get-ResponseIds([string]$Path) {
    if (-not (Test-Path $Path)) { return @() }
    $sec = ([regex]::Match((Get-Content $Path -Encoding UTF8 -Raw), '(?ms)^## 修改请求的回应\s*$(.*?)(?=^## |\z)')).Groups[1].Value
    @([regex]::Matches($sec, "(?<![A-Za-z0-9])$([regex]::Escape($Task))-(R\d+)(?!\d)") | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique)
}

# ---- 合并后清理:先保存证据,再删工作目录和分支 ----
if ($Cleanup) {
    if (-not (Test-Path $wtPath)) { Write-Error "没有工作目录:$wtPath"; exit 1 }
    if ((Get-Location).Path.StartsWith($wtPath)) { Write-Error "当前目录在要删的工作目录里。先切回主目录:$root"; exit 1 }
    $merged = git -C $root branch --merged $Base --format "%(refname:short)"
    if ($merged -notcontains $branch) { Write-Error "$branch 还没合并进 $Base。没合并的工作目录要先问 Lily"; exit 1 }
    # 新文件也要算,被忽略的(如证据)不算
    $dirty = git -C $wtPath status --porcelain
    if ($dirty) { Write-Error "工作目录里有没提交的改动,lead 先审查并提交:`n$dirty"; exit 1 }
    $ev = Join-Path $wtPath "dispatch-logs\evidence\$Task"
    if (Test-Path $ev) {
        $dest = Join-Path $root "dispatch-logs\evidence"
        New-Item -ItemType Directory -Force $dest | Out-Null
        Copy-Item $ev $dest -Recurse -Force
        "证据已复制到:$(Join-Path $dest $Task)"
    }
    git -C $root worktree remove --force $wtPath
    git -C $root branch -d $branch
    "已删除工作目录 $wtPath 和分支 $branch"
    exit 0
}

# ---- 合并(工作目录模式):先在工作目录里合并 main 并跑测试,通过才合并进 main。任何一步失败,main 不变 ----
if ($Merge) {
    if (-not $TestCommand) { Write-Error "项目设置里的 TestCommand 没填。先填上合并前要跑的测试命令"; exit 1 }
    if (-not (Test-Path $wtPath)) { Write-Error "没有工作目录:$wtPath"; exit 1 }
    $cur = git -C $root rev-parse --abbrev-ref HEAD
    if ($cur -ne $Base) { Write-Error "主目录在 $cur 分支上,先切回 $Base"; exit 1 }
    # 台账和进度由工具写,可以先不提交;其他改动要先提交,不然分不清哪些属于这次合并
    $dirtyMain = @(git -C $root status --porcelain | Where-Object { $_ -notmatch '(ledger\.jsonl|progress\.json)$' })
    if ($dirtyMain.Count) { Write-Error "主目录有没提交的改动,先提交:`n$($dirtyMain -join "`n")"; exit 1 }
    $dirtyWt = git -C $wtPath status --porcelain
    if ($dirtyWt) { Write-Error "工作目录有没提交的改动:`n$dirtyWt"; exit 1 }
    $prog = Get-Content (Join-Path $root "progress.json") -Encoding UTF8 -Raw | ConvertFrom-Json
    $t = @($prog.tasks | Where-Object { $_.id -eq $Task })
    if (-not $t.Count) { Write-Error "progress.json 里没有 $Task"; exit 1 }
    if ($t[0].review -ne "pass") { Write-Error "$Task 的审查结果是 $($t[0].review)。审查通过再合并,用 ledger.py review 记结论"; exit 1 }
    git -C $wtPath merge --no-edit $Base
    if ($LASTEXITCODE -ne 0) { git -C $wtPath merge --abort; Write-Error "把 $Base 合并进 $branch 时有冲突,已撤销。解决冲突后再合并"; exit 1 }
    $ev = Join-Path $root "dispatch-logs\evidence\$Task\merge"
    New-Item -ItemType Directory -Force $ev | Out-Null
    $started = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $code = Invoke-Logged @{ shell = $TestCommand; cwd = $wtPath; out = "$logDir\$Task-merge-test.out.txt" } "$logDir\$Task-merge-test.json"
    $out = Get-Content "$logDir\$Task-merge-test.out.txt" -Encoding UTF8 -ErrorAction SilentlyContinue
    @("命令:$TestCommand", "开始时间:$started", "退出码:$code", "工作目录:$wtPath", "") + @($out) | Out-File (Join-Path $ev "test.txt")
    if ($code -ne 0) { Write-Error "测试失败(退出码 $code),没有合并进 $Base。输出在 $ev\test.txt"; exit 1 }
    git -C $root merge --no-ff --no-edit $branch
    if ($LASTEXITCODE -ne 0) { git -C $root merge --abort; Write-Error "合并进 $Base 时有冲突,已撤销"; exit 1 }
    $status = if ($Playtest) { "verify" } else { "done" }
    python (Join-Path $root "tools\progress.py") set-status $Task $status
    "已把 $branch 合并进 $Base。测试证据:$ev\test.txt"
    "接着:提交主目录的 ledger.jsonl 和 progress.json,再运行 -Cleanup"
    exit 0
}

# ---- 验收(直接在主目录改的模式):跑验收命令、核对修改请求都有回应、记审查结论、改进度、提交,一步做完 ----
if ($Accept) {
    if (Test-Path $wtPath) { Write-Error "$Task 在工作目录里做:先 ledger.py review,再 -Merge、-Cleanup"; exit 1 }
    if (-not $Session) { Write-Error "-Accept 要用 -Session 写明 lead 的会话编号(写进提交的追溯信息)"; exit 1 }
    if (Test-SidekickSession $Session) { Write-Error "$Session 是助手的会话编号。-Session 写 lead 自己的会话编号"; exit 1 }
    $ev = Join-Path $root "dispatch-logs\evidence\$Task"
    if (Test-Path (Join-Path $ev "forbidden.txt")) { Write-Error "助手用过禁止的操作,见 $ev\forbidden.txt。先告诉 Lily;她同意后删掉这个文件再验收"; exit 1 }
    Set-WorkTemp
    $gr = Invoke-Gates "accept"
    $bad = @($gr | Where-Object { $_.Code -ne 0 })
    if ($bad.Count) {
        foreach ($g in $bad) { "$($g.Name) 没通过(退出码 $($g.Code)):$($g.Cmd)"; Get-Tail $g.Out 20 }
        Write-Error "验收命令没通过,不验收。续用让助手修"; exit 1
    }
    # 助手问了 lead 的问题,验收前要答(HEX 的助手问了 3 次分支的事,没人回答)
    $qs = @(Get-ReportItems (Join-Path $ev "report.md") "要 lead 回答的问题")
    if ($qs.Count -and $Note -notmatch '答') { Write-Error "助手有问题要 lead 回答:`n$($qs -join "`n")`n在 -Note 里写怎么答的,例如 -Note ""答:……""。要改代码的,先写修改请求"; exit 1 }
    $ids = @()
    $req = Join-Path $ev "requests-latest.md"
    if (Test-Path $req) {
        $ids = Get-RequestIds (Get-Content $req -Encoding UTF8 -Raw)
        $done = Get-ResponseIds (Join-Path $ev "report.md")
        $miss = @($ids | Where-Object { $done -notcontains $_ })
        if ($miss.Count) { Write-Error "最终报告没有回应这些修改请求:$($miss -join '、')。续用让助手逐条回应"; exit 1 }
    }
    $n = if ($Note) { $Note } else { "验收" }
    python (Join-Path $root "tools\ledger.py") review --task $Task --result pass --findings $ids.Count --by lead --note $n
    if ($LASTEXITCODE -ne 0) { Write-Error "台账没记上审查结论,不验收"; exit 1 }
    $status = if ($Playtest) { "verify" } else { "done" }
    python (Join-Path $root "tools\progress.py") set-status $Task $status 2>$null | Out-Null
    Save-LeadCommit "${Task}:lead 验收($n)"
    "已验收 $Task:验收命令通过,修改请求 $($ids.Count) 条都有回应,进度改成 $status,已提交。"
    exit 0
}

# ---- 退回:撤销派工以来的改动,回到起点。用 revert,历史不删;台账、进度和简报保留 ----
if ($Rollback) {
    if (Test-Path $wtPath) { Write-Error "$Task 在工作目录里做:不合并就是退回"; exit 1 }
    if (-not $Session) { Write-Error "-Rollback 要用 -Session 写明 lead 的会话编号"; exit 1 }
    if (Test-SidekickSession $Session) { Write-Error "$Session 是助手的会话编号。-Session 写 lead 自己的会话编号"; exit 1 }
    $sf = Join-Path $root "$evidence\start.txt"
    if (-not (Test-Path $sf)) { Write-Error "没有起点记录:$sf"; exit 1 }
    $start = (Get-Content $sf -Encoding UTF8 -TotalCount 1).Trim()
    $dirty = @(git -C $root status --porcelain | Where-Object { $_ -notmatch '(ledger\.jsonl|progress\.json)$' -and $_ -notmatch '^.. "?tasks/' })
    if ($dirty.Count) { Write-Error "主目录有没提交的改动,先处理:`n$($dirty -join "`n")"; exit 1 }
    # 台账、进度和简报可能还没提交:先备份,退回后放回原样
    $keep = Join-Path $logDir "rollback-keep"
    Remove-Item $keep -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force $keep | Out-Null
    foreach ($k in @("ledger.jsonl", "progress.json", "tasks")) { if (Test-Path (Join-Path $root $k)) { Copy-Item (Join-Path $root $k) $keep -Recurse -Force } }
    git -C $root revert --no-commit "$start..HEAD"
    if ($LASTEXITCODE -ne 0) { git -C $root revert --abort; Write-Error "退回失败,已撤销"; exit 1 }
    foreach ($k in @("ledger.jsonl", "progress.json", "tasks")) { if (Test-Path (Join-Path $keep $k)) { Copy-Item (Join-Path $keep $k) $root -Recurse -Force } }
    python (Join-Path $root "tools\progress.py") set-status $Task todo 2>$null | Out-Null
    Save-LeadCommit "${Task}:退回到派工前的起点 $start"
    "已退回到 $start。台账、进度和简报保留。"
    exit 0
}

if (-not $Model) { Write-Error "要用 -Model 写明模型。"; exit 1 }
if ($MessageFile) {
    if (-not (Test-Path $MessageFile)) { Write-Error "找不到 -MessageFile:$MessageFile"; exit 1 }
    $Message = Get-Content $MessageFile -Encoding UTF8 -Raw
}
# 续用不带消息 = 在这个会话里开始做任务,发完整的开工提示。用来续用本任务的探索会话(它已经读过代码)
$NewTaskResume = [bool]($Resume -and -not $Message)
if ($Contract -and -not ($Resume -and $Message)) { Write-Error "-Contract 要和 -Resume、-Message 一起用。"; exit 1 }
$cmd = Get-Command codex -ErrorAction SilentlyContinue
$pkg = Get-AppxPackage OpenAI.Codex -ErrorAction SilentlyContinue
if ($cmd) { $exe = $cmd.Source }
elseif ($pkg) { $exe = Join-Path $pkg.InstallLocation "app\resources\codex.exe" }
else { Write-Error "找不到 Codex 命令行。请先安装 Codex App,或运行 npm install -g @openai/codex。"; exit 1 }

# 环境缺口先消除,再检测,最后才写 learning.md。Codex 安装目录里自带 rg 等工具,加进 PATH
$env:PATH = (Split-Path $exe -Parent) + [IO.Path]::PathSeparator + $env:PATH
$missingCmds = @($NeedCommands | Where-Object { -not (Get-Command $_ -ErrorAction SilentlyContinue) })
$envNote = if ($missingCmds.Count) { "本机没有这些命令:$($missingCmds -join '、')。用替代办法继续,在最终报告里说明,不要因此停下。" } else { "" }

# Claude 只由 Lily 使用:不把 Claude 的会话令牌和配置带进 Codex 的环境
$claudeVars = @(Get-ChildItem env: | Where-Object { $_.Name -match '^(CLAUDE|ANTHROPIC)' } | ForEach-Object { $_.Name })
$claudeVars | ForEach-Object { Remove-Item "env:$_" -ErrorAction SilentlyContinue }

# 配置写成 key=value;值不加引号时 Codex 按普通文字处理
$cfg = @()
if ($Effort) { $cfg += @("-c", "model_reasoning_effort=$Effort") }
foreach ($k in $ProjectEnv.Keys) { $cfg += @("-c", "shell_environment_policy.set.$k=$($ProjectEnv[$k])") }
$schema = Join-Path $root "tools\schemas\final.schema.json"
$runId = "run-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$brief = $null

function Invoke-Codex([string[]]$CodexArgs, [string]$Prompt, [string]$Stem) {
    # npm 装的 codex 是 .cmd:批处理在换行处截断参数,修改请求只剩第一行。换成 ⏎ 再传
    if ($exe -match '\.(cmd|bat)$') { $Prompt = $Prompt -replace "`r?`n", " ⏎ " }
    $spec = @{ cmd = @($exe) + @($CodexArgs) + @("--json", "-o", "$Stem.report.txt", $Prompt); cwd = $work
               out = "$Stem.events.jsonl"; err = "$Stem.stderr.log" }
    $code = Invoke-Logged $spec "$Stem.run.json"
    $lines = Get-Content "$Stem.events.jsonl" -Encoding UTF8 -ErrorAction SilentlyContinue
    $thread = $lines | Where-Object { $_ -match '"thread\.started"' } | Select-Object -First 1 | ConvertFrom-Json
    $turn = $lines | Where-Object { $_ -match '"turn\.completed"' } | Select-Object -Last 1 | ConvertFrom-Json
    $final = $null
    if (Test-Path "$Stem.report.txt") {
        $raw = Get-Content "$Stem.report.txt" -Encoding UTF8 -Raw
        try { $final = $raw | ConvertFrom-Json } catch { $final = $null }
    }
    return @{ Code = $code; Thread = $(if ($thread) { $thread.thread_id } else { $Resume }); Usage = $(if ($turn) { $turn.usage } else { $null }); Final = $final; Stem = $Stem }
}

function Write-Ledger($r, [string]$Role, [int]$Run) {
    $u = $r.Usage
    $tin = if ($u) { $u.input_tokens } else { 0 }; $tc = if ($u) { $u.cached_input_tokens } else { 0 }; $to = if ($u) { $u.output_tokens } else { 0 }
    # Windows PowerShell 5.1 会丢掉空字符串参数,所以空值不传
    $la = @("record", "--task", $Task, "--role", $Role, "--agent", "Codex", "--model", $Model, "--effort", $effortName,
        "--run", $Run, "--tokens-in", $tin, "--tokens-cached", $tc, "--tokens-out", $to, "--note", $runId)
    if ($r.Thread) { $la += @("--session", $r.Thread) }
    if ($brief -and $brief.level) { $la += @("--level", $brief.level) }
    if ($brief -and $brief.module) { $la += @("--module", ($brief.module -replace '"', '\"')) }
    python (Join-Path $root "tools\ledger.py") @la
}

# ---- 探索:只读,不改文件。产出探索包 explore.md,lead 读它写计划 ----
if ($Explore) {
    if (-not $AskFile -or -not (Test-Path $AskFile)) { Write-Error "-Explore 要用 -AskFile 给出任务原话和 lead 的问题所在的文件"; exit 1 }
    $ask = (Resolve-Path $AskFile).Path
    $ev = Join-Path $root $evidence
    New-Item -ItemType Directory -Force $ev | Out-Null
    $prompt = "${envNote}你是助手,这次只探索代码,不改任何文件。先读 prompts/sidekick.md 的「探索」一节,再读 $ask(任务原话和 lead 的问题),然后在项目里找和任务相关的代码。最后一条消息按「探索」一节的格式写。"
    $r = Invoke-Codex (@("exec", "-m", $Model) + $cfg + @("-s", "read-only", "-C", $work)) $prompt $stem
    Write-Ledger $r "探索" 1
    $body = if (Test-Path "$stem.report.txt") { @(Get-Content "$stem.report.txt" -Encoding UTF8) } else { @("没有探索报告。查看 $stem.stderr.log") }
    $notes = Get-ModelNotes
    $pack = @("# $Task 探索包", "") + $body
    if ($notes.Count) { $pack += @("", "## 模型备注($Model):写计划时参考") + $notes }
    $path = Join-Path $ev "explore.md"
    $pack | Out-File $path
    ""
    "退出码:$($r.Code)"
    if ($r.Thread) { "会话编号:$($r.Thread)" }
    "探索包:$path(lead 只读这一个文件)"
    exit $r.Code
}

# 简报检查:不通过就不派工
if (-not $Preflight) {
    $json = python (Join-Path $root "tools\brief.py") phases $Task --json
    if ($LASTEXITCODE -ne 0) { exit 1 }
    $brief = $json | ConvertFrom-Json
    if (-not $brief.ok) { python (Join-Path $root "tools\brief.py") check $Task; Write-Error "简报没通过检查,不派工。"; exit 1 }
    # 助手直接在主目录改:主目录里不能有 lead 没提交的别的改动,不然分不清哪些是助手的
    if ((-not $Resume -or $NewTaskResume) -and $work -eq $root) {
        $dirty = @(git -C $root status --porcelain | Where-Object { $_ -notmatch '(ledger\.jsonl|progress\.json)$' -and $_ -notmatch '^.. "?tasks/' })
        if ($dirty.Count) { Write-Error "主目录有没提交的改动,先提交:`n$($dirty -join "`n")"; exit 1 }
    }
    # 登记进度:任务不在进度表里就加上;模板自带的示例任务换成这个任务。lead 每次派工只运行这一条命令
    $pf = Join-Path $root "progress.json"
    if (Test-Path $pf) {
        $prog = Get-Content $pf -Encoding UTF8 -Raw | ConvertFrom-Json
        $t = @($prog.tasks | Where-Object { $_.id -eq $Task })
        $head = Get-Content (Join-Path $root "tasks\$Task.md") -Encoding UTF8 -TotalCount 1
        $title = if ($head -match '^#\s*任务\s*\S+?[::]\s*(.+)$') { $Matches[1].Trim() } else { $Task }
        if (-not $t.Count) { python (Join-Path $root "tools\progress.py") add-task $title --milestone $prog.currentMilestone --id $Task --card "tasks/$Task.md" | Out-Null }
        elseif ($t[0].title -like "示例任务*") { python (Join-Path $root "tools\progress.py") edit-task $Task --title $title --card "tasks/$Task.md" | Out-Null }
        python (Join-Path $root "tools\progress.py") set-status $Task doing 2>$null | Out-Null
    }
}

# 改变契约的决定:先写进主目录的简报,下面再把简报带进工作目录。用文件传,避开命令行的引号问题
if ($Contract) {
    $decision = Join-Path $logDir "$Task-decision.txt"
    $Message | Out-File $decision
    python (Join-Path $root "tools\brief.py") decide $Task --text "@$decision"
    if ($LASTEXITCODE -ne 0) { Write-Error "决定没有写进简报,不续用。"; exit 1 }
}

# 工作目录:同时开着前端子代理时才用,放在项目文件夹旁边
if ($Worktree -and -not (Test-Path $wtPath)) {
    $start = if ($From) { $From } else { "HEAD" }
    git -C $root worktree add $wtPath -b $branch $start
    if ($LASTEXITCODE -ne 0) { Write-Error "建立工作目录失败:$wtPath"; exit 1 }
    foreach ($f in $CopyIntoWorktree) {
        $src = Join-Path $root $f
        if (Test-Path $src) {
            $dst = Join-Path $wtPath $f
            New-Item -ItemType Directory -Force (Split-Path $dst -Parent) | Out-Null
            Copy-Item $src $dst -Force
        }
        else { Write-Warning "要复制的文件不存在:$f" }
    }
}

New-Item -ItemType Directory -Force (Join-Path $work $evidence) | Out-Null
Set-WorkTemp
# 起点:第一次派工时的提交。交接包的 diff 和 -Rollback 都以它为准
$startFile = Join-Path $work "$evidence\start.txt"
if (-not $Preflight -and -not (Test-Path $startFile)) { git -C $work rev-parse HEAD | Out-File $startFile }

# 证据目录是空的阶段。阶段做没做完,以证据为准,不以助手的话为准
function Get-MissingEvidence {
    @(@($brief.phases) | ForEach-Object { $_.n } | Where-Object {
        $d = Join-Path $work "$evidence\$_"
        -not ((Test-Path $d) -and (Get-ChildItem $d -Force | Select-Object -First 1))
    })
}

# 最终报告存成 report.md。超过 60 行就提醒
function Save-Report($f) {
    $out = @("# $Task 最终报告", "", "- 状态:$($f.status) · 最后阶段 $($f.last_phase)", "- 摘要:$($f.summary)")
    if ($f.stop_reason) { $out += "- 停止原因:$($f.stop_reason)" }
    $all = @($runs | ForEach-Object { $_.Final } | Where-Object { $_ -and $_ -isnot [string] })
    foreach ($s in @(@("要 lead 回答的问题", "questions"), @("修改请求的回应", "responses"), @("假设", "assumptions"), @("接口修改请求", "interface_requests"), @("给下游", "downstream"), @("问题", "problems"))) {
        $items = if ($s[1] -eq "responses") { @($f.($s[1]) | Where-Object { $_ }) } else { @($all | ForEach-Object { $_.($s[1]) } | Where-Object { $_ } | Select-Object -Unique) }
        $out += @("", "## $($s[0])")
        $out += $(if ($items.Count) { $items | ForEach-Object { "- $_" } } else { "- 无" })
    }
    $path = Join-Path $work "$evidence\report.md"
    $out | Out-File $path
    if ($out.Count -gt 60) { Write-Warning "最终报告有 $($out.Count) 行,超过 60 行。续用时要求助手压缩。" }
    return $path
}

# 可写范围:简报「约束」里除「不要做」以外各行的 `路径`。助手改过的范围外文件(含改完又删掉的)从事件流里找,diff 里看不到(HEX T12 的临时探针)
function Get-OutOfScope {
    $card = Join-Path $work "tasks\$Task.md"
    if (-not (Test-Path $card)) { return @() }
    $sec = ([regex]::Match((Get-Content $card -Encoding UTF8 -Raw), '(?ms)^## 约束\s*$(.*?)(?=^## |\z)')).Groups[1].Value
    $scope = @($sec -split "`n" | Where-Object { $_ -notmatch '不要做' } | ForEach-Object { [regex]::Matches($_, '`([^`]+)`') | ForEach-Object { $_.Groups[1].Value.Trim().Replace('\', '/') } })
    if (-not $scope.Count) { return @() }
    $scope += @("dispatch-logs/", "learning.md")
    $base = (Resolve-Path $work).Path.Replace('\', '/').TrimEnd('/') + '/'
    $paths = @(foreach ($x in $runs) {
        Get-Content "$($x.Stem).events.jsonl" -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ -match '"file_change"' -and $_ -match '"item\.completed"' } |
            ForEach-Object { ($_ | ConvertFrom-Json).item.changes | ForEach-Object { $_.path.Replace('\', '/') } }
    })
    @($paths | ForEach-Object { if ($_.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) { $_.Substring($base.Length) } else { $_ } } | Select-Object -Unique |
        Where-Object { $p = $_; -not @($scope | Where-Object { $p.Contains($_) }).Count })
}

# 交接包:lead 审查只读这一个文件。报告、验收命令、diff 统计、关键改动(不含测试)、模型备注、下一步命令
function Write-Bundle($r, $gates) {
    $start = (Get-Content $startFile -Encoding UTF8 -TotalCount 1).Trim()
    $path = Join-Path $work "$evidence\bundle.md"
    # 上一轮的交接包留一份,lead 第一次审查看的版本不丢
    if (Test-Path $path) { Copy-Item $path (Join-Path $work "$evidence\bundle-prev.md") -Force }
    $f = $r.Final
    $b = @("# $Task 交接包", "")
    if ($f) { $b += "- 状态:$($f.status) · 最后阶段 $($f.last_phase) · $($f.summary)"; if ($f.stop_reason) { $b += "- 停止原因:$($f.stop_reason)" } }
    else { $b += "- 没有最终报告。查看 $($r.Stem).stderr.log" }
    if ($r.Thread) { $b += "- 会话编号:$($r.Thread)" }
    $b += "- 起点提交:$start · 分支:$((git -C $work rev-parse --abbrev-ref HEAD | Out-String).Trim())"
    $other = @(git -C $work log "$start..HEAD" --format="%h %s" --invert-grep --grep "Agent: Codex")
    if ($other.Count) { $b += "- 起点之后还有不是助手的提交,下面的 diff 混了它们:$($other -join ';')" }
    if ($stale) { $b += "- 探索之后、派工之前,代码又有 $stale 个提交,探索包可能过时" }
    $qs = @(Get-ReportItems (Join-Path $work "$evidence\report.md") "要 lead 回答的问题")
    if ($qs.Count) { $b += @("", "## 要 lead 回答的问题(验收前要答)") + $qs }
    $oos = @(Get-OutOfScope)
    if ($oos.Count) { $b += @("", "## 可写范围之外改过的文件(含改完又删掉的)") + @($oos | ForEach-Object { "- ``$_``" }) }
    $fp = Join-Path $work "$evidence\forbidden.txt"
    if (Test-Path $fp) { $b += @("", "## 禁止的操作(验收前先告诉 Lily)") + @(Get-Content $fp -Encoding UTF8 | ForEach-Object { "- ``$_``" }) }
    $b += @("", "## 验收命令")
    if ($envStop) { $b += "- 验收命令连续遇到环境错误(证书、网络),脚本没交给助手修。lead 查环境,需要时问 Lily" }
    if (-not @($gates).Count) { $b += "- 项目设置里没有 TestCommand 和 LintCommand" }
    foreach ($g in @($gates)) {
        $b += "- $($g.Name):$($g.Cmd) · 退出码 $($g.Code)"
        $n = if ($g.Code -ne 0) { 20 } else { 3 }
        $tail = Get-Tail $g.Out $n
        $b += @('```') + @(Get-TestSummary $g.Out | Where-Object { $tail -notcontains $_ }) + $tail + @('```')
    }
    if ($gateHistory.Count) { $b += @("", "## 这次派工中途没通过的验收(之后让助手修过)") + $gateHistory }
    $meta = @(".", ":(exclude)ledger.jsonl", ":(exclude)progress.json", ":(exclude)tasks")
    $ex = $meta + @(":(exclude,glob)**/tests/**", ":(exclude,glob)**/test/**", ":(exclude,glob)**/test_*", ":(exclude,glob)**/*_test.*",
        ":(exclude,glob)**/src/gametest/**", ":(exclude,glob)**/*Test.java", ":(exclude,glob)**/*Tests.java", ":(exclude,glob)**/*.test.*", ":(exclude,glob)**/*.spec.*")
    $files = @(git -C $work diff --name-only "$start..HEAD" -- @ex)
    # 原有的测试改了哪些断言:删掉的断言放在最前面,改弱测试最容易漏看(HEX T4 把数值断言改成了"大于 0")
    $tests = @(git -C $work diff --name-only --diff-filter=M "$start..HEAD" -- @meta | Where-Object { $files -notcontains $_ })
    $gone = @(foreach ($t in $tests) { git -C $work diff "$start..HEAD" -- $t | Where-Object { $_ -match '^-(?!--)' -and $_ -match '(?i)assert|expect|should' } | ForEach-Object { "$t`: $($_.Substring(1).Trim())" } })
    if ($gone.Count) { $b += @("", "## 原有测试里删掉的断言(先看这里)", '```') + @($gone | Select-Object -First 40) + @('```') }
    $b += @("", "## 改动", '```') + @(git -C $work diff --stat "$start..HEAD") + @('```')
    $rp = Join-Path $work "$evidence\report.md"
    if (Test-Path $rp) { $b += @("", "## 最终报告") + @(Get-Content $rp -Encoding UTF8 | Select-Object -Skip 2) }
    # 每个改动的文件都放进来,行数平分,免得前几个大文件把关键文件挤掉(fusion-bench C2-H2)。import 这类行不占位置
    $per = [Math]::Max(40, [int]($BundleDiffLines / [Math]::Max(1, $files.Count)))
    $b += @("", "## 关键改动(不含测试,每个文件最多 $per 行)")
    foreach ($fn in $files) {
        $d = @(git -C $work diff "$start..HEAD" -- $fn | Where-Object { $_ -notmatch '^(diff --git|index |--- |\+\+\+ |new file mode|deleted file mode)' -and $_ -notmatch '^[+ -]\s*(import |package |using |#include|from \S+ import )' })
        $b += @("", "### $fn", '```diff') + @($d | Select-Object -First $per) + @('```')
        if ($d.Count -gt $per) { $b += "(共 $($d.Count) 行,其余用 git diff $start..HEAD -- $fn)" }
    }
    $notes = Get-ModelNotes
    if ($notes.Count) { $b += @("", "## 模型备注($Model):写修改请求时参考") + $notes }
    $b += @("", "## 下一步",
        "- 要改:修改请求写进文件(每条一行,行首写编号 R1、R2…),-Task $Task -Model $Model -Resume $($r.Thread) -MessageFile 文件",
        "- 验收:-Task $Task -Accept -Session lead的会话编号 -Note ""看了哪些""",
        "- 整个退回:-Task $Task -Rollback -Session lead的会话编号")
    $b | Out-File $path
    return $path
}

function Invoke-Resume([string]$Thread, [string]$Text, [string]$Suffix) {
    $a = @("exec", "resume", $Thread, "-m", $Model) + $cfg + @("-c", "sandbox_mode=$Sandbox") + @("--output-schema", $schema)
    return Invoke-Codex $a $Text "$stem$Suffix"
}

$reportPath = $null
$bundlePath = $null
$runNo = 0
if ($Preflight) {
    $prompt = "环境预检。只运行这条命令一次:$Preflight 。不修改任何文件,不修复问题。stop_reason 写退出码和输出的最后 30 行,其他数组写空。"
    $r = Invoke-Codex (@("exec", "-m", $Model) + $cfg + @("-s", $Sandbox, "-C", $work, "--output-schema", $schema)) $prompt $stem
    Write-Ledger $r "预检" 1
    $runs = @($r)
}
else {
    $gateCmds = @(@($TestCommand, $LintCommand) | Where-Object { $_ })
    $gateNote = if ($gateCmds.Count) { "做完后派工脚本会跑验收命令($($gateCmds -join ';')),不通过会让你接着修,你也可以先自己跑。" } else { "" }
    $notes = Get-ModelNotes
    $noteText = if ($notes.Count) { "照着避开这些以前出过的问题:" + ($notes -join " ") } else { "" }
    $exp = Join-Path $work "$evidence\explore.md"
    # 探索之后代码又变了(HEX 的探索比实现早 4 小时)。只算改了代码的提交,lead 提交计划不算
    $stale = 0
    if (Test-Path $exp) {
        $since = [DateTimeOffset]::new((Get-Item $exp).LastWriteTimeUtc).ToUnixTimeSeconds()
        $stale = @(git -C $work log --format=%ct -- . ":(exclude)tasks" ":(exclude)ledger.jsonl" ":(exclude)progress.json" | Where-Object { [long]$_ -gt $since }).Count
    }
    $expNote = if (Test-Path $exp) { "探索包在 $evidence/explore.md,简报没写到的细节可以查" + $(if ($stale) { "(探索之后代码又有 $stale 个提交,以现在的代码为准)" } else { "" }) + "。" } else { "" }
    $start = "${envNote}这是新任务 $Task,最终报告只写 $Task。读 prompts/sidekick.md、AGENTS.md 和 tasks/$Task.md(简报),从阶段 1 一口气做到最后一个阶段,途中不和 lead 通信。${expNote}每个阶段做完,把验收命令的原始输出存到 $evidence/阶段编号/,然后直接开始下一个阶段。${gateNote}遇到证书、网络这类环境错误,原样重跑,不用关掉检查的参数绕过。${noteText}不要提交,也不要建分支或切换分支,派工脚本会在运行结束后在当前分支上提交。只在全部阶段完成、做完检查点阶段或遇到停止条件时结束,要 lead 回答的问题写进最终报告的 questions。"
    # 简报只由 lead 改。把主目录里最新的简报(含写回的决定)带进工作目录
    if ($work -ne $root) { Copy-Item (Join-Path $root "tasks\$Task.md") (Join-Path $work "tasks\$Task.md") -Force }
    $runs = @()
    $runBranch = (git -C $work rev-parse --abbrev-ref HEAD | Out-String).Trim()
    if ($Resume -and -not $NewTaskResume) {
        $text = $Message
        if ($Contract) { $text += "(这条决定已写进简报的「已定」)" }
        $text += "`n最后一条消息写 $Task 的完整最终报告:包括 $Task 之前几次运行做完的内容,不写别的任务。"
        # 修改请求存进证据,-Accept 核对每条都有回应
        if ((Get-RequestIds $Message).Count) {
            $Message | Out-File (Join-Path $work "$evidence\requests-latest.md")
            $text += "`n最终报告的 responses 只回应这次的修改请求,逐条写「$Task-R编号:怎么改的」,例如「$Task-R1:……」。"
        }
        $r = Invoke-Resume $Resume "${envNote}$text" ""
    }
    elseif ($NewTaskResume) { $r = Invoke-Resume $Resume $start "" }
    else {
        $a = @("exec", "-m", $Model) + $cfg + @("-s", $Sandbox, "-C", $work) + @("--output-schema", $schema)
        $r = Invoke-Codex $a $start $stem
    }
    $runs += $r; $runNo++
    Write-Ledger $r "助手" $runNo
    # 监工:没有最终报告就要求补;阶段证据不全、又没停下,就续"继续"
    for ($i = 1; -not $NoSupervise -and $i -le $MaxContinue; $i++) {
        $f = $r.Final
        if (($f -and $f.status -eq "停止") -or -not $r.Thread -or $r.Code -ne 0) { break }
        $missing = Get-MissingEvidence
        if ($f -and $missing.Count -eq 0) { break }
        $next = if ($missing.Count) { "继续:阶段 $($missing -join '、') 还没有证据($evidence/阶段编号/)。没做完就接着做,做完了就补存验收命令的原始输出。只在全部阶段完成或遇到停止条件时结束,最后一条消息按派工时给的格式写。最后一条消息写 $Task 的完整最终报告:包括 $Task 之前几次运行做完的内容,不写别的任务。" }
                else { "补最终报告:按派工时给的格式写最后一条消息,再结束。" }
        "监工:第 $i 次续跑。$next"
        $r = Invoke-Resume $r.Thread $next "-c$i"
        $runs += $r; $runNo++
        Write-Ledger $r "助手" $runNo
    }
    # 验收命令:不通过就让助手接着修。lead 看到的总是跑过测试和 lint 的结果
    $gates = Invoke-Gates "g0"
    $gateHistory = @(); $envRetried = $false; $envStop = $false
    for ($j = 1; -not $NoSupervise -and $j -le $MaxGateFix; $j++) {
        $bad = @($gates | Where-Object { $_.Code -ne 0 })
        if (-not $bad.Count -or -not $r.Thread -or ($r.Final -and $r.Final.status -eq "停止")) { break }
        # 环境错误不交给助手修:原样重跑 1 次,还不过就交给 lead(HEX T12 的助手为此关了证书检查)
        if (@($bad | Where-Object { Test-EnvFailure $_.Out }).Count) {
            if ($envRetried) { $envStop = $true; "监工:验收命令又遇到环境错误,不让助手修,交给 lead。"; break }
            $envRetried = $true; "监工:验收命令遇到环境错误,原样重跑 1 次。"
            $gates = Invoke-Gates "e$j"; $j--; continue
        }
        foreach ($g in $bad) { $gateHistory += "- 第 $j 次修之前:$($g.Name) 退出码 $($g.Code)" + $(@(Get-FailLines $g.Out | Select-Object -First 3) | ForEach-Object { "`n  - $_" }) }
        $fix = "派工脚本跑了验收命令,没通过,请修好。不要改测试或验收标准来通过,也不要用关掉检查的参数绕过。"
        foreach ($g in $bad) { $fix += "`n命令:$($g.Cmd)(退出码 $($g.Code))。失败相关的行:`n" + ((Get-FailLines $g.Out) -join "`n") + "`n输出的最后 40 行:`n" + ((Get-Tail $g.Out 40) -join "`n") }
        $fix += "`n修好后按派工时给的格式写最后一条消息。最后一条消息写 $Task 的完整最终报告:包括 $Task 之前几次运行做完的内容,不写别的任务。"
        "监工:验收命令没通过,第 $j 次让助手修。"
        $r = Invoke-Resume $r.Thread $fix "-g$j"
        $runs += $r; $runNo++
        Write-Ledger $r "助手" $runNo
        $gates = Invoke-Gates "g$j"
    }
    # 禁止的操作:扫助手跑过的命令。命中就写进证据,交接包列出来,-Accept 拒绝验收(HEX T12 关了证书检查,报告没提)
    if ($ForbiddenPattern) {
        $forbid = @(foreach ($x in $runs) { Get-Content "$($x.Stem).events.jsonl" -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ -match '"command_execution"' -and $_ -match $ForbiddenPattern } | ForEach-Object { ($_ | ConvertFrom-Json).item.command } }) | Select-Object -Unique
        if ($forbid.Count) { $forbid | Out-File (Join-Path $work "$evidence\forbidden.txt"); Write-Warning "助手用了禁止的操作,见 $evidence\forbidden.txt" }
    }
    if ($r.Final) { $reportPath = Save-Report $r.Final }
    # 助手不切换分支(HEX T9 照简报的"分支"一行自己建了分支)。切了就切回来;分支上有了新提交就不提交,交给 lead
    $branchOk = $true
    $nowBranch = (git -C $work rev-parse --abbrev-ref HEAD | Out-String).Trim()
    if ($nowBranch -ne $runBranch) {
        if ((git -C $work rev-parse HEAD) -eq (git -C $work rev-parse $runBranch)) {
            git -C $work switch -q $runBranch; git -C $work branch -q -D $nowBranch
            Write-Warning "助手切到了分支 $nowBranch,已切回 $runBranch 并删掉它,改动保留"
        }
        else { $branchOk = $false; Write-Warning "助手切到了分支 $nowBranch 并有了新提交,脚本不提交。先把它合回 $runBranch 再验收" }
    }
    # 助手不提交,由脚本提交,追溯信息写好。主目录模式不带台账、进度和简报,它们由 lead 的 -Accept 提交
    if ($branchOk -and (git -C $work status --porcelain)) {
        if ($work -eq $root) { git -C $work add -A -- . ":(exclude)ledger.jsonl" ":(exclude)progress.json" ":(exclude)tasks" }
        else { git -C $work add -A }
        if (git -C $work diff --cached --name-only) {
            $sess = if ($r.Thread) { $r.Thread } else { $runId }
            $sum = if ($r.Final) { $r.Final.summary } else { "没有最终报告" }
            $msgFile = "$stem.commit.txt"
            $msg = "${Task}:助手的改动($runId)`n`n$sum`n`nTask: $Task`nAgent: Codex`nModel: $Model`nEffort: $effortName`nSession: $sess`n"
            [IO.File]::WriteAllText($msgFile, $msg, (New-Object Text.UTF8Encoding $false))
            git -C $work commit -q -F $msgFile
            if ($LASTEXITCODE -ne 0) { Write-Warning "提交失败,改动还在:$work" }
        }
    }
    $bundlePath = Write-Bundle $r $gates
}

# ---- 汇总 ----
$last = $runs[-1]
""
"退出码:$($last.Code)    运行次数:$($runs.Count)"
"沙箱:$Sandbox    工作目录:$work"
if ($last.Thread) { "会话编号:$($last.Thread)(续用时传给 -Resume)" }
# Codex 报的是整个会话的累计用量,所以只看最后一次;每次的差值在台账里
$u = @($runs | Where-Object { $_.Usage }) | Select-Object -Last 1
if ($u) { "token 用量(会话累计):输入 $($u.Usage.input_tokens),其中缓存 $($u.Usage.cached_input_tokens),输出 $($u.Usage.output_tokens)" }
if ($u -and $u.Usage.input_tokens -gt $BigSession) { Write-Warning "助手会话已经很大(累计输入 $($u.Usage.input_tokens)):下个任务不要续用它,续用那个任务自己的探索会话或新开" }
"日志:$stem.*"
if ($brief) {
    $missing = Get-MissingEvidence
    "证据:$(Join-Path $work $evidence)    没有证据的阶段:$(if ($missing.Count) { $missing -join '、' } else { '无' })"
}
if ($last.Final) { "最后一条消息:$($last.Final.status) · 阶段 $($last.Final.last_phase) · $($last.Final.summary)"; if ($last.Final.stop_reason) { "停止原因:$($last.Final.stop_reason)" } }
elseif (Test-Path "$($last.Stem).report.txt") { Get-Content "$($last.Stem).report.txt" -Encoding UTF8 }
else { "没有最后一条消息。查看 $($last.Stem).stderr.log" }
if ($reportPath) { "最终报告:$reportPath" }
if ($bundlePath) { "交接包:$bundlePath(lead 审查只读这一个文件)" }
exit $last.Code
