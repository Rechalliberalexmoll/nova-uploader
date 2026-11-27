#!/usr/bin/env python3
"""NovaUploader - Nova3D 打印机 .cws 上传与管理工具

直接用打印机自带的 HTTP 接口（端口 8081），不依赖 NovaMaker，
因此不受其上传卡死问题影响。全部为标准库实现，无需安装任何依赖。
"""

import http.client
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, font as tkfont, ttk
from urllib.parse import quote

try:
    import winsound
except Exception:
    winsound = None

DEFAULT_PORT = 8081
CHUNK = 64 * 1024
# 程序自身所在目录（打包后是 exe 目录）
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _user_data_dir():
    """配置和历史放用户目录，跟程序本身分开，搬动 exe 不会丢。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "NovaUploader")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        return APP_DIR
    return path


DATA_DIR = _user_data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "printers.json")
CONFIG_PATH_LEGACY = os.path.join(APP_DIR, "printers.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
HISTORY_LIMIT = 300

# NovaMaker 的图标（64x64 PNG，内嵌以免打包后还要带外部文件）
ICON_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAHn0lEQVR42u1bXUhUXRtde58zzk02jT+RUQlBQXRhWiYNlE1k"
    "N9JVEN2VfuVFBGGYNxZ0W4R6VwS9hCBRoHVVUQqfkZIF/QmKUpJZ9Bq+Imrl6DlnfRff7POeGWecH6esaR44OM6c2Wevtfd+"
    "nvU8e7ZAZBMANKSXmQAYz43pBnxRbCLsfwnAApAHYC+A9VHu+11MjfgogP8CGHdgXGAy+Pc4gL+DX06n6+8gNidWe2S14Bqp"
    "BnA90TXzG5jTp/0HwF8OzBDBKw/AP8E3jTScAUYQ2z9BrAKAkEEmCMAPICf4WktTB8ggRr/CKR03rHOwla6m8K0Pd3zOpZDu"
    "JiJ5/j/WMgRkCMgQ8GebnnIXKwQ0TQNJkIQQAkIIWJYFy7LSmwApJSzLgmEYkZWIpsE0zfQkQIHLz8/H0aNHUVFRAU3TYBgG"
    "Ojo60N7ejuHh4V+ahDNBlTSfqM6WUhIAS0tL+enTJ0ayyclJVldXEwA1TVuufEBhO+PEviQCFPiioiJOTEyQJOfm5mgYhn3N"
    "z8/bRBw7dizke2lBgKZp7OrqIskQsE4zDIOWZXFycpL5+fkUQlAIkRJgCbS1gACZCqe3bds27NmzB6ZpQtf1RX2Ex+NBZWUl"
    "SELTtCVFG13XIYQIiTiJtrlkAgCgvLz8/6kWYyeSJFFWVhb3/dHAk4RhGCAJr9cLr9cLkjBNE0KInyuEcnNz4wKjNEFBQUHS"
    "BCjwLpcLtbW16O7uxrt37/D27Vv09PSgqqoqRH/80CigvPmhQ4fsdb6YKf/Q0NBAANR1Pam1npOTwydPnkR9zrVr12z/FOYb"
    "UusEVeOrV6/m58+fSZKWZUXtmGmaJEmfz5dUONQ0jUII3r59myQZCARomiYty6JlWTQMg4FAgCTZ1NQU6Rk/Lgw+ePCAhmFw"
    "dnbWBhoeBUiyo6ODQoiEw6AC4vP5Fo02iojZ2VkWFBSEDFTKo4DTEebk5EDTNLjdbkgpQdLW/6Zp2nlAc3OzvUYTXfsAsH//"
    "/kV9h7rP7XbD5/OF9HFJTlCFHU3ToOs6dF1HVlYWDMPAwYMHsWPHDrS1taGxsREDAwMQQkBKCSklNE2Dy+WCaZqYnp5esuRe"
    "jDwVEgGgpKQkhJSkcwFn2Ak3v9+P+vp6+P1+dHV1AQDq6+tRUlKC7OxsAMCGDRtQU1ODXbt2xRyRWP2IlmgBgGVZkFJiZGQE"
    "3759w9DQUMxoo8cLfuXKlaiursbevXsxOjqK8fFxbNy4EUeOHMHu3bvx7NkzuFwum6jnz5+HtNPS0oKbN2/i5MmT6OrqQlZW"
    "1oJpq0YvWtpMEh6PJ+pnADAzM4MrV67gxIkTePz4sU1MUmFQhZ28vDz29vZGdDp3794lALpcrpDooGmafanPpJT8+PEjT58+"
    "HTO6OL23lJK6rlNKyf7+fju/mJ+ftyW2eu/UqVN89eoVGxsb44oCejyj39raip07dyIQCEDXdXuUdV1Hb2+vfZ9zNJwpr5LI"
    "hmHg1q1baG5uxtatW9HW1gbDMLB+/XoUFhbi9evXGBwcxMDAgP19ZzGlrq4OW7ZsieobAODSpUu4c+cOzpw5E3fqHXEGqDBV"
    "WFjI2dlZm+nwsNbe3h5XTFcjeP78+Yhh0imWHj58yIqKCrsP69at49mzZzk1NcWLFy/ywIED3LdvH+vq6tjT08OJiQl++fKF"
    "nZ2drKmpWSxBil8HKEB+v5+WZS3otCKku7s7rvRWqb4LFy6QJL9//07DMGiapj19w5VkX18fu7u7+fXrV5qmydLS0ohte71e"
    "ejyeBQJtSemwYtDj8XBsbMzurLK5uTlalsXW1taYM0AJn7y8PPb390ckNFzIhCvKc+fOEQDdbrftW3RdDwGrUvOU1QNUYw0N"
    "DbaUVSOmbPv27TFngGrnxo0bceUMzllmGAanpqa4Zs0aSikjPmcp9YCYUlg9tKmpydbZJPn+/XsePnw4Jnj12ebNm22ZvFi+"
    "ED4bSHJ8fJzZ2dmxpndSBMTUASqG1tbW4urVq1i7di1M08SLFy8wMzNjF0ViFU0qKyvhdrvt6BH3di4Jt9sNr9eL6enpBRHn"
    "p1WFpZQYHBzE4OBgQmVu1dny8vKEcwAVAlesWIFNmzbhw4cPCecQKSNAyUzVAZXkxDOCAOD1ehPuvHNm/ahSup5shxK1QCCQ"
    "VKap5LHL5fo99wZV4vP06dO4y2CK6OPHj+Py5csQQmBkZGRJdcRlI0B1+P79+zFTUzXVpZRoaWnB9evX4fV6MTw8jKGhoZgO"
    "d9l2huKpGgkhYu4dOMtmZWVlLCoqIklWVVWlakcp9SWxRAhw7h4tVtKyLIv9/f0kyc7OzqRKaL8UAeH7h4oE0zTtHCBSPtDT"
    "08Pc3NxU7iItHwHOKVxcXMxHjx5FXQZjY2NsaGiwE6hUbaElpQRTacrBvXz5EhUVFfD5fPD7/SguLsaqVavw5s0b9PX14d69"
    "exgbGwupSfzS2+PJ+oR49gB+9O7wT50B4XFeVXiV2FGawTTNn/YjimUhIJq8XY7fEGV+JpchIENAhoAMAWGHCdLdGI2Aj3/A"
    "oQmFbzTSm3/koSkd/x6SGgdwFul/bO5sEKt9bC5zcDJzdBaZw9N/7PH5/wGI/Nm71KutNQAAAABJRU5ErkJggg=="
)



def migrate_legacy_config():
    """把以前放在 exe 旁边的 printers.json 搬到用户目录（原文件改名留档）。"""
    if DATA_DIR == APP_DIR:
        return False
    if os.path.exists(CONFIG_PATH) or not os.path.exists(CONFIG_PATH_LEGACY):
        return False
    try:
        shutil.copyfile(CONFIG_PATH_LEGACY, CONFIG_PATH)
        os.replace(CONFIG_PATH_LEGACY, CONFIG_PATH_LEGACY + ".migrated")
        return True
    except Exception:
        return False

DEFAULT_CONFIG = {
    "printers": [
        {"name": "Whale3 Pro (192.168.1.61)", "ip": "192.168.1.61", "port": 8081},
    ],
    "last": "192.168.1.61",
}


def load_config():
    """读取配置。解析失败时只备份坏文件、返回默认值，绝不覆盖用户原有内容。"""
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("printers"):
            return cfg
    except Exception:
        try:
            shutil.copyfile(CONFIG_PATH, CONFIG_PATH + ".bad")
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


_cfg_lock = threading.Lock()


def save_config(cfg):
    """原子写入，避免写入过程中的半截文件被另一个实例读到。"""
    with _cfg_lock:
        try:
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except Exception:
            pass


class PrinterError(Exception):
    pass


def ensure_winsock():
    """重新初始化 Winsock。

    实测：本机打开 Windows 原生文件对话框（GetOpenFileName）之后，进程的
    Winsock 会处于未初始化状态，后续 getaddrinfo 一律报
    [Errno 10093] WSAENOTINITIALISED，HTTP 请求全部失败。
    重新调用一次 WSAStartup 即可恢复。NovaMaker 上传后卡死也是同一个原因，
    只是它不会自愈。
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        buf = ctypes.create_string_buffer(408)
        ctypes.windll.ws2_32.WSAStartup(0x0202, ctypes.byref(buf))
    except Exception:
        pass


def _needs_winsock_reset(exc):
    return getattr(exc, "errno", None) == 10093


def _retry_net(fn, attempts=3):
    """网络调用失败且原因是 Winsock 被弄坏时，修复后重试。"""
    for i in range(attempts):
        try:
            return fn()
        except OSError as exc:
            if i + 1 < attempts and _needs_winsock_reset(exc):
                ensure_winsock()
                continue
            raise



class Printer:
    """单台打印机的 HTTP 客户端。请求串行化，避免把打印机那个很弱的 web 服务打爆。"""

    def __init__(self, ip, port=DEFAULT_PORT, lift_scale=1.0):
        self.ip = ip
        self.port = port
        # 抬升参数换算系数。实测 Nova 机器的 move 参数即毫米，保持 1.0；
        # 仅当某机型实测偏差明显时才需要校正（系数 = 实测毫米 / 请求值）。
        try:
            self.lift_scale = float(lift_scale)
        except (TypeError, ValueError):
            self.lift_scale = 1.0
        self.lock = threading.Lock()

    def _conn(self, timeout):
        return http.client.HTTPConnection(self.ip, self.port, timeout=timeout)

    def get(self, path, timeout=10):
        try:
            return _retry_net(lambda: self._get_once(path, timeout))
        except OSError as exc:
            raise PrinterError(f"连接打印机失败: {exc}") from exc

    def _get_once(self, path, timeout):
        with self.lock:
            conn = self._conn(timeout)
            try:
                conn.request("GET", path)
                resp = conn.getresponse()
                return resp.status, resp.read()
            finally:
                conn.close()

    def get_text(self, path, timeout=10):
        status, data = self.get(path, timeout)
        if status != 200:
            raise PrinterError(f"HTTP {status}")
        return data.decode("utf-8", "replace").strip()

    def get_json(self, path, timeout=10):
        text = self.get_text(path, timeout)
        try:
            return json.loads(text)
        except ValueError as exc:
            raise PrinterError(f"返回内容无法解析: {text[:80]}") from exc

    def model(self):
        return self.get_text("/setting/model")

    def sn(self):
        return self.get_text("/setting/snsid")

    def files(self):
        return self.get_json("/file/list")

    def jobs(self):
        return self.get_json("/job/list")

    def delete_file(self, name):
        return self.get_text("/file/delete/" + quote(name, safe=""), timeout=20)

    # ---- 打印控制（会真实作用于打印机）----
    def job_toggle(self, job_id):
        """暂停 / 继续当前任务。"""
        return self.get_text("/job/toggle/" + quote(job_id, safe=""), timeout=15)

    def job_stop(self, job_id):
        """停止当前任务（不可恢复）。"""
        return self.get_text("/job/stop/" + quote(job_id, safe=""), timeout=15)

    def file_print(self, name):
        """对打印机上的某个文件开始打印。"""
        return self.get_text("/file/print/" + quote(name, safe=""), timeout=20)

    def wifi_info(self):
        return self.get_json("/setting/wifiInfo", timeout=10)

    def wifi_list(self):
        return self.get_json("/setting/wifiList", timeout=25)

    def eth0_info(self):
        return self.get_json("/setting/eth0Info", timeout=10)

    def wifi_connect(self, ssid, password, security):
        """让打印机连接指定 WiFi。参数顺序取自固件：ssid / 密码 / security。"""
        return self.get_text("/setting/connectWifi/%s/%s/%d" % (
            quote(ssid, safe=""), quote(password or "", safe=""), int(security)),
            timeout=60)

    def printer_home(self):
        """Z 轴归位。真机执行较慢，回复可能很晚甚至不回。"""
        return self.get_text("/printer/home", timeout=45)

    def lift_raw(self, distance_mm):
        """把毫米换算成这台机器实际接受的参数值。"""
        return float(distance_mm) * self.lift_scale

    def printer_move(self, distance_mm):
        """Z 轴移动，正数上升、负数下降。"""
        # 固定小数位再裁掉尾零，避免 %g 把 0.00001 写成 1e-05 让固件解析失败
        val = ("%.5f" % self.lift_raw(distance_mm)).rstrip("0").rstrip(".")
        if val in ("", "-"):
            val = "0"
        return self.get_text("/printer/move/" + quote(val, safe=""), timeout=45)

    def upload(self, filepath, remote_name, on_progress):
        """原始字节 POST，已实测打印机按字节原样存储。"""
        try:
            return _retry_net(
                lambda: self._upload_once(filepath, remote_name, on_progress))
        except OSError as exc:
            raise PrinterError(f"上传中断: {exc}") from exc

    def _upload_once(self, filepath, remote_name, on_progress):
        size = os.path.getsize(filepath)
        with self.lock:
            conn = self._conn(30)
            try:
                conn.putrequest("POST", "/file/upload/" + quote(remote_name, safe=""))
                conn.putheader("Content-Type", "application/octet-stream")
                conn.putheader("Content-Length", str(size))
                conn.endheaders()
                sent = 0
                with open(filepath, "rb") as f:
                    while True:
                        buf = f.read(CHUNK)
                        if not buf:
                            break
                        conn.send(buf)
                        sent += len(buf)
                        on_progress(sent, size)
                resp = conn.getresponse()
                body = resp.read().decode("utf-8", "replace")
                return resp.status, body
            finally:
                conn.close()


def human_size(num):
    try:
        num = float(num)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return "-"


def parse_modified(text):
    """把 '2026-11-26 18:39 下午 GMT+00:00' 解析成可排序的元组。

    打印机给的时间本身已是 24 小时制，后面的「上午/下午」只是冗余标记，
    不能据此做 12 小时制换算，否则 18:39 会被算成 30 点。
    """
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})", str(text))
    if not m:
        return (0, 0, 0, 0, 0)
    return tuple(int(x) for x in m.groups())


def fmt_params(thickness, layer_ms, bottom_ms, bottom_num, lift_d, lift_s, cur_ms,
               cur_slice=0):
    """拼一行打印参数摘要；没有数据时返回空串。"""
    parts = []
    try:
        if thickness:
            parts.append("层高 %gmm" % float(thickness))
        bottoming = bottom_num and cur_slice and cur_slice <= bottom_num
        exp_ms = bottom_ms if (bottoming and bottom_ms) else layer_ms
        if exp_ms:
            parts.append("当前曝光 %.1fs%s" % (float(exp_ms) / 1000.0,
                                            "（底层）" if bottoming else ""))
        if lift_d and lift_s:
            parts.append("抬升 %gmm @ %gmm/min" % (float(lift_d), float(lift_s)))
        elif lift_d:
            parts.append("抬升 %gmm" % float(lift_d))
        if cur_ms:
            parts.append("当前层耗时 %.1fs" % (float(cur_ms) / 1000.0))
    except (TypeError, ValueError):
        pass
    return "  ·  ".join(parts)


def fmt_ts(ms):
    """毫秒时间戳 → 本地时间字符串；0 或非法值返回空串。"""
    try:
        ms = int(ms)
    except (TypeError, ValueError):
        return ""
    if ms <= 0:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ms / 1000.0))
    except (ValueError, OSError):
        return ""


def load_history():
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {str(x["id"]): x for x in data if isinstance(x, dict) and x.get("id")}
    except Exception:
        pass
    return {}


def save_history(records):
    with _cfg_lock:
        try:
            tmp = HISTORY_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(list(records.values()), f, ensure_ascii=False, indent=1)
            os.replace(tmp, HISTORY_PATH)
        except Exception:
            pass


def fmt_duration(seconds):
    seconds = int(max(0, seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}小时{minutes:02d}分"
    if minutes:
        return f"{minutes}分{secs:02d}秒"
    return f"{secs}秒"


# ==================== 界面主题 ====================
# 配色取自 NovaMaker 原版界面截图的实际采样值
THEME = {
    "bg":        "#323232",   # 页面底色
    "card":      "#464646",   # 卡片正文
    "header":    "#5F5F5F",   # 卡片标题栏
    "btn":       "#5F5F5F",   # 按钮
    "btn_hover": "#6E6E6E",
    "btn_down":  "#4A4A4A",
    "row":       "#3D3D3D",   # 未选中的列表行
    "trough":    "#323232",   # 进度条槽
    "accent":    "#0097E0",   # 强调蓝（选中项 / 进度条）
    "accent_hi": "#2AAEEC",
    "text":      "#E8E8E8",
    "text_dim":  "#A4A4A4",
    "ok":        "#3FBF6F",
    "warn":      "#E0A33C",
    "err":       "#E06C6C",
}

FONT = "Microsoft YaHei UI"


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """在 Canvas 上画圆角矩形（用平滑多边形模拟）。"""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class RoundButton(tk.Canvas):
    """圆角扁平按钮，宽度可跟随父容器拉伸。"""

    def __init__(self, master, text="", command=None, width=None, height=34,
                 fill=None, fg=None, hover=None, radius=6, font_size=10,
                 bold=False, s=1.0, padx=10):
        bg = master.cget("bg")
        if width:
            w = int(width * s)
        else:
            # 按文字实际宽度自适应，避免长文案被挤扁
            try:
                f = tkfont.Font(family=FONT, size=font_size,
                                weight="bold" if bold else "normal")
                w = f.measure(text) + int((padx * 2 + 6) * s)
            except Exception:
                w = int(90 * s)
        super().__init__(master, height=int(height * s), width=max(int(48 * s), w),
                         bg=bg, highlightthickness=0, bd=0, takefocus=0)
        self.s = s
        self._text = text
        self._cmd = command
        self._fill = fill or THEME["btn"]
        self._hover = hover or THEME["btn_hover"]
        self._fg = fg or THEME["text"]
        self._radius = radius
        self._fs = font_size
        self._bold = bold
        self._enabled = True
        self._inside = False
        self._padx = padx
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.configure(cursor="hand2")

    def _color(self):
        if not self._enabled:
            # 必须和卡片底色 #464646 拉开差距，否则禁用按钮会“消失”
            return "#3A3A3A", "#787878"
        if self._inside:
            return self._hover, self._fg
        return self._fill, self._fg

    def _redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        fill, fg = self._color()
        round_rect(self, 1, 1, w - 1, h - 1, self._radius * self.s, fill=fill, outline="")
        self.create_text(w / 2, h / 2, text=self._text, fill=fg,
                         font=(FONT, self._fs, "bold" if self._bold else "normal"))

    def _on_enter(self, _e):
        self._inside = True
        self._redraw()

    def _on_leave(self, _e):
        self._inside = False
        self._redraw()

    def _on_press(self, _e):
        if not self._enabled:
            return
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        round_rect(self, 1, 1, w - 1, h - 1, self._radius * self.s,
                   fill=THEME["btn_down"], outline="")
        self.create_text(w / 2, h / 2, text=self._text, fill=self._fg,
                         font=(FONT, self._fs, "bold" if self._bold else "normal"))

    def _on_release(self, _e):
        if not self._enabled:
            return
        self._redraw()
        if self._cmd and self._inside:
            self._cmd()

    def set_enabled(self, flag):
        self._enabled = bool(flag)
        self.configure(cursor="hand2" if flag else "arrow")
        self._redraw()

    def _auto_width(self, text):
        try:
            f = tkfont.Font(family=FONT, size=self._fs,
                            weight="bold" if self._bold else "normal")
            return max(int(48 * self.s), f.measure(text) + int((self._padx * 2 + 6) * self.s))
        except Exception:
            return int(90 * self.s)

    def set_text(self, text, width=None):
        self._text = text
        self.configure(width=int(width * self.s) if width else self._auto_width(text))
        self._redraw()


class Pill(tk.Canvas):
    """圆角胶囊标签，用于状态徽章。"""

    def __init__(self, master, text="", s=1.0, fill=None, fg="#FFFFFF",
                 height=22, font_size=9):
        bg = master.cget("bg")
        self.s = s
        self._text = text
        self._fill = fill or THEME["accent"]
        self._fg = fg
        self._fs = font_size
        super().__init__(master, height=int(height * s), width=self._measure(text),
                         bg=bg, highlightthickness=0, bd=0)
        self.bind("<Configure>", lambda e: self._redraw())
        self._redraw()

    def _measure(self, text):
        try:
            f = tkfont.Font(family=FONT, size=self._fs)
            return max(int(54 * self.s), f.measure(text) + int(24 * self.s))
        except Exception:
            return int(64 * self.s)

    def set(self, text, fill=None):
        self._text = text
        if fill:
            self._fill = fill
        self.configure(width=self._measure(text))
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        round_rect(self, 0, 0, w, h, h / 2.0, fill=self._fill, outline="")
        self.create_text(w / 2, h / 2, text=self._text, fill=self._fg,
                         font=(FONT, self._fs))


class BlueBar(tk.Canvas):
    """胶囊形蓝色进度条，末端带一个白色旋钮（和 NovaMaker 一致）。"""

    def __init__(self, master, height=16, s=1.0):
        bg = master.cget("bg")
        # 初始宽度给小值，靠 fill="x" 撑开；否则 Canvas 默认宽度会把整列撑宽
        super().__init__(master, height=int(height * s), width=int(40 * s),
                         bg=bg, highlightthickness=0, bd=0)
        self.s = s
        self.pct = 0.0
        self.bind("<Configure>", lambda e: self._redraw())

    def set(self, pct):
        try:
            self.pct = max(0.0, min(100.0, float(pct)))
        except (TypeError, ValueError):
            self.pct = 0.0
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 4 or h <= 4:
            return
        r = h / 2.0
        round_rect(self, 0, 0, w, h, r, fill=THEME["trough"], outline="")
        fill_w = w * self.pct / 100.0
        if fill_w >= h:
            round_rect(self, 0, 0, fill_w, h, r, fill=THEME["accent"], outline="")
        elif fill_w > 0:
            self.create_oval(0, 0, h, h, fill=THEME["accent"], outline="")
        if self.pct > 0:
            cx = min(max(fill_w, r), w - r)
            kr = max(2.0, r - 2 * self.s)
            self.create_oval(cx - kr, r - kr, cx + kr, r + kr,
                             fill="#FFFFFF", outline=THEME["accent"], width=max(1, int(2 * self.s)))


class SlimScrollbar(tk.Canvas):
    """极简滚动条：无箭头、无边框、圆角滑块，内容放得下时自动隐藏。"""

    def __init__(self, master, target, s=1.0, thickness=9):
        bg = master.cget("bg")
        super().__init__(master, width=int(thickness * s), bg=bg,
                         highlightthickness=0, bd=0, takefocus=0)
        self.target = target
        self.s = s
        self.first = 0.0
        self.last = 1.0
        self._hover = False
        self._drag = None
        self._thumb = (0.0, 0.0)
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set(self, first, last):
        self.first = float(first)
        self.last = float(last)
        self._redraw()

    def _set_hover(self, flag):
        self._hover = flag
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        span = self.last - self.first
        if span >= 0.998:          # 内容一屏放得下，不画
            self._thumb = (0.0, 0.0)
            return
        top = self.first * h
        bot = self.last * h
        min_h = min(float(h), 30.0 * self.s)
        if bot - top < min_h:
            mid = (top + bot) / 2.0
            top = max(0.0, mid - min_h / 2.0)
            bot = min(float(h), top + min_h)
            top = max(0.0, bot - min_h)
        self._thumb = (top, bot)
        pad = max(1.0, 2.0 * self.s)
        color = "#8E8E8E" if self._hover else "#6A6A6A"
        round_rect(self, pad, top, w - pad, bot, (w - 2 * pad) / 2.0,
                   fill=color, outline="")

    def _on_press(self, e):
        top, bot = self._thumb
        if top == bot:
            return
        if top <= e.y <= bot:
            self._drag = e.y - top
        else:
            self.target.yview_scroll(-1 if e.y < top else 1, "pages")

    def _on_drag(self, e):
        if self._drag is None:
            return
        h = self.winfo_height()
        if h <= 2:
            return
        span = self.last - self.first
        new_top = (e.y - self._drag) / h
        self.target.yview_moveto(max(0.0, min(1.0 - span, new_top)))

    def _on_release(self, _e):
        self._drag = None


class Card(tk.Frame):
    """带标题栏的卡片容器，标题栏颜色比正文略浅。"""

    def __init__(self, master, title="", s=1.0, header_height=34):
        super().__init__(master, bg=THEME["card"])
        self.s = s
        self.head = tk.Frame(self, bg=THEME["header"], height=int(header_height * s))
        self.head.pack(fill="x")
        self.head.pack_propagate(False)
        self.title_label = tk.Label(self.head, text=title, bg=THEME["header"],
                                    fg=THEME["text"], font=(FONT, 10), anchor="w")
        self.title_label.pack(side="left", padx=int(14 * s))
        self.body = tk.Frame(self, bg=THEME["card"])
        self.body.pack(fill="both", expand=True)


class PrinterRow(tk.Frame):
    """左侧打印机列表里的一行，选中时整行变强调蓝。"""

    def __init__(self, master, s, on_click):
        super().__init__(master, bg=THEME["row"], cursor="hand2")
        self.s = s
        self._on_click = on_click
        self._selected = False
        pad = int(10 * s)
        self.t1 = tk.Label(self, text="", bg=THEME["row"], fg=THEME["text"],
                           font=(FONT, 9), anchor="w")
        self.t1.pack(fill="x", padx=pad, pady=(int(8 * s), 0))
        self.t2 = tk.Label(self, text="", bg=THEME["row"], fg=THEME["text_dim"],
                           font=(FONT, 9), anchor="w")
        self.t2.pack(fill="x", padx=pad, pady=(0, int(8 * s)))
        for w in (self, self.t1, self.t2):
            w.bind("<Button-1>", self._click)

    def _click(self, _e):
        self._on_click(self)

    def update_text(self, line1, line2, selected):
        self._selected = selected
        bg = THEME["accent"] if selected else THEME["row"]
        fg1 = "#FFFFFF" if selected else THEME["text"]
        fg2 = "#E3F4FD" if selected else THEME["text_dim"]
        self.configure(bg=bg)
        self.t1.configure(text=line1, bg=bg, fg=fg1)
        self.t2.configure(text=line2, bg=bg, fg=fg2)


class Toast(tk.Toplevel):
    """右下角浮出通知，自动消失，点击立即关闭。"""

    def __init__(self, master, s, title, message, kind="ok"):
        super().__init__(master)
        self._parent = master
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        accent = {"ok": THEME["ok"], "warn": THEME["warn"],
                  "err": THEME["err"]}.get(kind, THEME["accent"])
        wrap = tk.Frame(self, bg=accent)
        wrap.pack(fill="both", expand=True)
        inner = tk.Frame(wrap, bg=THEME["card"])
        inner.pack(fill="both", expand=True, padx=(int(4 * s), 0))
        tk.Label(inner, text=title, bg=THEME["card"], fg=THEME["text"],
                 font=(FONT, 10, "bold"), anchor="w").pack(
            fill="x", padx=int(12 * s), pady=(int(10 * s), 0))
        tk.Label(inner, text=message, bg=THEME["card"], fg=THEME["text_dim"],
                 font=(FONT, 9), anchor="w", justify="left",
                 wraplength=int(280 * s)).pack(
            fill="x", padx=int(12 * s), pady=(int(4 * s), int(10 * s)))
        self.update_idletasks()
        w = max(self.winfo_reqwidth(), int(310 * s))
        h = max(self.winfo_reqheight(), int(80 * s))
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry("%dx%d+%d+%d" % (w, h, sw - w - int(26 * s), sh - h - int(80 * s)))
        for widget in (self, wrap, inner):
            widget.bind("<Button-1>", lambda _e: self._close())
        self.after(9000, self._close)

    def _close(self):
        try:
            self.destroy()
        except Exception:
            pass


def apply_window_icon(master):
    """设置标题栏与任务栏图标；数据内嵌，源码和 exe 都能用。"""
    try:
        img = tk.PhotoImage(data=ICON_PNG_B64)
        master.iconphoto(True, img)
        return img
    except Exception:
        return None


def apply_dark_titlebar(win):
    """把窗口的 Windows 标题栏切成深色。"""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        flag = ctypes.c_int(1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(flag), ctypes.sizeof(flag)) == 0:
                break
    except Exception:
        pass


class DarkDialog(tk.Toplevel):
    """深色对话框基类，风格与主界面一致。"""

    def __init__(self, master, title, s=None):
        super().__init__(master)
        self.s = s if s else getattr(master, "s", 1.0)
        self.result = False
        self.title(title)
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)
        try:
            self.transient(master.winfo_toplevel())
        except Exception:
            pass
        self.body = tk.Frame(self, bg=THEME["card"])
        self.body.pack(fill="both", expand=True, padx=int(10 * self.s),
                       pady=(int(10 * self.s), int(6 * self.s)))
        self.btnbar = tk.Frame(self, bg=THEME["bg"])
        self.btnbar.pack(fill="x", padx=int(10 * self.s), pady=(0, int(10 * self.s)))
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())

    def add_buttons(self, ok_text="确定", cancel_text="取消"):
        if cancel_text:
            RoundButton(self.btnbar, text=cancel_text, width=88, height=30, s=self.s,
                        command=self._on_cancel).pack(side="right",
                                                      padx=(int(6 * self.s), 0))
        RoundButton(self.btnbar, text=ok_text, width=88, height=30, s=self.s,
                    fill=THEME["accent"], hover=THEME["accent_hi"],
                    command=self._on_ok).pack(side="right")

    def _on_ok(self):
        self.result = True
        self.destroy()

    def _on_cancel(self):
        self.result = False
        self.destroy()

    def show(self):
        self.update_idletasks()
        w = max(self.winfo_reqwidth(), int(360 * self.s))
        h = self.winfo_reqheight()
        top = self.master.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - w) // 2
        y = top.winfo_rooty() + (top.winfo_height() - h) // 3
        self.geometry("%dx%d+%d+%d" % (w, h, max(0, x), max(0, y)))
        apply_dark_titlebar(self)
        try:
            self.grab_set()
        except Exception:
            pass
        self.wait_window(self)
        return self.result


def ask_dark(master, title, message, kind="info", ok_text="确定", cancel_text=None):
    """深色提示 / 确认框。kind: info / warn / error / ask"""
    color = {"warn": THEME["warn"], "error": THEME["err"]}.get(kind, THEME["text"])
    dlg = DarkDialog(master, title)
    tk.Label(dlg.body, text=message, bg=THEME["card"], fg=color, font=(FONT, 10),
             justify="left", anchor="w", wraplength=int(380 * dlg.s)).pack(
        fill="x", padx=int(4 * dlg.s), pady=int(6 * dlg.s))
    dlg.add_buttons(ok_text, cancel_text if cancel_text is not None
                    else ("取消" if kind == "ask" else None))
    return dlg.show()


class _DarkMessageBox:
    """替代 tkinter.messagebox，签名保持一致，配色跟随主题。"""

    @staticmethod
    def showinfo(title, message, parent=None, **_kw):
        return ask_dark(parent, title, message, "info")

    @staticmethod
    def showwarning(title, message, parent=None, **_kw):
        return ask_dark(parent, title, message, "warn")

    @staticmethod
    def showerror(title, message, parent=None, **_kw):
        return ask_dark(parent, title, message, "error")

    @staticmethod
    def askyesno(title, message, parent=None, **_kw):
        return ask_dark(parent, title, message, "ask")


messagebox = _DarkMessageBox()


class AddPrinterDialog(DarkDialog):
    """添加打印机：IP 与名称一次填完，校验失败就地提示。"""

    def __init__(self, master, s=None):
        super().__init__(master, "添加打印机", s=s)
        pad = int(6 * self.s)
        tk.Label(self.body, text="打印机 IP 地址", bg=THEME["card"],
                 fg=THEME["text_dim"], font=(FONT, 9), anchor="w").pack(
            fill="x", pady=(pad, int(2 * self.s)))
        self.ent_ip = self._entry()
        tk.Label(self.body, text="显示名称（留空则用 IP）", bg=THEME["card"],
                 fg=THEME["text_dim"], font=(FONT, 9), anchor="w").pack(
            fill="x", pady=(int(10 * self.s), int(2 * self.s)))
        self.ent_name = self._entry()
        self.lbl_err = tk.Label(self.body, text="", bg=THEME["card"], fg=THEME["err"],
                                font=(FONT, 9), anchor="w",
                                wraplength=int(360 * self.s))
        self.lbl_err.pack(fill="x", pady=(int(8 * self.s), 0))
        self.add_buttons("添加", "取消")
        self.ent_ip.focus_set()

    def _entry(self):
        e = tk.Entry(self.body, bg=THEME["row"], fg=THEME["text"], relief="flat",
                     insertbackground=THEME["text"], font=(FONT, 10), width=26)
        e.pack(fill="x", ipady=int(4 * self.s))
        return e

    def _on_ok(self):
        ip = self.ent_ip.get().strip()
        if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
            self.lbl_err.configure(text="IP 格式不对，应形如 192.168.1.61")
            return
        if any(int(x) > 255 for x in ip.split(".")):
            self.lbl_err.configure(text="IP 每段必须在 0-255 之间")
            return
        self.result = (ip, self.ent_name.get().strip() or ip)
        self.destroy()


STATUS_CN = {
    "Printing": "打印中", "Completed": "已完成", "Paused": "已暂停",
    "Cancelled": "已取消", "Stopped": "已停止", "Preparing": "准备中",
    "Idle": "空闲",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.s = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.title("NovaUploader — 打印机管理")
        self.configure(bg=THEME["bg"])
        self.geometry("%dx%d" % (int(1180 * self.s), int(760 * self.s)))
        self.minsize(int(1000 * self.s), int(660 * self.s))
        self._icon_img = apply_window_icon(self)

        self._migrated = migrate_legacy_config()
        self.cfg = load_config()
        self.events = queue.Queue()
        self.printer = None
        self.queue_files = []
        self.busy = False
        self.current_index = 0
        self._printing = False
        self._paused = False
        self._job_id = None
        self._wifi_map = {}
        self._wifi_sel = None
        self._gen = 0
        self._last_job_poll = 0.0
        self.log_lines = []
        self.log_win = None
        self.history = load_history()
        self.hist_win = None
        self._notify_on = bool(self.cfg.get("notify", True))
        self._active_job_id = None
        self.printer_rows = []

        self._build_ui()
        self._render_printers()
        last = self.cfg.get("last")
        idx = next((i for i, p in enumerate(self.cfg["printers"]) if p["ip"] == last), 0)
        self._select_index(idx, save=False)
        self.after(100, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.update_idletasks()
        self._dark_titlebar()
        self._log("工具已启动，数据目录：%s" % DATA_DIR)
        if self._migrated:
            self._log("已把 printers.json 从程序目录迁移到用户目录"
                      "（原文件改名为 printers.json.migrated）")

    def _dark_titlebar(self):
        apply_dark_titlebar(self)

    # ---------------- 界面骨架 ----------------
    def _build_ui(self):
        s = self.s
        style = ttk.Style(self)
        style.theme_use("clam")
        self.option_add("*TCombobox*Listbox.background", THEME["card"])
        self.option_add("*TCombobox*Listbox.foreground", THEME["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", THEME["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
        style.configure("Dark.Treeview", background=THEME["card"], fieldbackground=THEME["card"],
                        foreground=THEME["text"], borderwidth=0, relief="flat",
                        rowheight=int(26 * s), font=(FONT, 9))
        style.configure("Dark.Treeview.Heading", background=THEME["header"],
                        foreground=THEME["text_dim"], borderwidth=0, relief="flat",
                        font=(FONT, 9), padding=(int(6 * s), int(5 * s)))
        style.map("Dark.Treeview.Heading", background=[("active", THEME["header"])])
        style.map("Dark.Treeview",
                  background=[("selected", THEME["accent"])],
                  foreground=[("selected", "#FFFFFF")])
        style.layout("Dark.Treeview", [("Dark.Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Dark.TCombobox", fieldbackground=THEME["row"], background=THEME["btn"],
                        foreground=THEME["text"], arrowcolor=THEME["text_dim"],
                        bordercolor=THEME["card"], lightcolor=THEME["card"],
                        darkcolor=THEME["card"], selectbackground=THEME["row"],
                        selectforeground=THEME["text"], padding=(int(6 * s), int(3 * s)))
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", THEME["row"])],
                  foreground=[("readonly", THEME["text"])],
                  selectbackground=[("readonly", THEME["row"])],
                  selectforeground=[("readonly", THEME["text"])])

        # 底部状态条
        status = tk.Frame(self, bg=THEME["bg"], height=int(36 * s))
        status.pack(side="bottom", fill="x")
        status.pack_propagate(False)
        # 先摆按钮：按钮宽度固定，标签只占剩余空间，长文本不会再挤坏按钮
        RoundButton(status, text="日志", width=74, height=26, s=s,
                    command=self._show_log).pack(side="right", padx=int(12 * s), pady=int(5 * s))
        RoundButton(status, text="打印历史", width=90, height=26, s=s,
                    command=self._show_history).pack(side="right", padx=(0, int(6 * s)),
                                                     pady=int(5 * s))
        self.btn_notify = RoundButton(status, text="", width=82, height=26, s=s,
                                      command=self._toggle_notify)
        self.btn_notify.pack(side="right", padx=(0, int(6 * s)), pady=int(5 * s))
        self._sync_notify_btn()

        self.lbl_status = tk.Label(status, text="就绪", bg=THEME["bg"], fg=THEME["text_dim"],
                                   font=(FONT, 9), anchor="w")
        self.lbl_status.pack(side="left", fill="x", expand=True,
                             padx=(int(14 * s), int(6 * s)))

        body = tk.Frame(self, bg=THEME["bg"])
        body.pack(fill="both", expand=True, padx=int(12 * s), pady=(int(10 * s), 0))
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=3, uniform="main", minsize=int(260 * s))
        body.columnconfigure(2, weight=2, uniform="main", minsize=int(240 * s))
        body.rowconfigure(0, weight=0)
        body.rowconfigure(1, weight=0)
        body.rowconfigure(2, weight=1)

        # ---- 左栏：选择打印机 + 连接信息 ----
        side = tk.Frame(body, bg=THEME["bg"], width=int(272 * s))
        side.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(0, int(5 * s)))
        side.grid_propagate(False)

        card_p = Card(side, "选择打印机", s)
        card_p.pack(fill="x")
        RoundButton(card_p.head, text="⟳", width=28, height=22, s=s, font_size=10,
                    command=self._refresh_all).pack(side="right", padx=int(8 * s), pady=int(6 * s))

        self.rows_box = tk.Frame(card_p.body, bg=THEME["card"])
        self.rows_box.pack(fill="x", padx=int(8 * s), pady=int(8 * s))

        btns = tk.Frame(card_p.body, bg=THEME["card"])
        btns.pack(fill="x", padx=int(8 * s), pady=(0, int(8 * s)))
        RoundButton(btns, text="＋  添加", height=30, s=s,
                    command=self._add_printer).pack(side="left", fill="x", expand=True)
        RoundButton(btns, text="移除", width=60, height=30, s=s,
                    command=self._remove_printer).pack(side="left", padx=(int(6 * s), 0))

        card_net = Card(side, "网络设置", s)
        card_net.pack(side="bottom", fill="x", pady=(int(5 * s), 0))

        card_info = Card(side, "连接信息", s)
        card_info.pack(fill="both", expand=True, pady=(int(5 * s), 0))

        # ---- 顶部通栏：打印状态 ----
        card_job = Card(body, "打印状态", s)
        card_job.grid(row=0, column=1, columnspan=2, sticky="nsew", pady=(0, int(5 * s)))

        # ---- 右列上：打印控制 ----
        card_ctl = Card(body, "打印控制", s)
        card_ctl.grid(row=1, column=2, sticky="nsew", pady=(0, int(5 * s)))

        # ---- 左列：文件列表整列贯通 ----
        card_files = Card(body, "文件列表", s)
        card_files.grid(row=1, column=1, rowspan=2, sticky="nsew", padx=(0, int(5 * s)))

        # ---- 右列下：上传队列 ----
        card_up = Card(body, "上传队列", s)
        card_up.grid(row=2, column=2, sticky="nsew")

        self._build_job_card(card_job)
        self._build_network_card(card_net)
        self._build_control_card(card_ctl)
        self._build_files_card(card_files)
        self._build_upload_card(card_up)
        self._build_info_card(card_info)

    def _build_job_card(self, card):
        """横向通栏横幅：状态徽章 + 任务名 + 层数 / 进度条 / 已用·剩余。"""
        s = self.s
        top = tk.Frame(card.body, bg=THEME["card"])
        top.pack(fill="x", padx=int(18 * s), pady=(int(12 * s), 0))
        self.pill_state = Pill(top, "未连接", s=s, fill=THEME["text_dim"])
        self.pill_state.pack(side="left")
        self.lbl_job_name = tk.Label(top, text="—", bg=THEME["card"], fg=THEME["text"],
                                     font=(FONT, 11), anchor="w")
        self.lbl_job_name.pack(side="left", padx=int(12 * s), fill="x", expand=True)
        self.lbl_layers = tk.Label(top, text="", bg=THEME["card"], fg=THEME["text_dim"],
                                   font=(FONT, 10), anchor="e")
        self.lbl_layers.pack(side="right")

        mid = tk.Frame(card.body, bg=THEME["card"])
        mid.pack(fill="x", padx=int(18 * s), pady=(int(10 * s), int(6 * s)))
        self.bar_job = BlueBar(mid, height=14, s=s)
        self.bar_job.pack(fill="x")

        bot = tk.Frame(card.body, bg=THEME["card"])
        bot.pack(fill="x", padx=int(18 * s), pady=(0, int(2 * s)))
        self.lbl_elapsed = tk.Label(bot, text="", bg=THEME["card"], fg=THEME["text_dim"],
                                    font=(FONT, 9), anchor="w")
        self.lbl_elapsed.pack(side="left")
        self.lbl_remain_bar = tk.Label(bot, text="", bg=THEME["card"], fg=THEME["text_dim"],
                                       font=(FONT, 9), anchor="e")
        self.lbl_remain_bar.pack(side="right")
        self.lbl_pct = tk.Label(bot, text="", bg=THEME["card"], fg=THEME["accent"],
                                font=(FONT, 9, "bold"))
        self.lbl_pct.pack(side="right", padx=int(14 * s))

        self.lbl_params = tk.Label(card.body, text="", bg=THEME["card"],
                                   fg=THEME["text_dim"], font=(FONT, 8), anchor="w")
        self.lbl_params.pack(fill="x", padx=int(18 * s), pady=(0, int(10 * s)))

    def _build_network_card(self, card):
        """网络设置：查看当前 WiFi / 扫描 / 连接，以及有线网卡状态。"""
        s = self.s
        pad = int(8 * s)
        body = card.body

        row0 = tk.Frame(body, bg=THEME["card"])
        row0.pack(fill="x", padx=pad, pady=(int(8 * s), 0))
        tk.Label(row0, text="WIFI", bg=THEME["card"], fg=THEME["text_dim"],
                 font=(FONT, 9), width=5, anchor="w").pack(side="left")
        self.lbl_wifi_cur = tk.Label(row0, text="—", bg=THEME["card"], fg=THEME["text"],
                                     font=(FONT, 9), anchor="w")
        self.lbl_wifi_cur.pack(side="left", fill="x", expand=True)

        row1 = tk.Frame(body, bg=THEME["card"])
        row1.pack(fill="x", padx=pad, pady=(int(6 * s), 0))
        self.btn_wifi = tk.Menubutton(
            row1, text="点“扫描”获取列表 ▾", bg=THEME["row"], fg=THEME["text"],
            activebackground=THEME["btn"], activeforeground=THEME["text"],
            relief="flat", anchor="w", font=(FONT, 9), cursor="hand2",
            padx=int(7 * s), pady=int(3 * s))
        self.menu_wifi = tk.Menu(self.btn_wifi, tearoff=0, bg=THEME["card"],
                                 fg=THEME["text"], activebackground=THEME["accent"],
                                 activeforeground="#FFFFFF", font=(FONT, 9), bd=0)
        self.btn_wifi.configure(menu=self.menu_wifi)
        self.btn_wifi.pack(side="left", fill="x", expand=True)
        RoundButton(row1, text="扫描", width=52, height=26, s=s, font_size=9,
                    command=self._scan_wifi).pack(side="left", padx=(int(6 * s), 0))

        row2 = tk.Frame(body, bg=THEME["card"])
        row2.pack(fill="x", padx=pad, pady=(int(6 * s), 0))
        self.ent_pwd = tk.Entry(row2, show="*", bg=THEME["row"], fg=THEME["text"],
                                insertbackground=THEME["text"], relief="flat",
                                font=(FONT, 9), width=8)
        self.ent_pwd.pack(side="left", fill="x", expand=True, ipady=int(4 * s))
        self.btn_wifi_connect = RoundButton(row2, text="连接", width=52, height=26, s=s,
                                            font_size=9, fill=THEME["accent"],
                                            hover=THEME["accent_hi"],
                                            command=self._connect_wifi)
        self.btn_wifi_connect.pack(side="left", padx=(int(6 * s), 0))

        row3 = tk.Frame(body, bg=THEME["card"])
        row3.pack(fill="x", padx=pad, pady=(int(6 * s), int(8 * s)))
        tk.Label(row3, text="网线", bg=THEME["card"], fg=THEME["text_dim"],
                 font=(FONT, 9), width=5, anchor="w").pack(side="left")
        self.lbl_eth = tk.Label(row3, text="—", bg=THEME["card"], fg=THEME["text_dim"],
                                font=(FONT, 9), anchor="w")
        self.lbl_eth.pack(side="left", fill="x", expand=True)

    def _build_control_card(self, card):
        """打印控制：暂停/停止一行，Z 轴 4x2 网格，归位单独一行。"""
        s = self.s
        body = card.body
        pad = int(10 * s)

        row0 = tk.Frame(body, bg=THEME["card"])
        row0.pack(fill="x", padx=pad, pady=(int(9 * s), 0))
        row0.columnconfigure(0, weight=1, uniform="act")
        row0.columnconfigure(1, weight=1, uniform="act")
        self.btn_pause = RoundButton(row0, text="⏸  暂停", height=30, s=s,
                                     command=self._toggle_pause)
        self.btn_pause.grid(row=0, column=0, sticky="ew", padx=(0, int(4 * s)))
        self.btn_stop = RoundButton(row0, text="■  停止打印", height=30, s=s,
                                    command=self._stop_print)
        self.btn_stop.grid(row=0, column=1, sticky="ew", padx=(int(4 * s), 0))

        rowz = tk.Frame(body, bg=THEME["card"])
        rowz.pack(fill="x", padx=pad, pady=(int(10 * s), int(4 * s)))
        tk.Label(rowz, text="Z 轴", bg=THEME["card"], fg=THEME["text_dim"],
                 font=(FONT, 9), anchor="w").pack(side="left")
        self.lbl_ctl_hint = tk.Label(rowz, text="", bg=THEME["card"], fg=THEME["warn"],
                                     font=(FONT, 8), anchor="e")
        self.lbl_ctl_hint.pack(side="right")

        grid = tk.Frame(body, bg=THEME["card"])
        grid.pack(fill="x", padx=pad)
        for c in range(4):
            grid.columnconfigure(c, weight=1, uniform="z")
        self.z_buttons = []
        for r, (sign, sym) in enumerate(((1, "↑"), (-1, "↓"))):
            for c, d in enumerate(("0.05", "1", "10", "50")):
                bt = RoundButton(grid, text=sym + d, height=28, s=s, font_size=9, padx=6,
                                 command=lambda dd=d, sg=sign: self._move_z(sg * float(dd)))
                bt.grid(row=r, column=c, sticky="ew",
                        padx=(int(2 * s), int(2 * s)), pady=(0, int(4 * s)))
                self.z_buttons.append(bt)

        self.btn_home = RoundButton(body, text="归位", height=30, s=s, font_size=9,
                                    command=self._printer_home)
        self.btn_home.pack(fill="x", padx=pad, pady=(int(2 * s), int(9 * s)))

    def _build_files_card(self, card):
        s = self.s
        self.tree_files = self._make_tree(
            card.body, (("name", "名称", 210, True), ("size", "大小", 76, False),
                        ("date", "修改时间", 120, False)))
        bar = tk.Frame(card.body, bg=THEME["card"])
        bar.pack(side="bottom", fill="x", padx=int(10 * s), pady=(0, int(10 * s)))
        RoundButton(bar, text="删除选中", width=104, height=32, s=s,
                    command=self._delete_selected).pack(side="left")
        RoundButton(bar, text="刷新", width=78, height=32, s=s,
                    command=self._refresh_files).pack(side="left", padx=int(8 * s))
        RoundButton(bar, text="开始打印", width=96, height=32, s=s,
                    fill=THEME["accent"], hover=THEME["accent_hi"],
                    command=self._start_print).pack(side="right")

    def _build_upload_card(self, card):
        s = self.s
        self.lbl_pb = tk.Label(card.body, text="就绪", bg=THEME["card"], fg=THEME["text_dim"],
                               font=(FONT, 8), anchor="w")
        self.lbl_pb.pack(side="bottom", fill="x", padx=int(12 * s), pady=(0, int(8 * s)))

        prog = tk.Frame(card.body, bg=THEME["card"])
        prog.pack(side="bottom", fill="x", padx=int(10 * s), pady=(0, int(4 * s)))
        self.bar_up = BlueBar(prog, height=12, s=s)
        self.bar_up.pack(fill="x")

        bar = tk.Frame(card.body, bg=THEME["card"])
        bar.pack(side="bottom", fill="x", padx=int(10 * s), pady=(0, int(8 * s)))
        RoundButton(bar, text="选择 .cws 文件", height=32, s=s,
                    command=self._pick_files).pack(side="left")
        self.btn_upload = RoundButton(bar, text="开始上传", width=90, height=32, s=s,
                                      fill=THEME["accent"], hover=THEME["accent_hi"],
                                      command=self._start_upload)
        self.btn_upload.pack(side="left", padx=int(8 * s))
        RoundButton(bar, text="清空", width=64, height=32, s=s,
                    command=self._clear_queue).pack(side="left")

        self.tree_queue = self._make_tree(
            card.body, (("file", "文件", 140, True), ("size", "大小", 62, False),
                        ("state", "状态", 100, False)), height=4)

    def _build_info_card(self, card):
        """两列 grid：左列标签按实际文字宽度，右列数值，避免固定 width 把冒号截掉。"""
        s = self.s
        box = tk.Frame(card.body, bg=THEME["card"])
        box.pack(fill="both", expand=True, padx=int(12 * s), pady=int(12 * s))
        box.columnconfigure(1, weight=1)

        self.info_val = {}
        rows = (("model", "机器型号"), ("sn", "序列号"), ("ip", "IP 地址"),
                ("port", "端口"), ("lift", "Z 轴系数"), ("state", "连接状态"))
        for r, (key, title) in enumerate(rows):
            tk.Label(box, text=title + "：", bg=THEME["card"], fg=THEME["text_dim"],
                     font=(FONT, 9), anchor="w").grid(
                row=r, column=0, sticky="w", pady=int(4 * s))
            val = tk.Label(box, text="—", bg=THEME["card"], fg=THEME["text"],
                           font=(FONT, 9), anchor="w")
            val.grid(row=r, column=1, sticky="w", padx=(int(10 * s), 0),
                     pady=int(4 * s))
            self.info_val[key] = val

    def _make_tree(self, parent, cols, height=7):
        s = self.s
        wrap = tk.Frame(parent, bg=THEME["card"])
        wrap.pack(fill="both", expand=True, padx=int(10 * s), pady=(int(10 * s), int(6 * s)))
        tree = ttk.Treeview(wrap, columns=[c[0] for c in cols], show="headings",
                            style="Dark.Treeview", height=height)
        for key, title, width, stretch in cols:
            tree.heading(key, text=title)
            tree.column(key, width=int(width * s), stretch=stretch,
                        anchor="w" if key in ("name", "date", "file", "state") else "e")
        tree.pack(side="left", fill="both", expand=True)
        sb = SlimScrollbar(wrap, tree, s=s)
        sb.pack(side="left", fill="y", padx=(int(2 * s), 0))
        tree.configure(yscrollcommand=sb.set)
        return tree

    # ---------------- 打印机列表 ----------------
    def _render_printers(self):
        for row in self.printer_rows:
            row.destroy()
        self.printer_rows = []
        for i, entry in enumerate(self.cfg["printers"]):
            row = PrinterRow(self.rows_box, self.s, lambda r, idx=i: self._select_index(idx))
            row.pack(fill="x", pady=(0, int(6 * self.s)))
            model = entry.get("model") or entry.get("name") or ""
            row.update_text("机器型号：" + model,
                            "IP 地址：" + entry["ip"], i == self.current_index)
            self.printer_rows.append(row)

    def _select_index(self, idx, save=True):
        if idx < 0 or idx >= len(self.cfg["printers"]):
            idx = 0
        self.current_index = idx
        for i, row in enumerate(self.printer_rows):
            entry = self.cfg["printers"][i]
            model = entry.get("model") or entry.get("name") or ""
            row.update_text("机器型号：" + model, "IP 地址：" + entry["ip"], i == idx)
        if save:
            self.cfg["last"] = self.cfg["printers"][idx]["ip"]
            save_config(self.cfg)
        self._on_printer_change()

    def _render_info(self, model=None, sn=None):
        entry = self.cfg["printers"][self.current_index]
        self.info_val["model"].configure(text=model or "—")
        self.info_val["sn"].configure(text=sn or "—")
        self.info_val["ip"].configure(text=entry["ip"])
        self.info_val["port"].configure(text=str(entry.get("port", DEFAULT_PORT)))
        scale = float(entry.get("lift_scale", 1.0))
        self.info_val["lift"].configure(
            text="%g（默认）" % scale if scale == 1.0 else "%g（已校准）" % scale)

    def _set_conn(self, text, color):
        self.info_val["state"].configure(text=text, fg=color)

    # ---------------- 事件派发 ----------------
    def _on_printer_change(self):
        self._gen += 1
        gen = self._gen
        entry = self.cfg["printers"][self.current_index]
        self.printer = Printer(entry["ip"], entry.get("port", DEFAULT_PORT),
                               entry.get("lift_scale", 1.0))
        self._render_info()
        self._set_conn("连接中…", THEME["warn"])
        self._active_job_id = None
        self.tree_files.delete(*self.tree_files.get_children())
        self._apply_job(None)
        threading.Thread(target=self._probe_worker, args=(gen,), daemon=True).start()

    def _probe_worker(self, gen):
        p = self.printer
        try:
            model = p.model()
            sn = p.sn()
        except Exception as exc:
            if gen == self._gen:
                self.events.put(("conn", ("连接失败", THEME["err"])))
                self.events.put(("log", "连接 %s 失败：%s" % (p.ip, exc)))
            return
        if gen != self._gen:
            return
        entry = self.cfg["printers"][self.current_index]
        entry["model"] = model
        entry["sn"] = sn
        save_config(self.cfg)
        self.events.put(("conn", ("已连接", THEME["ok"])))
        self.events.put(("printer_info", (model, sn)))
        self.events.put(("log", "已连接 %s — %s / %s" % (p.ip, model, sn)))
        self._refresh_files(gen)
        self._refresh_jobs(gen)
        self._refresh_network(gen)

    def _refresh_all(self):
        self._on_printer_change()

    def _add_printer(self):
        res = AddPrinterDialog(self, self.s).show()
        if not res:
            return
        ip, name = res
        if any(p["ip"] == ip for p in self.cfg["printers"]):
            messagebox.showinfo("已存在", "这个 IP 已经在列表里了。", parent=self)
            return
        self.cfg["printers"].append({"name": name, "ip": ip, "port": DEFAULT_PORT})
        save_config(self.cfg)
        self._render_printers()
        self._select_index(len(self.cfg["printers"]) - 1)

    def _remove_printer(self):
        if len(self.cfg["printers"]) <= 1:
            messagebox.showinfo("提示", "至少要保留一台打印机。", parent=self)
            return
        entry = self.cfg["printers"][self.current_index]
        if not messagebox.askyesno("移除", "从列表移除 %s？\n（只影响本工具的列表）" % entry["ip"],
                                   parent=self):
            return
        self.cfg["printers"].pop(self.current_index)
        save_config(self.cfg)
        self._render_printers()
        self._select_index(0)

    # ---------------- 数据刷新 ----------------
    def _refresh_files(self, gen=None):
        gen = self._gen if gen is None else gen
        if self.printer:
            threading.Thread(target=self._files_worker,
                             args=(self.printer, gen), daemon=True).start()

    def _files_worker(self, p, gen):
        try:
            data = p.files()
        except Exception as exc:
            if gen == self._gen:
                self.events.put(("log", "读取文件列表失败：%s" % exc))
            return
        if gen != self._gen:
            return
        rows = []
        for item in data:
            name = item.get("name", "")
            ext = item.get("extension") or ""
            full = name + "." + ext if ext else name
            rows.append((full, item.get("size", 0), item.get("modifiedDate", "")))
        rows.sort(key=lambda r: parse_modified(r[2]), reverse=True)
        self.events.put(("files", rows))

    def _refresh_jobs(self, gen=None):
        gen = self._gen if gen is None else gen
        if not self.printer:
            return
        self._last_job_poll = time.time()
        threading.Thread(target=self._jobs_worker,
                         args=(self.printer, gen), daemon=True).start()

    def _jobs_worker(self, p, gen):
        try:
            jobs = p.jobs()
        except Exception:
            return
        if gen != self._gen:
            return
        self._merge_history(jobs)
        active = next((j for j in jobs if j.get("printInProgress")), None)
        if active:
            total = active.get("totalSlices") or 0
            cur = active.get("currentSlice") or 0
            avg = (active.get("averageSliceTime") or 0) / 1000.0
            info = {
                "name": active.get("jobName", "—"),
                "layers": "%d / %d" % (cur, total),
                "state": STATUS_CN.get(active.get("status", ""), active.get("status") or "—"),
                "remain": fmt_duration((total - cur) * avg) if avg > 0 and total > cur else "计算中…",
                "elapsed": fmt_duration((active.get("elapsedTime") or 0) / 1000.0),
                "pct": (cur / total * 100) if total else 0,
                "active": True,
                "id": active.get("id"),
                "paused": bool(active.get("printPaused")),
            }
        elif jobs:
            last = max(jobs, key=lambda j: (j.get("endPrintTime") or j.get("beginPrintTime") or 0))
            total = last.get("totalSlices") or 0
            st_cn = STATUS_CN.get(last.get("status", ""), last.get("status") or "—")
            end_ts = fmt_ts(last.get("endPrintTime"))
            state_txt = ("空闲 \u00b7 上次 %s 结束\uff08%s\uff09" % (end_ts, st_cn)
                         if end_ts else "空闲\uff08最近\uff1a%s\uff09" % st_cn)
            info = {
                "name": last.get("jobName", "—"),
                "layers": "%d / %d" % (total, total),
                "state": state_txt,
                "remain": "—",
                "elapsed": "",
                "pct": 0,
                "active": False,
                "id": None,
                "paused": False,
            }
        else:
            info = {"name": "—", "layers": "—", "state": "空闲", "remain": "—",
                    "elapsed": "", "pct": 0, "active": False,
                    "id": None, "paused": False}
        try:
            info["params"] = fmt_params(
                active.get("thickness"), active.get("layerTime"),
                active.get("bottomLayersTime"), active.get("numberOfBottomLayers"),
                active.get("zliftDistance"), active.get("zliftSpeed"),
                active.get("currentSliceTime"), cur) if active else ""
        except Exception:
            info["params"] = ""
        self.events.put(("job", info))

    # ---------------- 删除 ----------------
    def _delete_selected(self):
        sel = self.tree_files.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表里选中要删除的文件。", parent=self)
            return
        if self.busy:
            messagebox.showinfo("提示", "当前有操作在进行中，请稍候。", parent=self)
            return
        names = [self.tree_files.item(i, "values")[0] for i in sel]
        if not messagebox.askyesno("删除", "将从打印机删除：\n\n" + "\n".join(names) + "\n\n确定？",
                                   parent=self):
            return
        threading.Thread(target=self._delete_worker,
                         args=(self.printer, names, self._gen), daemon=True).start()

    def _delete_worker(self, p, names, gen):
        self.events.put(("busy", True))
        try:
            for name in names:
                try:
                    self.events.put(("log", "删除 %s：%s" % (name, p.delete_file(name))))
                except Exception as exc:
                    self.events.put(("log", "删除 %s 失败：%s" % (name, exc)))
        finally:
            self.events.put(("busy", False))
        if gen == self._gen:
            self._refresh_files(gen)

    # ---------------- 上传 ----------------
    def _pick_files(self):
        init = self.cfg.get("last_dir") or os.path.expanduser("~")
        paths = filedialog.askopenfilenames(
            parent=self, title="选择要上传的切片文件", initialdir=init,
            filetypes=[("切片文件", "*.cws"), ("所有文件", "*.*")])
        # 原生文件对话框会破坏进程的 Winsock，必须立刻修回来
        ensure_winsock()
        if not paths:
            return
        self.cfg["last_dir"] = os.path.normpath(os.path.dirname(paths[0]))
        save_config(self.cfg)
        known = {item["path"] for item in self.queue_files}
        added = 0
        for path in paths:
            if path in known:
                continue
            self.queue_files.append({"path": path, "name": os.path.basename(path),
                                     "size": os.path.getsize(path), "state": "等待",
                                     "done": False})
            added += 1
        self._render_queue()
        self._log("已加入队列 %d 个文件。" % added)

    def _render_queue(self):
        self.tree_queue.delete(*self.tree_queue.get_children())
        for i, item in enumerate(self.queue_files):
            self.tree_queue.insert("", "end", iid=str(i),
                                   values=(item["name"], human_size(item["size"]), item["state"]))

    def _set_state(self, idx, text):
        if 0 <= idx < len(self.queue_files):
            item = self.queue_files[idx]
            item["state"] = text
            if self.tree_queue.exists(str(idx)):
                self.tree_queue.item(str(idx), values=(item["name"],
                                                       human_size(item["size"]), text))

    def _clear_queue(self):
        if self.busy:
            return
        self.queue_files = []
        self._render_queue()
        self.bar_up.set(0)
        self.lbl_pb.configure(text="就绪")

    def _start_upload(self):
        if self.busy:
            messagebox.showinfo("提示", "正在上传中，请稍候。", parent=self)
            return
        pending = [i for i, it in enumerate(self.queue_files) if not it.get("done")]
        if not pending:
            messagebox.showinfo("提示", "队列里没有待上传的文件，请先选择 .cws 文件。", parent=self)
            return
        self.busy = True
        threading.Thread(target=self._upload_worker,
                         args=(self.printer, pending, self._gen), daemon=True).start()

    def _upload_worker(self, p, indices, gen):
        ok = 0
        for n, idx in enumerate(indices):
            item = self.queue_files[idx]
            base = "[%d/%d] %s" % (n + 1, len(indices), item["name"])
            self.events.put(("set_state", (idx, "上传中…")))
            seen = [-1]

            def cb(sent, total, _idx=idx, _base=base, _seen=seen):
                pct = int(sent * 100 / total) if total else 100
                if pct != _seen[0]:
                    _seen[0] = pct
                    self.events.put(("progress", (
                        pct, "%s  %d%%  (%s / %s)" % (_base, pct, human_size(sent),
                                                      human_size(total)))))

            try:
                status, body = p.upload(item["path"], item["name"], cb)
                try:
                    resp = json.loads(body)
                except ValueError:
                    resp = {}
                if status == 200 and resp.get("response") is True:
                    item["done"] = True
                    ok += 1
                    self.events.put(("set_state", (idx, "✓ 已完成")))
                    self.events.put(("log", "上传成功：%s" % item["name"]))
                else:
                    self.events.put(("set_state", (idx, "✗ 失败 " + body[:40])))
                    self.events.put(("log", "上传失败 %s：HTTP %s %s" % (item["name"], status, body[:100])))
            except Exception as exc:
                self.events.put(("set_state", (idx, "✗ " + str(exc))))
                self.events.put(("log", "上传异常 %s：%s" % (item["name"], exc)))

        self.events.put(("progress", (100 if ok else 0, "完成 %d/%d" % (ok, len(indices)))))
        self.events.put(("busy", False))
        self.events.put(("log", "本轮结束：成功 %d 个，失败 %d 个。" % (ok, len(indices) - ok)))
        if gen == self._gen:
            self._refresh_files(gen)
            self._refresh_jobs(gen)

    # ---------------- 网络设置 ----------------
    def _refresh_network(self, gen=None):
        gen = self._gen if gen is None else gen
        if self.printer:
            threading.Thread(target=self._network_worker,
                             args=(self.printer, gen), daemon=True).start()

    def _network_worker(self, p, gen):
        try:
            info = p.wifi_info()
            eth = p.eth0_info()
        except Exception as exc:
            if gen == self._gen:
                self.events.put(("log", "读取网络信息失败\uff1a%s" % exc))
            return
        if gen != self._gen:
            return
        self.events.put(("network", (info, eth)))

    def _scan_wifi(self):
        if not self.printer:
            return
        def work():
            try:
                lst = self.printer.wifi_list()
            except Exception as exc:
                self.events.put(("log", "扫描 WiFi 失败\uff1a%s" % exc))
                return
            self.events.put(("wifi_list", lst))
        threading.Thread(target=work, daemon=True).start()

    def _fill_wifi(self, lst):
        best = {}
        for it in (lst or []):
            ssid = (it.get("ssid") or "").strip()
            if not ssid:
                continue
            lvl = it.get("level") or -999
            if ssid not in best or lvl > (best[ssid].get("level") or -999):
                best[ssid] = it
        rows = sorted(best.values(), key=lambda x: -(x.get("level") or -999))
        self._wifi_map = {}
        self.menu_wifi.delete(0, "end")
        labels = []
        for it in rows:
            label = "%s   (%d dBm)" % (it["ssid"], it.get("level") or 0)
            labels.append(label)
            self._wifi_map[label] = it
            self.menu_wifi.add_command(label=label,
                                       command=lambda L=label: self._pick_wifi(L))
        if labels:
            self._pick_wifi(labels[0])
        else:
            self._wifi_sel = None
            self.btn_wifi.configure(text="未发现 WiFi ▾")
        self._log("扫描到 %d 个 WiFi。" % len(labels))

    def _pick_wifi(self, label):
        self._wifi_sel = label
        self.btn_wifi.configure(text=label + "  \u25be")

    def _connect_wifi(self):
        if self._printing:
            messagebox.showwarning("已阻止",
                                   "打印进行中，切换 WiFi 会中断打印。", parent=self)
            return
        label = getattr(self, "_wifi_sel", None)
        item = self._wifi_map.get(label) if label else None
        if not item:
            messagebox.showinfo("提示", "请先点\u201c扫描\u201d，再选择一个 WiFi。", parent=self)
            return
        ssid = item["ssid"]
        sec = int(item.get("security") or 0)
        pwd = self.ent_pwd.get()
        if sec != 0 and not pwd:
            messagebox.showinfo("提示", "该 WiFi 加密，需要填密码。", parent=self)
            return
        if not messagebox.askyesno(
                "连接 WiFi",
                "将把打印机连接到：\n\n%s\n\n注意：连接后打印机 IP 可能变化，本工具可能暂时连不上，\n届时需要重新扫描或添加新 IP。\n\n确定吗？" % ssid,
                parent=self):
            return
        self.ent_pwd.delete(0, "end")
        self._run_action("连接 WiFi %s" % ssid,
                         lambda p: p.wifi_connect(ssid, pwd, sec), secret=pwd)

    # ---------------- 打印控制动作 ----------------
    def _update_control_state(self):
        if not hasattr(self, "btn_pause"):
            return
        printing = bool(self._printing)
        if printing:
            self.btn_pause.set_text("▶  继续" if self._paused else "⏸  暂停")
            self.btn_pause.set_enabled(True)
        else:
            self.btn_pause.set_text("⏸  暂停")
            self.btn_pause.set_enabled(False)
        self.btn_stop.set_enabled(printing)
        for b in self.z_buttons:
            b.set_enabled(not printing)
        self.btn_home.set_enabled(not printing)
        if hasattr(self, "btn_wifi_connect"):
            self.btn_wifi_connect.set_enabled(not printing)
        self.lbl_ctl_hint.configure(text="打印中已锁定" if printing else "")

    @staticmethod
    def _scrub(text, secret):
        """把敏感串从日志文本里抹掉，原文和 URL 编码形式都处理。"""
        txt = str(text)
        if not secret:
            return txt
        for form in (secret, quote(secret, safe=""), quote(secret)):
            if form and len(form) >= 2 and form in txt:
                txt = txt.replace(form, "***")
        return txt

    @staticmethod
    def _brief(raw, limit=90):
        """把接口返回压缩成一行，避免整包 JSON 灌进日志。"""
        txt = str(raw).strip()
        try:
            data = json.loads(txt)
        except ValueError:
            return txt if len(txt) <= limit else txt[:limit - 1] + "…"
        if isinstance(data, dict):
            for key in ("message", "status", "jobName", "response"):
                if data.get(key) not in (None, ""):
                    return "%s=%s" % (key, data[key])
            return "已返回 %d 个字段" % len(data)
        if isinstance(data, list):
            return "已返回 %d 条记录" % len(data)
        return txt[:limit]

    def _run_action(self, title, fn, secret=None):
        def work():
            self.events.put(("busy", True))
            try:
                raw = self._scrub(fn(self.printer), secret)
                full = raw if len(raw) <= 400 else raw[:399] + "…"
                self.events.put(("logx", ("%s → %s" % (title, full),
                                        "%s → %s" % (title, self._brief(raw)))))
            except Exception as exc:
                self.events.put(("log", "%s 失败：%s"
                                 % (title, self._scrub(exc, secret))))
            finally:
                self.events.put(("busy", False))
            time.sleep(1.0)
            self._refresh_jobs(self._gen)
            self._refresh_network(self._gen)
        threading.Thread(target=work, daemon=True).start()

    def _toggle_pause(self):
        if not self._job_id:
            messagebox.showinfo("提示", "当前没有正在打印的任务。", parent=self)
            return
        self._run_action("暂停/继续", lambda p: p.job_toggle(self._job_id))

    def _stop_print(self):
        if not self._job_id:
            messagebox.showinfo("提示", "当前没有正在打印的任务。", parent=self)
            return
        if not messagebox.askyesno(
                "停止打印",
                "将立即停止当前打印任务。\n\n停止后无法恢复，已打印的部分只能报废。\n\n确定要停止吗？",
                parent=self, icon="warning"):
            return
        self._run_action("停止打印", lambda p: p.job_stop(self._job_id))

    def _move_z(self, distance):
        if self._printing:
            messagebox.showwarning("已阻止", "打印进行中，不能移动 Z 轴。", parent=self)
            return
        raw = self.printer.lift_raw(distance)
        self._log("Z 轴移动 %+g mm，实际发送参数 %g" % (distance, raw))
        self._run_action("Z 轴移动 %+g mm" % distance,
                         lambda p: p.printer_move(distance))

    def _printer_home(self):
        if self._printing:
            messagebox.showwarning("已阻止", "打印进行中，不能归位。", parent=self)
            return
        if not messagebox.askyesno(
                "Z 轴归位",
                "Z 轴将回到原点，移动幅度较大。\n请确认平台上方没有干涉、料槽已取下。\n\n确定归位？",
                parent=self):
            return
        self._run_action("Z 轴归位", lambda p: p.printer_home())

    def _start_print(self):
        if self._printing:
            messagebox.showwarning("提示", "打印机正在打印，请等待完成或先停止。", parent=self)
            return
        sel = self.tree_files.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在文件列表中选中要打印的文件。", parent=self)
            return
        name = self.tree_files.item(sel[0], "values")[0]
        if not messagebox.askyesno(
                "开始打印",
                "将对以下文件开始打印：\n\n%s\n\n打印机会立即开始工作，确定吗？" % name,
                parent=self):
            return
        self._run_action("开始打印 %s" % name, lambda p: p.file_print(name))

    # ---------------- 渲染 ----------------
    def _apply_job(self, info):
        prev_id = getattr(self, "_active_job_id", None)
        now_id = info.get("id") if (info and info.get("active")) else None
        if prev_id and prev_id != now_id:
            self._notify_finished(prev_id)
        self._active_job_id = now_id
        self._printing = bool(info and info.get("active"))
        self._paused = bool(info and info.get("paused"))
        self._job_id = info.get("id") if info else None
        self._update_control_state()
        if not info:
            self.pill_state.set("未连接", THEME["text_dim"])
            self.lbl_job_name.configure(text="—")
            self.lbl_layers.configure(text="")
            self.lbl_elapsed.configure(text="")
            self.lbl_remain_bar.configure(text="")
            self.lbl_pct.configure(text="")
            self.lbl_params.configure(text="")
            self.bar_job.set(0)
            return
        active = info.get("active")
        pct = info.get("pct") or 0
        if active:
            self.pill_state.set("打印中", THEME["accent"])
            self.lbl_elapsed.configure(text="已用 " + info["elapsed"])
            self.lbl_remain_bar.configure(text="剩余 " + info["remain"])
            self.lbl_pct.configure(text="%.1f%%" % pct)
            self.lbl_layers.configure(text=info["layers"] + " 层")
            self.lbl_params.configure(text=info.get("params") or "")
        else:
            self.pill_state.set("空闲", THEME["text_dim"])
            last = max(self.history.values(),
                       key=lambda r: r.get("end") or r.get("begin") or 0,
                       default=None)
            self.lbl_params.configure(text=fmt_params(
                (last or {}).get("thickness"), (last or {}).get("layer_ms"),
                (last or {}).get("bottom_ms"), (last or {}).get("bottom_num"),
                (last or {}).get("lift_d"), (last or {}).get("lift_s"),
                (last or {}).get("cur_ms"), (last or {}).get("slices")) if last else "")
            self.lbl_elapsed.configure(text=info.get("state", ""))
            self.lbl_remain_bar.configure(text="")
            self.lbl_pct.configure(text="")
            self.lbl_layers.configure(text=info["layers"] + " 层")
        self.lbl_job_name.configure(text=info["name"])
        self.bar_job.set(pct if active else 0)

    def _apply_network(self, info, eth):
        info = info or {}
        ssid = info.get("ssid") or "—"
        ip = info.get("ip") or ""
        self.lbl_wifi_cur.configure(text=("%s   %s" % (ssid, ip)).strip())
        eth = eth or {}
        dhcp = eth.get("ipEth0Dhcp")
        static = eth.get("ipEth0Static")
        if dhcp or static:
            self.lbl_eth.configure(text=dhcp or static, fg=THEME["text"])
        elif "ipEth0Dhcp" in eth:
            self.lbl_eth.configure(text="未配置", fg=THEME["text_dim"])
        else:
            self.lbl_eth.configure(text="—", fg=THEME["text_dim"])

    def _fill_files(self, rows):
        self.tree_files.delete(*self.tree_files.get_children())
        for name, size, date in rows:
            # 打印机给的时间已是 24 小时制，「上午/下午」是冗余标记，去掉更清爽
            shown = (str(date).replace(" GMT+00:00", "")
                     .replace("上午", "").replace("下午", "").strip())
            self.tree_files.insert("", "end", values=(name, human_size(size), shown))

    def _pump(self):
        if getattr(self, "_in_pump", False):
            return
        self._in_pump = True
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "logx":
                    self._log(payload[0], payload[1])
                elif kind == "files":
                    self._fill_files(payload)
                elif kind == "job":
                    self._apply_job(payload)
                elif kind == "printer_info":
                    model, sn = payload
                    self._render_info(model, sn)
                    self._render_printers()
                elif kind == "conn":
                    self._set_conn(*payload)
                elif kind == "network":
                    self._apply_network(*payload)
                elif kind == "wifi_list":
                    self._fill_wifi(payload)
                elif kind == "history_changed":
                    if self.hist_win and self.hist_win.winfo_exists():
                        self.hist_win.refresh(list(self.history.values()))
                elif kind == "progress":
                    pct, text = payload
                    self.bar_up.set(pct)
                    self.lbl_pb.configure(text=text)
                elif kind == "set_state":
                    self._set_state(*payload)
                elif kind == "busy":
                    self.busy = payload
                    self.btn_upload.set_enabled(not payload)
        except queue.Empty:
            pass
        if not self.busy and time.time() - self._last_job_poll > 5:
            self._refresh_jobs()
        self.after(200, self._pump)
        self._in_pump = False

    # ---------------- 完成通知 ----------------
    def _sync_notify_btn(self):
        if hasattr(self, "btn_notify"):
            self.btn_notify.set_text("通知 开" if self._notify_on else "通知 关", width=82)

    def _toggle_notify(self):
        self._notify_on = not self._notify_on
        self.cfg["notify"] = self._notify_on
        save_config(self.cfg)
        self._sync_notify_btn()
        self._log("打印完成通知已%s。" % ("开启" if self._notify_on else "关闭"))

    def _notify_finished(self, job_id):
        rec = self.history.get(str(job_id)) or {}
        name = rec.get("name") or "任务"
        raw = rec.get("status") or ""
        cn = STATUS_CN.get(raw, raw or "已结束")
        ok = (raw == "Completed")
        elapsed = (fmt_duration((rec.get("elapsed_ms") or 0) / 1000.0)
                   if rec.get("elapsed_ms") else "")
        msg = cn + ("，用时 " + elapsed if elapsed else "")
        self._log("打印%s：%s" % (cn, name))
        if not self._notify_on:
            return
        try:
            Toast(self, self.s, "打印完成" if ok else "打印结束",
                  "%s\n%s" % (name, msg), "ok" if ok else "warn")
        except Exception:
            pass
        if winsound:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK if ok
                                     else winsound.MB_ICONHAND)
            except Exception:
                pass

    # ---------------- 打印历史 ----------------
    def _merge_history(self, jobs):
        entry = self.cfg["printers"][self.current_index]
        sn = entry.get("sn") or ""
        ip = entry.get("ip") or ""
        pname = entry.get("name") or ip
        changed = False
        for j in (jobs or []):
            jid = j.get("id")
            if not jid:
                continue
            jid = str(jid)
            rec = {
                "id": jid,
                "name": j.get("jobName") or "",
                "status": j.get("status") or "",
                "begin": int(j.get("beginPrintTime") or 0),
                "end": int(j.get("endPrintTime") or 0),
                "slices": int(j.get("totalSlices") or 0),
                "elapsed_ms": int(j.get("elapsedTime") or 0),
                "avg_ms": int(j.get("averageSliceTime") or 0),
                "sn": sn,
                "ip": ip,
                "pname": pname,
                "thickness": j.get("thickness") or 0,
                "layer_ms": j.get("layerTime") or 0,
                "bottom_ms": j.get("bottomLayersTime") or 0,
                "bottom_num": j.get("numberOfBottomLayers") or 0,
                "lift_d": j.get("zliftDistance") or 0,
                "lift_s": j.get("zliftSpeed") or 0,
                "cur_ms": j.get("currentSliceTime") or 0,
            }
            if self.history.get(jid) != rec:
                self.history[jid] = rec
                changed = True
        # 老记录没有打印机标识：按本次任务列表里出现的 id 认领归属
        if sn:
            now_ids = {str(j.get("id")) for j in (jobs or []) if j.get("id")}
            for jid, old in self.history.items():
                if not old.get("sn") and jid in now_ids:
                    old["sn"] = sn
                    old["ip"] = ip
                    old["pname"] = pname
                    changed = True
        if changed:
            if len(self.history) > HISTORY_LIMIT:
                keep = sorted(self.history.values(),
                              key=lambda r: r.get("begin") or 0)[-HISTORY_LIMIT:]
                self.history = {r["id"]: r for r in keep}
            save_history(self.history)
            self.events.put(("history_changed", None))

    def _show_history(self):
        if self.hist_win and self.hist_win.winfo_exists():
            self.hist_win.lift()
            self.hist_win.refresh(list(self.history.values()))
            return
        self.hist_win = HistoryWindow(self, self.s, list(self.history.values()))

    def _clear_history(self):
        if not messagebox.askyesno("清空历史",
                                   "将删除本机保存的全部打印历史记录。\n\n确定吗？",
                                   parent=self):
            return
        self.history = {}
        save_history({})
        if self.hist_win and self.hist_win.winfo_exists():
            self.hist_win.refresh([])
        self._log("打印历史已清空。")

    # ---------------- 日志 ----------------
    def _log(self, msg, status=None):
        """msg 进日志窗口（保留原文），status 只进状态栏（自动截断）。"""
        line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
        self.log_lines.append(line)
        if len(self.log_lines) > 2000:
            del self.log_lines[:500]
        text = msg if status is None else status
        shown = text if len(text) <= 56 else text[:55] + "…"
        self.lbl_status.configure(text=shown)
        if self.log_win and self.log_win.winfo_exists():
            self.log_win.append(line)

    def _show_log(self):
        if self.log_win and self.log_win.winfo_exists():
            self.log_win.lift()
            return
        self.log_win = LogWindow(self, self.s, self.log_lines)

    def _on_close(self):
        self._gen += 1
        if self.log_win and self.log_win.winfo_exists():
            self.log_win.destroy()
        self.destroy()


class LogWindow(tk.Toplevel):
    def __init__(self, master, s, lines):
        super().__init__(master)
        self.title("运行日志")
        self.configure(bg=THEME["bg"])
        self.geometry("%dx%d" % (int(760 * s), int(460 * s)))
        self.txt = tk.Text(self, bg=THEME["card"], fg=THEME["text_dim"], bd=0,
                           highlightthickness=0, wrap="word", font=(FONT, 9),
                           insertbackground=THEME["text"], padx=int(10 * s), pady=int(8 * s))
        self.txt.pack(side="left", fill="both", expand=True, padx=(int(10 * s), 0), pady=int(10 * s))
        sb = SlimScrollbar(self, self.txt, s=s)
        sb.pack(side="left", fill="y", pady=int(10 * s), padx=(int(2 * s), int(10 * s)))
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.insert("end", "\n".join(lines) + "\n")
        self.txt.see("end")
        apply_dark_titlebar(self)

    def append(self, line):
        self.txt.insert("end", line + "\n")
        self.txt.see("end")


class HistoryWindow(tk.Toplevel):
    """打印历史：可按打印机筛选，每条记录带机器标识。"""

    def __init__(self, master, s, records):
        super().__init__(master)
        self.title("打印历史")
        self.configure(bg=THEME["bg"])
        self.geometry("%dx%d" % (int(1020 * s), int(520 * s)))
        self.s = s
        self._all = list(records or [])
        self._filter = None
        self._labels = {}

        head = tk.Frame(self, bg=THEME["bg"])
        head.pack(fill="x", padx=int(10 * s), pady=(int(10 * s), int(6 * s)))
        tk.Label(head, text="打印机", bg=THEME["bg"], fg=THEME["text_dim"],
                 font=(FONT, 9)).pack(side="left", padx=(0, int(8 * s)))
        self.btn_filter = tk.Menubutton(
            head, text="全部打印机  \u25be", bg=THEME["row"], fg=THEME["text"],
            activebackground=THEME["btn"], activeforeground=THEME["text"],
            relief="flat", anchor="w", font=(FONT, 9), cursor="hand2",
            padx=int(8 * s), pady=int(3 * s))
        self.menu_filter = tk.Menu(self.btn_filter, tearoff=0, bg=THEME["card"],
                                   fg=THEME["text"], activebackground=THEME["accent"],
                                   activeforeground="#FFFFFF", font=(FONT, 9), bd=0)
        self.btn_filter.configure(menu=self.menu_filter)
        self.btn_filter.pack(side="left")
        self.lbl_count = tk.Label(head, text="", bg=THEME["bg"], fg=THEME["text_dim"],
                                  font=(FONT, 9))
        self.lbl_count.pack(side="right")

        cols = (("end", "结束时间", 140), ("printer", "打印机", 150),
                ("name", "任务名", 250), ("status", "状态", 80),
                ("slices", "层数", 60), ("elapsed", "用时", 100), ("avg", "平均层时", 90))
        wrap = tk.Frame(self, bg=THEME["bg"])
        wrap.pack(fill="both", expand=True, padx=int(10 * s))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in cols], show="headings",
                                 style="Dark.Treeview")
        for key, title, px in cols:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=int(px * s), stretch=(key == "name"),
                             anchor="w" if key in ("end", "printer", "name", "status") else "e")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = SlimScrollbar(wrap, self.tree, s=s)
        sb.pack(side="left", fill="y", padx=(int(2 * s), 0))
        self.tree.configure(yscrollcommand=sb.set)

        bar = tk.Frame(self, bg=THEME["bg"])
        bar.pack(fill="x", padx=int(10 * s), pady=int(10 * s))
        tk.Label(bar, text="数据目录：%s" % DATA_DIR, bg=THEME["bg"],
                 fg=THEME["text_dim"], font=(FONT, 8), anchor="w").pack(side="left")
        RoundButton(bar, text="清空历史", width=90, height=26, s=s, font_size=9,
                    command=master._clear_history).pack(side="right")

        self.refresh(records)
        apply_dark_titlebar(self)

    def _rebuild_menu(self):
        labels = {}
        for r in self._all:
            key = r.get("sn") or ""
            name = r.get("pname") or r.get("ip") or "未标注"
            labels.setdefault(key, name if not key else "%s\uff08%s\uff09" % (name, key))
        if self._filter is not None and self._filter not in labels:
            self._filter = None
        self._labels = labels
        self.menu_filter.delete(0, "end")
        self.menu_filter.add_command(label="全部打印机",
                                     command=lambda: self._set_filter(None))
        for key in sorted(labels, key=lambda k: labels[k]):
            self.menu_filter.add_command(label=labels[key],
                                         command=lambda k=key: self._set_filter(k))
        self.btn_filter.configure(text=self._current_label() + "  \u25be")

    def _current_label(self):
        if self._filter is None:
            return "全部打印机"
        return self._labels.get(self._filter, self._filter or "未标注")

    def _set_filter(self, key):
        self._filter = key
        self.btn_filter.configure(text=self._current_label() + "  \u25be")
        self._render()

    def refresh(self, records=None):
        if records is not None:
            self._all = list(records)
        self._rebuild_menu()
        self._render()

    def _render(self):
        self.tree.delete(*self.tree.get_children())
        rows = [r for r in self._all
                if self._filter is None or (r.get("sn") or "") == self._filter]
        rows.sort(key=lambda r: (r.get("end") or r.get("begin") or 0), reverse=True)
        for r in rows:
            raw = r.get("status") or ""
            terminal = raw in ("Completed", "Cancelled", "Stopped")
            end_txt = fmt_ts(r.get("end")) if terminal else ""
            if not end_txt:
                end_txt = "\u2014" if terminal else "打印中"
            elapsed = r.get("elapsed_ms") or 0
            avg = r.get("avg_ms") or 0
            self.tree.insert("", "end", values=(
                end_txt,
                r.get("pname") or (r.get("sn") or "未标注"),
                r.get("name") or "\u2014",
                STATUS_CN.get(raw, raw or "\u2014"),
                r.get("slices") or 0,
                fmt_duration(elapsed / 1000.0) if elapsed else "\u2014",
                ("%.1f 秒" % (avg / 1000.0)) if avg else "\u2014",
            ))
        self.lbl_count.configure(text="共 %d 条" % len(rows))


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()


if __name__ == "__main__":
    main()
