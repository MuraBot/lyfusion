# 把简报派给 Codex 助手,并当监工:缺最终报告就要求补,阶段证据不全又没停下就续跑。试点版。
# 每次运行自动记台账;运行结束后在任务分支上提交改动,最终报告存成 report.md。用法见 prompts/dispatch.md:
#   .\tools\codex-dispatch.ps1 -Task T5 -Model gpt-6.1-sol -Worktree [-From task/T4]
#   .\tools\codex-dispatch.ps1 -Task T5 -Model gpt-6.1-sol -Resume 会话编号 -Message "lead 的回答:……" [-Contract]
#   .\tools\codex-dispatch.ps1 -Task T5 -Model 模型名 -Review [-Resume 审查者的会话编号]
#   .\tools\codex-dispatch.ps1 -Task 预检 -Model 模型名 -Effort low -Preflight "构建命令"
#   .\tools\codex-dispatch.ps1 -Task T5 -Merge [-Playtest]   跑测试,通过才合并进 main,再改状态
#   .\tools\codex-dispatch.ps1 -Task T5 -Cleanup     合并后删除工作目录和分支,先保存证据
# 可选参数:
#   -Effort low/medium/high 等      推理强度;不加就用 Codex 的默认配置
#   -Sandbox workspace-write 或 danger-full-access   不加就用下面"项目设置"里的默认值。审查固定只读
#   -Contract                       -Message 是改变契约的决定:先写进简报的"已定",再交给助手
#   -Playtest                       合并后要 Lily 试玩:状态改成 verify,不改成 done
#   -NoSupervise                    不自动续跑
# 本文件保存为带 BOM 的 UTF-8,Windows PowerShell 5.1 才能正确读取中文。
param(
    [Parameter(Mandatory = $true)][string]$Task,
    [string]$Model,
    [string]$Resume,
    [string]$Message,
    [switch]$Contract,
    [switch]$Review,
    [string]$Base = "main",
    [string]$Effort,
    [ValidateSet("", "workspace-write", "danger-full-access")][string]$Sandbox = "",
    [switch]$Worktree,
    [string]$From,
    [string]$Preflight,
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
# -Merge 在工作目录里跑的测试命令,例如 "gradlew.bat test"。退出码不是 0 就不合并
$TestCommand = ""
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

# ---- 合并:先在工作目录里合并 main 并跑测试,通过才合并进 main。任何一步失败,main 不变 ----
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
    Push-Location $wtPath
    try { $out = cmd /c "$TestCommand 2>&1"; $code = $LASTEXITCODE }
    finally { Pop-Location }
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

if (-not $Model) { Write-Error "要用 -Model 写明模型。"; exit 1 }
if ($Resume -and -not $Message -and -not $Review) { Write-Error "续用会话时要用 -Message 写明交给 agent 的内容。"; exit 1 }
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

# 改变契约的决定:先写进主目录的简报,下面再把简报带进工作目录。用文件传,避开命令行的引号问题
if ($Contract) {
    $decision = Join-Path $logDir "$Task-decision.txt"
    $Message | Out-File $decision
    python (Join-Path $root "tools\brief.py") decide $Task --text "@$decision"
    if ($LASTEXITCODE -ne 0) { Write-Error "决定没有写进简报,不续用。"; exit 1 }
}

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

# 证据目录是空的阶段。阶段做没做完,以证据为准,不以助手的话为准
function Get-MissingEvidence {
    @(@($brief.phases) | ForEach-Object { $_.n } | Where-Object {
        $d = Join-Path $work "$evidence\$_"
        -not ((Test-Path $d) -and (Get-ChildItem $d -Force | Select-Object -First 1))
    })
}

# 最终报告存成 report.md:lead 和审查者读它,不读助手的过程。超过 60 行就提醒
function Save-Report($f) {
    $out = @("# $Task 最终报告", "", "- 状态:$($f.status) · 最后阶段 $($f.last_phase)", "- 摘要:$($f.summary)")
    if ($f.stop_reason) { $out += "- 停止原因:$($f.stop_reason)" }
    foreach ($s in @(@("假设", "assumptions"), @("接口修改请求", "interface_requests"), @("给下游", "downstream"), @("问题", "problems"))) {
        $items = @($f.($s[1]) | Where-Object { $_ })
        $out += @("", "## $($s[0])")
        $out += $(if ($items.Count) { $items | ForEach-Object { "- $_" } } else { "- 无" })
    }
    $path = Join-Path $work "$evidence\report.md"
    $out | Out-File $path
    if ($out.Count -gt 60) { Write-Warning "最终报告有 $($out.Count) 行,超过 60 行。续用时要求助手压缩。" }
    return $path
}

$effortName = if ($Effort) { $Effort } else { "default" }
$stem = Join-Path $logDir ("{0}-{1}" -f $Task, (Get-Date -Format "yyyyMMdd-HHmmss"))
$reportPath = $null

if ($Preflight) {
    $prompt = "环境预检。只运行这条命令一次:$Preflight 。不修改任何文件,不修复问题。stop_reason 写退出码和输出的最后 30 行,其他数组写空。"
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
    $prompt = "读 prompts/review.md 和 tasks/$Task.md(简报)。用 git diff $Base...HEAD 查看这个模块的全部改动。验收证据在 $evidence/,每个阶段一个文件夹;助手的最终报告是 $evidence/report.md。按 review.md 做对抗审查,不修改任何文件。最后一条消息是 review.md 格式的审查报告。"
    if ($Resume) { $a = @("exec", "resume", $Resume, "-m", $Model) + $cfg + @("-c", "sandbox_mode=read-only") }
    else { $a = @("exec", "-m", $Model) + $cfg + @("-s", "read-only", "-C", $work) }
    $r = Invoke-Codex $a $prompt $stem
    Write-Ledger $r "审查" 1
    $runs = @($r)
}
else {
    $start = "${envNote}你是助手。读 prompts/sidekick.md、AGENTS.md 和 tasks/$Task.md(简报),从阶段 1 一口气做到最后一个阶段,途中不和 lead 通信。每个阶段做完,把验收命令的原始输出存到 $evidence/阶段编号/,然后直接开始下一个阶段。不要提交,派工脚本会在运行结束后提交。只在全部阶段完成、做完检查点阶段或遇到停止条件时结束,要 lead 回答的问题写进最后一条消息。"
    # 简报只由 lead 改。把主目录里最新的简报(含写回的决定)带进工作目录
    if ($work -ne $root) { Copy-Item (Join-Path $root "tasks\$Task.md") (Join-Path $work "tasks\$Task.md") -Force }
    $runs = @()
    if ($Resume) {
        $note = if ($Contract) { "(这条决定已写进简报的「已定」)" } else { "" }
        $a = @("exec", "resume", $Resume, "-m", $Model) + $cfg + @("-c", "sandbox_mode=$Sandbox") + @("--output-schema", $schema)
        $r = Invoke-Codex $a "${envNote}$Message$note" $stem
    }
    else {
        $a = @("exec", "-m", $Model) + $cfg + @("-s", $Sandbox, "-C", $work) + @("--output-schema", $schema)
        $r = Invoke-Codex $a $start $stem
    }
    $runs += $r
    Write-Ledger $r "助手" 1
    # 监工:没有最终报告就要求补;阶段证据不全、又没停下,就续"继续"
    for ($i = 1; -not $NoSupervise -and $i -le $MaxContinue; $i++) {
        $f = $r.Final
        if (($f -and $f.status -eq "停止") -or -not $r.Thread -or $r.Code -ne 0) { break }
        $missing = Get-MissingEvidence
        if ($f -and $missing.Count -eq 0) { break }
        $next = if ($missing.Count) { "继续:阶段 $($missing -join '、') 还没有证据($evidence/阶段编号/)。没做完就接着做,做完了就补存验收命令的原始输出。只在全部阶段完成或遇到停止条件时结束,最后一条消息按派工时给的格式写。" }
                else { "补最终报告:按派工时给的格式写最后一条消息,再结束。" }
        "监工:第 $i 次续跑。$next"
        $stem2 = "$stem-c$i"
        $a = @("exec", "resume", $r.Thread, "-m", $Model) + $cfg + @("-c", "sandbox_mode=$Sandbox") + @("--output-schema", $schema)
        $r = Invoke-Codex $a $next $stem2
        $runs += $r
        Write-Ledger $r "助手" ($i + 1)
    }
    if ($r.Final) { $reportPath = Save-Report $r.Final }
    # 助手不提交。在任务分支上由脚本提交,追溯信息写好,lead 和审查者看 git diff
    if ($work -ne $root -and (git -C $work status --porcelain)) {
        $sess = if ($r.Thread) { $r.Thread } else { $runId }
        $sum = if ($r.Final) { $r.Final.summary } else { "没有最终报告" }
        $msgFile = "$stem.commit.txt"
        $msg = "${Task}:助手的改动($runId)`n`n$sum`n`nTask: $Task`nAgent: Codex`nModel: $Model`nEffort: $effortName`nSession: $sess`n"
        [IO.File]::WriteAllText($msgFile, $msg, (New-Object Text.UTF8Encoding $false))
        git -C $work add -A
        git -C $work commit -q -F $msgFile
        if ($LASTEXITCODE -ne 0) { Write-Warning "提交失败,改动还在工作目录里:$work" }
    }
}

# ---- 汇总 ----
$last = $runs[-1]
""
"退出码:$($last.Code)    运行次数:$($runs.Count)"
"沙箱:$(if ($Review) { 'read-only' } else { $Sandbox })    工作目录:$work"
if ($last.Thread) { "会话编号:$($last.Thread)(续用时传给 -Resume)" }
$tin = 0; $tc = 0; $tout = 0
foreach ($x in $runs) { if ($x.Usage) { $tin += $x.Usage.input_tokens; $tc += $x.Usage.cached_input_tokens; $tout += $x.Usage.output_tokens } }
"token 用量(合计):输入 $tin,其中缓存 $tc,输出 $tout"
"日志:$stem.*"
if ($brief) {
    $missing = Get-MissingEvidence
    "证据:$(Join-Path $work $evidence)    没有证据的阶段:$(if ($missing.Count) { $missing -join '、' } else { '无' })"
    if ($work -ne $root) { "改动:git -C `"$work`" diff --stat $Base...HEAD" }
}
if ($last.Final) { "最后一条消息:$($last.Final.status) · 阶段 $($last.Final.last_phase) · $($last.Final.summary)"; if ($last.Final.stop_reason) { "停止原因:$($last.Final.stop_reason)" } }
elseif (Test-Path "$($last.Stem).report.txt") { Get-Content "$($last.Stem).report.txt" -Encoding UTF8 }
else { "没有最后一条消息。查看 $($last.Stem).stderr.log" }
if ($reportPath) { "最终报告:$reportPath" }
exit $last.Code
