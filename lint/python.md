# Python 规则

项目 lint 命令(`fusion/config.json`):`python -m ruff check --target-version py310 plugin/core`

| # | 问题 | 出现记录 | 怎么接住 | 状态 |
|---|---|---|---|---|
| P1 | 源码里的中文写成 `\uXXXX` 转义 | rc.1 任务 6(`views.py`)、任务 7(测试),共 2 次,lead 都手动改回(反馈第 13、18 条) | 自写检查:`.py` 文件里转义出的字符落在中文范围(汉字、中文标点、全角字符)就报错 | 待实现 |
| P2 | 只在新版 Python 能过的语法(例如 f-string 表达式里嵌同一种引号,3.10、3.11 是语法错误) | rc.1 任务 7(反馈第 18 条) | ruff `--target-version py310`(引擎声明支持 3.10) | 已生效 |
| P3 | 对整个项目或没改的文件跑格式化器,造成纯排版改动 | aq.2 H2 的意见 | 写进 WORK_RULES("不要对整个项目或没改的文件跑格式化器") | 只能提示 |
| P4 | pytest 临时目录(`--basetemp`)放进工位里会被提交的位置 | rc.1 任务 4(反馈第 10 条) | 项目 `.gitignore` 加 `_pytest_tmp/`;WORK_RULES 的测试跑法 | 已生效 |
| P5 | 为了凑 lead 写的检查标准,把源码里的字符串拆开 | rc.1 任务 8(反馈第 12 条) | 写进 LEAD_GUIDE 或模型备注:标准写在产出上,不写在源码文字上 | 只能提示 |
| P6 | 删除旧功能时在旧代码外面包一层适配 | v4 起 luna 的老问题 | 模型备注 `prompts/models/gpt-6-luna.md`(用禁止句,做完搜旧名字) | 只能提示 |
