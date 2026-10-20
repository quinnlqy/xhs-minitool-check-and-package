# 通用脚本与证据范围

脚本路径相对于 skill 目录。Python 3.12+ 仅标准库；浏览器脚本使用 Node 20.19+、目标项目的 Playwright 和已安装浏览器。所有例子均需按项目路径替换，不能假定当前目录是发布产物。不自动安装运行时或下载浏览器。

## 打包

```sh
python /path/to/skill/scripts/package_release.py --root ./dist-xhs --out ./artifacts/tool-v1.zip --extract ./artifacts/tool-v1-extracted --report ./artifacts/tool-v1-package.json
```

构建目录与三个输出互相隔离；输出必须全新，不覆盖旧包/报告/解压目录。拒绝符号链接/junction、开发垃圾和越界资源；核对 HTML/CSS 静态引用及大小写，记录模块/内联脚本等问题。ZIP 内容排序并使用固定时间戳，校验 CRC、归档与解压文件 SHA-256。

结构错误退出码 1，仅生成失败报告，不生成 ZIP。结构通过退出码 0，状态仍为 `structural_preflight_only`；人工复核项、项目流程、平台及真机未自动完成。动态路径/srcset/正则 API 命中需语义复核。默认规则来源及 `--rules` 见 [平台核对](platform-checks.md)。

## 浏览器检查

```sh
node /path/to/skill/scripts/smoke_release.mjs --project /path/to/project --root ./artifacts/tool-v1-extracted --package-report ./artifacts/tool-v1-package.json --config ./release-flow.json --out ./artifacts/tool-v1-browser --channel msedge
```

`--project` 用于解析已有 `@playwright/test` 或 `playwright`，无需在 skill 内放依赖。省略 channel 时使用已安装的 Playwright Chromium；缺失浏览器应说明或按用户授权安装，不静默下载。

传 `--package-report` 后校验报告中的 ZIP 哈希和当前完整解压树；报告移动后用 `--zip` 指定 ZIP 当前位置。失败发生在浏览器运行前。未传报告只测目录，报告的 `artifactBinding` 明确为未绑定，不能称已验证交付 ZIP。

配置示例（选择器/断言换成真实产品；可运行例子见仓库 examples）：

```json
{
  "ready":"#main-menu",
  "steps":[
    {"tap":"#start","visible":"#workspace"},
    {"tap":"#back","visible":"#main-menu","hidden":"#workspace"}
  ],
  "viewports":[
    {"width":390,"height":844,"safeArea":{"top":60,"bottom":34},"nativeButtons":[{"top":60,"right":8,"width":44,"height":44}]},
    {"width":844,"height":390}
  ]
}
```

默认 normal、cssom-unreadable、crypto-unavailable 三种场景，各跑每个视口，互相隔离 context。所有请求限定同源 `/nested/tool/`；严格离线 CSP、无缓存、无 SPA fallback，记录 404、外网、页面错误和 CSP 违规。原生按钮是真正拦截点击的几何夹具，不是官方统一位置。

每次 tap 须有 visible/hidden/text 结果断言；先滚动并核对中心命中/宿主占位重叠，再真实 tap。fill 和 reload 可用于输入/持久化流程，结果仍须真实断言。通用配置不能证明复杂制作手势和原生保存矩阵已测，按项目补充专用测试。

可自定义 `scenarios`，字段：`name`、`inject`（cssom/crypto/storage/webgl 或数组）、`ready`、`steps`、`abort`（匹配 URL 的数组）、`replace`（URL 匹配→替换 JS 内容）、`expectedPageErrors`（预期错误子串数组）。`checkOverflow:false` 只在已解释的特殊场景使用。预期故障精确允许，未知错误仍失败。

报告保存截图、错误、服务文件哈希、产物绑定与实际执行场景。console.error 单独记录供语义检查；业务失败若只写控制台，须增加 UI/数据断言。一个 smoke 通过不代表完整流程或手机通过。

## 脚本自测与交付

```sh
python /path/to/skill/scripts/test_release.py --work ./artifacts/selftest-v1 --project /path/to/project --channel msedge
```

不传 project 只测打包器；提供 project 后测正常/CSSOM/crypto、遮罩、原生占位和动态缺失资源等正反例。修改工具后先运行自测。仓库 `npm test` 自动创建独立的 artifacts/selftest-*，解释器与浏览器选择见 README。

交付记录：版本、入口、ZIP 和清单、大小、SHA-256、规范来源日期、复现前/修复后证据、实际操作与数据断言、未测项。官方模拟器、同一 SHA 的 Android、iOS 及审核分别报告。未授权时不上传/发布。
