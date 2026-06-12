# -*- coding:utf-8 -*-
"""
三节课自动刷课脚本 - 优化版（解决时长获取失败和暂停日志冗余）
"""
import time
import random
import os
import json
import configparser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

MAX_WAIT_VIDEO_END = 3600
QUIZ_WAIT_SECONDS = 120
PLAY_STALL_TIMEOUT = 60
PROGRESS_FILE = "progress.json"

def find_chrome_binary():
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        r"D:\360Downloads\Software\Google\Chrome\Application\chrome.exe",
        os.environ.get("CHROME_BIN", "")
    ]
    for path in possible_paths:
        if path and os.path.isfile(path):
            return path
    return None

def read_config_value(config, section, key, fallback=None, as_boolean=False):
    try:
        value = config.get(section, key)
        if '#' in value:
            value = value.split('#')[0].strip()
        if as_boolean:
            return value.lower() in ('true', 'yes', '1', 'on')
        return value
    except (configparser.NoSectionError, configparser.NoOptionError):
        return fallback

config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")

USERNAME = config.get("login", "username")
PASSWORD = config.get("login", "password")
course_type = config.get("course_type", "type")
url = config.get("url", "url")
years = config.get("years", "years")
FORCE_LEARN = read_config_value(config, "settings", "force_learn", fallback=False, as_boolean=True)

class AutoCourseBot:
    def __init__(self, username, password):
        chrome_options = Options()
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
        chrome_binary = find_chrome_binary()
        if chrome_binary:
            chrome_options.binary_location = chrome_binary
            print(f"✅ 找到 Chrome 浏览器：{chrome_binary}")
        else:
            print("⚠️ 未自动找到 Chrome")
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.maximize_window()
        self.wait = WebDriverWait(self.driver, 20)
        self.username = username
        self.password = password
        self.completed_chapters = self.load_progress()

    def load_progress(self):
        if os.path.exists(PROGRESS_FILE):
            try:
                # 使用 utf-8-sig 自动处理 BOM（PowerShell Set-Content 会添加 BOM）
                with open(PROGRESS_FILE, 'r', encoding='utf-8-sig') as f:
                    return set(json.load(f))
            except:
                return set()
        return set()

    def save_progress(self, course_title, chapter_title):
        key = f"{course_title}|{chapter_title}"
        self.completed_chapters.add(key)
        try:
            # 确保不写入 BOM，使用 utf-8 编码
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump(list(self.completed_chapters), f, ensure_ascii=False, indent=2)
        except:
            pass

    def is_chapter_completed_by_record(self, course_title, chapter_title):
        key = f"{course_title}|{chapter_title}"
        return key in self.completed_chapters

    def handle_popup(self):
        try:
            popup_btn = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.score-popup button.close-btn"))
            )
            if popup_btn.is_displayed():
                popup_btn.click()
                print("⚡ 关闭弹窗")
                time.sleep(1)
        except:
            pass

    def handle_leave_page_tip(self):
        try:
            modal = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.leave-page-tip-modal-container"))
            )
            if modal.is_displayed():
                print("⚠️ 中断弹窗，点击继续学习")
                btn = modal.find_element(By.CSS_SELECTOR, "button.button")
                btn.click()
                time.sleep(1)
                self.ensure_video_play(silent=True)
        except:
            pass

    def ensure_video_play(self, speed=2, silent=False):
        """静默或带日志地恢复播放，优先使用JS"""
        # 处理播放器错误
        try:
            error_refresh = self.driver.find_element(By.CSS_SELECTOR, "xg-error .xgplayer-error-refresh")
            if error_refresh.is_displayed():
                print("  检测到播放器错误，点击刷新按钮")
                error_refresh.click()
                time.sleep(3)
        except:
            pass

        # 优先处理 xgplayer-nostart 状态：需要点击启动按钮才能进入正常播放
        try:
            is_nostart = self.driver.execute_script("""
                var player = document.querySelector('.xgplayer');
                return player && player.classList.contains('xgplayer-nostart');
            """)
            if is_nostart:
                # 点击 xgplayer-start 启动按钮
                start_btn = self.driver.find_element(By.CSS_SELECTOR, ".xgplayer-start")
                if start_btn.is_displayed():
                    if not silent:
                        print("  点击 xgplayer-start 启动按钮")
                    try:
                        start_btn.click()
                    except:
                        self.driver.execute_script("arguments[0].click();", start_btn)
                    time.sleep(2)
                    # 启动后设置倍速
                    self.driver.execute_script(f"var v = document.querySelector('video'); if(v) v.playbackRate = {speed};")
                    return True
        except:
            pass

        # 方法1: 直接调用 video.play()
        try:
            self.driver.execute_script(f"""
                var v = document.querySelector('video');
                if (v && v.paused) {{ v.playbackRate = {speed}; v.play(); }}
            """)
            if not silent:
                print(f"🚀 静默恢复播放（{speed}倍速）")
            return True
        except:
            pass

        # 方法2: 模拟点击播放按钮
        for selector in ["xg-start .xgplayer-icon-play", "xg-play .xgplayer-icon-play", ".xgplayer-icon-play", "video"]:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                time.sleep(0.5)
                elem.click()
                if not silent:
                    print(f"  点击 {selector}")
                break
            except:
                continue

        # 设置倍速
        try:
            self.driver.execute_script(f"var v = document.querySelector('video'); if(v && v.playbackRate!={speed}) v.playbackRate = {speed};")
        except:
            pass
        return True

    def wait_for_video_element(self, timeout=25):
        """等待视频元素出现，超时时间更长以适应慢加载页面"""
        for i in range(timeout):
            try:
                has_video = self.driver.execute_script("return document.querySelector('video') !== null;")
                if has_video:
                    return True
                # 检查是否有xgplayer容器（即使video还没渲染出来）
                has_player = self.driver.execute_script("return document.querySelector('.xgplayer, .video-player') !== null;")
                if has_player:
                    # 播放器容器已出现，再等几秒让video元素渲染
                    time.sleep(3)
                    has_video = self.driver.execute_script("return document.querySelector('video') !== null;")
                    if has_video:
                        return True
            except:
                pass
            time.sleep(1)
        return False

    def get_video_src(self):
        try:
            return self.driver.execute_script("""
                var v = document.querySelector('video');
                return v ? (v.src || v.querySelector('source')?.src || '') : '';
            """) or ""
        except:
            return ""

    def get_video_duration(self, max_retries=15):
        """尝试多次获取时长，必要时先触发播放"""
        for i in range(max_retries):
            dur = self.driver.execute_script("return document.querySelector('video')?.duration || 0;")
            if dur and dur > 0:
                return dur
            # 可能是未开始播放导致 duration 为 0，尝试点击播放
            if i == 3:
                self.ensure_video_play(silent=True)
            time.sleep(1)
        return 0

    def login(self):
        self.driver.get(url)
        username_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input#rc_select_0")))
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.input-text[type='password']")))
        password_input.send_keys(self.password)
        login_btn = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.confirm-btn")))
        login_btn.click()
        print("✅ 登录成功")
        time.sleep(3)

    def get_all_course_links(self, course_type):
        card_modules = self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.card-module")))
        card_module = card_modules[int(years) - 1]
        time.sleep(2)
        course_links = card_module.find_elements(By.CSS_SELECTOR, "a.card-item")
        if course_links:
            target = course_links[int(course_type) - 1]
            self.driver.execute_script("arguments[0].scrollIntoView(true);", target)
            time.sleep(1)
            target.click()
            print("已点击课程类型入口")
            time.sleep(5)
        all_links = []
        while True:
            a_tags = self.driver.find_elements(By.TAG_NAME, "a")
            for a in a_tags:
                href = a.get_attribute("href")
                text = a.text.strip()
                if href and "/course/" in href and (text, href) not in all_links:
                    all_links.append((text, href))
            try:
                next_btn = self.driver.find_element(By.CLASS_NAME, "ant-pagination-next")
                if next_btn.get_attribute("aria-disabled") == "true":
                    break
                else:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
                    time.sleep(1)
                    next_btn.click()
                    time.sleep(5)
            except:
                break
        print(f"📚 共获取到 {len(all_links)} 门课程")
        return all_links

    def study_course(self, href):
        self.driver.execute_script("window.open(arguments[0]);", href)
        time.sleep(5)
        self.driver.switch_to.window(self.driver.window_handles[-1])
        try:
            try:
                course_title = self.driver.find_element(By.TAG_NAME, "h1").text
            except:
                course_title = "未知课程"
            print(f"🎓 开始学习课程: {course_title}")
            study_btn = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.course-study-button"))
            )
            study_btn.click()
            print("已点击「开始学习」按钮，等待页面加载...")
            time.sleep(8)
            self.process_chapters(course_title)
        except Exception as e:
            print(f"⚠️ 课程处理异常: {e}")
        finally:
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
            time.sleep(2)

    def is_test_chapter(self, title):
        keywords = ["测试", "考试", "测验", "练习", "quiz", "exam", "test"]
        return any(kw in title.lower() for kw in keywords)

    def _check_all_sub_videos_completed(self, course_title, parent_node_id=""):
        """检查指定父章节内的子视频是否都在 progress.json 中有记录。
        如果指定了 parent_node_id，只检查该 nav-menu-item 内的子视频；
        否则回退到检查全页面（旧逻辑）。"""
        try:
            section_cons = []
            if parent_node_id:
                # 在包含该 node-id 的 nav-menu-item 内查找子视频
                try:
                    con = self.driver.find_element(By.CSS_SELECTOR, f".chapter-item-con[node-id='{parent_node_id}']")
                    nav_item = self.driver.execute_script("""
                        var el = arguments[0];
                        while (el && !el.classList.contains('nav-menu-item')) {
                            el = el.parentElement;
                        }
                        return el;
                    """, con)
                    if nav_item:
                        section_cons = nav_item.find_elements(By.CSS_SELECTOR, ".section-item-con[node-id]")
                except:
                    pass
            if not section_cons:
                # 回退：检查全页面
                section_cons = self.driver.find_elements(By.CSS_SELECTOR, ".section-item-con[node-id]")
            if not section_cons:
                return False
            for con in section_cons:
                try:
                    name = con.find_element(By.CSS_SELECTOR, ".section-name")
                    # 使用 JS textContent 而非 Selenium .text，因为隐藏/未滚动到视图的元素 .text 返回空字符串
                    title = self.driver.execute_script(
                        "return arguments[0].textContent.replace(/\\u00a0/g, ' ').trim();", name
                    )
                    title = ' '.join(title.split())
                    if not title:
                        # 无法获取子视频名称，视为未完成
                        return False
                    if not self.is_chapter_completed_by_record(course_title, title):
                        return False
                except:
                    return False
            return True
        except:
            return False

    def expand_all_collapses(self):
        # 尝试多种折叠/手风琴选择器，确保所有折叠内容都展开
        for selector in [
            ".ant-collapse-header",
            ".chapter-item-con",
            ".chapter-con",
            ".section-title",
            ".section-head",
            "[class*='collapse-header']",
            "[class*='accordion']",
            ".ant-collapse-item .ant-collapse-header",
            ".chapter-item[data-expanded='false']",
            ".node-item [class*='arrow']",
            ".node-item [class*='expand']",
            "[class*='toggle']",
        ]:
            elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
            for elem in elems:
                try:
                    if elem.is_displayed():
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                        time.sleep(0.3)
                        elem.click()
                        time.sleep(0.5)
                except:
                    pass
        # 额外通过JS展开所有折叠面板的content区域
        try:
            self.driver.execute_script("""
                document.querySelectorAll('.ant-collapse-content, .ant-collapse-content-box').forEach(el => {
                    el.style.height = 'auto';
                    el.style.overflow = 'visible';
                    el.style.display = 'block';
                });
            """)
        except:
            pass

    def click_by_node_id(self, node_id):
        """通过 node-id 属性点击章节或子视频，最可靠的方式"""
        # 优先尝试 chapter-item-con（主章节）
        try:
            elem = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, f".chapter-item-con[node-id='{node_id}']"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(0.5)
            try:
                elem.click()
            except:
                self.driver.execute_script("arguments[0].click();", elem)
            return True
        except:
            pass

        # 尝试 section-item-con（子视频）
        try:
            elem = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, f".section-item-con[node-id='{node_id}']"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(0.5)
            try:
                elem.click()
            except:
                self.driver.execute_script("arguments[0].click();", elem)
            return True
        except:
            pass

        # 回退：任意 [node-id] 元素
        try:
            elem = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, f"[node-id='{node_id}']"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(0.5)
            try:
                elem.click()
            except:
                self.driver.execute_script("arguments[0].click();", elem)
            return True
        except:
            pass

        # 最终回退：找 nav-menu-item 父级再点击
        try:
            # 尝试 chapter-item-con 或 section-item-con
            elem = self.driver.find_element(By.CSS_SELECTOR, f".chapter-item-con[node-id='{node_id}'], .section-item-con[node-id='{node_id}']")
            nav_item = self.driver.execute_script("""
                var el = arguments[0];
                while (el && !el.classList.contains('nav-menu-item')) {
                    el = el.parentElement;
                }
                return el || arguments[0];
            """, elem)
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", nav_item)
            time.sleep(0.5)
            nav_item.click()
            return True
        except:
            return False

    def safe_click_by_text(self, title, retries=3):
        clean_title = ' '.join(title.split())
        for attempt in range(retries):
            try:
                # 方法0: 通过 XPath + translate 处理 &nbsp;(\xa0)
                # XPath normalize-space() 不处理 \xa0，需用 translate 将 \xa0 转为普通空格
                xpath_nbsp = f"//*[translate(normalize-space(translate(., '\u00a0', ' ')), '\u00a0', ' ')='{clean_title.replace(chr(39), chr(92)+chr(39))}']"
                try:
                    elem = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, xpath_nbsp)))
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                    time.sleep(0.5)
                    elem.click()
                    return True
                except:
                    pass

                # 方法1: 原始精确匹配（兼容无 &nbsp; 的情况）
                xpath = f"//*[normalize-space()='{clean_title.replace(chr(39), chr(92)+chr(39))}']"
                try:
                    elem = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                    time.sleep(0.5)
                    elem.click()
                    return True
                except:
                    pass

                # 方法2: 包含匹配（兼容多余文字的情况）
                xpath2 = f"//div[contains(@class, 'chapter-item') or contains(@class, 'node-item')]//*[contains(translate(normalize-space(translate(., '\u00a0', ' ')), '\u00a0', ' '), '{clean_title.replace(chr(39), chr(92)+chr(39))}')]"
                elem = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath2)))
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                time.sleep(0.5)
                elem.click()
                return True
            except StaleElementReferenceException:
                print(f"  元素 '{clean_title}' 陈旧，重试 {attempt+1}/{retries}")
                time.sleep(1)
            except Exception as e:
                if attempt == retries - 1:
                    # 方法3: JS搜索点击（终极回退）
                    try:
                        result = self.driver.execute_script("""
                            var target = arguments[0];
                            // 优先找 chapter-item-con[contains text]，点击它
                            var allCons = document.querySelectorAll('.chapter-item-con, [node-id]');
                            for (var el of allCons) {
                                var text = el.textContent.replace(/\\u00a0/g, ' ').trim();
                                if (text.includes(target)) {
                                    el.scrollIntoView({block: 'center'});
                                    el.click();
                                    return true;
                                }
                            }
                            // 回退：找其他可点击元素
                            var allEls = document.querySelectorAll('.nav-menu-item, .chapter-item, .node-item, .chapter-name');
                            for (var el of allEls) {
                                var text = el.textContent.replace(/\\u00a0/g, ' ').trim();
                                if (text.includes(target)) {
                                    el.scrollIntoView({block: 'center'});
                                    el.click();
                                    return true;
                                }
                            }
                            return false;
                        """, clean_title)
                        if result:
                            return True
                    except:
                        pass
                time.sleep(1)
        return False

    def process_chapters(self, course_title):
        try:
            time.sleep(3)
            self.expand_all_collapses()
            time.sleep(2)

            # 查找章节：优先用 nav-menu-item（可点击容器），提取标题+node-id
            chapter_info = []  # [(clean_title, node_id, has_sub_videos), ...]
            nav_items = self.driver.find_elements(By.CSS_SELECTOR, ".nav-menu-item")
            if nav_items:
                for item in nav_items:
                    try:
                        name_elem = item.find_element(By.CSS_SELECTOR, ".chapter-name, .node-name-con, .name")
                        title = name_elem.text.strip()
                        node_id = ""
                        try:
                            con = item.find_element(By.CSS_SELECTOR, ".chapter-item-con, [node-id]")
                            node_id = con.get_attribute("node-id") or ""
                        except:
                            pass
                        # 检测是否有折叠子视频（section-item-con）
                        has_sub = len(item.find_elements(By.CSS_SELECTOR, ".section-item-con[node-id]")) > 0
                        if title:
                            clean_title = ' '.join(title.split())
                            if clean_title not in [c[0] for c in chapter_info]:
                                chapter_info.append((clean_title, node_id, has_sub))
                    except:
                        continue

            # 回退：如果 nav-menu-item 没找到，用旧的 chapter-item 选择器
            if not chapter_info:
                items = self.driver.find_elements(By.CSS_SELECTOR, ".chapter-item")
                if not items:
                    items = self.driver.find_elements(By.CSS_SELECTOR, ".node-item")
                for item in items:
                    try:
                        title_elem = item.find_element(By.CSS_SELECTOR, ".node-name-con, .chapter-name, .name")
                        title = title_elem.text.strip()
                        node_id = ""
                        try:
                            con = item.find_element(By.CSS_SELECTOR, ".chapter-item-con, [node-id]")
                            node_id = con.get_attribute("node-id") or ""
                        except:
                            pass
                        has_sub = len(item.find_elements(By.CSS_SELECTOR, ".section-item-con[node-id]")) > 0
                        if title:
                            clean_title = ' '.join(title.split())
                            if clean_title not in [c[0] for c in chapter_info]:
                                chapter_info.append((clean_title, node_id, has_sub))
                    except:
                        continue

            if not chapter_info:
                print("⚠️ 未找到任何章节")
                return
            print(f"🎯 共找到 {len(chapter_info)} 个章节")

            for idx, (clean_title, node_id, has_sub) in enumerate(chapter_info):
                is_recorded = self.is_chapter_completed_by_record(course_title, clean_title)

                # 含子视频的父章节：即使父章节有完成记录，也要验证子视频是否真的完成
                if has_sub:
                    all_sub_done = self._check_all_sub_videos_completed(course_title, node_id)
                    if all_sub_done and not FORCE_LEARN:
                        if not is_recorded:
                            self.save_progress(course_title, clean_title)
                        print(f"✅ [{idx+1}/{len(chapter_info)}]: {clean_title} — 子视频全部完成，跳过")
                        continue
                    # 子视频未全部完成，需要继续处理（即使父章节有记录也不跳过）
                    if is_recorded and not FORCE_LEARN:
                        print(f"⚠️ [{idx+1}/{len(chapter_info)}]: {clean_title} — 有完成记录但子视频未全部完成，重新处理")
                    else:
                        print(f"📖 [{idx+1}/{len(chapter_info)}]: {clean_title} (有子视频)")
                else:
                    # 普通章节：有记录直接跳过
                    if is_recorded and not FORCE_LEARN:
                        print(f"✅ [{idx+1}/{len(chapter_info)}]: {clean_title} — 已完成，跳过")
                        continue
                    print(f"📖 [{idx+1}/{len(chapter_info)}]: {clean_title}")

                # 在点击前保存当前视频状态，用于后续判断视频是否真正切换
                prev_src = self.get_video_src()
                prev_time_val = 0
                try:
                    prev_time_val = self.driver.execute_script("return document.querySelector('video')?.currentTime || 0;") or 0
                except:
                    pass

                # 如果有折叠子视频，直接跳过主章节视频，进入子视频处理
                if has_sub:
                    print(f"  含折叠子视频，直接展开并处理子视频...")
                    # 先点击展开该章节（如果还没展开的话）
                    if node_id:
                        self.click_by_node_id(node_id)
                        time.sleep(2)
                    self.try_play_sub_videos(course_title, clean_title, prev_src, node_id)
                    continue

                # 普通章节：点击章节
                clicked = False
                if node_id:
                    clicked = self.click_by_node_id(node_id)
                    if not clicked:
                        print(f"  node-id 点击失败，尝试文本匹配...")
                if not clicked:
                    clicked = self.safe_click_by_text(clean_title)
                if not clicked:
                    print(f"  无法定位章节 '{clean_title}'，跳过")
                    continue

                time.sleep(3)
                if self.is_test_chapter(clean_title):
                    self.handle_quiz(clean_title)
                    self.save_progress(course_title, clean_title)
                else:
                    if self.play_video_and_wait(clean_title, prev_src=prev_src, prev_time=prev_time_val):
                        self.save_progress(course_title, clean_title)
                    else:
                        # 视频未成功播放，可能该章节包含折叠子视频
                        print(f"  🔍 主章节视频未切换，尝试查找并播放折叠子视频...")
                        self.try_play_sub_videos(course_title, clean_title, prev_src)
            print("✅ 所有章节处理完毕")
        except Exception as e:
            print(f"处理章节失败: {e}")

    def handle_quiz(self, title):
        print(f"📝 检测到测试题章节: {title}")
        start = time.time()
        while time.time() - start < QUIZ_WAIT_SECONDS:
            try:
                if self.driver.find_elements(By.CSS_SELECTOR, ".finish-svg, .check-svg"):
                    print("✅ 测试题已完成")
                    return
                next_btn = self.driver.find_elements(By.CSS_SELECTOR, ".next-section-btn, .next-btn")
                if next_btn and next_btn[0].is_displayed():
                    print("✅ 出现下一节按钮")
                    return
            except:
                pass
            time.sleep(2)
        input("超时，按回车继续...")

    def try_play_sub_videos(self, course_title, parent_title, prev_src_before_click="", parent_node_id=""):
        """尝试查找并播放折叠在章节标题下的子视频"""
        # 先尝试再次展开折叠内容
        self.expand_all_collapses()
        time.sleep(2)

        # 查找子视频：只在当前父章节的 nav-menu-item 中查找，避免找到其他章节的同名子视频
        sub_info = []  # [(title, node_id), ...]

        # 方法1: 在包含 parent_node_id 的 nav-menu-item 内查找
        target_container = None
        if parent_node_id:
            try:
                con = self.driver.find_element(By.CSS_SELECTOR, f".chapter-item-con[node-id='{parent_node_id}']")
                # 向上找到 nav-menu-item
                target_container = self.driver.execute_script("""
                    var el = arguments[0];
                    while (el && !el.classList.contains('nav-menu-item')) {
                        el = el.parentElement;
                    }
                    return el;
                """, con)
            except:
                pass

        if target_container:
            section_cons = target_container.find_elements(By.CSS_SELECTOR, ".section-item-con[node-id]")
            for con in section_cons:
                nid = con.get_attribute("node-id") or ""
                try:
                    name = con.find_element(By.CSS_SELECTOR, ".section-name")
                    # 使用 JS textContent 而非 Selenium .text，避免隐藏元素返回空字符串
                    title = self.driver.execute_script(
                        "return arguments[0].textContent.replace(/\\u00a0/g, ' ').trim();", name
                    )
                    if title:
                        clean_t = ' '.join(title.split())
                        if clean_t not in [s[0] for s in sub_info]:
                            sub_info.append((clean_t, nid))
                except:
                    continue

        # 方法2: 通过 chapter-item-active 查找（如果点击后active已切换）
        if not sub_info:
            try:
                active_item = self.driver.find_element(By.CSS_SELECTOR, ".chapter-item-active")
                # 验证 active_item 是否是当前父章节
                active_name = active_item.find_element(By.CSS_SELECTOR, ".chapter-name").text.strip()
                if parent_title in active_name or active_name in parent_title:
                    section_cons = active_item.find_elements(By.CSS_SELECTOR, ".section-item-con[node-id]")
                    for con in section_cons:
                        nid = con.get_attribute("node-id") or ""
                        try:
                            name = con.find_element(By.CSS_SELECTOR, ".section-name")
                            # 使用 JS textContent 而非 Selenium .text
                            title = self.driver.execute_script(
                                "return arguments[0].textContent.replace(/\\u00a0/g, ' ').trim();", name
                            )
                            if title:
                                clean_t = ' '.join(title.split())
                                if clean_t not in [s[0] for s in sub_info]:
                                    sub_info.append((clean_t, nid))
                        except:
                            continue
            except:
                pass

        # 方法3: JS精确定位 —— 在包含 parent_node_id 的 nav-menu-item 内查找
        if not sub_info and parent_node_id:
            print(f"  使用JS在父章节内搜索子视频...")
            try:
                js_result = self.driver.execute_script("""
                    var parentId = arguments[0];
                    var results = [];
                    // 找到包含该 node-id 的 nav-menu-item
                    var con = document.querySelector(".chapter-item-con[node-id='" + parentId + "']");
                    var navItem = con;
                    while (navItem && !navItem.classList.contains('nav-menu-item')) {
                        navItem = navItem.parentElement;
                    }
                    if (navItem) {
                        navItem.querySelectorAll('.section-item-con[node-id]').forEach(el => {
                            var nameEl = el.querySelector('.section-name');
                            if (nameEl) {
                                var text = nameEl.textContent.replace(/\\u00a0/g, ' ').trim();
                                var nid = el.getAttribute('node-id') || '';
                                if (text) results.push({text: text, nodeId: nid});
                            }
                        });
                    }
                    return results;
                """, parent_node_id)
                if js_result:
                    for item in js_result:
                        clean_t = ' '.join(item['text'].split())
                        if clean_t and clean_t not in [s[0] for s in sub_info]:
                            sub_info.append((clean_t, item.get('nodeId', '') or ''))
            except:
                pass

        if not sub_info:
            # 最终回退：通过JS查找全局子视频（仅在其他方法都失败时使用）
            print("  使用JS全局搜索子视频条目...")
            try:
                js_result = self.driver.execute_script("""
                    var results = [];
                    // 查找所有 section-item-con（折叠子视频）
                    document.querySelectorAll('.section-item-con[node-id]').forEach(el => {
                        var nameEl = el.querySelector('.section-name');
                        if (nameEl) {
                            var text = nameEl.textContent.replace(/\\u00a0/g, ' ').trim();
                            var nid = el.getAttribute('node-id') || '';
                            if (text) results.push({text: text, nodeId: nid});
                        }
                    });
                    return results;
                """)
                if js_result:
                    seen = set()
                    for item in js_result:
                        clean_t = ' '.join(item['text'].split())
                        if clean_t and clean_t != parent_title and clean_t not in seen:
                            seen.add(clean_t)
                            sub_info.append((clean_t, item.get('nodeId', '') or ''))
            except:
                pass

        if not sub_info:
            print(f"  未找到子视频，该章节标记为未完成（不保存进度）")
            return

        # 只保留未完成的子视频（有记录的跳过）
        sub_to_play = []
        for t, nid in sub_info:
            if self.is_chapter_completed_by_record(course_title, t) and not FORCE_LEARN:
                print(f"  ✅ 子视频已完成: {t}，跳过")
            else:
                sub_to_play.append((t, nid))

        if not sub_to_play:
            # 所有子视频都已完成，标记父章节完成
            self.save_progress(course_title, parent_title)
            print(f"  ✅ 所有子视频均已完成，标记父章节完成: {parent_title}")
            return

        print(f"  需学习 {len(sub_to_play)} 个子视频")

        for sub_title, sub_node_id in sub_to_play:
            print(f"  📹 播放子视频: {sub_title}")

            # 保存当前视频源
            prev_src = self.get_video_src()
            prev_time_val = 0
            try:
                prev_time_val = self.driver.execute_script("return document.querySelector('video')?.currentTime || 0;") or 0
            except:
                pass

            # 点击子视频
            clicked = False
            if sub_node_id:
                clicked = self.click_by_node_id(sub_node_id)
            if not clicked:
                clicked = self.safe_click_by_text(sub_title)
            if not clicked:
                print(f"  无法定位子视频 '{sub_title}'，跳过")
                continue
            time.sleep(3)
            if self.play_video_and_wait(sub_title, prev_src=prev_src, prev_time=prev_time_val):
                self.save_progress(course_title, sub_title)
            else:
                print(f"  ⚠️ 子视频 '{sub_title}' 播放失败")

        # 所有子视频处理完后，检查是否可以标记父章节为完成
        all_subs_done = all(
            self.is_chapter_completed_by_record(course_title, st)
            for st, _ in sub_to_play
        )
        if all_subs_done:
            self.save_progress(course_title, parent_title)
            print(f"  ✅ 父章节所有子视频已完成: {parent_title}")

    def get_video_state(self):
        try:
            current = self.driver.execute_script("return document.querySelector('video')?.currentTime || 0;")
            duration = self.driver.execute_script("return document.querySelector('video')?.duration || 0;")
            paused = self.driver.execute_script("return document.querySelector('video')?.paused || true;")
            return {"current": current, "duration": duration, "paused": paused}
        except:
            return {"current": 0, "duration": 0, "paused": True}

    def is_video_finished(self):
        try:
            ended = self.driver.execute_script("return document.querySelector('video')?.ended || false;")
            if ended:
                return True
            state = self.get_video_state()
            if state["duration"] > 0 and state["current"] / state["duration"] >= 0.95:
                return True
        except:
            pass
        return False

    def play_video_and_wait(self, title, prev_src="", prev_time=0):
        """播放视频并等待完成。prev_src/prev_time 用于检测视频是否真正切换"""
        print(f"▶️ 播放视频: {title}")
        # 等待视频元素存在
        if not self.wait_for_video_element():
            # 检查是否存在 xgplayer 或视频容器 —— 如果有，说明视频页面还没完全加载，不是图文章节
            has_player_container = False
            try:
                has_player_container = self.driver.execute_script("""
                    return !!(document.querySelector('.xgplayer') ||
                              document.querySelector('.video-player') ||
                              document.querySelector('[class*="player-container"]'));
                """)
            except:
                pass
            if has_player_container:
                # 有播放器容器但没 video 元素，再等待一下
                print("⚠️ 检测到播放器容器但无 video 元素，等待加载...")
                if self.wait_for_video_element(timeout=15):
                    pass  # video 元素出现了，继续往下走
                else:
                    print("⚠️ 播放器容器仍无 video 元素，视频可能加载失败")
                    return False
            else:
                # 完全没有任何播放器容器，可能是图文章节
                print("⚠️ 无视频元素和播放器容器，可能是图文章节，标记为完成")
                return True

        # 等待视频源切换：与点击前的视频源比较，确认是新视频已加载
        video_changed = False
        for i in range(15):
            new_src = self.get_video_src()
            if prev_src:
                if new_src and new_src != prev_src:
                    video_changed = True
                    print(f"  视频源已切换 (等待{i+1}秒)")
                    break
            else:
                if new_src:
                    video_changed = True
                    print(f"  视频源已加载 (等待{i+1}秒)")
                    break
            time.sleep(1)

        if not video_changed and prev_src:
            print("⚠️ 视频源未切换，可能该章节包含折叠子视频而非独立视频")

        # 获取视频时长（带重试和播放触发）
        duration = self.get_video_duration(max_retries=15)
        if duration <= 0:
            if not video_changed and prev_src:
                print("⚠️ 视频源未切换且无法获取时长，该章节可能无独立视频")
                return False
            print("⚠️ 无法获取视频时长，将尝试播放5分钟后标记完成")
            self.ensure_video_play(silent=False)
            time.sleep(300)  # 5分钟
            if self.is_video_finished():
                print("✅ 视频已播放完毕（通过固定等待）")
                return True
            print("⚠️ 固定等待结束，但仍未检测到完成，跳过")
            return False

        # 快速检查是否已完成 —— 仅在确认视频源已真正切换且播放器不在nostart状态后才信任
        state = self.get_video_state()
        if state["current"] > 0 and state["duration"] > 0 and (state["current"] / state["duration"] >= 0.95):
            # 检查 xgplayer 是否在 nostart 状态 —— 是则不信任进度数据
            is_nostart = False
            try:
                is_nostart = self.driver.execute_script("""
                    var player = document.querySelector('.xgplayer');
                    return player && player.classList.contains('xgplayer-nostart');
                """)
            except:
                pass
            if is_nostart:
                print("⚠️ 播放器处于 nostart 状态，进度数据不可信，需要启动播放器")
            elif video_changed:
                print("✅ 视频已播放完毕")
                return True
            else:
                # 视频源未切换，但进度 > 95% —— 这很可能是上一个视频的残留状态
                print(f"⚠️ 检测到进度 {int(state['current']/state['duration']*100)}% 但视频源未切换")
                print("  这可能是上一个视频的残留状态，尝试重新播放以验证")
                try:
                    self.driver.execute_script("""
                        var v = document.querySelector('video');
                        if (v) { v.currentTime = 0; v.pause(); }
                    """)
                    time.sleep(2)
                    new_time = self.driver.execute_script("return document.querySelector('video')?.currentTime || 0;")
                    new_dur = self.driver.execute_script("return document.querySelector('video')?.duration || 0;")
                    if new_dur > 0 and new_time / new_dur >= 0.95:
                        print("  重置后仍处于末尾，确认该视频确实已播放完毕")
                        return True
                except:
                    pass
                print("  视频源未切换且可能是残留状态，该章节可能无独立视频（含折叠子视频）")
                return False

        # 开始播放
        self.ensure_video_play(speed=2, silent=False)

        # 额外检查：确保 xgplayer 已脱离 nostart 状态
        try:
            still_nostart = self.driver.execute_script("""
                var player = document.querySelector('.xgplayer');
                return player && player.classList.contains('xgplayer-nostart');
            """)
            if still_nostart:
                print("  ⚠️ 播放器仍处于 nostart 状态，再次点击启动按钮")
                start_btn = self.driver.find_element(By.CSS_SELECTOR, ".xgplayer-start")
                try:
                    start_btn.click()
                except:
                    self.driver.execute_script("arguments[0].click();", start_btn)
                time.sleep(3)
        except:
            pass
        total_wait = max(int(duration * 1.2) + 30, 120)
        total_wait = min(total_wait, duration * 2)
        print(f"  视频时长: {duration} 秒，总超时 {total_wait} 秒")

        start_time = time.time()
        last_progress = -1
        stall_start = None
        pause_recovery_count = 0
        current_speed = 2
        last_recovery_progress = -1
        last_pause_log_time = 0  # 用于限制暂停日志频率

        while True:
            elapsed = time.time() - start_time
            if elapsed > total_wait:
                print("⏰ 总播放超时")
                break

            if self.is_video_finished():
                print("✅ 视频已播放完毕")
                return True

            self.handle_popup()
            self.handle_leave_page_tip()

            state = self.get_video_state()
            if state["duration"] > 0:
                progress = int(state["current"] / state["duration"] * 100)
                if progress != last_progress:
                    print(f"  进度: {progress}% ({int(state['current'])}/{int(state['duration'])}秒)")
                    last_progress = progress
                    stall_start = None
                    if progress > last_recovery_progress:
                        pause_recovery_count = 0
                    last_recovery_progress = progress

                # 处理暂停：静默恢复，但限制日志输出（每10秒最多一次）
                if state["paused"]:
                    pause_recovery_count += 1
                    now = time.time()
                    if now - last_pause_log_time > 10:
                        print(f"  视频暂停，静默恢复（{current_speed}倍速）")
                        last_pause_log_time = now
                    self.ensure_video_play(speed=current_speed, silent=True)
                    stall_start = None
                    time.sleep(1)
                    if pause_recovery_count >= 5 and current_speed > 1:
                        # 暂停恢复超过5次，先检查是否又回到了 nostart 状态
                        try:
                            is_nostart = self.driver.execute_script("""
                                var player = document.querySelector('.xgplayer');
                                return player && player.classList.contains('xgplayer-nostart');
                            """)
                            if is_nostart:
                                print(f"  ⚠️ 播放器回到了 nostart 状态，重新点击启动按钮")
                                start_btn = self.driver.find_element(By.CSS_SELECTOR, ".xgplayer-start")
                                try:
                                    start_btn.click()
                                except:
                                    self.driver.execute_script("arguments[0].click();", start_btn)
                                time.sleep(2)
                                pause_recovery_count = 0
                                continue
                        except:
                            pass
                        current_speed = 1
                        print(f"  ⚠️ 暂停恢复超过5次，降为1倍速并静默恢复")
                        self.ensure_video_play(speed=1, silent=False)
                        pause_recovery_count = 0
                    continue

                # 卡顿检测
                if elapsed > 30 and progress == last_progress:
                    if stall_start is None:
                        stall_start = time.time()
                    elif time.time() - stall_start > PLAY_STALL_TIMEOUT:
                        print(f"⚠️ 视频已卡住超过 {PLAY_STALL_TIMEOUT} 秒，跳过")
                        return False
            time.sleep(random.uniform(2, 5))

        return self.is_video_finished()

if __name__ == "__main__":
    bot = AutoCourseBot(USERNAME, PASSWORD)
    bot.login()
    links = bot.get_all_course_links(course_type)
    for t, href in links:
        bot.study_course(href)
    print("🎉 所有课程学习完毕")
    bot.driver.quit()
