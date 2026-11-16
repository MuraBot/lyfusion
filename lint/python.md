# Python 规则

项目 lint 命令(`fusion/config.json`):`python -m ruff check --target-version py310 plugin/core`

| # | 问题 | 出现记录 | 怎么接住 | 状态 |
|---|---|---|---|---|
| P1 | 源码里的中文写成 `\uXXXX` 转义 | rc.1 任务 6(`views.py`)、任务 7(测试),共 2 次,lead 都手动改回(反馈第 13、18 条) | 自写检查:`.py` 文件里转义出的字符落在中文范围(汉字、中文标点、全角字符)就报错 | 不做(插件文本改英文后用不上，规则留给中文项目;rc.2 任务 18) |
| P2 | 只在新版 Python 能过的语法(例如 f-string 表达式里嵌同一种引号,3.10、3.11 是语法错误) | rc.1 任务 7(反馈第 18 条) | ruff `--target-version py310`(引擎声明支持 3.10) | 已生效 |
| P3 | 对整个项目或没改的文件跑格式化器,造成纯排版改动 | aq.2 H2 的意见 | 写进 WORK_RULES("不要对整个项目或没改的文件跑格式化器") | 只能提示 |
| P4 | pytest 临时目录(`--basetemp`)放进工位里会被提交的位置 | rc.1 任务 4(反馈第 10 条) | 项目 `.gitignore` 加 `_pytest_tmp/`;WORK_RULES 的测试跑法 | 已生效 |
| P5 | 为了凑 lead 写的检查标准,把源码里的字符串拆开 | rc.1 任务 8(反馈第 12 条) | 写进 LEAD_GUIDE 或模型备注:标准写在产出上,不写在源码文字上 | 只能提示 |
| P6 | 删除旧功能时在旧代码外面包一层适配 | v4 起 luna 的老问题 | 模型备注 `prompts/models/gpt-6-luna.md`(用禁止句,做完搜旧名字) | 只能提示 |
| P7 | 源码字符串里直接写了看不见的字符(BOM `U+FEFF`、零宽字符),读代码看不出来,编辑器也可能悄悄删掉 | rc.2 T9(`tests/test_plan_markdown.py`,brief 写的是 `\ufeff`,助手照"不写 \u 转义"写成了原字符),lead 验收后改回 | 自写检查:`.py` 文件里(文件开头的 BOM 除外)出现 U+FEFF、U+200B~U+200D、U+2060 就报错;和 P1 放在同一个脚本。P1 只管中文范围,这类字符要写成转义 | 已生效(`lint/check.py`,rc.2 T16) |
