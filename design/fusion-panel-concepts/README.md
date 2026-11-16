# Fusion 面板概念图(2026-11-16)

Lily 觉得现在的 Fusion 面板不好看,请"lyfusion 会话"用 magpie image(接的是 ChatGPT 生图,gpt-image-2)出概念图。rc.4 按方案 1 做了,实际做法见文末"rc.4 实际做法"。图片只留在本地,不进 git(Lily 定)。

| 文件 | 内容 |
|---|---|
| `concept-1-dark-popover.png` | 深色。卡片从 "● Fusion" 按钮上方弹出、带指向按钮的小尖角;Fusion 开关、助手模型列表(勾选)、思考强度分段按钮、Fast mode 开关、上下文 −/+、交接分段按钮、底部一行本会话 lead 调用数 |
| `concept-2-light-popover.png` | 浅色,同方案 1 |
| `concept-3-dark-toolbar.png` | 深色。贴在输入框上方、靠右的两行小工具条,占地最少 |

推荐方案 1(最好看,也最像 Lily 说的"像模型选择器")。方案 3 做备选。

## 能不能做(查过桌面端给 mod 的接口和官方文档)
资料:mods 文档 [interface](https://code.claude.com/docs/en/plugins/mods/interface)、[reference](https://code.claude.com/docs/en/plugins/mods/reference)、[gallery](https://code.claude.com/docs/en/plugins/mods/gallery);类型文件由 plugin-authoring 技能写出(2.1.317)。

- **位置**:mod 能画的地方是输入框上方那一条(`AbovePrompt`,v2.1.323 起每个 mod 一行)、底部模式标签(`SessionMode`,现在的 "● Fusion")、提示行(`PromptHint`)、侧边栏(`Pane`)。**没有"浮在按钮上的弹出层"这种位置**,模型选择器那种盖住输入框的下拉做不到。
  - 可行做法:面板仍画在 `AbovePrompt`,但不再占满整行,而是一个靠右、宽约 360 的卡片(`Box` 的 `width`、`alignSelf: 'flex-end'`),正好在 Fusion 按钮上方,看起来就是方案 1。
  - 可试:`Box` 的 `hover` 组(`scope`)能"悬停时显示一个绝对定位的卡片"(`position: 'absolute'`)。也许能做出悬停 Fusion 标签就浮出的卡片,要原型验证。
- **控件**:桌面端有 `Box`(背景色、`borderStyle: 'round'`、内外边距、`hover`)、`Text`(颜色、粗细、字号)、`Button`(`variant: primary/secondary`,子元素只能是文字)、`Input`、`Select`(下拉)、`Svg`、`Client`。
  - **分段按钮**(思考强度、交接):一排 `Button`,选中的用 `primary`,其余 `secondary`。能做。
  - **开关**(Fusion、Fast mode):没有现成的开关。`Svg` 能画出开关的样子,但它自己不能点(`isInteractive` 只给悬停和动画,点击要放在外层元素上),`Button` 里又只能放文字。办法:开关图旁边配一个按钮,或者整行做成按钮("Fast mode  ○ Off")。要原型看效果。
  - **`Client`**:我们自己的一个文件画一块区域,能收鼠标、按键、做动画,但画的还是同一套基础控件(不是自由的网页),所以不是"随便画"的出路。
  - **上下文 −/+**:两个小按钮。能做。
- **颜色**:跟着桌面端主题走;`Text`/`Box` 的颜色用主题色名,深浅色自动适配。

## rc.4 实际做法(2026-11-16)
用热加载的临时 mod 出了 5 版预览,按 Lily 每版的反馈改,最后和方案 1 有几处不同:

- **位置**:不画在输入框上方那一条。那一条会占满整行,卡片右对齐时左边是一大片灰,而且卡片高度一变(比如打开 Sidekick 列表)灰的那片也跟着变,会闪。改成桌面端的 widget 小窗:`$.ui.open({ placement: 'widget', backgroundColor: 'transparent' })`,"● Fusion" 按钮开关它。卡片铺满小窗(`width="100%"`),小窗变大小时 Pane 会重画,所以跟着变。卡片不带自己的边框(Plain),行距 `xs`,内边距 `sm`。
- **悬停浮出**:试了,`hover` 组在桌面端没让卡片浮出来,放弃。
- **开关**:用 S2 的做法。Svg 画开关图,一个空的 Client(`hooks/hit.tsx`)绝对定位盖在图上,只收点击。旁边不配按钮(按钮和开关是一回事,Lily 说重复)。Svg 是图片,不能用主题色名,开关的橙色 `#D97757` 和灰色是写死的;其他文字和背景都用主题色名。
- **选择**:Sidekick、Reasoning effort、Context limit 不把选项摊在卡片里,做成模型选择器那样的一行(值 + `›`)。M3 那种往旁边弹的二级菜单在桌面端只能弹到左边,所以改成**原地切换**:点开后整张卡换成列表,顶行 `‹ 标题` 返回。每行是一个 Client(`hooks/row.tsx`),自己算悬停(灰底)、打勾、灰字标签("Recommended"、"Unavailable")。
- **说明文字**:每个列表顶部一行短说明,位置统一;不写 Codex(以后可能试 Haiku 做 sidekick)。"Fusion" 下面没有小字。
- **Context limit**:档位列表 + 一直在下面的自定义输入框(单位 k),超过模型上限时下面那行变成错误提示。
- **sidekick 规定**:不提供 gpt-6-astra;gpt-6-luna 的 effort 从 high 起,High 带 "Recommended"。在引擎里做(`config.py` 的 `EXCLUDED_MODELS`、`EFFORT_POLICY`),卡片和 `/fusion` 都遵守。
- **其他界面**:终端等没有 widget 的地方还是 rc.3 那种 Select 面板。
- **版本不一致**:mod 带着自己的 `MOD_VERSION`,和 `config panel` 里引擎的 `version` 比,不一致就只显示一句 "lyfusion was updated (旧 → 新). Start a new session to load it."、弹一次提示、不改设置。rc.3 及更早的会话没有这个检查。
- **不开新会话换 mod**(查文档,没实测):上传的插件跑桌面端自己保存的那份,`/reload-plugins` 会重读那个位置,上传后在旧会话里打它可以试;userConfig 改设置只是用同一份代码重跑。没有做进 mod。

## rc.5 的修改(2026-11-16,Lily 测完 rc.4)
- **底栏小灯**:rc.4 里 Fusion 开着小灯也是灰的。原因:桌面端画 Button 时不认里面 `Text` 的颜色(主题色名、十六进制、plain 都试过)。改成 emoji:🟠 开、⚪ 关、🟡 要新开会话。按钮的字号和灰底大小由桌面端自己定(Text `size`、Button `variant` 都不起作用),对不齐模型选择器，先这样。
- **圆角**:Box 没有圆角属性;圆角边框(`borderStyle: 'round'`)要占一整格，行太大。改成在行后面垫一张圆角图(Svg,高 22 px、圆角 6 px),鼠标移上去时用 Box 的 `hover` 显示;小标签也垫圆角图。Client 里不能画 Svg,所以行的文字由卡片画，上面盖一层空的 Client 收点击(`hooks/hit.tsx`,和开关同一个),`hooks/row.tsx` 删掉。
- **sidekick**:白名单 gpt-6.1-sol、gpt-6.1-terra、gpt-6-luna,别的模型 `/fusion` 和卡片都不接受。

## 原来的下一步(已做完)
做一个小原型 mod(只做面板,不改引擎),验证:靠右卡片、分段按钮、开关的两种做法、悬停浮出卡片。Fusion 栏的前端由 lead 自己写(Lily 2026-11-13 定,不派给 luna);写完必须过 `claude plugin validate`。
