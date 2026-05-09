import sys
import random
import math
import time
import threading
import subprocess
import ctypes
import winsound
import winreg
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QMenu, QLabel, QInputDialog, QFileDialog,
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QLineEdit, QMessageBox
)
from PySide6.QtCore import QTimer, Qt, QPoint
from PySide6.QtGui import QPixmap, QAction, QPainter
from PIL import ImageQt

from animator import PetAnimator
from config import Config


UPDATE_INTERVAL_MS = 16
BEHAVIOR_INTERVAL_MS = 100
NO_INTERACTION_TIMEOUT_MS = 15000
LOCKED_IDLE_TIMEOUT_MS = 30000
LOCKED_FAILED_DURATION_MS = 10000
REVIEW_DURATION_MS = 2000
FLING_THRESHOLD = 8.0
FLING_FRICTION = 0.98
BASE_W = 192
BASE_H = 208
PEEK_PIXELS = 18


class DeskPet(QWidget):
    def __init__(self, animator: PetAnimator, config: Config, parent=None):
        super().__init__(parent)
        self.animator = animator
        self.config = config

        self.setWindowFlags(
            Qt.SplashScreen
            | Qt.FramelessWindowHint
            | Qt.NoDropShadowWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)

        saved_scale = config.get("scale", 0.5)
        self._scale = saved_scale
        self._resize_window()

        self._current_pixmap = QPixmap()

        screen = QApplication.primaryScreen().availableGeometry()
        self._screen = screen
        saved_x = config.get("pos_x")
        saved_y = config.get("pos_y")
        if saved_x is not None and saved_y is not None:
            self._pos_x = saved_x
            self._pos_y = saved_y
        else:
            self._pos_x = (screen.width() - self._win_w()) // 2
            self._pos_y = screen.height() - self._win_h() - 40
        self.move(int(self._pos_x), int(self._pos_y))

        self._vx = 0.0
        self._vy = 0.0
        self._speed = 2.5
        self._behavior = "idle"
        self._behavior_timer = 0.0
        self._next_behavior_change = random.uniform(2000, 5000)
        self._jump_start_y = 0.0

        self._locked = False
        self._is_dragging = False
        self._drag_pos = None
        self._drag_last_x = 0
        self._hovered = False
        self._last_interaction_time = time.time()
        self._fling_vx = 0.0
        self._fling_vy = 0.0
        self._post_review_vx = 0.0
        self._post_review_vy = 0.0

        # Focus / pomodoro state
        self._focus_active = False
        self._focus_seconds = 0
        self._focus_task = ""
        self._focus_timer = QTimer(self)
        self._focus_timer.timeout.connect(self._focus_tick)

        # Head label: shows time + notes + focus on hover
        self._head_label = QLabel()
        self._head_label.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint
        )
        self._head_label.setAutoFillBackground(True)
        self._head_label.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #333333;
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        self._head_label.setWordWrap(True)
        self._head_label.setAlignment(Qt.AlignCenter)
        self._head_label.hide()

        self._head_timer = QTimer(self)
        self._head_timer.timeout.connect(self._refresh_head)
        self._head_timer.start(1000)

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._update_anim)
        self._anim_timer.start(UPDATE_INTERVAL_MS)

        self._behav_timer = QTimer(self)
        self._behav_timer.timeout.connect(self._update_behavior)
        self._behav_timer.start(BEHAVIOR_INTERVAL_MS)

        self._update_display()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def _win_w(self) -> int:
        return int(BASE_W * self._scale)

    def _win_h(self) -> int:
        return int(BASE_H * self._scale)

    def _resize_window(self):
        self.setFixedSize(self._win_w(), self._win_h())

    def set_scale(self, scale: float):
        self._scale = max(0.25, min(scale, 3.0))
        self.config.set("scale", self._scale)
        self._resize_window()
        self._update_display()
        self._apply_bounds()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _update_anim(self):
        if self._behavior == "fling":
            self._update_fling()
        dt = UPDATE_INTERVAL_MS
        if self._locked or self._behavior == "idle":
            dt = int(dt * 0.5)
        self.animator.update(dt)
        self._update_display()

    def _update_display(self):
        pil_image = self.animator.current_frame()
        qt_image = ImageQt.ImageQt(pil_image)
        pixmap = QPixmap.fromImage(qt_image).scaled(
            self._win_w(), self._win_h(),
            Qt.KeepAspectRatio, Qt.FastTransformation,
        )
        self._current_pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self._current_pixmap.isNull():
            painter.drawPixmap(0, 0, self._current_pixmap)
        painter.end()

    def showEvent(self, event):
        super().showEvent(event)
        self._remove_dwm_border()
        QTimer.singleShot(100, self._remove_dwm_border)

    def _remove_dwm_border(self):
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi

            GWL_EXSTYLE = -20
            WS_EX_CLIENTEDGE = 0x00000200
            WS_EX_WINDOWEDGE = 0x00000100
            WS_EX_STATICEDGE = 0x00020000
            WS_EX_DLGMODALFRAME = 0x00000001
            exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            exstyle &= ~WS_EX_CLIENTEDGE
            exstyle &= ~WS_EX_WINDOWEDGE
            exstyle &= ~WS_EX_STATICEDGE
            exstyle &= ~WS_EX_DLGMODALFRAME
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, exstyle)

            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            WS_BORDER = 0x00800000
            WS_DLGFRAME = 0x00400000
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style &= ~WS_CAPTION
            style &= ~WS_THICKFRAME
            style &= ~WS_BORDER
            style &= ~WS_DLGFRAME
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)

            DWMWA_NCRENDERING_POLICY = 2
            DWMNCRP_DISABLED = 2
            policy = ctypes.c_int(DWMNCRP_DISABLED)
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_NCRENDERING_POLICY,
                ctypes.byref(policy), ctypes.sizeof(policy)
            )

            try:
                DWMWA_BORDER_COLOR = 34
                DWMWA_COLOR_NONE = 0xFFFFFFFF
                color = ctypes.c_uint32(DWMWA_COLOR_NONE)
                dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_BORDER_COLOR,
                    ctypes.byref(color), ctypes.sizeof(color)
                )
            except Exception:
                pass

            try:
                DWMWA_WINDOW_CORNER_PREFERENCE = 33
                DWMWCP_DONOTROUND = 1
                corner_pref = ctypes.c_uint32(DWMWCP_DONOTROUND)
                dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                    ctypes.byref(corner_pref), ctypes.sizeof(corner_pref)
                )
            except Exception:
                pass

            SWP_FRAMECHANGED = 0x0020
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Behavior
    # ------------------------------------------------------------------
    def _update_behavior(self):
        if self._is_dragging:
            return
        if self._locked:
            if self._hovered:
                if self.animator.state != "waving":
                    self.animator.set_state("waving")
                self._behavior = "idle"
                self._behavior_timer = 0.0
            else:
                dt = BEHAVIOR_INTERVAL_MS
                self._behavior_timer += dt
                if self._behavior == "idle":
                    if self._behavior_timer >= LOCKED_IDLE_TIMEOUT_MS:
                        state = random.choice(["failed", "waiting"])
                        self._behavior = state
                        self._behavior_timer = 0.0
                        self.animator.set_state(state)
                    elif self.animator.state not in ("idle", "waving", "failed", "waiting", "review"):
                        self.animator.set_state("idle")
                elif self._behavior in ("failed", "waiting"):
                    if self._behavior_timer >= LOCKED_FAILED_DURATION_MS:
                        self._behavior = "idle"
                        self._behavior_timer = 0.0
                        self.animator.set_state("idle")
            self._apply_bounds()
            if self._behavior == "jump":
                self._update_jump()
            return

        if self._hovered and self._behavior != "fling":
            return

        dt = BEHAVIOR_INTERVAL_MS
        self._behavior_timer += dt
        self._screen = QApplication.primaryScreen().availableGeometry()

        if self._behavior == "idle":
            if self._behavior_timer >= self._next_behavior_change:
                self._start_move()
        elif self._behavior == "move":
            self._pos_x += self._vx
            self._pos_y += self._vy
            self._apply_bounds()
            self.move(int(self._pos_x), int(self._pos_y))
            if self._behavior_timer >= self._next_behavior_change:
                self._start_idle()
        elif self._behavior == "review":
            if self._behavior_timer >= self._next_behavior_change:
                self._behavior = "move"
                self._behavior_timer = 0.0
                self._vx = self._post_review_vx
                self._vy = self._post_review_vy
                self._next_behavior_change = random.uniform(2000, 6000)
                if self._vx > 0:
                    self.animator.set_state("running-right")
                else:
                    self.animator.set_state("running-left")
        elif self._behavior == "jump":
            self._update_jump()

    def _start_idle(self):
        self._behavior = "idle"
        self._behavior_timer = 0.0
        self._next_behavior_change = random.uniform(4000, 10000)
        self._vx = 0.0
        self._vy = 0.0
        if self._hovered:
            self.animator.set_state("waving")
        else:
            self.animator.set_state("idle")

    def _start_move(self):
        self._behavior = "move"
        self._behavior_timer = 0.0
        self._next_behavior_change = random.uniform(2000, 6000)
        angle = random.uniform(-math.pi / 3, math.pi / 3)
        if random.random() > 0.5:
            angle = math.pi - angle
        self._vx = self._speed * math.cos(angle)
        self._vy = self._speed * math.sin(angle) * 0.3
        if self._vx > 0:
            self.animator.set_state("running-right")
        else:
            self.animator.set_state("running-left")

    def _start_jump(self):
        self._behavior = "jump"
        self._behavior_timer = 0.0
        self._next_behavior_change = 1200
        self._jump_start_y = self._pos_y
        self.animator.set_state("jumping")

    def _update_jump(self):
        t = self._behavior_timer / self._next_behavior_change
        hop = 80 * math.sin(t * math.pi)
        self._pos_y = self._jump_start_y - hop
        self._apply_bounds()
        self.move(int(self._pos_x), int(self._pos_y))
        if self._behavior_timer >= self._next_behavior_change:
            self._start_idle()

    def _update_fling(self):
        self._pos_x += self._vx
        self._pos_y += self._vy
        margin = 0
        w = self._win_w()
        h = self._win_h()
        if self._pos_x < margin:
            self._pos_x = margin
            self._vx = abs(self._vx) * 0.7
        elif self._pos_x > self._screen.width() - w - margin:
            self._pos_x = self._screen.width() - w - margin
            self._vx = -abs(self._vx) * 0.7
        if self._pos_y < margin:
            self._pos_y = margin
            self._vy = abs(self._vy) * 0.7
        elif self._pos_y > self._screen.height() - h - margin:
            self._pos_y = self._screen.height() - h - margin
            self._vy = -abs(self._vy) * 0.7
        self.move(int(self._pos_x), int(self._pos_y))
        self._vx *= FLING_FRICTION
        self._vy *= FLING_FRICTION
        if abs(self._vx) < 0.75 and abs(self._vy) < 0.75:
            self._start_idle()

    def _apply_bounds(self):
        margin = 0
        changed = False
        w = self._win_w()
        h = self._win_h()
        if self._pos_x < margin:
            self._pos_x = margin
            self._vx = abs(self._vx)
            changed = True
        elif self._pos_x > self._screen.width() - w - margin:
            self._pos_x = self._screen.width() - w - margin
            self._vx = -abs(self._vx)
            changed = True
        if self._pos_y < margin:
            self._pos_y = margin
            self._vy = abs(self._vy)
            changed = True
        elif self._pos_y > self._screen.height() - h - margin:
            self._pos_y = self._screen.height() - h - margin
            self._vy = -abs(self._vy)
            changed = True
        if changed:
            if self._behavior == "move":
                self._post_review_vx = self._vx
                self._post_review_vy = self._vy
                self._behavior = "review"
                self._behavior_timer = 0.0
                self._next_behavior_change = REVIEW_DURATION_MS
                self.animator.set_state("review")
            elif self._locked and self._behavior != "jump":
                self._start_jump()

    # ------------------------------------------------------------------
    # Head label (time + notes)
    # ------------------------------------------------------------------
    def _refresh_head(self):
        if not self.config.get("show_head", True):
            self._head_label.hide()
            return
        from datetime import datetime
        lines = []
        if self._focus_active:
            if self._focus_task:
                short = self._focus_task[:20] + "…" if len(self._focus_task) > 20 else self._focus_task
                lines.append(f'<span style="color:#333333;">{short}</span>')
            m, s = divmod(self._focus_seconds, 60)
            lines.append(f'<span style="color:#333333;">{m:02d}:{s:02d}</span>')
        else:
            lines.append(f'<span style="color:#333333;">{datetime.now().strftime("%H:%M")}</span>')
        for note in self.config.notes:
            text = note.get("text", "") if isinstance(note, dict) else str(note)
            color = note.get("color", "#333333") if isinstance(note, dict) else "#333333"
            short = text[:22] + "…" if len(text) > 22 else text
            lines.append(f'<span style="color:{color};">• {short}</span>')
        self._head_label.setText("<br>".join(lines))
        self._head_label.setTextFormat(Qt.RichText)
        self._head_label.adjustSize()
        bx = (self.width() - self._head_label.width()) // 2
        by = -self._head_label.height() - 6
        global_pos = self.mapToGlobal(QPoint(bx, by))
        self._head_label.move(global_pos)
        self._head_label.show()
        self._head_label.raise_()

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------
    def _add_note(self):
        text, ok = QInputDialog.getText(self, "添加便签", "要写什么？")
        if ok and text.strip():
            self.config.add_note(text.strip())
            self.config.save()
            self._refresh_head()

    def _clear_notes(self):
        self.config.clear_notes()
        self.config.save()
        self._refresh_head()

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._is_dragging = True
            self._drag_last_x = self.x()
            self._last_interaction_time = time.time()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._is_dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            delta_x = new_pos.x() - self._drag_last_x
            if delta_x > 0 and self.animator.state != "running-right":
                self.animator.set_state("running-right")
            elif delta_x < 0 and self.animator.state != "running-left":
                self.animator.set_state("running-left")
            self._fling_vx = new_pos.x() - self._drag_last_x
            self._fling_vy = new_pos.y() - self._pos_y
            self.move(new_pos)
            self._pos_x = new_pos.x()
            self._pos_y = new_pos.y()
            self._drag_last_x = new_pos.x()
            self._last_interaction_time = time.time()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            self._last_interaction_time = time.time()
            fling_speed = math.hypot(self._fling_vx, self._fling_vy)
            if fling_speed > FLING_THRESHOLD:
                self._behavior = "fling"
                self._behavior_timer = 0.0
                self._vx = self._fling_vx * 0.6
                self._vy = self._fling_vy * 0.6
                self.animator.set_state("running")
            else:
                self._behavior = "idle"
                self._behavior_timer = 0.0
                self._next_behavior_change = 1500
                self._vx = 0.0
                self._vy = 0.0
                if self._hovered:
                    self.animator.set_state("waving")
                else:
                    self.animator.set_state("idle")
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._locked:
                self._start_jump()
            event.accept()

    def enterEvent(self, event):
        self._hovered = True
        if not self._is_dragging:
            self.animator.set_state("waving")
        self._refresh_head()

    def leaveEvent(self, event):
        self._hovered = False
        if self._is_dragging:
            return
        if self._locked:
            self.animator.set_state("idle")
            return
        if self._behavior == "move":
            if self._vx > 0:
                self.animator.set_state("running-right")
            else:
                self.animator.set_state("running-left")
        elif self._behavior == "jump":
            self.animator.set_state("jumping")
        elif self._behavior == "idle":
            self.animator.set_state("idle")

    def moveEvent(self, event):
        super().moveEvent(event)
        self._refresh_head()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------
    def contextMenuEvent(self, event):
        menu = QMenu(self)

        lock_action = QAction("禁止乱跑" if not self._locked else "允许乱跑", self)
        lock_action.triggered.connect(self._toggle_lock)
        menu.addAction(lock_action)

        if self._focus_active:
            focus_action = QAction("取消专注", self)
            focus_action.triggered.connect(self._cancel_focus)
        else:
            focus_action = QAction("专注模式…", self)
            focus_action.triggered.connect(self._start_focus)
        menu.addAction(focus_action)

        note_menu = QMenu("便签", self)
        add_note = QAction("添加便签", self)
        add_note.triggered.connect(self._add_note)
        note_menu.addAction(add_note)
        for i, note in enumerate(self.config.notes):
            text = note.get("text", "") if isinstance(note, dict) else str(note)
            display = text[:16] + "…" if len(text) > 16 else text
            a = QAction(f"📝 {display}", self)
            a.triggered.connect(lambda checked, idx=i: self._edit_note(idx))
            note_menu.addAction(a)
        if self.config.notes:
            note_menu.addSeparator()
            clear_notes = QAction("清除全部便签", self)
            clear_notes.triggered.connect(self._clear_notes)
            note_menu.addAction(clear_notes)
        menu.addMenu(note_menu)

        launch_menu = QMenu("快速启动", self)
        for app in self.config.apps:
            a = QAction(app["name"], self)
            a.triggered.connect(lambda checked, c=app["cmd"]: self._launch_app(c))
            launch_menu.addAction(a)
        if self.config.apps:
            launch_menu.addSeparator()
        manage_apps = QAction("管理快速启动…", self)
        manage_apps.triggered.connect(self._manage_apps)
        launch_menu.addAction(manage_apps)
        menu.addMenu(launch_menu)

        head_action = QAction("显示头顶文字" if not self.config.get("show_head", True) else "隐藏头顶文字", self)
        head_action.triggered.connect(self._toggle_head)
        menu.addAction(head_action)

        size_menu = QMenu("大小", self)
        for s in [0.25, 0.375, 0.5, 0.625, 0.75, 1.0]:
            a = QAction(f"{int(s * 100)}%", self)
            a.triggered.connect(lambda checked, sc=s: self.set_scale(sc))
            size_menu.addAction(a)
        menu.addMenu(size_menu)

        char_menu = QMenu("切换角色", self)
        for cid, name in [("jiaoyi", "娇阿依小公主"), ("hexiaoyuan", "何小猿"), ("guoba", "锅巴小公主"), ("weiwei", "维维"), ("yinglang", "银狼")]:
            a = QAction(name, self)
            a.triggered.connect(lambda checked, c=cid: self._switch_character(c))
            char_menu.addAction(a)
        menu.addMenu(char_menu)

        autostart_action = QAction("取消开机自启" if self._is_autostart_enabled() else "开机自启", self)
        autostart_action.triggered.connect(self._toggle_autostart)
        menu.addAction(autostart_action)

        menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        menu.exec(event.globalPos())

    def _start_focus(self):
        minutes, ok = QInputDialog.getInt(self, "专注模式", "专注多少分钟？", 25, 1, 120)
        if not ok:
            return
        text, ok2 = QInputDialog.getText(self, "专注模式", "专注事项：")
        if not ok2:
            return
        self._focus_active = True
        self._focus_seconds = minutes * 60
        self._focus_task = text.strip()
        self._focus_timer.start(1000)
        self._refresh_head()
        if self._behavior != "fling":
            self._behavior = "idle"
            self.animator.set_state("idle")

    def _cancel_focus(self):
        self._focus_active = False
        self._focus_timer.stop()
        self._focus_task = ""
        self._refresh_head()

    def _focus_tick(self):
        self._focus_seconds -= 1
        self._refresh_head()
        if self._focus_seconds <= 0:
            self._focus_done()

    def _focus_done(self):
        self._focus_active = False
        self._focus_timer.stop()
        self._focus_task = ""
        self._refresh_head()
        self.animator.set_state("waving")
        self._play_alert()

    def _play_alert(self):
        threading.Thread(target=lambda: winsound.Beep(800, 2000), daemon=True).start()

    def _launch_app(self, cmd: str):
        try:
            if Path(cmd).exists() or " " in cmd or "\\" in cmd or "/" in cmd:
                subprocess.Popen([cmd], shell=False)
            else:
                subprocess.Popen(cmd, shell=True)
        except Exception:
            pass

    def _manage_apps(self):
        dialog = ManageAppsDialog(self.config.apps, self)
        if dialog.exec() == QDialog.Accepted:
            self.config.set_apps(dialog.apps)
            self.config.save()

    def _edit_note(self, index: int):
        note = self.config.notes[index]
        text = note.get("text", "") if isinstance(note, dict) else str(note)
        new_text, ok = QInputDialog.getText(self, "编辑便签", "内容：", text=text)
        if not ok:
            return
        if new_text.strip():
            self.config.update_note(index, new_text.strip())
        else:
            self.config.remove_note(index)
        self.config.save()
        self._refresh_head()

    def _toggle_head(self):
        show = not self.config.get("show_head", True)
        self.config.set("show_head", show)
        self.config.save()
        self._refresh_head()

    def _switch_character(self, char_id: str):
        project_root = _project_root()
        char_dir = project_root / "assets" / "characters" / char_id
        frames_dir = char_dir / "frames"
        img_files = list(char_dir.glob("*.webp")) + list(char_dir.glob("*.png"))
        spritesheet = img_files[0] if img_files else char_dir / "spritesheet.webp"
        if not (frames_dir / "manifest.json").exists():
            from atlas import extract_frames
            extract_frames(spritesheet, frames_dir)
        self.animator = PetAnimator(frames_dir)
        self.config.set("character", char_id)
        self.config.save()
        self._update_display()
        self._behavior = "idle"
        self.animator.set_state("review")
        QTimer.singleShot(REVIEW_DURATION_MS, lambda cid=char_id: self._finish_review_entrance(cid))

    def _finish_review_entrance(self, cid: str):
        if self.config.get("character") != cid:
            return
        if self._hovered:
            self.animator.set_state("waving")
        else:
            self.animator.set_state("idle")

    def _is_autostart_enabled(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, "GuobaPrincess")
            winreg.CloseKey(key)
            return True
        except OSError:
            return False

    def _toggle_autostart(self):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        exe_path = sys.executable
        if self._is_autostart_enabled():
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, "GuobaPrincess")
                winreg.CloseKey(key)
            except Exception:
                pass
        else:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "GuobaPrincess", 0, winreg.REG_SZ, exe_path)
                winreg.CloseKey(key)
            except Exception:
                pass

    def _toggle_lock(self):
        self._locked = not self._locked
        self._last_interaction_time = time.time()
        if self._locked:
            self._vx = 0.0
            self._vy = 0.0
            self._behavior = "idle"
            self._behavior_timer = 0.0
            if self._hovered:
                self.animator.set_state("waving")
            else:
                self.animator.set_state("idle")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            QApplication.quit()

    def _save_state(self):
        self.config.set("pos_x", int(self._pos_x))
        self.config.set("pos_y", int(self._pos_y))
        self.config.set("scale", self._scale)
        self.config.save()


class AddAppDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加应用")
        self.setFixedSize(360, 150)
        self.name = ""
        self.cmd = ""

        layout = QVBoxLayout(self)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("名称:", self))
        self.name_edit = QLineEdit(self)
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)

        cmd_layout = QHBoxLayout()
        cmd_layout.addWidget(QLabel("命令:", self))
        self.cmd_edit = QLineEdit(self)
        cmd_layout.addWidget(self.cmd_edit)
        browse_btn = QPushButton("浏览…", self)
        browse_btn.clicked.connect(self._browse)
        cmd_layout.addWidget(browse_btn)
        layout.addLayout(cmd_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定", self)
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择可执行文件", "",
            "可执行文件 (*.exe *.bat *.cmd);;所有文件 (*.*)"
        )
        if path:
            self.cmd_edit.setText(path)

    def _on_ok(self):
        self.name = self.name_edit.text().strip()
        self.cmd = self.cmd_edit.text().strip()
        if not self.name or not self.cmd:
            QMessageBox.warning(self, "输入不完整", "名称和命令都不能为空。")
            return
        self.accept()


class ManageAppsDialog(QDialog):
    def __init__(self, apps, parent=None):
        super().__init__(parent)
        self.setWindowTitle("管理快速启动")
        self.setFixedSize(380, 340)
        self.apps = [dict(a) for a in apps]

        layout = QVBoxLayout(self)

        self.list_widget = QListWidget(self)
        self._refresh_list()
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加", self)
        add_btn.clicked.connect(self._add_app)
        remove_btn = QPushButton("移除", self)
        remove_btn.clicked.connect(self._remove_app)
        up_btn = QPushButton("上移", self)
        up_btn.clicked.connect(self._move_up)
        down_btn = QPushButton("下移", self)
        down_btn.clicked.connect(self._move_down)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(up_btn)
        btn_layout.addWidget(down_btn)
        layout.addLayout(btn_layout)

        ok_cancel = QHBoxLayout()
        ok_cancel.addStretch()
        ok_btn = QPushButton("确定", self)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        ok_cancel.addWidget(ok_btn)
        ok_cancel.addWidget(cancel_btn)
        layout.addLayout(ok_cancel)

    def _refresh_list(self):
        self.list_widget.clear()
        for app in self.apps:
            self.list_widget.addItem(f"{app['name']}  ({app['cmd']})")

    def _add_app(self):
        dialog = AddAppDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.apps.append({"name": dialog.name, "cmd": dialog.cmd})
            self._refresh_list()

    def _remove_app(self):
        idx = self.list_widget.currentRow()
        if idx >= 0:
            self.apps.pop(idx)
            self._refresh_list()

    def _move_up(self):
        idx = self.list_widget.currentRow()
        if idx > 0:
            self.apps[idx], self.apps[idx - 1] = self.apps[idx - 1], self.apps[idx]
            self._refresh_list()
            self.list_widget.setCurrentRow(idx - 1)

    def _move_down(self):
        idx = self.list_widget.currentRow()
        if 0 <= idx < len(self.apps) - 1:
            self.apps[idx], self.apps[idx + 1] = self.apps[idx + 1], self.apps[idx]
            self._refresh_list()
            self.list_widget.setCurrentRow(idx + 1)


def _ensure_single_instance():
    kernel32 = ctypes.windll.kernel32
    ERROR_ALREADY_EXISTS = 183
    mutex = kernel32.CreateMutexW(None, False, "Global\\gxy-deskpet-single-instance")
    if not mutex:
        return None
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(mutex)
        return None
    return mutex


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def main():
    log_path = Path.home() / "gxy-deskpet.log"
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            log.write("[START] App starting\n")
            log.flush()

            mutex = _ensure_single_instance()
            if not mutex:
                log.write("[EXIT] Another instance already running\n")
                log.flush()
                return

            app = QApplication(sys.argv)
            log.write("[OK] QApplication created\n")
            log.flush()

            config = Config()
            log.write("[OK] Config loaded\n")
            log.flush()

            char_id = config.get("character", "jiaoyi")
            project_root = _project_root()
            log.write(f"[INFO] Project root: {project_root}\n")
            log.flush()

            char_dir = project_root / "assets" / "characters" / char_id
            frames_dir = char_dir / "frames"
            img_files = list(char_dir.glob("*.webp")) + list(char_dir.glob("*.png"))
            spritesheet = img_files[0] if img_files else char_dir / "spritesheet.webp"
            log.write(f"[INFO] Frames dir: {frames_dir}\n")
            log.flush()

            if not (frames_dir / "manifest.json").exists():
                from atlas import extract_frames
                log.write("[INFO] Extracting frames...\n")
                log.flush()
                extract_frames(spritesheet, frames_dir)

            animator = PetAnimator(frames_dir)
            log.write("[OK] Animator created\n")
            log.flush()

            pet = DeskPet(animator, config)
            log.write("[OK] DeskPet window created\n")
            log.flush()

            pet.show()
            log.write("[OK] Window shown\n")
            log.flush()

            app.aboutToQuit.connect(pet._save_state)

            code = app.exec()
            log.write(f"[EXIT] Event loop exited with code {code}\n")
            log.flush()
            sys.exit(code)
    except Exception:
        import traceback
        with open(log_path, "a", encoding="utf-8") as log:
            log.write("[ERROR]\n")
            log.write(traceback.format_exc())
            log.flush()
        raise


if __name__ == "__main__":
    main()
