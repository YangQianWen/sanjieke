# -*- coding:utf-8 -*-
"""
三节课自动刷课脚本 - 修复版（稳定学习未完成章节）
功能：
- 自动登录
- 获取课程列表
- 智能跳过已完成章节（基于视频实际播放进度）
- 自动设置2倍速
- 处理弹窗
- 检测视频卡住并跳过
- 支持断点续学
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

# ---------- 配置 ----------
MAX_WAIT_VIDEO_END = 3600      # 最大等待视频结束时间（秒）扩大到1小时
QUIZ_WAIT_SECONDS = 120        # 等待测试题完成的最大时间（秒）
PLAY_STALL_TIMEOUT = 60        # 视频卡住（currentTime不变）的最大秒数
PROGRESS_FILE = "progress.json"  # 记录已学章节的文件

# ---------- 自动查找Chrome路径 ----------
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

# ---------- 读取配置 ----------
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

# 强制学习模式（如果为true，忽略本地进度记录，但仍然检测视频实际完成状态）
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
            print("⚠️ 未自动找到 Chrome，请手动指定路径")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.maximize_window()
        self.wait = WebDriverWait(self.driver, 20)
        self.username = username
        self.password = password
        self.completed_chapters = self.load_progress()  # 加载已完成的章节记录

    # ========== 进度记录（断点续学） ==========
    def load_progress(self):
        if os.path.exists(PROGRESS_FILE) and not FORCE_LEARN:
            try:
                with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
            except:
                return set()
        return set()

    def save_progress(self, course_title, chapter_title):
        key = f"{course_title}|{chapter_title}"
        self.completed_chapters.add(key)
        try:
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump(list(self.completed_chapters), f, ensure_ascii=False, indent=2)
        except:
            pass

    def is_chapter_completed_by_record(self, course_title, chapter_title):
        key = f"{course_title}|{chapter_title}"
        return key in self.completed_chapters

    # ========== 辅助方法 ==========
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
                self.ensure_video_play()
        except:
            pass

    def ensure_video_play(self):
        """点击播放按钮并设置2倍速"""
        for selector in ["xg-start .xgplayer-icon-play", "xg-play .xgplayer-icon-play", ".xgplayer-icon-play", "video"]:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                time.sleep(0.5)
                elem.click()
                print(f"  点击 {selector}")
                time.sleep(1)
                break
            except:
                continue
        try:
            self.driver.execute_script("""
                var v = document.querySelector('video');
                if (v) v.playbackRate = 2;
            """)
            print("🚀 已设置2倍速")
        except:
            pass

    # ========== 登录与课程列表 ==========
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
        """学习单门课程"""
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

    # ========== 章节处理核心逻辑 ==========
    def is_test_chapter(self, title):
        keywords = ["测试", "考试", "测验", "练习", "quiz", "exam", "test"]
        return any(kw in title.lower() for kw in keywords)

    def safe_click_by_title(self, title, selector_type=".section-container .node-item", fallback_selector=".chapter-item-con"):
        """根据标题点击章节，返回被点击的元素"""
        escaped = title.replace("'", "\\'")
        xpath = f"//*[contains(@class, 'node-name-con') and normalize-space(text())='{escaped}']/ancestor::div[contains(@class, 'node-item') or contains(@class, 'chapter-item-con')]"
        try:
            elem = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(1)
            elem.click()
            return elem
        except:
            # 降级方案
            leaves = self.driver.find_elements(By.CSS_SELECTOR, selector_type)
            if not leaves:
                leaves = self.driver.find_elements(By.CSS_SELECTOR, fallback_selector)
            for leaf in leaves:
                try:
                    t = leaf.find_element(By.CSS_SELECTOR, ".node-name-con, .chapter-name").text.strip()
                    if t == title:
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", leaf)
                        time.sleep(1)
                        leaf.click()
                        return leaf
                except:
                    continue
            return None

    def process_chapters(self, course_title):
        """处理课程章节：只学习未完成的（基于视频实际进度）"""
        try:
            # 等待菜单加载
            menu = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.nav-menu-container"))
            )

            # 展开所有大章节
            items = menu.find_elements(By.CSS_SELECTOR, "div.nav-menu-item")
            for item in items:
                try:
                    if "chapter-item-con-section" in item.get_attribute("class"):
                        expand_btn = item.find_element(By.CSS_SELECTOR, ".chapter-item-con")
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", expand_btn)
                        time.sleep(0.5)
                        expand_btn.click()
                        print("  展开一个大章节")
                        time.sleep(1)
                except StaleElementReferenceException:
                    menu = self.driver.find_element(By.CSS_SELECTOR, "div.nav-menu-container")
                    items = menu.find_elements(By.CSS_SELECTOR, "div.nav-menu-item")
                    continue

            time.sleep(2)

            # 收集所有叶子节点
            leaf_selector = ".section-container .node-item"
            leaves = self.driver.find_elements(By.CSS_SELECTOR, leaf_selector)
            if not leaves:
                leaf_selector = ".chapter-item-con"
                leaves = self.driver.find_elements(By.CSS_SELECTOR, leaf_selector)

            if not leaves:
                print("⚠️ 未找到任何可学习章节")
                return

            # 提取所有章节标题
            chapters = []
            for leaf in leaves:
                try:
                    title = leaf.find_element(By.CSS_SELECTOR, ".node-name-con, .chapter-name").text.strip()
                    if title:
                        chapters.append(title)
                except:
                    continue

            print(f"🎯 共找到 {len(chapters)} 个章节")

            # 遍历每个章节，检查本地记录
            for idx, title in enumerate(chapters):
                # 先检查本地进度记录
                if self.is_chapter_completed_by_record(course_title, title) and not FORCE_LEARN:
                    print(f"✅ 已完成（记录）: {title}，跳过")
                    continue

                print(f"📖 开始学习 [{idx+1}/{len(chapters)}]: {title}")

                # 点击章节
                clicked = self.safe_click_by_title(title, leaf_selector)
                if not clicked:
                    print(f"  无法定位章节 '{title}'，跳过")
                    continue

                time.sleep(3)

                # 判断是否为测试题
                if self.is_test_chapter(title):
                    self.handle_quiz(title)
                    # 测试题完成后保存进度
                    self.save_progress(course_title, title)
                    continue

                # 视频章节：播放并等待完成
                completed = self.play_video_and_wait(title)
                if completed:
                    print(f"✅ 章节 '{title}' 学习完成，保存进度")
                    self.save_progress(course_title, title)
                else:
                    print(f"⚠️ 章节 '{title}' 未能完成（可能播放失败），不保存进度")

            print("✅ 所有章节处理完毕")

        except Exception as e:
            print(f"处理章节失败: {e}")

    def handle_quiz(self, title):
        print(f"📝 检测到测试题章节: {title}")
        print("等待测试题完成（自动检测完成图标或下一节按钮）...")
        start = time.time()
        while time.time() - start < QUIZ_WAIT_SECONDS:
            try:
                if self.driver.find_elements(By.CSS_SELECTOR, ".finish-svg, .check-svg, .quiz-finished"):
                    print("✅ 测试题已完成")
                    time.sleep(2)
                    return
                next_btn = self.driver.find_elements(By.CSS_SELECTOR, ".next-section-btn, .next-btn")
                if next_btn and next_btn[0].is_displayed() and next_btn[0].is_enabled():
                    print("✅ 出现下一节按钮，认为测试题已完成")
                    return
            except:
                pass
            time.sleep(2)
        print(f"⏰ 等待测试题完成超时 ({QUIZ_WAIT_SECONDS}秒)，手动完成后请按回车继续...")
        input("按回车键继续下一个章节...")

    def play_video_and_wait(self, title):
        """播放视频并等待结束，返回是否完成"""
        print(f"▶️ 开始处理视频: {title}")

        # 等待页面稳定
        time.sleep(2)

        # 先检查视频是否已经播放完毕（例如之前已完成但未记录）
        if self.is_video_finished():
            print(f"  检测到视频已播放完毕，无需重新学习")
            return True

        # 确保视频播放
        self.ensure_video_play()

        # 获取视频时长
        duration = self.get_video_duration()
        if duration is None or duration <= 0:
            print("⚠️ 无法获取视频时长，尝试播放60秒后退出")
            # 没有视频元素，可能是非视频内容，等待30秒后返回成功（避免卡死）
            time.sleep(30)
            return True  # 假设完成

        # 动态设置超时时间：视频时长的1.2倍 + 30秒缓冲，最少120秒
        max_wait = max(int(duration * 1.2) + 30, 120)
        print(f"  视频时长: {duration} 秒，最大等待 {max_wait} 秒")

        start_time = time.time()
        last_progress = -1
        last_current = -1
        stall_start = None

        while True:
            elapsed = time.time() - start_time
            if elapsed > max_wait:
                print(f"⏰ 等待超时 ({max_wait}秒)，强制结束")
                break

            # 检查是否结束
            if self.is_video_finished():
                print("✅ 视频已播放完毕")
                return True

            # 处理弹窗
            self.handle_popup()
            self.handle_leave_page_tip()

            # 获取当前进度
            current, dur = self.get_video_progress()
            if dur > 0:
                progress = int(current / dur * 100)
                if progress != last_progress:
                    print(f"  播放进度: {progress}% ({int(current)}/{int(dur)}秒)")
                    last_progress = progress

                # 检测卡住
                if current == last_current:
                    if stall_start is None:
                        stall_start = time.time()
                    elif time.time() - stall_start > PLAY_STALL_TIMEOUT:
                        print(f"⚠️ 视频已卡住超过 {PLAY_STALL_TIMEOUT} 秒，强制跳过")
                        return False
                else:
                    stall_start = None
                    last_current = current

            time.sleep(random.uniform(2, 5))

        return False  # 超时未完成

    def get_video_duration(self):
        """获取视频总时长（秒），失败返回None"""
        try:
            return self.driver.execute_script("return document.querySelector('video')?.duration || 0;")
        except:
            return None

    def get_video_progress(self):
        """获取当前播放时间和总时长"""
        try:
            current = self.driver.execute_script("return document.querySelector('video')?.currentTime || 0;")
            duration = self.driver.execute_script("return document.querySelector('video')?.duration || 0;")
            return current, duration
        except:
            return 0, 0

    def is_video_finished(self):
        """检查当前视频是否已播放完毕（ended 或进度 ≥ 95%）"""
        try:
            ended = self.driver.execute_script("return document.querySelector('video')?.ended || false;")
            if ended:
                return True
            current, duration = self.get_video_progress()
            if duration > 0 and current / duration >= 0.95:
                return True
        except:
            pass
        return False

# ---------- 主程序 ----------
if __name__ == "__main__":
    bot = AutoCourseBot(USERNAME, PASSWORD)
    bot.login()
    links = bot.get_all_course_links(course_type)
    # 学习前3门课程（可根据需要修改或删除切片）
    for t, href in links[:3]:
        bot.study_course(href)
    print("🎉 所有课程学习完毕")
    bot.driver.quit()
