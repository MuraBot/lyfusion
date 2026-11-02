# 把简报派给 Codex 助手,并当监工:会话停了但阶段没做完,自动续跑。每次运行自动记台账。试点版。
# 用法见 prompts/dispatch.md:
#   .\tools\codex-dispatch.ps1 -Task T5 -Model gpt-6.1-sol -Worktree [-From task/T4]
#   .\tools\codex-dispatch.ps1 -Task T5 -Model gpt-6.1-sol -Resume 会话编号 -Message "lead 的决定:……"
#   .\tools\codex-dispatch.ps1 -Task T5 -Model 模型名 -Review [-Resume 审查者的会话编号]
#   .\tools\codex-dispatch.ps1 -Task 预检 -Model 模型名 -Effort low -Preflight "构建命令"
#   .\tools\codex-dispatch.ps1 -Task T5 -Cleanup     合并后删除工作目录和分支,先保存证据
# 可选参数:
#   -Effort low/medium/high 等      推理强度;不加就用 Codex 的默认配置
#   -Sandbox workspace-write 或 danger-full-access   不加就用下面"项目设置"里的默认值。审查固定只读
#   -NoSupervise                    不自动续跑
# 本文件保存为带 BOM 的 UTF-8,Windows PowerShell 5.1 才能正确读取中文。
param(
    [Parameter(Mandatory = $true)][string]$Task,
    [string]$Model,
    [string]$Resume,
    [string]$Message,
    [switch]$Review,
    [string]$Base = "main",
    [string]$Effort,
    [ValidateSet("", "workspace-write", "danger-full-access")][string]$Sandbox = "",
    [switch]$Worktree,
    [string]$From,
    [string]$Preflight,
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

# ---- 合并后清理:先保存证据,再删工作目录和分支 ----
if ($Cleanup) {
    if (-not (Test-Path $wtPath)) { Write-Error "没有工作目录:$wtPath"; exit 1 }
    if ((Get-Location).Path.StartsWith($wtPath)) { Write-Error "当前目录在要删的工作目录里。先切回主目录:$root"; exit 1 }
    $merged = git -C $root branch --merged $Base --format "%(refname:short)"
    if ($merged -notcontains $branch) { Write-Error "$branch 还没合并进 $Base。没合并的工作目录要先问 Lily"; exit 1 }
    # 开着沙箱时助手不提交,改动都在工作目录里。新文件也要算,被忽略的(如证据)不算
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

if (-not $Model) { Write-Error "要用 -Model 写明模型。"; exit 1 }
if ($Resume -and -not $Message -and -not $Review) { Write-Error "续用会话时要用 -Message 写明交给 agent 的内容。"; exit 1 }
$cmd = Get-Command codex -ErrorAction SilentlyContinue
$pkg = Get-AppxPackage OpenAI.Codex -ErrorAction SilentlyContinue
if ($cmd) { $exe = $cmd.Source }
elseif ($pkg) { $exe = Join-Path $pkg.InstallLocation "app\resources\codex.exe" }
else { Write-Error "找不到 Codex 命令行。请先安装 Codex App,或运行 npm install -g @openai/codex。"; exit 1 }

# 环境缺口先消除,再检测,最后才写 learning.md。Codex 安装目录里自带 rg 等工具,加进 PATH
$env:PATH = (Split-Path $exe -Parent) + [IO.Path]::PathSeparator + $env:PATH
$missingCmds = @($NeedCommands | Where-Object { -not (Get-Command $_ -ErrorAction SilentlyContinue) })
$envNote = if ($missingCmds.Count) { "本机没有这些命令:$($missingCmds -join '、')。用替代办法继续,在回报里说明,不要因此停下。" } else { "" }

# 简报检查:不通过就不派工
$brief = $null
if (-not $Review -and -not $Preflight) {
    $json = python (Join-Path $root "tools\brief.py") phases $Task --json
    if ($LASTEXITCODE -ne 0) { exit 1 }
    $brief = $json | ConvertFrom-Json
    if (-not $brief.ok) { python (Join-Path $root "tools\brief.py") check $Task; Write-Error "简报没通过检查,不派工。"; exit 1 }
}

# 工作目录:每个简报一个,放在项目文件夹旁边
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

$logDir = Join-Path $root "dispatch-logs"
$mailDir = Join-Path $root "mail"
New-Item -ItemType Directory -Force $logDir, $mailDir | Out-Null
$evidence = "dispatch-logs/evidence/$Task"
New-Item -ItemType Directory -Force (Join-Path $work $evidence) | Out-Null
$schema = Join-Path $root "tools\schemas\final.schema.json"
$runId = "run-" + (Get-Date -Format "yyyyMMdd-HHmmss")

# Claude 只由 Lily 使用:不把 Claude 的会话令牌和配置带进 Codex 的环境
$claudeVars = @(Get-ChildItem env: | Where-Object { $_.Name -match '^(CLAUDE|ANTHROPIC)' } | ForEach-Object { $_.Name })
$claudeVars | ForEach-Object { Remove-Item "env:$_" -ErrorAction SilentlyContinue }

# 配置写成 key=value;值不加引号时 Codex 按普通文字处理
$cfg = @()
if ($Effort) { $cfg += @("-c", "model_reasoning_effort=$Effort") }
foreach ($k in $ProjectEnv.Keys) { $cfg += @("-c", "shell_environment_policy.set.$k=$($ProjectEnv[$k])") }
# 工作目录在主目录外时,信箱也要能写。resume 没有 --add-dir,改用配置(试点版,未实测)
$addDir = @()
$rootsCfg = @()
if ($work -ne $root) {
    $addDir = @("--add-dir", $mailDir)
    # 用 TOML 单引号字面量:值里没有双引号,路径带空格时 PowerShell 5.1 也不会把参数拆开
    $rootsCfg = @("-c", ("sandbox_workspace_write.writable_roots=['{0}']" -f $mailDir))
}

function Invoke-Codex([string[]]$CodexArgs, [string]$Prompt, [string]$Stem) {
    # Windows PowerShell 5.1 传参时不转义双引号,提示词里的 " 要写成 \"
    $p = $Prompt -replace '"', '\"'
    $ca = @($CodexArgs | ForEach-Object { $_ -replace '"', '\"' })
    Push-Location $work
    try { & $exe @ca --json -o "$Stem.report.txt" $p > "$Stem.events.jsonl" 2> "$Stem.stderr.log"; $code = $LASTEXITCODE }
    finally { Pop-Location }
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

$effortName = if ($Effort) { $Effort } else { "default" }
$stem = Join-Path $logDir ("{0}-{1}" -f $Task, (Get-Date -Format "yyyyMMdd-HHmmss"))

if ($Preflight) {
    $prompt = "环境预检。只运行这条命令一次:$Preflight 。不修改任何文件,不修复问题。stop_reason 写退出码和输出的最后 30 行。"
    $r = Invoke-Codex (@("exec", "-m", $Model) + $cfg + @("-s", $Sandbox, "-C", $work, "--output-schema", $schema)) $prompt $stem
    Write-Ledger $r "预检" 1
    $runs = @($r)
}
elseif ($Review) {
    # 交审前先把 main 合并进任务分支,让简报和接口是最新的
    if ($work -ne $root) {
        git -C $work merge --no-edit $Base
        if ($LASTEXITCODE -ne 0) { git -C $work merge --abort; Write-Error "合并 $Base 进 $branch 时有冲突。先解决冲突,再审查。"; exit 1 }
    }
    $prompt = "读 prompts/review.md 和 tasks/$Task.md(简报)。用 git diff $Base...HEAD 查看这个模块的全部改动。验收证据在 $evidence/,每个阶段一个文件夹。按 review.md 做对抗审查,不修改任何文件。最后一条消息是 review.md 格式的审查报告。"
    if ($Resume) { $a = @("exec", "resume", $Resume, "-m", $Model) + $cfg + @("-c", "sandbox_mode=read-only") }
    else { $a = @("exec", "-m", $Model) + $cfg + @("-s", "read-only", "-C", $work) }
    $r = Invoke-Codex $a $prompt $stem
    Write-Ledger $r "审查" 1
    $runs = @($r)
}
else {
    $commitRule = if ($Sandbox -eq "danger-full-access") {
        "每个阶段回报后,在 $branch 分支上提交这个阶段。提交说明末尾只写一行 Phase: 阶段编号,其余追溯信息由提交钩子补上。不推送,不碰 main。"
    } else { "不要提交:沙箱里 .git 是只读的。回报时 mail.py 会自动存改动快照。" }
    $start = "${envNote}你是助手。读 prompts/sidekick.md、AGENTS.md 和 tasks/$Task.md(简报),按简报从阶段 1 做到最后一个阶段。每个阶段开始前运行 python tools/mail.py inbox $Task --as assistant。每个阶段做完:验收命令的原始输出存到 $evidence/阶段编号/,运行 python tools/mail.py send $Task report 回报,然后直接开始下一个阶段。$commitRule 只在全部阶段完成或遇到停止条件时结束。"
    # 简报只由 lead 改。把主目录里最新的简报(含信箱里写回的决定)带进工作目录
    if ($work -ne $root) { Copy-Item (Join-Path $root "tasks\$Task.md") (Join-Path $work "tasks\$Task.md") -Force }
    # 派工记录:提交钩子按它补追溯信息,mail.py close 按它检查派工进程是否还在运行
    $metaPath = Join-Path $mailDir "$Task.meta.json"
    $meta = [ordered]@{ task = $Task; agent = "Codex"; model = $Model; effort = $effortName; runId = $runId; pid = $PID; session = "$Resume"; finished = $false }
    function Save-Meta { $meta | ConvertTo-Json | Set-Content -Encoding UTF8 $metaPath }
    Save-Meta
    $runs = @()
    if ($Resume) {
        $a = @("exec", "resume", $Resume, "-m", $Model) + $cfg + @("-c", "sandbox_mode=$Sandbox") + $rootsCfg + @("--output-schema", $schema)
        $r = Invoke-Codex $a "${envNote}$Message" $stem
    }
    else {
        $a = @("exec", "-m", $Model) + $cfg + @("-s", $Sandbox, "-C", $work) + $addDir + @("--output-schema", $schema)
        $r = Invoke-Codex $a $start $stem
    }
    $runs += $r
    if ($r.Thread) { $meta.session = $r.Thread; Save-Meta }
    Write-Ledger $r "助手" 1
    # 监工:阶段没做完、也没停下,就自动续跑;阶段做完却缺回报,就要求补回报
    $total = @($brief.phases).Count
    for ($i = 1; -not $NoSupervise -and $i -le $MaxContinue; $i++) {
        $st = python (Join-Path $root "tools\mail.py") status $Task --json | ConvertFrom-Json
        $missing = @(1..$total | Where-Object { $st.reportedPhases -notcontains $_ })
        $f = $r.Final
        if ($missing.Count -eq 0 -or ($f -and $f.status -eq "停止") -or -not $r.Thread -or $r.Code -ne 0) { break }
        $next = if ($f -and $f.status -eq "完成") { "补回报:阶段 $($missing -join '、') 没有回报。用 python tools/mail.py send $Task report 补上,再结束。" }
                else { "继续:阶段 $($missing -join '、') 还没回报。先运行 python tools/mail.py inbox $Task --as assistant,然后接着做。只在全部阶段完成或遇到停止条件时结束。" }
        "监工:第 $i 次续跑。$next"
        $stem2 = "$stem-c$i"
        $a = @("exec", "resume", $r.Thread, "-m", $Model) + $cfg + @("-c", "sandbox_mode=$Sandbox") + $rootsCfg + @("--output-schema", $schema)
        $r = Invoke-Codex $a $next $stem2
        $runs += $r
        Write-Ledger $r "助手" ($i + 1)
    }
    $meta.finished = $true
    Save-Meta
}

# ---- 汇总 ----
$last = $runs[-1]
""
"退出码:$($last.Code)    运行次数:$($runs.Count)"
"沙箱:$(if ($Review) { 'read-only' } else { $Sandbox })    工作目录:$work"
if ($last.Thread) { "会话编号:$($last.Thread)(续用时传给 -Resume)" }
$tin = 0; $tout = 0
foreach ($x in $runs) { if ($x.Usage) { $tin += $x.Usage.input_tokens; $tout += $x.Usage.output_tokens } }
"token 用量(合计):输入 $tin,输出 $tout"
"日志:$stem.*"
"证据:$(Join-Path $work $evidence)"
if ($brief) {
    $st = python (Join-Path $root "tools\mail.py") status $Task --json | ConvertFrom-Json
    "已回报的阶段:$($st.reportedPhases -join '、') / 共 $(@($brief.phases).Count) 个    没回复的提问:$($st.openQuestions -join '、')"
}
if ($last.Final) { "最后一条消息:$($last.Final.status) · 阶段 $($last.Final.last_phase) · $($last.Final.summary)"; if ($last.Final.stop_reason) { "停止原因:$($last.Final.stop_reason)" } }
elseif (Test-Path "$($last.Stem).report.txt") { Get-Content "$($last.Stem).report.txt" -Encoding UTF8 }
else { "没有最后一条消息。查看 $($last.Stem).stderr.log" }
""
"lead 提交时的追溯信息:"
"Task: $Task"
"Agent: Codex"
"Model: $Model"
"Effort: $effortName"
"Session: $(if ($last.Thread) { $last.Thread } else { $runId })"
if ($brief -and $Sandbox -ne "danger-full-access") { "Phase: 全部" }
exit $last.Code
