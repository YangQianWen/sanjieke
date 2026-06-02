# -*- coding:utf-8 -*-
"""
三节课自动刷课脚本 - 最终稳定版
功能：
- 自动登录
- 获取课程列表
- 自动学习课程（支持强制学习所有章节）
- 自动设置2倍速
- 处理弹窗
- 检测视频卡住并跳过
- 处理测试题（等待或手动）
"""
import time
import random
import os
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
MAX_WAIT_VIDEO_END = 1800      # 最大等待视频结束时间（秒）
QUIZ_WAIT_SECONDS = 60         # 等待测试题完成的最大时间（秒）
PLAY_STALL_TIMEOUT = 30        # 视频卡住（currentTime不变）的最大秒数

# ---------- 自动查找Chrome路径 ----------
def find_chrome_binary():
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        r"D:\360Downloads\Software\Google\Chrome\Application\chrome.exe",  # 你的路径
        os.environ.get("CHROME_BIN", "")
    ]
    for path in possible_paths:
        if path and os.path.isfile(path):
            return path
    return None

# ---------- 读取配置（支持行内注释） ----------
def read_config_value(config, section, key, fallback=None, as_boolean=False):
    """读取配置值，自动去除行内注释（#后面的内容）"""
    try:
        value = config.get(section, key)
        # 去除行内注释：找到第一个 # 并截断
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

# 强制学习模式（忽略已完成标记）
FORCE_LEARN = read_config_value(config, "settings", "force_learn", fallback=True, as_boolean=True)

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

    # ========== 辅助方法 ==========
    def handle_popup(self):
        """关闭评价弹窗"""
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
        """处理离开页面提示"""
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
        """确保视频播放（点击播放按钮 + 设置2倍速）"""
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

            self.process_chapters()
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

    def is_finished(self, element):
        """检查章节元素是否已完成（仅在非强制学习模式下使用）"""
        if FORCE_LEARN:
            return False
        try:
            if element.find_elements(By.CSS_SELECTOR, ".finish-svg, .check-svg"):
                return True
            classes = element.get_attribute("class") or ""
            if "finished" in classes or "complete" in classes:
                return True
            status = element.find_elements(By.CSS_SELECTOR, ".status-text, .section-finish")
            if status and ("已完成" in status[0].text or "100%" in status[0].text):
                return True
        except:
            pass
        return False

    def safe_click_by_title(self, title, selector_type=".section-container .node-item", fallback_selector=".chapter-item-con"):
        """根据标题点击章节，自动处理 stale element"""
        escaped = title.replace("'", "\\'")
        xpath = f"//*[contains(@class, 'node-name-con') and normalize-space(text())='{escaped}']/ancestor::div[contains(@class, 'node-item') or contains(@class, 'chapter-item-con')]"
        try:
            elem = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(1)
            elem.click()
            return True
        except:
            # 降级：通过遍历叶子节点匹配标题
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
                        return True
                except:
                    continue
            return False

    def process_chapters(self):
        """处理课程章节（展开 -> 收集 -> 逐个学习）"""
        try:
            # 1. 获取菜单容器
            menu = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.nav-menu-container"))
            )

            # 2. 展开所有大章节
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

            # 3. 等待子章节加载
            time.sleep(2)

            # 4. 收集所有叶子节点
            leaf_selector = ".section-container .node-item"
            leaves = self.driver.find_elements(By.CSS_SELECTOR, leaf_selector)
            if not leaves:
                leaf_selector = ".chapter-item-con"
                leaves = self.driver.find_elements(By.CSS_SELECTOR, leaf_selector)

            if not leaves:
                print("⚠️ 未找到任何可学习章节")
                return

            # 5. 提取章节信息
            chapters = []
            for leaf in leaves:
                try:
                    title = leaf.find_element(By.CSS_SELECTOR, ".node-name-con, .chapter-name").text.strip()
                    if not title:
                        continue
                    finished = self.is_finished(leaf)
                    chapters.append((title, finished))
                except:
                    continue

            print(f"🎯 共找到 {len(chapters)} 个章节")
            if FORCE_LEARN:
                print("⚡ 强制学习模式：将播放所有章节（忽略已完成标记）")

            # 6. 逐个学习
            for idx, (title, finished) in enumerate(chapters):
                if finished and not FORCE_LEARN:
                    print(f"✅ 已完成: {title}，跳过")
                    continue

                print(f"📖 开始学习 [{idx+1}/{len(chapters)}]: {title}")

                if not self.safe_click_by_title(title, leaf_selector):
                    print(f"  无法定位章节 '{title}'，跳过")
                    continue

                time.sleep(3)

                if self.is_test_chapter(title):
                    self.handle_quiz(title)
                else:
                    self.play_video_and_wait(title)

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
        print(f"▶️ 播放视频: {title}")
        self.ensure_video_play()

        # 检查是否有视频元素
        has_video = self.driver.execute_script("return document.querySelector('video') !== null;")
        if not has_video:
            print("⚠️ 当前页面没有视频元素，等待3秒后跳过")
            time.sleep(3)
            return

        start_time = time.time()
        last_progress = -1
        last_current = -1
        stall_start = None

        while True:
            elapsed = time.time() - start_time
            if elapsed > MAX_WAIT_VIDEO_END:
                print(f"⏰ 等待超时 ({MAX_WAIT_VIDEO_END}秒)，强制结束")
                break

            try:
                ended = self.driver.execute_script("return document.querySelector('video')?.ended || false;")
                if ended:
                    print("✅ 视频已播放完毕")
                    break
            except:
                pass

            self.handle_popup()
            self.handle_leave_page_tip()

            try:
                current = self.driver.execute_script("return document.querySelector('video')?.currentTime || 0;")
                duration = self.driver.execute_script("return document.querySelector('video')?.duration || 0;")
                if duration > 0:
                    progress = int(current / duration * 100)
                    if progress != last_progress:
                        print(f"  播放进度: {progress}% ({int(current)}/{int(duration)}秒)")
                        last_progress = progress

                    if current == last_current:
                        if stall_start is None:
                            stall_start = time.time()
                        elif time.time() - stall_start > PLAY_STALL_TIMEOUT:
                            print(f"⚠️ 视频已卡住超过 {PLAY_STALL_TIMEOUT} 秒，强制跳过")
                            break
                    else:
                        stall_start = None
                        last_current = current
                else:
                    if stall_start is None:
                        stall_start = time.time()
                    elif time.time() - stall_start > PLAY_STALL_TIMEOUT:
                        print(f"⚠️ 视频无法加载（duration=0）超过 {PLAY_STALL_TIMEOUT} 秒，强制跳过")
                        break
            except Exception as e:
                print(f"  获取进度异常: {e}")

            time.sleep(random.uniform(2, 5))

        print(f"🏁 结束视频: {title}")
        time.sleep(2)

# ---------- 主程序 ----------
if __name__ == "__main__":
    bot = AutoCourseBot(USERNAME, PASSWORD)
    bot.login()
    links = bot.get_all_course_links(course_type)
    # 学习前3门课程（可根据需要修改）
    for t, href in links[:3]:
        bot.study_course(href)
    print("🎉 所有课程学习完毕")
    bot.driver.quit()