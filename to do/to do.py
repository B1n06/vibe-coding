import tkinter as tk
from tkinter import ttk, messagebox
import time
from datetime import datetime
import json
import os
import ctypes
from ctypes import wintypes
from tkinter import Canvas

# --- 颜色主题定义 ---
THEME = {
    "bg_main": "#0f1419",      # 深色背景
    "bg_secondary": "#1a1f26", # 次级背景
    "bg_highlight": "#252c36", # 高亮背景
    "accent_primary": "#6366f1",    # 紫色主色
    "accent_secondary": "#8b5cf6",  # 紫色次色
    "text_primary": "#ffffff",      # 白色文本
    "text_secondary": "#a0aec0",    # 灰色文本
    "success": "#10b981",           # 绿色
    "warning": "#f59e0b",           # 橙色
    "danger": "#ef4444",            # 红色
    "progress_bg": "#1e293b",       # 进度条背景
}

URGENCY_ORDER = {
    "🔴 紧急": 0,
    "🟡 一般": 1,
    "🟢 宽松": 2,
}

# --- 配置参数 ---
EYE_CARE_MINUTES = 45      # 用眼健康提醒：连续心流专注多少分钟后提醒
FLOW_AUTO_STOP_MINUTES = 45 # 心流自动停止时间（触发复盘选项）
MAX_REVIEW_MINUTES = 10    # 复盘最长时间
MAX_PAUSE_MINUTES = 15     # 休息/娱乐限制时间
DATA_FILE = "tasks.json"   # 待办事项保存文件
STATS_FILE = "flow_stats.json"  # 心流统计文件

# --- Windows API 工具函数 ---
def bring_window_to_front(root=None):
    """强制将消息框窗口置顶到最前面。
    如果提供了 `root`（tk 根窗口），会短暂把它设为 topmost。
    """
    try:
        if root is not None:
            root.attributes("-topmost", True)
            root.update()
            root.attributes("-topmost", False)
        else:
            # 回退方案：把当前前台窗口再设为前台
            hwnd = ctypes.windll.kernel32.GetForegroundWindow()
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except:
        pass

class TodoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("心流与待办助手")
        self.root.geometry("800x700")
        self.root.resizable(True, True)
        
        # 设置窗口背景颜色
        self.root.configure(bg=THEME["bg_main"])
        
        # 状态管理：IDLE(空闲), FLOW(心流中), REVIEW(复盘中), PAUSE(暂停休息中)
        self.state = "IDLE" 
        self.flow_start_time = 0
        self.accumulated_flow_time = 0
        self.eye_care_reminded = False
        
        # 复盘相关
        self.review_start_time = 0
        self.review_auto_stopped_flag = False
        
        # 休息相关
        self.pause_start_time = 0
        self.pause_reminded = False

        # 循环控制：标记一次心流周期是否已完成（达到45分钟并进入复盘/休息）
        self.cycle_completed = False

        # 统计信息：总次数和每日次数
        self.flow_total_count = 0
        self.flow_daily_count = 0
        self.flow_count_date = datetime.now().date().isoformat()

        # 任务 ID 计数器，保证删除时能稳定定位到具体任务
        self.task_id_counter = 1

        self.tasks = []
        self.load_tasks()
        self.load_flow_stats()
        self.setup_ui()
        
        # 启动UI界面的时钟刷新
        self.root.after(1000, self.tick)

    def setup_ui(self):
        """设置现代化、高级的用户界面"""
        # 创建主容器
        main_container = tk.Frame(self.root, bg=THEME["bg_main"])
        main_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        # ========== 1. 顶部心流控制面板 ==========
        control_frame = tk.Frame(main_container, bg=THEME["bg_secondary"], height=300)
        control_frame.pack(fill=tk.X, padx=0, pady=0)
        control_frame.pack_propagate(False)
        
        # 添加视觉分隔线
        separator1 = tk.Frame(main_container, bg=THEME["accent_primary"], height=3)
        separator1.pack(fill=tk.X, padx=0, pady=0)
        
        # === 状态显示 ===
        status_inner = tk.Frame(control_frame, bg=THEME["bg_secondary"])
        status_inner.pack(fill=tk.X, padx=25, pady=(15, 10))
        
        self.status_label = tk.Label(
            status_inner, 
            text="当前状态: 待命", 
            font=("微软雅黑", 13, "bold"),
            bg=THEME["bg_secondary"],
            fg=THEME["text_primary"]
        )
        self.status_label.pack(side=tk.LEFT)
        
        # === 时间显示 ===
        time_frame = tk.Frame(control_frame, bg=THEME["bg_secondary"])
        time_frame.pack(fill=tk.X, padx=25, pady=(0, 15))
        
        self.timer_label = tk.Label(
            time_frame,
            text="00:00:00",
            font=("Arial", 48, "bold"),
            bg=THEME["bg_secondary"],
            fg=THEME["accent_primary"]
        )
        self.timer_label.pack(anchor=tk.W)

        # === 心流次数统计 ===
        stats_frame = tk.Frame(control_frame, bg=THEME["bg_secondary"])
        stats_frame.pack(fill=tk.X, padx=25, pady=(0, 12))

        self.total_count_label = tk.Label(
            stats_frame,
            text="总次数: 0",
            font=("微软雅黑", 10, "bold"),
            bg=THEME["bg_highlight"],
            fg=THEME["text_primary"],
            padx=12,
            pady=6
        )
        self.total_count_label.pack(side=tk.LEFT, padx=(0, 10))

        self.daily_count_label = tk.Label(
            stats_frame,
            text="今日次数: 0",
            font=("微软雅黑", 10, "bold"),
            bg=THEME["bg_highlight"],
            fg=THEME["text_primary"],
            padx=12,
            pady=6
        )
        self.daily_count_label.pack(side=tk.LEFT)
        
        # === 进度条 ===
        progress_frame = tk.Frame(control_frame, bg=THEME["bg_secondary"])
        progress_frame.pack(fill=tk.X, padx=25, pady=(0, 20))
        
        progress_label = tk.Label(
            progress_frame,
            text="心流进度 (45分钟)",
            font=("微软雅黑", 10),
            bg=THEME["bg_secondary"],
            fg=THEME["text_secondary"]
        )
        progress_label.pack(anchor=tk.W, pady=(0, 8))
        
        # 创建进度条背景
        self.progress_canvas = Canvas(
            progress_frame,
            width=400,
            height=12,
            bg=THEME["progress_bg"],
            highlightthickness=0,
            relief=tk.FLAT
        )
        self.progress_canvas.pack(anchor=tk.W, fill=tk.X)
        self.progress_fill = self.progress_canvas.create_rectangle(0, 0, 0, 12, fill=THEME["accent_primary"], outline="")
        
        # === 按钮组 ===
        btn_frame = tk.Frame(control_frame, bg=THEME["bg_secondary"])
        btn_frame.pack(fill=tk.X, padx=25, pady=(0, 15))
        
        self.btn_start = self._create_button(
            btn_frame, "▶️ 开始心流", THEME["success"], self.start_flow
        )
        self.btn_start.pack(side=tk.LEFT, padx=8)
        
        self.btn_pause = self._create_button(
            btn_frame, "⏸️ 暂停休息", THEME["warning"], lambda: None, state=tk.DISABLED
        )
        self.btn_pause.pack(side=tk.LEFT, padx=8)
        
        self.btn_stop = self._create_button(
            btn_frame, "⏹️ 停止", THEME["danger"], lambda: None, state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=8)
        
        # ========== 2. 输入区域 ==========
        input_frame = tk.Frame(main_container, bg=THEME["bg_main"])
        input_frame.pack(fill=tk.X, padx=25, pady=(20, 15))
        
        tk.Label(
            input_frame, 
            text="新任务:",
            font=("微软雅黑", 10),
            bg=THEME["bg_main"],
            fg=THEME["text_primary"]
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        self.task_entry = tk.Entry(
            input_frame,
            width=30,
            font=("微软雅黑", 10),
            bg=THEME["bg_secondary"],
            fg=THEME["text_primary"],
            insertbackground=THEME["accent_primary"],
            relief=tk.FLAT,
            bd=0
        )
        self.task_entry.pack(side=tk.LEFT, padx=5, ipady=8)
        
        tk.Label(
            input_frame,
            text="紧急程度:",
            font=("微软雅黑", 10),
            bg=THEME["bg_main"],
            fg=THEME["text_primary"]
        ).pack(side=tk.LEFT, padx=(15, 10))
        
        self.urgency_combo = ttk.Combobox(
            input_frame,
            values=["🔴 紧急", "🟡 一般", "🟢 宽松"],
            width=10,
            state="readonly",
            font=("微软雅黑", 9)
        )
        self.urgency_combo.current(1)
        self.urgency_combo.pack(side=tk.LEFT, padx=5)
        
        add_btn = self._create_button(
            input_frame, "➕ 添加", THEME["accent_secondary"], self.add_task
        )
        add_btn.pack(side=tk.LEFT, padx=(15, 0))
        
        # ========== 3. 列表显示区域 ==========
        list_header = tk.Frame(main_container, bg=THEME["bg_main"])
        list_header.pack(fill=tk.X, padx=25, pady=(12, 8))
        
        tk.Label(
            list_header,
            text="📋 待办事项清单",
            font=("微软雅黑", 11, "bold"),
            bg=THEME["bg_main"],
            fg=THEME["text_primary"]
        ).pack(anchor=tk.W)
        
        # 设置Treeview样式
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "Treeview",
            background=THEME["bg_secondary"],
            foreground=THEME["text_primary"],
            fieldbackground=THEME["bg_secondary"],
            font=("微软雅黑", 10)
        )
        style.configure("Treeview.Heading", font=("微软雅黑", 10, "bold"))
        style.map("Treeview", background=[("selected", THEME["accent_primary"])])
        
        task_panel = tk.Frame(main_container, bg=THEME["bg_main"], height=220)
        task_panel.pack(fill=tk.X, padx=25, pady=(0, 10))
        task_panel.pack_propagate(False)

        tree_frame = tk.Frame(task_panel, bg=THEME["bg_main"])
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("Task", "Urgency")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=6,
            style="Treeview"
        )
        self.tree.heading("Task", text="📝 任务描述")
        self.tree.heading("Urgency", text="🎯 优先级")
        self.tree.column("Task", width=500)
        self.tree.column("Urgency", width=100, anchor=tk.CENTER)
        tree_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Delete>", lambda event: self.delete_task())
        
        # 删除按钮
        delete_btn = self._create_button(
            main_container, "🗑️ 删除选中", THEME["danger"], self.delete_task
        )
        delete_btn.pack(pady=(4, 14))
        
        self.refresh_list()
        self.update_flow_stats_display()

    def _create_button(self, parent, text, color, command, state=tk.NORMAL):
        """创建现代化按钮"""
        btn = tk.Button(
            parent,
            text=text,
            font=("微软雅黑", 10, "bold"),
            bg=color,
            fg=THEME["text_primary"],
            command=command,
            state=state,
            relief=tk.FLAT,
            bd=0,
            padx=15,
            pady=8,
            cursor="hand2"
        )
        # 添加hover效果
        def on_enter(event):
            if btn['state'] == tk.NORMAL:
                btn.config(relief=tk.RAISED)
        def on_leave(event):
            btn.config(relief=tk.FLAT)
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn

    # --- 任务管理逻辑 ---
    def add_task(self):
        task = self.task_entry.get().strip()
        urgency = self.urgency_combo.get()
        if not task:
            messagebox.showwarning("提示", "请输入任务内容！")
            return
        self.tasks.append({"id": self._generate_task_id(), "task": task, "urgency": urgency})
        self.save_tasks()
        self.refresh_list()
        self.task_entry.delete(0, tk.END)

    def delete_task(self):
        selected = self.tree.selection()
        if not selected:
            return
        selected_ids = {int(item) for item in selected}
        self.tasks = [task for task in self.tasks if int(task["id"]) not in selected_ids]
        self.save_tasks()
        self.refresh_list()

    def refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        sorted_tasks = sorted(
            self.tasks,
            key=lambda task: (
                URGENCY_ORDER.get(task.get("urgency", "🟡 一般"), len(URGENCY_ORDER)),
                int(task.get("id", 0)),
            ),
        )
        for t in sorted_tasks:
            self.tree.insert("", tk.END, iid=str(t["id"]), values=(t["task"], t["urgency"]))

    def _generate_task_id(self):
        task_id = self.task_id_counter
        self.task_id_counter += 1
        return task_id

    def load_tasks(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded_tasks = json.load(f)

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

                # 将旧格式数据尽快迁移到新格式，避免后续删除异常
                self.save_tasks()
            else:
                self.tasks = []

    def save_tasks(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.tasks, f, ensure_ascii=False, indent=4)

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
        if not hasattr(self, "total_count_label") or not hasattr(self, "daily_count_label"):
            return
        self.total_count_label.config(text=f"总次数: {self.flow_total_count}")
        self.daily_count_label.config(text=f"今日次数: {self.flow_daily_count}")

    def record_completed_flow(self):
        self.sync_daily_flow_counter()
        self.flow_total_count += 1
        self.flow_daily_count += 1
        self.update_flow_stats_display()
        self.save_flow_stats()

    # --- 心流控制逻辑 ---
    def start_flow(self):
        self.sync_daily_flow_counter()
        if not self.tasks:
            messagebox.showinfo("提示", "列表为空，请先添加你要处理的任务再开始心流！")
            return
            
        self.state = "FLOW"
        self.flow_start_time = time.time()
        # 从头开始新的心流周期
        self.accumulated_flow_time = 0
        self.eye_care_reminded = False
        self.cycle_completed = False
        
        self.status_label.config(text="当前状态: 💡 深度工作中 (心流开启)", fg=THEME["success"])
        self.timer_label.config(fg=THEME["success"])
        
        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL, text="⏸️ 暂停休息", command=self.pause_flow_manual)
        self.btn_stop.config(state=tk.NORMAL, text="⏹️ 停止", command=self.stop_flow)

    def resume_flow(self):
        """从休息恢复心流（保留已用时间）"""
        self.sync_daily_flow_counter()
        # 如果上一个周期已完成，则新开一个周期（清零累计时间）
        if getattr(self, 'cycle_completed', False):
            self.accumulated_flow_time = 0
            self.cycle_completed = False
            # 重置进度条
            try:
                self.progress_canvas.coords(self.progress_fill, 0, 0, 0, 12)
            except:
                pass

        self.state = "FLOW"
        self.flow_start_time = time.time()
        self.eye_care_reminded = False
        
        self.status_label.config(text="当前状态: 💡 深度工作中 (心流开启)", fg=THEME["success"])
        self.timer_label.config(fg=THEME["success"])
        
        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL, text="⏸️ 暂停休息", command=self.pause_flow_manual)
        self.btn_stop.config(state=tk.NORMAL, text="⏹️ 停止", command=self.stop_flow)

    def start_pause(self):
        """直接进入休息状态（不复盘）"""
        self.state = "PAUSE"
        self.pause_start_time = time.time()
        self.pause_reminded = False

        self.status_label.config(text=f"当前状态: ☕ 休息中 (限时 {MAX_PAUSE_MINUTES} 分钟)", fg=THEME["warning"])
        self.timer_label.config(fg=THEME["warning"])
        
        self.btn_start.config(state=tk.NORMAL, text="▶️ 恢复心流", command=self.resume_flow)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)

    def pause_flow_manual(self):
        """手动暂停（用户点击暂停按钮）"""
        self.accumulated_flow_time += (time.time() - self.flow_start_time)
        self.start_pause()

    def start_review(self):
        """开始复盘状态"""
        self.state = "REVIEW"
        self.review_start_time = time.time()
        self.review_auto_stopped_flag = False
        
        self.status_label.config(text=f"当前状态: 📝 复盘中 (限时 {MAX_REVIEW_MINUTES} 分钟)", fg=THEME["accent_primary"])
        self.timer_label.config(fg=THEME["accent_primary"])
        
        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL, text="⏹️ 结束复盘", command=self.finish_review)
        self.btn_stop.config(state=tk.DISABLED)

    def finish_review(self):
        """复盘完成，进入休息"""
        self.state = "PAUSE"
        self.pause_start_time = time.time()
        self.pause_reminded = False
        
        self.status_label.config(text=f"当前状态: ☕ 休息中 (限时 {MAX_PAUSE_MINUTES} 分钟)", fg=THEME["warning"])
        self.timer_label.config(fg=THEME["warning"])
        
        self.btn_start.config(state=tk.NORMAL, text="▶️ 恢复心流", command=self.resume_flow)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)

    def stop_flow(self):
        """停止心流（用户点击停止按钮）"""
        self.state = "IDLE"
        self.accumulated_flow_time = 0
        
        self.status_label.config(text="当前状态: 待命", fg=THEME["text_secondary"])
        self.timer_label.config(text="00:00:00", fg=THEME["text_secondary"])
        
        self.btn_start.config(state=tk.NORMAL, text="▶️ 开始心流", command=self.start_flow)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        
        # 重置进度条
        self.progress_canvas.coords(self.progress_fill, 0, 0, 0, 12)

    def format_time(self, seconds):
        mins, secs = divmod(int(seconds), 60)
        hours, mins = divmod(mins, 60)
        return f"{hours:02d}:{mins:02d}:{secs:02d}"

    def tick(self):
        """每一秒执行一次的时钟与后台监控"""
        now = time.time()
        self.sync_daily_flow_counter()

        if self.state == "FLOW":
            # 1. 更新专注时间UI
            current_flow = now - self.flow_start_time
            total_flow = self.accumulated_flow_time + current_flow
            self.timer_label.config(text=self.format_time(total_flow))
            
            # 更新进度条
            progress_percentage = min(total_flow / (FLOW_AUTO_STOP_MINUTES * 60), 1.0)
            canvas_width = self.progress_canvas.winfo_width()
            if canvas_width > 1:  # 避免窗口未完全初始化
                fill_width = canvas_width * progress_percentage
                self.progress_canvas.coords(self.progress_fill, 0, 0, fill_width, 12)
            
            # 2. 检测是否达到45分钟，弹出复盘选项
            if total_flow >= FLOW_AUTO_STOP_MINUTES * 60 and not self.eye_care_reminded:
                # 标记本次心流周期已完成（需要复盘或休息）
                self.cycle_completed = True
                self.eye_care_reminded = True  # 防止重复触发

                # 累加心流时间
                self.accumulated_flow_time = total_flow
                self.record_completed_flow()

                # 确保弹窗在最前面
                try:
                    self.root.attributes("-topmost", True)
                except:
                    pass

                result = messagebox.askyesno(
                    "🌿 护眼提醒 & 心流周期完成",
                    f"您已经连续专注 {FLOW_AUTO_STOP_MINUTES} 分钟了！\n\n是否进行学习复盘？\n\n（选择是则进入复盘模式，最长 {MAX_REVIEW_MINUTES} 分钟；选择否则直接进入休息）",
                    parent=self.root
                )

                try:
                    self.root.attributes("-topmost", False)
                except:
                    pass

                if result:
                    # 选择复盘
                    self.start_review()
                else:
                    # 不复盘，直接进入休息
                    self.start_pause()

        elif self.state == "REVIEW":
            # 1. 显示复盘时间
            review_time = now - self.review_start_time
            self.timer_label.config(text=self.format_time(review_time))
            
            # 2. 检测是否达到10分钟，自动结束复盘
            if review_time >= MAX_REVIEW_MINUTES * 60 and not self.review_auto_stopped_flag:
                self.review_auto_stopped_flag = True
                try:
                    self.root.attributes("-topmost", True)
                except:
                    pass

                messagebox.showinfo(
                    "⏱️ 复盘时间到",
                    f"复盘时间已达 {MAX_REVIEW_MINUTES} 分钟，即将进入休息模式。",
                    parent=self.root
                )

                try:
                    self.root.attributes("-topmost", False)
                except:
                    pass
                self.finish_review()

        elif self.state == "PAUSE":
            # 1. 倒计时休息时间
            pause_time_spent = now - self.pause_start_time
            time_left = (MAX_PAUSE_MINUTES * 60) - pause_time_spent
            
            if time_left > 0:
                self.timer_label.config(text="-" + self.format_time(time_left))
            else:
                self.timer_label.config(text="超前 00:00:00", fg="red")
                
                # 2. 防沉迷提醒（休息时间结束）
                if not self.pause_reminded:
                    self.pause_reminded = True
                    bring_window_to_front()
                    self.root.attributes("-topmost", True)
                    messagebox.showwarning(
                        "⚠️ 休息结束",
                        "休息时间已经结束！\n\n请立即停止娱乐活动，回到电脑前继续点击'恢复心流'完成你的任务。",
                        parent=self.root
                    )
                    self.root.attributes("-topmost", False)
                    
                    # 自动回到IDLE状态
                    self.state = "IDLE"
                    self.status_label.config(text="当前状态: 待命", fg=THEME["text_secondary"])
                    self.timer_label.config(text="00:00:00", fg=THEME["text_secondary"])
                    self.btn_start.config(state=tk.NORMAL, text="▶️ 开始心流")
                    self.btn_pause.config(state=tk.DISABLED)
                    self.btn_stop.config(state=tk.DISABLED)
                    # 重置进度条
                    self.progress_canvas.coords(self.progress_fill, 0, 0, 0, 12)
                    # 清理累计时间，允许下一次心流为全新周期
                    self.accumulated_flow_time = 0
                    self.cycle_completed = False

        # 循环调用自身
        self.root.after(1000, self.tick)


if __name__ == "__main__":
    root = tk.Tk()
    app = TodoApp(root)
    root.mainloop()