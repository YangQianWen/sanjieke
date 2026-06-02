```plain
# 三节课自动学习脚本（修复增强版）

本项目基于 [Mogul-Wang/sanjieke](https://github.com/Mogul-Wang/sanjieke) 进行深度修复与功能增强，解决了原版脚本中的多个稳定性问题（如误判章节完成、视频闪退、卡死、元素失效等），并增加了强制学习模式、视频自然结束等待、卡顿自动跳过等特性。

## ✨ 主要功能

- ✅ 自动登录三节课企业学习平台
- ✅ 自动获取课程列表（支持翻页）
- ✅ 自动识别课程章节结构（大章节 + 子章节）
- ✅ 自动播放未完成视频，**跳过已完成章节**（或强制播放所有章节）
- ✅ **2倍速播放**，缩短学习时间
- ✅ **自动处理弹窗**（评价弹窗、离开页面提示）
- ✅ **等待视频自然结束**（基于 `video.ended` 检测），不再固定时长
- ✅ **视频卡住检测**（30 秒无进度变化则自动跳过）
- ✅ **测试题章节识别与等待**（超时可手动干预）
- ✅ **ChromeDriver 自动匹配**（使用 `webdriver-manager`，无需手动下载）
- ✅ **强制学习模式**（忽略平台“已完成”标记，重新播放所有章节）
- ✅ **静音播放**（不打扰用户）

## 🛠️ 修复的已知问题（与原版对比）

| 原版问题 | 本版解决方案 |
|---------|-------------|
| 视频播放 3 秒闪退 | 增加最小播放时间保护，移除过早的完成检测 |
| 所有章节被误判为“已完成” | 增加 `force_learn` 配置，忽略完成标记 |
| `stale element` 错误导致脚本中断 | 每次点击前根据标题重新定位元素，避免引用过期 |
| 已完成的视频卡在 0% 进度 | 增加卡住检测，30 秒无变化则跳过 |
| 测试题页面卡死 | 识别测试题章节，等待完成图标或手动继续 |
| ChromeDriver 版本不匹配 | 使用 `webdriver-manager` 自动匹配驱动 |
| 视频无法自动播放 | 添加 Chrome 参数 `--autoplay-policy=no-user-gesture-required` |

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
# true = 强制学习所有章节（忽略平台已完成标记）
# false = 只学习未完成的章节（可能存在误判）
force_learn = true
```
## 🚀 使用方法
1.克隆本仓库或下载 study_course.py。
2.安装依赖：pip install selenium webdriver-manager
3.修改 config.ini 中的账号信息（见上节）。
4.运行脚本：python study_course.py
脚本会自动：

打开 Chrome 浏览器
登录平台
获取课程列表（默认只学习前 3 门，可在代码末尾修改 links[:3]）
依次进入每门课程，展开所有章节，按顺序播放未完成（或强制）的视频
视频播放完毕后自动关闭标签页，继续下一门课程

## 📝 自定义配置（下载后需要修改的选项）
### 1. 修改学习的课程数量
打开 study_course.py，找到文件末尾的：
for t, href in links[:3]:
将 3 改为你想学习的课程数量（例如 links[:10] 表示学习前 10 门，去掉 [:3] 则学习全部课程）。

### 2. 调整视频卡住检测时间
如果需要更灵敏或更宽松的卡住检测，修改文件开头的 PLAY_STALL_TIMEOUT 变量（单位：秒）：
PLAY_STALL_TIMEOUT = 30   # 30秒无进度变化则跳过
### 3. 修改测试题等待时间
如果测试题完成较慢，可增加 QUIZ_WAIT_SECONDS 的值（默认 60 秒）。

### 4. Chrome 安装路径（非默认路径）
如果你将 Chrome 安装在非标准位置（例如 D 盘或其他自定义目录），请修改 find_chrome_binary() 函数中的路径列表，添加你的实际路径。函数位于代码开头附近：

```plain
possible_paths = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    r"D:\你的自定义路径\chrome.exe",   # 在这里添加你的路径
    os.environ.get("CHROME_BIN", "")
]
```
### 5. 关闭强制学习模式
如果你希望只学习平台标记为“未完成”的章节（避免重复播放已学内容），可将 config.ini 中的 force_learn 改为 false：
force_learn = false

注意：由于三节课平台可能提前显示“已完成”占位符，导致误判，建议保持 force_learn = true 以确保不遗漏任何视频。如果视频因已完成而无法重新播放，卡住检测会自动跳过。

## 📌 注意事项
+. 首次运行会自动下载匹配的 ChromeDriver（需联网），后续使用缓存。
+. 如果网络较慢，可适当增加代码中的 time.sleep() 等待时间。
+. 若视频因平台限制无法自动播放，脚本会尝试 JavaScript 调用 video.play()。
+. 测试题章节默认等待 60 秒检测完成状态，超时会提示手动完成并回车继续。
+. 如遇到新页面结构变化导致元素定位失败，请提供错误日志，我会协助更新选择器。

## 📄 许可证
本项目仅供技术学习与研究使用。
严禁用于任何违反平台规定的“刷课”“作弊”等行为，使用者须自行承担相关风险。

## 🔗 参考
原始仓库：Mogul-Wang/sanjieke
Selenium 官方文档：https://www.selenium.dev/documentation/
