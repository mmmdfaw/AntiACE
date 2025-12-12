import sys
import os
import time
import threading
import warnings
import win32api
import win32process
import win32con
import win32gui
import win32event
import winerror
import psutil
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QSystemTrayIcon,
                             QMenu, QMessageBox, QCheckBox, QGroupBox, QComboBox, QStyle)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QIcon, QFont, QColor, QPalette, QPixmap, QPainter
import ctypes
from ctypes import wintypes



# 管理员权限检查
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


class MonitorThread(QThread):
    """监控线程"""

    status_update = pyqtSignal(str, bool, str)
    interval_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.processes_to_monitor = ["SGuard64.exe", "SGuardSvc64.exe"]
        self.low_priority = win32process.IDLE_PRIORITY_CLASS
        self.check_interval = 2
        self.running = False
        self.lock = threading.Lock()

    def set_check_interval(self, interval):
        with self.lock:
            self.check_interval = interval

    def get_process_by_name(self, name):
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] and proc.info['name'].lower() == name.lower():
                    return proc
        except:
            pass
        return None

    def set_process_priority(self, pid, priority_class):
        try:
            handle = win32api.OpenProcess(win32con.PROCESS_SET_INFORMATION, False, pid)
            win32process.SetPriorityClass(handle, priority_class)
            win32api.CloseHandle(handle)
            return True
        except:
            return False

    def set_process_affinity(self, pid, affinity_mask):
        try:
            handle = win32api.OpenProcess(win32con.PROCESS_SET_INFORMATION, False, pid)
            win32process.SetProcessAffinityMask(handle, affinity_mask)
            win32api.CloseHandle(handle)
            return True
        except:
            return False

    def get_last_cpu_mask(self):
        try:
            cpu_count = psutil.cpu_count(logical=True)
            if cpu_count > 0:
                return 1 << (cpu_count - 1)
        except:
            pass
        return 1

    def check_and_fix_process(self, process_name):
        proc = self.get_process_by_name(process_name)
        if not proc:
            return False, f"{process_name}: 未运行"

        pid = proc.info['pid']
        fix_applied = False

        try:
            handle = win32api.OpenProcess(
                win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_SET_INFORMATION,
                False,
                pid
            )

            # 检查优先级
            try:
                current_priority = win32process.GetPriorityClass(handle)
                if current_priority != self.low_priority:
                    if self.set_process_priority(pid, self.low_priority):
                        fix_applied = True
            except:
                pass

            # 检查CPU亲和性
            try:
                current_affinity = win32process.GetProcessAffinityMask(handle)[0]
                target_affinity = self.get_last_cpu_mask()
                if current_affinity != target_affinity:
                    if self.set_process_affinity(pid, target_affinity):
                        fix_applied = True
            except:
                pass

            win32api.CloseHandle(handle)

            if fix_applied:
                return True, f"{process_name}: ✨ 修改中"
            else:
                return True, f"{process_name}: ✓ 修改成功"
        except:
            return True, f"{process_name}: ✗ 访问失败"

    def run(self):
        self.running = True
        while self.running:
            for process_name in self.processes_to_monitor:
                running, status = self.check_and_fix_process(process_name)
                self.status_update.emit(process_name, running, status)

            with self.lock:
                interval = self.check_interval
            self.msleep(interval * 1000)

    def stop(self):
        self.running = False
        self.wait()


class ProcessMonitorWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        if not is_admin():
            self.show_admin_warning()
            return

        self.monitor_thread = MonitorThread()
        self.tray_icon = None
        self.minimize_to_tray = True

        self.init_ui()
        self.setup_tray_icon()
        self.start_monitoring()

        # 确保在任务栏显示
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)

    def show_admin_warning(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("权限错误")
        msg.setText("需要此管理员权限运行程序！")
        msg.setInformativeText("请右键点击程序，选择'以管理员身份运行'。")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.buttonClicked.connect(sys.exit)
        msg.exec_()

    def create_tray_icon(self):
        """创建托盘图标（使用内置图标）"""
        # 使用PyQt5内置图标
        from PyQt5.QtWidgets import QStyle
        from PyQt5.QtGui import QIcon

        # 方法1: 使用系统图标
        style = self.style()
        icon = style.standardIcon(QStyle.SP_ComputerIcon)

        # 或者使用其他内置图标：
        # icon = style.standardIcon(QStyle.SP_DriveHDIcon)  # 硬盘图标
        # icon = style.standardIcon(QStyle.SP_DesktopIcon)  # 桌面图标
        # icon = style.standardIcon(QStyle.SP_MessageBoxInformation)  # 信息图标

        return icon

    def init_ui(self):
        self.setWindowTitle("缓解ACE扫盘工具")
        self.setGeometry(300, 300, 500, 400)

        # 创建自定义托盘图标
        self.setWindowIcon(self.create_tray_icon())

        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QLabel#title {
                font-size: 20px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #1c6ea4;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # 标题
        title_label = QLabel("🔍 缓解ACE扫盘工具")
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # 进程状态显示
        self.status_labels = {}
        for i, process_name in enumerate(["SGuard64.exe", "SGuardSvc64.exe"]):
            group = QGroupBox(f"进程 {i + 1}: {process_name}")
            group_layout = QVBoxLayout()

            status_label = QLabel("正在检测...")
            status_label.setFont(QFont("Arial", 10))
            status_label.setWordWrap(True)
            group_layout.addWidget(status_label)
            group.setLayout(group_layout)
            layout.addWidget(group)

            self.status_labels[process_name] = status_label

        # 控制面板
        control_group = QGroupBox("控制面板")
        control_layout = QVBoxLayout()



        # 托盘选项
        tray_layout = QHBoxLayout()
        self.tray_cb = QCheckBox("关闭窗口时隐藏到托盘")
        self.tray_cb.setChecked(True)
        tray_layout.addWidget(self.tray_cb)
        tray_layout.addStretch()
        control_layout.addLayout(tray_layout)

        # 按钮
        button_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("🔄 立即刷新")
        self.refresh_btn.clicked.connect(self.manual_refresh)

        self.about_btn = QPushButton("ℹ️ 关于")
        self.about_btn.clicked.connect(self.show_about)


        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.about_btn)
        button_layout.addStretch()

        control_layout.addLayout(button_layout)
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)


    def setup_tray_icon(self):
        """设置系统托盘图标"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("系统托盘不可用")
            return

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.create_tray_icon())

        # 创建托盘菜单
        tray_menu = QMenu()

        show_action = tray_menu.addAction("显示主窗口")
        show_action.triggered.connect(self.show_normal)

        tray_menu.addSeparator()



        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_clicked)

        # 显示托盘图标
        self.tray_icon.show()
        self.tray_icon.setToolTip("缓解ACE扫盘工具\n正在后台运行")

        # 显示通知
        self.tray_icon.showMessage(
            "缓解ACE扫盘工具",
            "程序已启动并将在后台运行",
            QSystemTrayIcon.Information,
            2000
        )

    def start_monitoring(self):
        self.monitor_thread.status_update.connect(self.update_status_ui)
        self.monitor_thread.start()

    def update_status_ui(self, process_name, is_running, status):
        if process_name in self.status_labels:
            if "✨" in status:
                color = "#e67e22"
            elif "✓" in status:
                color = "#27ae60"
            elif "✗" in status:
                color = "#e74c3c"
            else:
                color = "#2c3e50"

            self.status_labels[process_name].setText(status)
            self.status_labels[process_name].setStyleSheet(f"color: {color}; padding: 5px;")

    def manual_refresh(self):
        for process_name in ["SGuard64.exe", "SGuardSvc64.exe"]:
            running, status = self.monitor_thread.check_and_fix_process(process_name)
            self.update_status_ui(process_name, running, status)

    def change_check_interval(self, interval_str):
        try:
            interval = int(interval_str)
            self.monitor_thread.set_check_interval(interval)
        except:
            pass

    def show_about(self):
        about_text = """
        <p>缓解ACE扫盘工具</p>

        <p><b>功能：</b></p>
        <ul>
        <li>监控SGuard进程运行状态</li>
        <li>自动调整进程优先级为低</li>
        <li>自动设置CPU相关性为最后一个核</li>
        <li>支持后台托盘运行</li>
        </ul>

        <p>©<a href=\"https://github.com/mmmdfaw/AntiACE\">开源链接</a></p>
        """

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("关于")
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(about_text)
        msg_box.setTextInteractionFlags(Qt.TextBrowserInteraction)
        msg_box.exec()

    def tray_icon_clicked(self, reason):
        """托盘图标被点击"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_normal()

    def show_normal(self):
        """显示主窗口"""
        self.show()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        """关闭窗口事件处理"""
        if self.tray_cb.isChecked() and self.tray_icon is not None:
            # 最小化到托盘
            self.hide()
            event.ignore()
        else:
            # 直接退出
            self.quit_application()

    def quit_application(self):
        """退出程序"""
        if self.monitor_thread:
            self.monitor_thread.stop()
        if self.tray_icon:
            self.tray_icon.hide()
        QApplication.quit()


def main():
    # 高DPI支持
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("缓解ACE扫盘工具")
    app.setQuitOnLastWindowClosed(False)  # 重要：不自动退出

    window = ProcessMonitorWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()