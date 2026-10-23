# 小红书小工具检查与打包 Skill

面向 Codex 的通用 skill：检查已有 H5、网页游戏和静态工具，修复确认的发布问题，打包离线 ZIP，并验证真正交付的文件。

重点解决“本地能打开，却不知道最终包有没有检查完整”的问题：启动与遮罩、按钮实际点击、短屏/安全区、空存档完整流程、原生保存异常、旧内核及多平台包隔离。**本地通过不代表官方模拟器、真机或审核通过。**

这是社区工作流，不是小红书官方 SDK、审核认证工具或一键生成小工具的引擎。检查规则中的历史保守配置需要对照[当前官方文档](https://miniapp-sandbox.xiaohongshu.com/minitool/doc)确认。项目源文件、业务数据、截图和整份平台文档镜像不随仓库发布。

2026-10-23补充了五类发布回归：恢复后立即返回再继续的暂停竞态、响应式缩小后的实际触摸区域、兼容层执行前的顶层API、隐藏内容时保护旧档，以及正式包调试绕过检查。详见[完整流程检查表](skills/xhs-minitool-release/references/functional-completeness.md#发布前新增交互回归)。这些是按实际功能选用的检查方法，不是承诺自动识别并修复所有问题。

## 安装与调用

在 Codex 中发送：

> 使用 skill-installer，从 https://github.com/quinnlqy/xhs-minitool-check-and-package 的 skills/xhs-minitool-release 安装 skill。

已有同名 skill 时先比较和备份，不直接覆盖本地定制。也可以下载本仓库，按所用 Codex 的技能目录规则安装 `skills/xhs-minitool-release/` 整个文件夹；仓库内使用可放入 `.agents/skills/xhs-minitool-release/`。目录规则见 [OpenAI 官方说明](https://learn.chatgpt.com/docs/build-skills)。

然后调用：

> 使用 $xhs-minitool-release，只检查当前小红书小工具，验证实际发布包，列出复现问题和未测项。

或：

> 使用 $xhs-minitool-release，检查并修复当前项目，保留之前的修复，重新打包小红书小工具，验证最终 ZIP 并交付报告。

分享 skill 本身不需要公开你的应用源码。它也不会自动上传小工具或提交审核。

## 包含什么

| 文件 | 用途 |
| --- | --- |
| [SKILL.md](skills/xhs-minitool-release/SKILL.md) | 检查、确认修复、打包、验证与交付流程 |
| [功能完整性](skills/xhs-minitool-release/references/functional-completeness.md) | 空存档、实际主流程、按钮、原生保存与重试矩阵 |
| [兼容性清单](skills/xhs-minitool-release/references/regressions.md) | 启动遮罩、旧 API、安全区、滚动、异步生命周期等可观察回归 |
| [平台规则与来源](skills/xhs-minitool-release/references/platform-checks.md) | 官方资料核对方法、历史保守配置和适用边界 |
| [脚本使用](skills/xhs-minitool-release/references/tools.md) | 参数、产物、依赖和验证范围 |
| `scripts/package_release.py` | 结构/路径/资源扫描、人工复核项、确定性 ZIP、CRC、逐文件及 ZIP 哈希、全新解压 |
| `scripts/smoke_release.mjs` | 子路径、离线 CSP、无缓存、真实触摸/命中、遮罩和宿主占位、故障注入、产物绑定 |
| `scripts/test_release.py` | 打包与浏览器的正反例自检，刻意制造缺陷应被拒绝 |

扫描不会自动修复项目，不会把正则命中当确定违规，也不能静态识别所有动态资源、着色器问题或业务错误。原生保存矩阵与游戏制作手势需要项目专用测试；这里的通用 smoke 不会伪造已完成这些测试。

## 运行依赖

- 打包器：Python **3.12+**，仅标准库。
- 浏览器检查：Node.js **20.19+**（建议 22/24），目标项目已有 `@playwright/test` 或 `playwright`，以及已安装的兼容浏览器。
- 纯安装/阅读 skill 不需要安装这些运行依赖。已有项目按自己的环境和 `AGENTS.md` 选择解释器，不创建隐式虚拟环境，不自动下载浏览器。

## 可运行示例

以下命令从本仓库根目录运行。`python` 换成你已安装的 Python 3.12+；输出必须是全新路径，重复运行请改版本或目录。

```sh
python skills/xhs-minitool-release/scripts/package_release.py --root examples/demo --out artifacts/demo-v1.zip --extract artifacts/demo-v1-extracted --report artifacts/demo-v1-package.json
```

本仓库的示例是离线计算表单，用于演示检查工具，不是已通过平台审核的小工具。安装浏览器测试依赖并运行：

```sh
npm ci
npx playwright install chromium
node skills/xhs-minitool-release/scripts/smoke_release.mjs --project . --root artifacts/demo-v1-extracted --package-report artifacts/demo-v1-package.json --config examples/flow.json --out artifacts/demo-v1-browser
```

已有 Edge 时可加 `--channel msedge`；已有 Chrome 时可加 `--channel chrome`。可以将 `--project` 指向你已有 Playwright 的项目，避免重复安装。本工具不会自动执行上面的浏览器下载命令。

`--package-report` 校验原 ZIP 哈希和当前解压树的全部文件，目录被改动、文件缺失/增加或 ZIP 被替换时拒绝运行。将报告移到别的电脑后，可用 `--zip /实际位置/tool.zip` 指定归档当前位置。未传报告时仅验证给定目录，输出明确记录没有证明该目录来自 ZIP。

`examples/flow.json` 展示进入、填写、计算断言、返回以及多屏幕检查。检查自己的工具时必须改为自己的 ready、操作和结果断言，不能用 body 可见代替功能就绪。

## 工具自身的验证

```sh
npm ci
npx playwright install chromium
npm test
```

自检每次生成新的 `artifacts/selftest-*`，覆盖确定性打包、路径/文件类型、禁止覆盖旧包、资源缺失、实际按钮命中、CSSOM 不可读、crypto 缺失、遮罩未清理、宿主导航遮挡和运行时 404，以及被篡改的 ZIP/解压文件。`artifacts/` 不进入 Git。

只测打包器：

```sh
python skills/xhs-minitool-release/scripts/test_release.py --work artifacts/package-selftest-v1
```

测试入口可用环境变量 `PYTHON` 选择解释器、`PLAYWRIGHT_CHANNEL` 选择已有浏览器、`PLAYWRIGHT_PROJECT` 指向已有 Playwright 的项目。这些设置只影响本次测试。

v1.0.0 在 2026-10-20 使用 Windows、Python 3.12、Node.js 24 和 Edge 完成本仓库独立依赖的验证：19 项自检，含 21 组浏览器正反例及 3 种产物篡改拒绝；另有示例的 9 组多视口/故障场景通过。没有官方模拟器或 Android/iOS 真机验收记录。

## 报告怎么读

- `blocked`：结构问题阻止打包。
- `structural_preflight_only`：结构预检完成；`manualReviewRequired` 仍需逐项读实际代码确认，不能当全面验收。
- 浏览器 `passed`：仅所列配置场景通过；不是完整业务、官方宿主或真实手机的自动证明。
- 交付应附版本、SHA-256、大小、清单、具体测试与未测项，分别标记官方模拟器、Android、iOS 和审核状态。

规则变化时先核对官方资料，再通过 `--rules` 调整已确认的结构/体积配置。不能为了让报告变绿而删除故障场景或放宽业务断言。

## 贡献与许可

欢迎提交脱敏后的最小复现和改进：说明触发条件、修复前/后结果、运行版本、宿主和环境；不要上传真实存档、账号凭据、未公开业务代码或用户截图。修改工具后运行正反例自检。

本仓库原创说明、脚本与示例使用 [MIT License](LICENSE)。第三方产品名和链接仅用于说明适用对象，不表示官方背书。平台规范以官方当前文档为准，来源与资料边界见 [sources.md](skills/xhs-minitool-release/references/sources.md)。
