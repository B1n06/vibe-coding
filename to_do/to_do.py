
import tkinter as tk
from tkinter import messagebox
import time
from datetime import datetime
import json
import os
import ctypes

try:
    import customtkinter as ctk
except ImportError as exc:
    raise SystemExit(
        "缺少依赖 customtkinter。\n"
        "请先运行：pip install customtkinter\n"
        "然后再运行本文件。"
    ) from exc


# =====================
# 主题与配置
# =====================
THEME = {
    "window": "#070B18",
    "topbar": "#080D1F",
    "panel": "#10172E",
    "panel_soft": "#141D3A",
    "panel_deep": "#0C1227",
    "card": "#111A35",
    "card_hover": "#172145",
    "border": "#263154",
    "border_soft": "#1C2546",
    "text": "#F5F7FF",
    "muted": "#A4AED0",
    "muted_2": "#6E7AA3",
    "purple": "#7B5CFF",
    "purple_2": "#9275FF",
    "purple_dark": "#5A42D9",
    "blue": "#5AA2FF",
    "cyan": "#2DD4BF",
    "green": "#3DD6A3",
    "amber": "#F4B840",
    "red": "#F05B6C",
    "progress_bg": "#29345F",
}

URGENCY_VALUES = ["🔴 紧急", "🟡 一般", "🟢 宽松"]

URGENCY_ORDER = {
    "🔴 紧急": 0,
    "🟡 一般": 1,
    "🟢 宽松": 2,
}

EYE_CARE_MINUTES = 45
FLOW_AUTO_STOP_MINUTES = 45
MAX_REVIEW_MINUTES = 10
MAX_PAUSE_MINUTES = 15
DATA_FILE = "tasks.json"
STATS_FILE = "flow_stats.json"

FONT_CN = "Microsoft YaHei UI"
FONT_TIMER = "Arial"


# =====================
# 系统辅助
# =====================
def enable_high_dpi_awareness():
    """Windows 高 DPI 适配，降低界面发糊的概率。"""
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def bring_window_to_front(root=None):
    """尽量把提醒框置顶。"""
    try:
        if root is not None:
            root.attributes("-topmost", True)
            root.update()
            root.attributes("-topmost", False)
        else:
            hwnd = ctypes.windll.kernel32.GetForegroundWindow()
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def center_window(root, width=1020, height=700):
    """设置窗口尺寸，并交给 Tk 窗口管理器居中。"""
    root.update_idletasks()
    root.geometry(f"{width}x{height}")
    root.update_idletasks()

    try:
        root.eval(f"tk::PlaceWindow {root._w} center")
    except Exception:
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")


class PrioritySelector(ctk.CTkFrame):
    """三段式优先级选择器，替代下拉框，避免右侧默认箭头区域破坏整体风格。"""

    def __init__(self, parent, default_value="🟡 一般"):
        super().__init__(
            parent,
            fg_color=THEME["panel_soft"],
            border_width=1,
            border_color=THEME["border_soft"],
            corner_radius=12,
        )
        self.value = default_value
        self.buttons = {}

        options = [
            ("🔴 紧急", "紧急", THEME["red"]),
            ("🟡 一般", "一般", THEME["amber"]),
            ("🟢 宽松", "宽松", THEME["green"]),
        ]

        for index, (value, label, color) in enumerate(options):
            self.grid_columnconfigure(index, weight=1, uniform="priority")
            btn = ctk.CTkButton(
                self,
                text=label,
                height=42,
                width=76,
                corner_radius=10,
                border_width=0,
                fg_color="transparent",
                hover_color=THEME["card_hover"],
                text_color=color,
                font=(FONT_CN, 14, "bold"),
                command=lambda v=value: self.set(v),
            )
            btn.grid(row=0, column=index, sticky="ew", padx=(4 if index == 0 else 2, 4 if index == 2 else 2), pady=4)
            self.buttons[value] = (btn, color)

        self.set(default_value)

    def get(self):
        return self.value

    def set(self, value):
        if value not in self.buttons:
            value = "🟡 一般"
        self.value = value
        for option, (btn, color) in self.buttons.items():
            if option == value:
                btn.configure(fg_color=THEME["purple_dark"], text_color=THEME["text"])
            else:
                btn.configure(fg_color="transparent", text_color=color)


class TodoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("to do")
        self.root.withdraw()
        center_window(self.root, 1020, 700)
        self.root.minsize(920, 620)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)

        self.root.configure(fg_color=THEME["window"])

        # 状态管理：IDLE(空闲), FLOW(心流中), REVIEW(复盘中), PAUSE(暂停休息中)
        self.state = "IDLE"
        self.flow_start_time = 0
        self.accumulated_flow_time = 0
        self.eye_care_reminded = False

        self.review_start_time = 0
        self.review_auto_stopped_flag = False

        self.pause_start_time = 0
        self.pause_reminded = False
        self.cycle_completed = False

        self.flow_total_count = 0
        self.flow_daily_count = 0
        self.flow_count_date = datetime.now().date().isoformat()

        self.task_id_counter = 1
        self.tasks = []

        self.load_tasks()
        self.load_flow_stats()
        self.setup_ui()
        self.root.after(80, self._show_centered_window)
        self.root.after(1000, self.tick)

    def _show_centered_window(self):
        center_window(self.root, 1020, 700)
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    # =====================
    # UI
    # =====================
    def setup_ui(self):
        shell = ctk.CTkFrame(self.root, fg_color=THEME["window"], corner_radius=0)
        shell.pack(fill="both", expand=True)

        self._build_top_bar(shell)

        content = ctk.CTkFrame(shell, fg_color=THEME["window"], corner_radius=0)
        content.pack(fill="both", expand=True, padx=18, pady=(12, 14))
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        self._build_flow_panel(content)
        self._build_input_panel(content)
        self._build_task_panel(content)

        self.refresh_list()
        self.update_flow_stats_display()
        self._update_progress_bar(0)

    def _build_top_bar(self, parent):
        top = ctk.CTkFrame(parent, height=44, fg_color=THEME["topbar"], corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)
        top.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(top, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=26, pady=0)

        ctk.CTkLabel(
            left,
            text="✦",
            font=(FONT_CN, 16, "bold"),
            text_color=THEME["blue"],
        ).pack(side="left", padx=(0, 14))

        ctk.CTkLabel(
            left,
            text="to do",
            font=(FONT_CN, 16, "bold"),
            text_color=THEME["text"],
        ).pack(side="left")

        ctk.CTkLabel(
            top,
            text="珍惜时间 · 轻松规划 · 稳定执行",
            font=(FONT_CN, 12),
            text_color=THEME["muted_2"],
        ).grid(row=0, column=2, sticky="e", padx=30)

    def _build_flow_panel(self, parent):
        panel = ctk.CTkFrame(
            parent,
            fg_color=THEME["panel"],
            border_width=1,
            border_color=THEME["border_soft"],
            corner_radius=18,
        )
        panel.grid(row=0, column=0, sticky="ew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        hero = ctk.CTkFrame(panel, fg_color="transparent")
        hero.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 4))
        hero.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(hero, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nw")

        status_row = ctk.CTkFrame(left, fg_color="transparent")
        status_row.pack(anchor="w")

        ctk.CTkLabel(
            status_row,
            text="●",
            font=(FONT_CN, 16, "bold"),
            text_color=THEME["blue"],
        ).pack(side="left", padx=(0, 12))

        self.status_label = ctk.CTkLabel(
            status_row,
            text="当前状态：待命",
            font=(FONT_CN, 16, "bold"),
            text_color=THEME["text"],
        )
        self.status_label.pack(side="left")

        self.timer_label = ctk.CTkLabel(
            left,
            text="00:00:00",
            font=(FONT_TIMER, 64, "bold"),
            text_color=THEME["purple_2"],
        )
        self.timer_label.pack(anchor="w", pady=(6, 0))

        stats = ctk.CTkFrame(hero, fg_color="transparent")
        stats.grid(row=0, column=1, sticky="ne", padx=(22, 0), pady=(2, 0))

        self.total_count_label = self._stat_card(
            stats,
            icon="⌁",
            title="总次数",
            value=self.flow_total_count,
            accent=THEME["purple_dark"],
        )
        self.daily_count_label = self._stat_card(
            stats,
            icon="☷",
            title="今日次数",
            value=self.flow_daily_count,
            accent="#1B6B75",
        )

        progress_card = ctk.CTkFrame(
            panel,
            fg_color=THEME["panel_soft"],
            border_width=1,
            border_color=THEME["border_soft"],
            corner_radius=16,
        )
        progress_card.grid(row=1, column=0, sticky="ew", padx=24, pady=(2, 14))
        progress_card.grid_columnconfigure(0, weight=1)

        progress_head = ctk.CTkFrame(progress_card, fg_color="transparent")
        progress_head.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 5))
        progress_head.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            progress_head,
            text=f"心流进度（{FLOW_AUTO_STOP_MINUTES}分钟）",
            font=(FONT_CN, 14, "bold"),
            text_color=THEME["text"],
        ).grid(row=0, column=0, sticky="w")

        self.progress_percent_label = ctk.CTkLabel(
            progress_head,
            text="0%",
            font=(FONT_CN, 14, "bold"),
            text_color=THEME["muted"],
        )
        self.progress_percent_label.grid(row=0, column=1, sticky="e")

        self.progress_bar = ctk.CTkProgressBar(
            progress_card,
            height=12,
            corner_radius=8,
            fg_color=THEME["progress_bg"],
            progress_color=THEME["purple_2"],
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        self.progress_bar.set(0)

        buttons = ctk.CTkFrame(progress_card, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 14))
        buttons.grid_columnconfigure(0, weight=1, uniform="buttons")
        buttons.grid_columnconfigure(1, weight=1, uniform="buttons")
        buttons.grid_columnconfigure(2, weight=1, uniform="buttons")

        self.btn_start = self._make_button(
            buttons,
            "▶  开始心流",
            THEME["green"],
            self.start_flow,
            height=44,
        )
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.btn_pause = self._make_button(
            buttons,
            "⏸  暂停休息",
            THEME["amber"],
            lambda: None,
            height=44,
            state="disabled",
        )
        self.btn_pause.grid(row=0, column=1, sticky="ew", padx=10)

        self.btn_stop = self._make_button(
            buttons,
            "■  停止",
            THEME["red"],
            lambda: None,
            height=44,
            state="disabled",
        )
        self.btn_stop.grid(row=0, column=2, sticky="ew", padx=(10, 0))

    def _stat_card(self, parent, icon, title, value, accent):
        card = ctk.CTkFrame(
            parent,
            width=196,
            height=76,
            fg_color=THEME["card"],
            border_width=1,
            border_color=THEME["border"],
            corner_radius=14,
        )
        card.pack(side="left", padx=(0, 16))
        card.pack_propagate(False)

        icon_box = ctk.CTkFrame(
            card,
            width=46,
            height=46,
            fg_color=accent,
            corner_radius=12,
        )
        icon_box.pack(side="left", padx=(14, 12), pady=14)
        icon_box.pack_propagate(False)

        ctk.CTkLabel(
            icon_box,
            text=icon,
            font=(FONT_CN, 16, "bold"),
            text_color=THEME["text"],
        ).pack(expand=True)

        texts = ctk.CTkFrame(card, fg_color="transparent")
        texts.pack(side="left", fill="both", expand=True, pady=10)

        ctk.CTkLabel(
            texts,
            text=title,
            font=(FONT_CN, 11, "bold"),
            text_color=THEME["muted"],
        ).pack(anchor="w")

        value_label = ctk.CTkLabel(
            texts,
            text=str(value),
            font=(FONT_CN, 16, "bold"),
            text_color=THEME["text"],
        )
        value_label.pack(anchor="w", pady=(2, 0))
        return value_label

    def _build_input_panel(self, parent):
        panel = ctk.CTkFrame(
            parent,
            fg_color=THEME["panel"],
            border_width=1,
            border_color=THEME["border_soft"],
            corner_radius=18,
        )
        panel.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            panel,
            text="新任务",
            font=(FONT_CN, 16, "bold"),
            text_color=THEME["text"],
        ).grid(row=0, column=0, sticky="w", padx=(20, 12), pady=12)

        self.task_entry = ctk.CTkEntry(
            panel,
            height=40,
            placeholder_text="输入待办事项...",
            font=(FONT_CN, 15),
            fg_color=THEME["panel_soft"],
            text_color=THEME["text"],
            placeholder_text_color=THEME["muted_2"],
            border_width=1,
            border_color=THEME["border_soft"],
            corner_radius=12,
        )
        self.task_entry.grid(row=0, column=1, sticky="ew", padx=(0, 18), pady=12)
        self.task_entry.bind("<Return>", lambda _event: self.add_task())

        ctk.CTkLabel(
            panel,
            text="紧急程度",
            font=(FONT_CN, 16, "bold"),
            text_color=THEME["text"],
        ).grid(row=0, column=2, sticky="w", padx=(0, 10), pady=12)

        self.urgency_combo = PrioritySelector(panel, default_value="🟡 一般")
        self.urgency_combo.grid(row=0, column=3, sticky="ew", padx=(0, 18), pady=12)

        add_btn = self._make_button(
            panel,
            "+  添加",
            THEME["purple"],
            self.add_task,
            height=44,
            width=140,
        )
        add_btn.grid(row=0, column=4, sticky="e", padx=(0, 24), pady=14)

    def _build_task_panel(self, parent):
        panel = ctk.CTkFrame(
            parent,
            fg_color=THEME["panel"],
            border_width=1,
            border_color=THEME["border_soft"],
            corner_radius=18,
        )
        panel.grid(row=2, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(14, 8))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="▣  待办事项清单",
            font=(FONT_CN, 16, "bold"),
            text_color=THEME["text"],
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="选中任务后按 Delete 或点击下方按钮删除",
            font=(FONT_CN, 12),
            text_color=THEME["muted_2"],
        ).grid(row=0, column=1, sticky="e")

        list_outer = ctk.CTkFrame(
            panel,
            fg_color=THEME["panel_soft"],
            border_width=1,
            border_color=THEME["border_soft"],
            corner_radius=14,
        )
        list_outer.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 10))
        list_outer.grid_columnconfigure(0, weight=1)
        list_outer.grid_rowconfigure(1, weight=1)

        header_row = ctk.CTkFrame(list_outer, fg_color=THEME["panel_deep"], corner_radius=10)
        header_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        header_row.grid_columnconfigure(0, weight=1)
        header_row.grid_columnconfigure(1, minsize=190)

        ctk.CTkLabel(
            header_row,
            text="任务描述",
            font=(FONT_CN, 14, "bold"),
            text_color=THEME["muted"],
        ).grid(row=0, column=0, sticky="w", padx=18, pady=8)

        ctk.CTkLabel(
            header_row,
            text="优先级",
            font=(FONT_CN, 14, "bold"),
            text_color=THEME["muted"],
        ).grid(row=0, column=1, sticky="ew", padx=18, pady=8)

        self.task_scroll = ctk.CTkScrollableFrame(
            list_outer,
            fg_color=THEME["panel_soft"],
            scrollbar_fg_color=THEME["panel_soft"],
            scrollbar_button_color=THEME["panel_2"] if "panel_2" in THEME else THEME["card"],
            scrollbar_button_hover_color=THEME["purple_dark"],
            corner_radius=0,
        )
        self.task_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        self.task_scroll.grid_columnconfigure(0, weight=1)
        self.task_scroll.grid_columnconfigure(1, minsize=190)

        self.task_rows = {}
        self.selected_task_ids = set()

        delete_btn = self._make_button(
            panel,
            "🗑  删除选中",
            THEME["red"],
            self.delete_task,
            height=42,
            width=190,
        )
        delete_btn.grid(row=2, column=0, pady=(0, 12))

        panel.bind("<Delete>", lambda _event: self.delete_task())
        self.root.bind("<Delete>", lambda _event: self.delete_task())

    # =====================
    # 居中小弹窗
    # =====================
    def _center_modal(self, modal, width=430, height=230):
        """将弹窗放在屏幕正中心，而不是相对于主窗口"""
        self.root.update_idletasks()
        modal.update_idletasks()

        # 获取屏幕尺寸
        screen_width = modal.winfo_screenwidth()
        screen_height = modal.winfo_screenheight()

        # 计算弹窗在屏幕中心的位置
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2

        modal.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

    def show_dialog(self, title, message, kind="info"):
        modal = ctk.CTkToplevel(self.root)
        modal.title(title)
        modal.transient(self.root)
        modal.grab_set()
        modal.resizable(False, False)
        modal.configure(fg_color=THEME["window"])
        modal.attributes("-topmost", True)  # 设置弹窗始终在最上层

        width = 430
        height = 210 if len(message) < 50 else 240
        self._center_modal(modal, width, height)
        modal.after(10, lambda: self._center_modal(modal, width, height))

        accent = THEME["amber"] if kind == "warning" else THEME["blue"]
        icon = "!" if kind == "warning" else "i"

        body = ctk.CTkFrame(
            modal,
            fg_color=THEME["panel"],
            border_width=1,
            border_color=THEME["border_soft"],
            corner_radius=18,
        )
        body.pack(fill="both", expand=True, padx=18, pady=18)
        body.grid_columnconfigure(1, weight=1)

        icon_box = ctk.CTkFrame(body, width=44, height=44, fg_color=accent, corner_radius=12)
        icon_box.grid(row=0, column=0, padx=(18, 14), pady=(20, 8), sticky="n")
        icon_box.grid_propagate(False)
        ctk.CTkLabel(
            icon_box,
            text=icon,
            font=(FONT_CN, 20, "bold"),
            text_color=THEME["text"],
        ).place(relx=0.5, rely=0.5, anchor="center")

        text_area = ctk.CTkFrame(body, fg_color="transparent")
        text_area.grid(row=0, column=1, sticky="nsew", padx=(0, 18), pady=(18, 8))

        ctk.CTkLabel(
            text_area,
            text=title,
            font=(FONT_CN, 16, "bold"),
            text_color=THEME["text"],
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            text_area,
            text=message,
            font=(FONT_CN, 13),
            text_color=THEME["muted"],
            justify="left",
            wraplength=300,
            anchor="w",
        ).pack(anchor="w", pady=(10, 0))

        ok = self._make_button(
            body,
            "知道了",
            THEME["purple"],
            modal.destroy,
            height=38,
            width=116,
        )
        ok.grid(row=1, column=0, columnspan=2, sticky="e", padx=18, pady=(4, 18))

        modal.bind("<Escape>", lambda _event: modal.destroy())
        modal.bind("<Return>", lambda _event: modal.destroy())
        modal.lift()  # 确保弹窗在最上方
        modal.focus_force()
        modal.wait_window()

    def ask_dialog(self, title, message, yes_text="是", no_text="否"):
        result = {"value": False}

        modal = ctk.CTkToplevel(self.root)
        modal.title(title)
        modal.transient(self.root)
        modal.grab_set()
        modal.resizable(False, False)
        modal.configure(fg_color=THEME["window"])
        modal.attributes("-topmost", True)  # 设置弹窗始终在最上层

        width = 470
        height = 260
        self._center_modal(modal, width, height)
        modal.after(10, lambda: self._center_modal(modal, width, height))

        body = ctk.CTkFrame(
            modal,
            fg_color=THEME["panel"],
            border_width=1,
            border_color=THEME["border_soft"],
            corner_radius=18,
        )
        body.pack(fill="both", expand=True, padx=18, pady=18)
        body.grid_columnconfigure(1, weight=1)

        icon_box = ctk.CTkFrame(body, width=46, height=46, fg_color=THEME["purple_dark"], corner_radius=12)
        icon_box.grid(row=0, column=0, padx=(18, 14), pady=(20, 8), sticky="n")
        icon_box.grid_propagate(False)
        ctk.CTkLabel(
            icon_box,
            text="?",
            font=(FONT_CN, 20, "bold"),
            text_color=THEME["text"],
        ).place(relx=0.5, rely=0.5, anchor="center")

        text_area = ctk.CTkFrame(body, fg_color="transparent")
        text_area.grid(row=0, column=1, sticky="nsew", padx=(0, 18), pady=(18, 8))

        ctk.CTkLabel(
            text_area,
            text=title,
            font=(FONT_CN, 16, "bold"),
            text_color=THEME["text"],
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            text_area,
            text=message,
            font=(FONT_CN, 13),
            text_color=THEME["muted"],
            justify="left",
            wraplength=330,
            anchor="w",
        ).pack(anchor="w", pady=(10, 0))

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=1, column=0, columnspan=2, sticky="e", padx=18, pady=(8, 18))

        def choose(value):
            result["value"] = value
            modal.destroy()

        no_btn = self._make_button(
            actions,
            no_text,
            THEME["card_hover"],
            lambda: choose(False),
            height=38,
            width=118,
        )
        no_btn.pack(side="left", padx=(0, 10))

        yes_btn = self._make_button(
            actions,
            yes_text,
            THEME["purple"],
            lambda: choose(True),
            height=38,
            width=128,
        )
        yes_btn.pack(side="left")

        modal.bind("<Escape>", lambda _event: choose(False))
        modal.bind("<Return>", lambda _event: choose(True))
        modal.lift()  # 确保弹窗在最上方
        modal.focus_force()
        modal.wait_window()
        return result["value"]

    def _make_button(self, parent, text, color, command, height=48, width=None, state="normal"):
        return ctk.CTkButton(
            parent,
            text=text,
            height=height,
            width=width or 120,
            corner_radius=12,
            fg_color=color,
            hover_color=self._lighten(color, 0.10),
            text_color=THEME["text"],
            font=(FONT_CN, 14, "bold"),
            command=command,
            state=state,
        )

    @staticmethod
    def _lighten(hex_color, amount=0.10):
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r = min(255, int(r + (255 - r) * amount))
        g = min(255, int(g + (255 - g) * amount))
        b = min(255, int(b + (255 - b) * amount))
        return f"#{r:02x}{g:02x}{b:02x}"

    # =====================
    # 任务管理
    # =====================
    def add_task(self):
        task = self.task_entry.get().strip()
        urgency = self.urgency_combo.get()
        if not task:
            self.show_dialog("提示", "请输入任务内容！", kind="warning")
            return

        self.tasks.append({"id": self._generate_task_id(), "task": task, "urgency": urgency})
        self.save_tasks()
        self.refresh_list()
        self.task_entry.delete(0, "end")

    def delete_task(self):
        if not self.selected_task_ids:
            return

        selected_ids = {int(item) for item in self.selected_task_ids}
        self.tasks = [task for task in self.tasks if int(task["id"]) not in selected_ids]
        self.selected_task_ids.clear()
        self.save_tasks()
        self.refresh_list()

    def toggle_task_selection(self, task_id):
        task_id = int(task_id)
        if task_id in self.selected_task_ids:
            self.selected_task_ids.remove(task_id)
        else:
            self.selected_task_ids.add(task_id)
        self._render_task_selection()

    def _render_task_selection(self):
        for task_id, widgets in self.task_rows.items():
            selected = int(task_id) in self.selected_task_ids
            bg = THEME["purple_dark"] if selected else widgets["normal_bg"]
            for widget in widgets["widgets"]:
                widget.configure(fg_color=bg)
            for label in widgets["labels"]:
                label.configure(text_color=THEME["text"] if selected else label._normal_text_color)

    def refresh_list(self):
        if not hasattr(self, "task_scroll"):
            return

        for child in self.task_scroll.winfo_children():
            child.destroy()

        self.task_rows = {}
        self.selected_task_ids = {
            int(task_id)
            for task_id in self.selected_task_ids
            if any(int(t.get("id", 0)) == int(task_id) for t in self.tasks)
        }

        sorted_tasks = sorted(
            self.tasks,
            key=lambda task: (
                URGENCY_ORDER.get(task.get("urgency", "🟡 一般"), len(URGENCY_ORDER)),
                int(task.get("id", 0)),
            ),
        )

        if not sorted_tasks:
            empty = ctk.CTkFrame(
                self.task_scroll,
                fg_color=THEME["panel_soft"],
                corner_radius=12,
            )
            empty.grid(row=0, column=0, columnspan=2, sticky="ew", pady=18)
            ctk.CTkLabel(
                empty,
                text="暂无任务。添加一项任务后即可开始心流。",
                font=(FONT_CN, 15),
                text_color=THEME["muted_2"],
            ).pack(pady=18)
            return

        for row_index, task_item in enumerate(sorted_tasks):
            task_id = int(task_item["id"])
            normal_bg = THEME["card"] if row_index % 2 == 0 else "#0F1832"

            row = ctk.CTkFrame(
                self.task_scroll,
                fg_color=normal_bg,
                corner_radius=12,
                height=44,
            )
            row.grid(row=row_index, column=0, columnspan=2, sticky="ew", pady=5)
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, minsize=190)
            row.bind("<Button-1>", lambda _event, tid=task_id: self.toggle_task_selection(tid))

            task_label = ctk.CTkLabel(
                row,
                text=task_item.get("task", ""),
                font=(FONT_CN, 15),
                text_color=THEME["text"],
                anchor="w",
            )
            task_label._normal_text_color = THEME["text"]
            task_label.grid(row=0, column=0, sticky="ew", padx=18, pady=10)
            task_label.bind("<Button-1>", lambda _event, tid=task_id: self.toggle_task_selection(tid))

            urgency = task_item.get("urgency", "🟡 一般")
            urgency_color = {
                "🔴 紧急": THEME["red"],
                "🟡 一般": THEME["amber"],
                "🟢 宽松": THEME["green"],
            }.get(urgency, THEME["muted"])

            urgency_label = ctk.CTkLabel(
                row,
                text=urgency,
                font=(FONT_CN, 14, "bold"),
                text_color=urgency_color,
                anchor="center",
            )
            urgency_label._normal_text_color = urgency_color
            urgency_label.grid(row=0, column=1, sticky="ew", padx=18, pady=10)
            urgency_label.bind("<Button-1>", lambda _event, tid=task_id: self.toggle_task_selection(tid))

            self.task_rows[task_id] = {
                "widgets": [row],
                "labels": [task_label, urgency_label],
                "normal_bg": normal_bg,
            }

        self._render_task_selection()

    def _generate_task_id(self):
        task_id = self.task_id_counter
        self.task_id_counter += 1
        return task_id

    def load_tasks(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    loaded_tasks = json.load(f)
            except (json.JSONDecodeError, OSError):
                loaded_tasks = []

            if isinstance(loaded_tasks, list):
                normalized_tasks = []
                max_task_id = 0
                for index, task in enumerate(loaded_tasks, start=1):
                    if isinstance(task, dict):
                        task_id = int(task.get("id", index))
                        normalized_tasks.append({
                            "id": task_id,
                            "task": task.get("task", ""),
                            "urgency": task.get("urgency", "🟡 一般"),
                        })
                        max_task_id = max(max_task_id, task_id)
                self.tasks = normalized_tasks
                self.task_id_counter = max_task_id + 1 if max_task_id else 1
                self.save_tasks()
            else:
                self.tasks = []

    def save_tasks(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.tasks, f, ensure_ascii=False, indent=4)

    # =====================
    # 统计
    # =====================
    def sync_daily_flow_counter(self):
        today = datetime.now().date().isoformat()
        if self.flow_count_date != today:
            self.flow_count_date = today
            self.flow_daily_count = 0
            self.update_flow_stats_display()
            self.save_flow_stats()

    def load_flow_stats(self):
        today = datetime.now().date().isoformat()
        stats = {"total_count": 0, "daily_count": 0, "date": today}

        if os.path.exists(STATS_FILE):
            try:
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    loaded_stats = json.load(f)
                if isinstance(loaded_stats, dict):
                    stats.update(loaded_stats)
            except (json.JSONDecodeError, OSError):
                pass

        if stats.get("date") != today:
            stats["daily_count"] = 0
            stats["date"] = today

        self.flow_total_count = int(stats.get("total_count", 0))
        self.flow_daily_count = int(stats.get("daily_count", 0))
        self.flow_count_date = stats.get("date", today)
        self.update_flow_stats_display()

    def save_flow_stats(self):
        payload = {
            "total_count": self.flow_total_count,
            "daily_count": self.flow_daily_count,
            "date": self.flow_count_date,
        }
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)

    def update_flow_stats_display(self):
        if hasattr(self, "total_count_label"):
            self.total_count_label.configure(text=str(self.flow_total_count))
        if hasattr(self, "daily_count_label"):
            self.daily_count_label.configure(text=str(self.flow_daily_count))

    def record_completed_flow(self):
        self.sync_daily_flow_counter()
        self.flow_total_count += 1
        self.flow_daily_count += 1
        self.update_flow_stats_display()
        self.save_flow_stats()

    # =====================
    # 心流控制
    # =====================
    def start_flow(self):
        self.sync_daily_flow_counter()

        self.state = "FLOW"
        self.flow_start_time = time.time()
        self.accumulated_flow_time = 0
        self.eye_care_reminded = False
        self.cycle_completed = False

        self.status_label.configure(text="当前状态：深度工作中", text_color=THEME["green"])
        self.timer_label.configure(text_color=THEME["green"])

        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="⏸  暂停休息", command=self.pause_flow_manual)
        self.btn_stop.configure(state="normal", text="■  停止", command=self.stop_flow)

    def resume_flow(self):
        self.sync_daily_flow_counter()
        if getattr(self, "cycle_completed", False):
            self.accumulated_flow_time = 0
            self.cycle_completed = False
            self._update_progress_bar(0)

        self.state = "FLOW"
        self.flow_start_time = time.time()
        self.eye_care_reminded = False

        self.status_label.configure(text="当前状态：深度工作中", text_color=THEME["green"])
        self.timer_label.configure(text_color=THEME["green"])

        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="⏸  暂停休息", command=self.pause_flow_manual)
        self.btn_stop.configure(state="normal", text="■  停止", command=self.stop_flow)

    def start_pause(self):
        self.state = "PAUSE"
        self.pause_start_time = time.time()
        self.pause_reminded = False

        self.status_label.configure(text="当前状态：休息中", text_color=THEME["amber"])
        self.timer_label.configure(text_color=THEME["amber"])

        self.btn_start.configure(state="normal", text="▶  恢复心流", command=self.resume_flow)
        self.btn_pause.configure(state="disabled")
        self.btn_stop.configure(state="disabled")

    def pause_flow_manual(self):
        self.accumulated_flow_time += time.time() - self.flow_start_time
        self.start_pause()

    def start_review(self):
        self.state = "REVIEW"
        self.review_start_time = time.time()
        self.review_auto_stopped_flag = False

        self.status_label.configure(text="当前状态：复盘中", text_color=THEME["purple_2"])
        self.timer_label.configure(text_color=THEME["purple_2"])

        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="■  结束复盘", command=self.finish_review)
        self.btn_stop.configure(state="disabled")

    def finish_review(self):
        self.state = "PAUSE"
        self.pause_start_time = time.time()
        self.pause_reminded = False

        self.status_label.configure(text="当前状态：休息中", text_color=THEME["amber"])
        self.timer_label.configure(text_color=THEME["amber"])

        self.btn_start.configure(state="normal", text="▶  恢复心流", command=self.resume_flow)
        self.btn_pause.configure(state="disabled")
        self.btn_stop.configure(state="disabled")

    def stop_flow(self):
        self.state = "IDLE"
        self.accumulated_flow_time = 0

        self.status_label.configure(text="当前状态：待命", text_color=THEME["text"])
        self.timer_label.configure(text="00:00:00", text_color=THEME["purple_2"])

        self.btn_start.configure(state="normal", text="▶  开始心流", command=self.start_flow)
        self.btn_pause.configure(state="disabled")
        self.btn_stop.configure(state="disabled")
        self._update_progress_bar(0)

    def format_time(self, seconds):
        mins, secs = divmod(int(seconds), 60)
        hours, mins = divmod(mins, 60)
        return f"{hours:02d}:{mins:02d}:{secs:02d}"

    def _update_progress_bar(self, ratio):
        ratio = max(0, min(float(ratio), 1))
        if hasattr(self, "progress_bar"):
            self.progress_bar.set(ratio)
        if hasattr(self, "progress_percent_label"):
            self.progress_percent_label.configure(text=f"{int(ratio * 100)}%")

    def tick(self):
        now = time.time()
        self.sync_daily_flow_counter()

        if self.state == "FLOW":
            current_flow = now - self.flow_start_time
            total_flow = self.accumulated_flow_time + current_flow
            self.timer_label.configure(text=self.format_time(total_flow))

            progress_percentage = min(total_flow / (FLOW_AUTO_STOP_MINUTES * 60), 1.0)
            self._update_progress_bar(progress_percentage)

            if total_flow >= FLOW_AUTO_STOP_MINUTES * 60 and not self.eye_care_reminded:
                self.cycle_completed = True
                self.eye_care_reminded = True
                self.accumulated_flow_time = total_flow
                self.record_completed_flow()

                result = self.ask_dialog(
                    "护眼提醒 & 心流周期完成",
                    f"你已经连续专注 {FLOW_AUTO_STOP_MINUTES} 分钟了！\n\n是否进行学习复盘？\n\n选择“是”进入复盘模式，最长 {MAX_REVIEW_MINUTES} 分钟；选择“否”直接进入休息。",
                    yes_text="开始复盘",
                    no_text="直接休息",
                )

                if result:
                    self.start_review()
                else:
                    self.start_pause()

        elif self.state == "REVIEW":
            review_time = now - self.review_start_time
            self.timer_label.configure(text=self.format_time(review_time))

            if review_time >= MAX_REVIEW_MINUTES * 60 and not self.review_auto_stopped_flag:
                self.review_auto_stopped_flag = True

                self.show_dialog(
                    "复盘时间到",
                    f"复盘时间已达 {MAX_REVIEW_MINUTES} 分钟，即将进入休息模式。",
                    kind="info",
                )
                self.finish_review()

        elif self.state == "PAUSE":
            pause_time_spent = now - self.pause_start_time
            time_left = (MAX_PAUSE_MINUTES * 60) - pause_time_spent

            if time_left > 0:
                self.timer_label.configure(text="-" + self.format_time(time_left))
            else:
                self.timer_label.configure(text="超前 00:00:00", text_color=THEME["red"])

                if not self.pause_reminded:
                    self.pause_reminded = True
                    bring_window_to_front(self.root)
                    self.show_dialog(
                        "休息结束",
                        "休息时间已经结束！\n\n请立即停止娱乐活动，回到电脑前继续点击“恢复心流”完成你的任务。",
                        kind="warning",
                    )

                    self.state = "IDLE"
                    self.status_label.configure(text="当前状态：待命", text_color=THEME["text"])
                    self.timer_label.configure(text="00:00:00", text_color=THEME["purple_2"])
                    self.btn_start.configure(state="normal", text="▶  开始心流", command=self.start_flow)
                    self.btn_pause.configure(state="disabled")
                    self.btn_stop.configure(state="disabled")
                    self._update_progress_bar(0)
                    self.accumulated_flow_time = 0
                    self.cycle_completed = False

        self.root.after(1000, self.tick)


if __name__ == "__main__":
    enable_high_dpi_awareness()
    root = ctk.CTk()
    app = TodoApp(root)
    root.mainloop()
