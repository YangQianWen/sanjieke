---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'f8db1b8a-a416-42b8-a766-c8be75a740a1'
  PropagateID: 'f8db1b8a-a416-42b8-a766-c8be75a740a1'
  ReservedCode1: 'cf42fe48-bfea-410c-a616-6c569b35e986'
  ReservedCode2: 'cf42fe48-bfea-410c-a616-6c569b35e986'
---

# 三节课自动学习脚本（修复增强版）

本项目基于 [Mogul-Wang/sanjieke](https://github.com/Mogul-Wang/sanjieke) 进行深度修复与功能增强，解决了原版脚本中的多个稳定性问题（如误判章节完成、视频闪退、卡死、元素失效等），并增加了强制学习模式、视频自然结束等待、卡顿自动跳过等特性。


# 6月11日-问题修复总结

## 问题总览

| # | 问题 | 根因 | 核心修复 |
|---|------|------|----------|
| 1 | 章节全部无法定位 | `&nbsp;`(\xa0)导致XPath文本匹配失败 | 新增 `click_by_node_id()` |
| 2 | 未播放视频误报已完成 | 视频源未切换时读取残留进度 | `play_video_and_wait` 视频源对比 |
| 3 | 折叠子视频无法识别 | DOM选择器不覆盖子视频结构 | 新增 `try_play_sub_videos()` |
| 4 | 配置与进度加载逻辑错误 | fallback=True / FORCE_LEARN时忽略json | 修正默认值与加载条件 |
| 5 | 跳过/重学逻辑与需求矛盾 | 已完成章节仍进入验证流程 | json有记录即跳过 |

---

## 问题一：章节无法定位，全部被跳过

**现象**：运行脚本后输出 `无法定位章节 '章节1 思维之剑® 必修课'，跳过`，所有章节都点不中。

**根因**：页面HTML中章节名使用 `&nbsp;`（Unicode `\xa0`，非断行空格）排版，例如：
```
HTML 实际内容：章节1&nbsp;&nbsp;思维之剑®&nbsp;&nbsp;必修课
XPath 搜索文本：章节1 思维之剑® 必修课（仅含普通空格 0x20）
```
XPath 的 `normalize-space()` 函数只处理普通空格（0x20），不处理 `\xa0`，导致文本匹配完全失败。

**修复方案**：
- 新增 `click_by_node_id()`：通过 `.chapter-item-con[node-id]` 属性直接点击，绕过文本匹配
- 重写 `safe_click_by_text()`：4层回退机制处理 `\xa0`：
  - 方法0：XPath `translate()` 将 `\xa0` 转为普通空格
  - 方法1：原始精确匹配（兼容无 `&nbsp;` 的情况）
  - 方法2：`contains()` 模糊匹配 + translate 处理
  - 方法3：JS 搜索点击（终极回退，替换 `\xa0` 后匹配）
- `process_chapters()` 优先使用 `node-id` 点击，文本匹配作为回退

---

## 问题二：未播放视频误报"视频已播放完毕"

**现象**：含折叠子视频的章节（如"二、'四有'目标制定之有定义"），点击父标题后视频源没切换，但脚本读取到上一个视频的残留进度（>95%），直接判定已完成并跳过。

**根因**：原代码的快速检查逻辑未区分视频源是否切换：
```python
# 原代码：不管视频源变了没，进度>95%就返回True
if state["current"] / state["duration"] >= 0.95:
    return True
```
当点击折叠子视频的父标题时，页面不切换视频，`<video>` 元素仍播放上一章节的视频，读取的进度是残留状态。

**修复方案**：重写 `play_video_and_wait()`：
- 新增 `prev_src` 参数：点击前保存当前视频源URL，点击后对比
- `video_changed` 标志：最多等待15秒对比视频源是否变化
- 信任判定：仅当 `video_changed=True` 时才信任"已播放完毕"判断
- 残留状态验证：视频源未切换但进度>95%时，尝试 `currentTime=0` 重置，重置失败说明是残留状态，返回 `False`
- 触发子视频处理：返回 `False` 时自动调用 `try_play_sub_videos()`

---

## 问题三：折叠子视频无法识别

**现象**：部分章节下折叠了子视频（如"四有"课程的2个子视频），脚本只读取了父标题，子视频从未被学习。

**根因**：原代码只查找 `.chapter-item` 和 `.chapter-name`，不知道子视频的DOM结构。

通过浏览器实际检查发现两种不同的页面结构：

| | 平铺结构（思维之剑课程） | 折叠结构（四有目标课程） |
|---|---|---|
| 容器 | `.nav-menu-item` | `.nav-menu-item.chapter-item-active` |
| 章节 | `.chapter-item-con[node-id]` | `.chapter-item-con[node-id]` |
| 标题 | `.chapter-name` | `.chapter-name`(父) + `.section-name`(子) |
| 子视频 | 无 | `.section-item-con[node-id]` |

**修复方案**：
- `process_chapters()` 主动检测 `has_sub`：如果 `nav-menu-item` 内有 `.section-item-con[node-id]`，标记 `has_sub=True`
- `has_sub=True` 时直接进入子视频流程，不再尝试播放父标题视频
- 新增 `try_play_sub_videos()`：优先查找 `.chapter-item-active .section-item-con[node-id]`，标题用 `.section-name`
- 新增 `_check_all_sub_videos_completed()` 辅助方法

---

## 问题四：配置与进度加载逻辑错误

**现象**：`config.ini` 配置 `force_learn = false`，但脚本仍强制重学；`FORCE_LEARN=True` 时不加载 `progress.json`，已完成记录丢失。

**修复**：

| 位置 | 修复前 | 修复后 |
|------|--------|--------|
| `FORCE_LEARN` 默认值 | `fallback=True` | `fallback=False` |
| `load_progress()` 条件 | `and not FORCE_LEARN` | 始终加载 `progress.json` |

---

## 问题五：跳过/重学逻辑与需求矛盾

**需求**：json 里有记录的就是学习完成的，再次运行程序就跳过，只学习未播放过的课程视频。

**修复**：在 `process_chapters()` 和 `try_play_sub_videos()` 中统一实现"有记录即跳过"：
- 普通章节：`is_recorded and not FORCE_LEARN` → 直接跳过
- 含子视频的父章节：通过 `_check_all_sub_videos_completed()` 检查所有子视频是否都有记录，全部完成则跳过
- 子视频：`is_chapter_completed_by_record` 返回 True → 直接跳过，只播放未完成的
- `FORCE_LEARN=True`：唯一可覆盖跳过逻辑的情况

---

## 核心决策流程

```
遍历每个章节:
├── json有记录 且 force_learn=false → ✅ 已完成，跳过
├── 有子视频 且 所有子视频都在json里 → ✅ 子视频全部完成，跳过
└── 未完成 → 进入学习
    ├── 有子视频 → 点击展开 → try_play_sub_videos()
    │    └── 遍历子视频:
    │         ├── json有记录 → 跳过
    │         └── 没记录 → 点击播放 → 播完才 save_progress
    │              └── 全部播完 → 标记父章节完成
    └── 普通章节 → 点击播放
         └── 播完才 save_progress
```

## 防误写 progress.json 的3层保障

| 层级 | 保障机制 | 说明 |
|------|----------|------|
| 1 | `play_video_and_wait` 返回值 | 只有返回 True 才调用 `save_progress`，视频源未切换时返回 False |
| 2 | `video_changed` 检测 | 对比点击前后视频源URL，未变化时不信任进度数据 |
| 3 | 子视频全部完成才标记父章节 | 任何一个子视频播放失败，父章节不标记完成，下次运行时重试 |

## 代码改动清单

**新增方法**

| 方法名 | 作用 |
|--------|------|
| `click_by_node_id()` | 通过 node-id 属性直点章节，绕过文本匹配 |
| `try_play_sub_videos()` | 查找并播放折叠子视频，支持CSS选择器+JS两种查找方式 |
| `_check_all_sub_videos_completed()` | 检查当前页面所有子视频是否都在 progress.json 中有记录 |

**重写方法**

| 方法名 | 核心改动 |
|--------|----------|
| `process_chapters()` | 优先 nav-menu-item + node-id 点击；检测 has_sub；有记录即跳过 |
| `play_video_and_wait()` | 新增 prev_src 参数，视频源切换检测，残留状态验证 |
| `safe_click_by_text()` | 4层回退处理 `\xa0`，JS搜索优先匹配 chapter-item-con |
| `expand_all_collapses()` | 从3种选择器扩展到11种 + JS强制展开 ant-collapse-content |

**关键修正**

| 位置 | 修正前 | 修正后 |
|------|--------|--------|
| `FORCE_LEARN` 默认值 | `fallback=True` | `fallback=False` |
| `load_progress()` 条件 | `and not FORCE_LEARN` | 始终加载 |
| 已完成章节处理 | 进入验证流程 | 直接跳过（FORCE_LEARN=False） |
| 子视频跳过逻辑 | 进入验证 | 有记录即跳过 |


# 6月8日-代码改进总结（凝练版）
## 核心改进
1、断点续学：用 progress.json 记录已完成章节（"课程|章节"），重启后自动跳过。
2、精准完成检测：不再依赖DOM图标，改用 video.ended 或进度 ≥95%。
3、动态超时：等待时间 = 视频时长 ×1.2 + 30秒（最少120秒），避免提前退出。
4、卡住检测：30秒无进度变化则跳过该章节，继续后续。
5、单节容错：一节失败不影响其他章节。

## 重启运行操作
无需任何操作，脚本自动读取 progress.json，只学未完成的。

## progress.json 修改
- 删除文件 → 全部重置。
- 清空内容 `[]` → 全部重置。
- 删除某条记录 → 只重学对应章节。
- 强制学习所有：config.ini 添加 `force_learn = true`。


# 6月2日-更新

## ✨ 主要功能

- ✅ 自动登录三节课企业学习平台
- ✅ 自动获取课程列表（支持翻页）
- ✅ 自动识别课程章节结构（大章节 + 子章节 + 折叠子视频）
- ✅ 自动播放未完成视频，**跳过已完成章节**（基于 progress.json 记录）
- ✅ **2倍速播放**，缩短学习时间
- ✅ **自动处理弹窗**（评价弹窗、离开页面提示）
- ✅ **等待视频自然结束**（基于 `video.ended` 检测），不再固定时长
- ✅ **视频卡住检测**（30 秒无进度变化则自动跳过）
- ✅ **折叠子视频自动识别与播放**（自动展开折叠章节，逐一播放子视频）
- ✅ **视频源切换检测**（防止上一个视频残留进度导致误判已完成）
- ✅ **测试题章节识别与等待**（超时可手动干预）
- ✅ **ChromeDriver 自动匹配**（使用 `webdriver-manager`，无需手动下载）
- ✅ **强制学习模式**（忽略 progress.json 已完成记录，重新播放所有章节）
- ✅ **静音播放**（不打扰用户）

## 🛠️ 修复的已知问题（与原版对比）

| 原版问题 | 本版解决方案 |
|---------|-------------|
| 视频播放 3 秒闪退 | 增加最小播放时间保护，移除过早的完成检测 |
| 所有章节被误判为"已完成" | 增加 `force_learn` 配置，忽略完成标记 |
| `stale element` 错误导致脚本中断 | 每次点击前根据标题重新定位元素，避免引用过期 |
| 已完成的视频卡在 0% 进度 | 增加卡住检测，30 秒无变化则跳过 |
| 测试题页面卡死 | 识别测试题章节，等待完成图标或手动继续 |
| ChromeDriver 版本不匹配 | 使用 `webdriver-manager` 自动匹配驱动 |
| 视频无法自动播放 | 添加 Chrome 参数 `--autoplay-policy=no-user-gesture-required` |
| 章节名含 `&nbsp;` 导致无法点击 | 新增 `click_by_node_id()` 通过 node-id 点击，4层回退处理 `\xa0` |
| 折叠子视频无法识别 | 新增 `try_play_sub_videos()`，支持 `.section-item-con` 子视频结构 |
| 视频源未切换时误报已完成 | 重写 `play_video_and_wait()`，对比视频源URL，检测残留状态 |
| `force_learn` 默认值错误 | `fallback=True` 改为 `fallback=False` |
| `load_progress()` 忽略 progress.json | 移除 `and not FORCE_LEARN` 条件，始终加载记录 |

## 📦 环境依赖

- Python 3.8+
- Google Chrome 浏览器（建议最新版）
- 以下 Python 库：

```bash
pip install selenium webdriver-manager
```

## ⚙️ 配置文件 config.ini（必须修改）
在项目根目录创建 config.ini，并填写你自己的账号信息。请务必修改以下内容：

```plain
[login]
username = 你的手机号/邮箱
password = 你的密码

[course_type]
# 1 = 通用能力课程，2 = 专业能力课程（根据平台入口调整）
type = 1

[url]
url = https://sntelelearning.b.sanjieke.cn/login/sign_in

[years]
# 第几年课程（1/2/3）
years = 1

[settings]
# true = 强制重学所有章节（忽略 progress.json 已完成记录）
# false = 只学习 progress.json 中未记录的章节（默认）
force_learn = false
```

## 🚀 使用方法
1. 克隆本仓库或下载 study_course.py。
2. 安装依赖：`pip install selenium webdriver-manager`
3. 修改 config.ini 中的账号信息（见上节）。
4. 运行脚本：`python study_course.py`

脚本会自动：
- 打开 Chrome 浏览器
- 登录平台
- 获取课程列表（默认只学习前 3 门，可在代码末尾修改 `links[:3]`）
- 依次进入每门课程，展开所有章节，按顺序播放未完成（或强制）的视频
- 视频播放完毕后自动关闭标签页，继续下一门课程

## 📝 自定义配置（下载后需要修改的选项）

### 1. 修改学习的课程数量
打开 study_course.py，找到文件末尾的：
```python
for t, href in links[:3]:
```
将 3 改为你想学习的课程数量（例如 `links[:10]` 表示学习前 10 门，去掉 `[:3]` 则学习全部课程）。

### 2. 调整视频卡住检测时间
如果需要更灵敏或更宽松的卡住检测，修改文件开头的 `PLAY_STALL_TIMEOUT` 变量（单位：秒）：
```python
PLAY_STALL_TIMEOUT = 30   # 30秒无进度变化则跳过
```

### 3. 修改测试题等待时间
如果测试题完成较慢，可增加 `QUIZ_WAIT_SECONDS` 的值（默认 60 秒）。

### 4. Chrome 安装路径（非默认路径）
如果你将 Chrome 安装在非标准位置（例如 D 盘或其他自定义目录），请修改 `find_chrome_binary()` 函数中的路径列表，添加你的实际路径。函数位于代码开头附近：

```plain
possible_paths = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    r"D:\你的自定义路径\chrome.exe",   # 在这里添加你的路径
    os.environ.get("CHROME_BIN", "")
]
```

### 5. 强制学习模式

默认 `force_learn = false`：只学习 progress.json 中没有记录的章节，已完成的一律跳过。

如需强制重学所有章节（忽略已有记录），可将 config.ini 中的 force_learn 改为 true：
```plain
force_learn = true
```

## 📌 注意事项
- 首次运行会自动下载匹配的 ChromeDriver（需联网），后续使用缓存。
- 如果网络较慢，可适当增加代码中的 `time.sleep()` 等待时间。
- 若视频因平台限制无法自动播放，脚本会尝试 JavaScript 调用 `video.play()`。
- 测试题章节默认等待 60 秒检测完成状态，超时会提示手动完成并回车继续。
- 如遇到新页面结构变化导致元素定位失败，请提供错误日志，我会协助更新选择器。

## 📄 许可证
本项目仅供技术学习与研究使用。
严禁用于任何违反平台规定的"刷课""作弊"等行为，使用者须自行承担相关风险。

## 🔗 参考
- 原始仓库：[Mogul-Wang/sanjieke](https://github.com/Mogul-Wang/sanjieke)
- Selenium 官方文档：https://www.selenium.dev/documentation/
