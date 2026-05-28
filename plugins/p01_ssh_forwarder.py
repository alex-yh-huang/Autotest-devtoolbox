"""
Plugin: SSH 埠口轉發器 (多樹莓派 Port Forwarding + 一鍵開啟網頁 + 通道自癒上電喚醒版)
檔名：p01_ssh_forwarder.py
功能：快速建立 SSH Tunnel 至 Raspberry Pi，自動帶入固定密碼 1。
      管理操作包含「⚡ 上電喚醒」功能（上電控制與保持喚醒完全精準分類）。
      【終極修復】透過預檢機制，徹底防止未上電開網頁導致 Paramiko 底層 Transport 崩潰被 Kill 的問題。
      【動態自癒】解決非程式上電（手動上電）時網頁卡 Loading 的問題，開網頁時自動預檢並解鎖 Flag。
      【提示優化】未上電時點擊開啟網頁，UI 將百分之百彈出具體的「未上電警示」告知使用者，不再無反應。
"""
import socket
import threading
import sys
import webbrowser
import time
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread
from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, 
    QLineEdit, QRadioButton, QButtonGroup, QTreeWidget, 
    QTreeWidgetItem, QMessageBox, QHeaderView, QWidget,
    QDialog, QProgressBar, QComboBox
)
import paramiko
from core.plugin_base import PluginBase


class TunnelSignals(QObject):
    finished = pyqtSignal(str)  
    error = pyqtSignal(str, str)  


# ── 背景執行上電與精準喚醒檢查 (Ping + TCP Port) 的背景工作執行緒 ───────────────────
class WakeupWorker(QThread):
    progress_signal = pyqtSignal(str, int)  # (提示文字, 進度百分比)
    finished_signal = pyqtSignal(bool, str) # (是否成功, 結果訊息)

    def __init__(self, ssh_client, tunnel_id, power_method, wakeup_method, forward_server):
        super().__init__()
        self.ssh_client = ssh_client
        self.tunnel_id = tunnel_id
        self.power_method = power_method      
        self.wakeup_method = wakeup_method    
        self.forward_server = forward_server  

    def run(self):
        try:
            # 1. 執行上電控制 (維持你原有的控制邏輯)
            if self.power_method == 0:
                self.progress_signal.emit("正在執行上電控制 (Gen2 - Pin 23)...", 10)
                stdin, stdout, stderr = self.ssh_client.exec_command("sudo pinctrl 23 op dh")
            else:
                self.progress_signal.emit("正在執行上電控制 (Gen2 - Pin 24)...", 10)
                stdin, stdout, stderr = self.ssh_client.exec_command("sudo pinctrl 24 op dh")
            stdout.channel.recv_exit_status() 
            time.sleep(0.5)

            # 2. 執行精準拆分的保持喚醒指令
            if self.wakeup_method == 0:
                self.progress_signal.emit("正在配置 Gen1 保持喚醒...", 20)
                self.ssh_client.exec_command("gpioset gpiochip3 6=1")
            elif self.wakeup_method == 1:
                self.progress_signal.emit("正在配置 Gen2 保持喚醒...", 20)
                self.ssh_client.exec_command("i2cset -y 1 0x21 0x0b 0x40")
            elif self.wakeup_method == 2:
                self.progress_signal.emit("正在配置 TA2 保持喚醒...", 20)
                self.ssh_client.exec_command("i2cset -y 1 0x23 0x08 0x7F")
            
            time.sleep(1.5) 

            # 3. 雙重檢查機制 (擴充為雙目標偵測)
            max_attempts = 35
            # 定義兩個可能出現的目標 IP
            target_list = ["192.168.200.1", "169.254.200.1"]
            target_port = 80
            
            for i in range(1, max_attempts + 1):
                current_progress = 25 + int((i / max_attempts) * 70)
                self.progress_signal.emit(f"機台系統初始化中... 請稍候 (第 {i}/{max_attempts} 秒)...", current_progress)
                
                # 遍歷檢查每個 target_ip
                for target_ip in target_list:
                    # 第一重：Ping 測試
                    ping_cmd = f"ping -c 1 -W 1 {target_ip}"
                    _, stdout, _ = self.ssh_client.exec_command(ping_cmd)
                    
                    if stdout.channel.recv_exit_status() == 0:
                        # 第二重：測試 80 Port
                        test_port_cmd = f"nc -z -w 1 {target_ip} {target_port}"
                        _, stdout_p, _ = self.ssh_client.exec_command(test_port_cmd)
                        
                        if stdout_p.channel.recv_exit_status() == 0:
                            # 成功偵測到其中一個存活的網段
                            if self.forward_server:
                                self.forward_server.force_unlock = True

                            self.progress_signal.emit(f"連線成功 ({target_ip})！網頁伺服器已就緒。", 100)
                            time.sleep(0.8)
                            self.finished_signal.emit(True, f"成功連線至 {target_ip}:{target_port}！\n機台已正常上電，網頁服務已完全就緒。")
                            return
                
                # 若這輪檢查兩個 IP 都沒通，繼續等待
                time.sleep(1.0)

            self.finished_signal.emit(False, f"喚醒服務就緒逾時！\n已嘗試檢查 192.168.200.1 與 169.254.200.1，但網頁服務皆無回應。")

        except Exception as e:
            self.finished_signal.emit(False, f"執行硬體控制時發生異常：\n{str(e)}")


# ── 上電與喚醒選擇彈出視窗 ──────────────────────────────────────
class WakeupDialog(QDialog):
    def __init__(self, parent, ssh_client, tunnel_id, forward_server):
        super().__init__(parent)
        self.parent_plugin = parent
        self.ssh_client = ssh_client
        self.tunnel_id = tunnel_id
        self.forward_server = forward_server
        self.worker = None
        self.setWindowTitle("⚡ 機台上電與強制保持喚醒設定")
        self.setFixedSize(420, 240)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog { background-color: #252526; }
            QLabel { color: #f0f0f0; font-size: 13px; font-weight: bold; }
            QComboBox { 
                background-color: #333333; color: #e0e0e0; 
                border: 1px solid #555555; border-radius: 4px; padding: 5px; font-size: 12px;
            }
            QComboBox QAbstractItemView { background-color: #2d2d2d; color: #e0e0e0; selection-background-color: #1e3a5f; }
            QPushButton { 
                background-color: #1e3a5f; color: #f0f0f0; 
                border: 1px solid #2d5a8f; border-radius: 4px; padding: 6px 14px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #4a9eff; border-color: #4a9eff; }
            QProgressBar {
                border: 1px solid #555; border-radius: 4px; background-color: #1e1e1e;
                text-align: center; color: #ffffff; font-weight: bold;
            }
            QProgressBar::chunk { background-color: #007acc; border-radius: 3px; }
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(14)

        self.config_widget = QWidget()
        config_layout = QVBoxLayout(self.config_widget)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(12)

        lbl_power = QLabel("請選擇上電方法：")
        self.combo_power = QComboBox()
        self.combo_power.addItem("Gen2 (sudo pinctrl 23 op dh)")
        self.combo_power.addItem("Gen2 (sudo pinctrl 24 op dh)")
        config_layout.addWidget(lbl_power)
        config_layout.addWidget(self.combo_power)

        lbl_wakeup = QLabel("請選擇強制保持喚醒方法：")
        self.combo_wakeup = QComboBox()
        self.combo_wakeup.addItem("Gen1 (gpioset gpiochip3 6=1)")
        self.combo_wakeup.addItem("Gen2 (i2cset -y 1 0x21 0x0b 0x40)")
        self.combo_wakeup.addItem("TA2 (i2cset -y 1 0x23 0x08 0x7F)")
        config_layout.addWidget(lbl_wakeup)
        config_layout.addWidget(self.combo_wakeup)

        self.btn_execute = QPushButton("⚡ 開始執行上電喚醒")
        self.btn_execute.clicked.connect(self._start_execution)
        config_layout.addWidget(self.btn_execute)

        self.main_layout.addWidget(self.config_widget)

        self.loading_widget = QWidget()
        loading_layout = QVBoxLayout(self.loading_widget)
        loading_layout.setContentsMargins(0, 20, 0, 20)
        loading_layout.setSpacing(12)

        self.lbl_status = QLabel("準備發送控制指令...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #4a9eff; font-size: 12px;")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)

        loading_layout.addWidget(self.lbl_status)
        loading_layout.addWidget(self.progress_bar)
        
        self.loading_widget.hide()
        self.main_layout.addWidget(self.loading_widget)

    def _start_execution(self):
        power_idx = self.combo_power.currentIndex()
        wakeup_idx = self.combo_wakeup.currentIndex()

        if self.tunnel_id in self.parent_plugin.active_tunnels:
            self.parent_plugin.active_tunnels[self.tunnel_id]["is_waking_up"] = True

        self.config_widget.hide()
        self.loading_widget.show()

        self.worker = WakeupWorker(self.ssh_client, self.tunnel_id, power_idx, wakeup_idx, self.forward_server)
        self.worker.progress_signal.connect(self._update_progress)
        self.worker.finished_signal.connect(self._execution_finished)
        self.worker.start()

    def _update_progress(self, text, val):
        self.lbl_status.setText(text)
        self.progress_bar.setValue(val)

    def _execution_finished(self, success, message):
        if self.tunnel_id in self.parent_plugin.active_tunnels:
            self.parent_plugin.active_tunnels[self.tunnel_id]["is_waking_up"] = False

        self.close() 
        if success:
            self.parent_plugin._show_message(QMessageBox.Icon.Information, "操作成功", message)
        else:
            self.parent_plugin._show_message(QMessageBox.Icon.Warning, "連線提示", message)

    def reject(self):
        if self.worker and self.worker.isRunning():
            return 
        super().reject()


class SshForwarderPlugin(PluginBase):
    PLUGIN_NAME = "SSH 轉拋"
    PLUGIN_ICON = "🚀"
    PLUGIN_DESC = "多台 Pi 轉拋工具 (相同 IP、不同 SSH Port 專用)"
    PLUGIN_ORDER = 2

    def setup_ui(self):
        self.active_tunnels = {}
        self.tunnel_counter = 0
        self.signals = TunnelSignals()
        
        self.signals.finished.connect(self._handle_finished)
        self.signals.error.connect(self._handle_error)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        mode_box = QHBoxLayout()
        mode_box.setSpacing(20)
        
        mode_label = QLabel("連線模式：")
        mode_label.setStyleSheet("color: #e0e0e0; font-weight: bold; font-size: 13px;")
        mode_box.addWidget(mode_label)

        self.btn_group = QButtonGroup(self)
        
        self.radio_eth = QRadioButton("有線模式 (固定 IP)")
        self.radio_eth.setChecked(True)
        self.radio_eth.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        self.btn_group.addButton(self.radio_eth, 1)
        mode_box.addWidget(self.radio_eth)

        self.radio_wifi = QRadioButton("Wi-Fi 模式 (網段)")
        self.radio_wifi.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        self.btn_group.addButton(self.radio_wifi, 2)
        mode_box.addWidget(self.radio_wifi)
        
        mode_box.addStretch()
        layout.addLayout(mode_box)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(12)

        self.lbl_ip = QLabel("Pi IP:")
        self.lbl_ip.setStyleSheet("color: #cccccc; font-size: 13px;")
        self.txt_ip = QLineEdit("192.168.100.250")
        self.txt_ip.setReadOnly(True)
        self.txt_ip.setStyleSheet(self._input_style(readonly=True))

        self.lbl_port = QLabel("SSH Port:")
        self.lbl_port.setStyleSheet("color: #cccccc; font-size: 13px;")
        self.txt_port = QLineEdit("50034")
        self.txt_port.setStyleSheet(self._input_style())

        self.lbl_local_port = QLabel("本機 Port:")
        self.lbl_local_port.setStyleSheet("color: #cccccc; font-size: 13px;")
        self.txt_local_port = QLineEdit("8080")
        self.txt_local_port.setStyleSheet(self._input_style())
        
        btn_connect = QPushButton("建立通道")
        btn_connect.setStyleSheet(self._btn_style("#1e3a5f"))
        btn_connect.clicked.connect(self._start_tunnel)

        input_layout.addWidget(self.lbl_ip)
        input_layout.addWidget(self.txt_ip, 4) 
        
        input_layout.addWidget(self.lbl_port)
        input_layout.addWidget(self.txt_port, 2)
        
        input_layout.addWidget(self.lbl_local_port)
        input_layout.addWidget(self.txt_local_port, 2)
        
        input_layout.addWidget(btn_connect)
        layout.addLayout(input_layout)

        self.target_hint = QLabel("💡 提示：各台樹莓派內部目標皆固定轉拋至 169.254.200.1:80")
        self.target_hint.setStyleSheet("color: #4a9eff; font-size: 12px; padding-left: 2px;")
        layout.addWidget(self.target_hint)

        list_label = QLabel("目前運行中的通道管理：")
        list_label.setStyleSheet("color: #e0e0e0; font-weight: bold; font-size: 13px;")
        layout.addWidget(list_label)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["ID", "遠端 SSH 伺服器 (Pi)", "本機對應 (Local)", "遠端目標 (Target)", "管理操作"])
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(4, 185)
        
        self.tree.setStyleSheet("""
            QTreeWidget {
                background: #1e1e1e;
                color: #cccccc;
                border: 1px solid #2a2a2a;
                border-radius: 6px;
                font-size: 13px;
            }
            QTreeWidget::item { padding: 6px; }
            QHeaderView::section {
                background: #252525;
                color: #888;
                border: none;
                padding: 4px 8px;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.tree, 1)

        self.btn_group.idClicked.connect(self._toggle_mode)

    def _show_message(self, icon_type, title, text):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(icon_type)
        msg.setStyleSheet("""
            QMessageBox { background-color: #252526; }
            QLabel { color: #f0f0f0; font-size: 13px; min-width: 260px; }
            QPushButton { background-color: #3e3e42; color: #f0f0f0; border: 1px solid #555555; border-radius: 4px; padding: 5px 16px; font-size: 12px; min-width: 65px; }
            QPushButton:hover { background-color: #4a9eff; border-color: #4a9eff; color: #ffffff; }
        """)
        msg.exec()

    def _input_style(self, readonly=False):
        bg = "#1a1a1a" if readonly else "#2a2a2a"
        color = "#888888" if readonly else "#e0e0e0"
        return f"""
            QLineEdit {{
                background: {bg}; color: {color}; border: 1px solid #3a3a3a;
                border-radius: 6px; padding: 6px 10px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: #4a9eff; }}
        """

    def _btn_style(self, bg):
        return f"""
            QPushButton {{
                background: {bg}; color: #e0e0e0; border: 1px solid #444;
                border-radius: 6px; padding: 6px 16px; font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #4a9eff; border-color: #4a9eff; color: #fff; }}
        """

    def _toggle_mode(self, mode_id):
        if mode_id == 1:  
            self.txt_ip.setText("192.168.100.250")
            self.txt_ip.setReadOnly(True)
            self.txt_ip.setStyleSheet(self._input_style(readonly=True))
            self.txt_port.setText("50034")
            self.txt_port.setReadOnly(False)
            self.txt_port.setStyleSheet(self._input_style(readonly=False))
        else:  
            self.txt_ip.setText("192.168.50.100")
            self.txt_ip.setReadOnly(False)
            self.txt_ip.setStyleSheet(self._input_style(readonly=False))
            self.txt_port.setText("22")
            self.txt_port.setReadOnly(True)
            self.txt_port.setStyleSheet(self._input_style(readonly=True))

    def _start_tunnel(self):
        ip = self.txt_ip.text().strip()
        ssh_port_str = self.txt_port.text().strip()
        local_port_str = self.txt_local_port.text().strip()
        
        remote_host = "169.254.200.1"
        remote_port = 80
        password = "1"  

        if not ip or not ssh_port_str or not local_port_str:
            self._show_message(QMessageBox.Icon.Warning, "欄位錯誤", "所有參數欄位皆不可為空！")
            return

        try:
            ssh_port = int(ssh_port_str)
            local_port = int(local_port_str)
        except ValueError:
            self._show_message(QMessageBox.Icon.Warning, "格式錯誤", "Port 必須為純數字！")
            return

        for _, t_data in self.active_tunnels.items():
            if t_data["info"]["local_port"] == local_port:
                self._show_message(QMessageBox.Icon.Warning, "Port 衝突", f"本機 Port {local_port} 已經被佔用！")
                return
            if t_data["info"]["ssh_port"] == ssh_port and t_data["info"]["ip"] == ip:
                self._show_message(QMessageBox.Icon.Warning, "連線重複", f"已經存在連往 {ip}:{ssh_port} 的通道！")
                return

        # 強制清理重複 Port
        for tid, t_data in list(self.active_tunnels.items()):
            if t_data["info"]["local_port"] == local_port:
                self._stop_tunnel(tid)
                self._handle_finished(tid) # 確保 UI 更新
                time.sleep(0.5) # 給作業系統一點時間回收 Port

        tunnel_id = f"TUNNEL_{self.tunnel_counter:03d}"
        mode_str = "有線" if self.radio_eth.isChecked() else "Wi-Fi"

        info = {
            "id": tunnel_id, "mode": mode_str, "ip": ip,
            "ssh_port": ssh_port, "local_port": local_port,
            "remote_target": f"{remote_host}:{remote_port}"
        }

        t = threading.Thread(
            target=self._ssh_forwarding_worker,
            args=(tunnel_id, ip, ssh_port, "pi", password, local_port, remote_host, remote_port),
            daemon=True
        )
        
        self.active_tunnels[tunnel_id] = {
            "thread": t,
            "server": None,
            "client_instance": None, 
            "is_waking_up": False,  
            "info": info
        }
        t.start()
        self.tunnel_counter += 1
        self._add_tunnel_to_ui(info)

    def _ssh_forwarding_worker(self, tunnel_id, ssh_host, ssh_port, username, password, local_port, remote_host, remote_port):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(ssh_host, port=ssh_port, username=username, password=password, timeout=20)
            
            if tunnel_id in self.active_tunnels:
                self.active_tunnels[tunnel_id]["client_instance"] = client
            
            transport = client.get_transport()
            transport.set_keepalive(5)
            
            class ForwardServer:
                def __init__(self, listen_port, transport, ssh_client):
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.sock.bind(('127.0.0.1', listen_port))
                    self.sock.listen(10)
                    self.transport = transport
                    self.ssh_client = ssh_client
                    self.running = True
                    # 定義要檢查的目標清單
                    self.targets = [("192.168.200.1", 80), ("169.254.200.1", 80)]

                def get_active_target(self):
                    """動態測試並返回第一個存活的目標，若都不通則回傳 None"""
                    for ip, port in self.targets:
                        try:
                            cmd = f"nc -z -w 1 {ip} {port}"
                            _, stdout, _ = self.ssh_client.exec_command(cmd)
                            if stdout.channel.recv_exit_status() == 0:
                                return (ip, port)
                        except:
                            continue
                    return None # 修改這裡：回傳 None 而非預設值

                def start_loop(self):
                    self.sock.settimeout(1.0)
                    while self.running:
                        try:
                            chan_sock, _ = self.sock.accept()
                            # 每次建立連線時，重新動態抓取目標
                            active_target = self.get_active_target()
                            chan = self.transport.open_channel('direct-tcpip', active_target, chan_sock.getpeername())
                        except socket.timeout: continue
                        except Exception: 
                            try: chan_sock.close()
                            except: pass
                            continue
                        
                        # ... (後面 forward_data 的邏輯保持不變) ...
                        def forward_data(src, dst):
                            src.settimeout(None) 
                            dst.settimeout(None)
                            try:
                                while True:
                                    data = src.recv(131072) 
                                    if not data: break
                                    dst.sendall(data)
                            except: pass
                            finally:
                                try: src.close(); dst.close()
                                except: pass

                        threading.Thread(target=forward_data, args=(chan_sock, chan), daemon=True).start()
                        threading.Thread(target=forward_data, args=(chan, chan_sock), daemon=True).start()

                def close(self):
                    self.running = False
                    try:
                        self.sock.shutdown(socket.SHUT_RDWR)
                        self.sock.close()
                    except Exception: pass

            # 呼叫時不再傳入固定的 remote_target
            server = ForwardServer(local_port, transport, client)
            if tunnel_id in self.active_tunnels:
                self.active_tunnels[tunnel_id]["server"] = server
            server.start_loop()
            
        except Exception as e:
            self.signals.error.emit(tunnel_id, str(e))
        finally:
            self.signals.finished.emit(tunnel_id)

    def _open_browser_url(self, tunnel_id, port):
        tunnel_data = self.active_tunnels.get(tunnel_id)
        if not tunnel_data or tunnel_data.get("server") is None:
            return

        srv = tunnel_data["server"]
        active_target = srv.get_active_target()
        
        # 當兩者都不通時，active_target 為 None，這段警告會精準觸發
        if not active_target:
            self._show_message(
                QMessageBox.Icon.Warning, 
                "⚠️ 設備未上電提示", 
                "偵測到目標機台尚未上電（或網頁服務未就緒）！\n\n"
                "目前無法偵測到 192.168.200.1 或 169.254.200.1 的網頁服務。\n\n"
                "請先點擊該通道右側的【⚡ 上電喚醒】按鈕，待執行完成後再重開網頁。"
            )
            return

        # 只有在 active_target 確實存在時才會執行
        url = f"http://localhost:{port}/"
        webbrowser.open(url)

    def _trigger_hardware_wakeup(self, tunnel_id):
        if tunnel_id not in self.active_tunnels:
            return
        
        ssh_client = self.active_tunnels[tunnel_id]["client_instance"]
        forward_server = self.active_tunnels[tunnel_id]["server"]
        if not ssh_client:
            self._show_message(QMessageBox.Icon.Warning, "硬體控制錯誤", "SSH 通道尚未就緒，請稍後再試！")
            return

        dialog = WakeupDialog(self, ssh_client, tunnel_id, forward_server)
        dialog.exec()

    def _add_tunnel_to_ui(self, info):
        item = QTreeWidgetItem(self.tree)
        item.setText(0, info["id"])
        item.setText(1, f"[{info['mode']}] pi@{info['ip']}:{info['ssh_port']}")
        
        local_widget = QWidget()
        local_layout = QHBoxLayout(local_widget)
        local_layout.setContentsMargins(0, 0, 4, 0)
        local_layout.setSpacing(8)
        
        lbl_local = QLabel(f"127.0.0.1:{info['local_port']}")
        lbl_local.setStyleSheet("color: #cccccc;")
        
        btn_open = QPushButton("🌐 開啟網頁")
        btn_open.setStyleSheet("""
            QPushButton {
                background: #1e3a5f; color: #ffffff; border: 1px solid #444; 
                border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #4a9eff; border-color: #4a9eff; }
        """)
        l_port = info['local_port']
        tid = info["id"]
        btn_open.clicked.connect(lambda checked=False, t=tid, p=l_port: self._open_browser_url(t, p))
        
        local_layout.addWidget(lbl_local)
        local_layout.addWidget(btn_open)
        local_layout.addStretch()
        
        item.setText(3, info["remote_target"])

        manage_widget = QWidget()
        manage_layout = QHBoxLayout(manage_widget)
        manage_layout.setContentsMargins(0, 0, 0, 0)
        manage_layout.setSpacing(6)

        btn_wakeup = QPushButton("⚡ 上電喚醒")
        btn_wakeup.setStyleSheet("""
            QPushButton {
                background: #2d5a27; color: #ffffff; border: 1px solid #3d6a37; 
                border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #3e8e41; border-color: #3e8e41; }
        """)
        btn_wakeup.clicked.connect(lambda checked=False, t=tid: self._trigger_hardware_wakeup(t))

        btn_disconnect = QPushButton("中斷")
        btn_disconnect.setStyleSheet("""
            QPushButton {
                background: #5a1818; color: #e0e0e0; border: 1px solid #721c24; 
                border-radius: 4px; padding: 2px 8px; font-size: 11px;
            }
            QPushButton:hover { background: #cc0000; color: #fff; }
        """)
        btn_disconnect.clicked.connect(lambda checked=False, t=tid: self._stop_tunnel(t))
        
        manage_layout.addWidget(btn_wakeup)
        manage_layout.addWidget(btn_disconnect)
        manage_layout.addStretch()

        self.tree.addTopLevelItem(item)
        self.tree.setItemWidget(item, 2, local_widget)     
        self.tree.setItemWidget(item, 4, manage_widget)    

    def _stop_tunnel(self, tunnel_id):
        if tunnel_id in self.active_tunnels:
            t_data = self.active_tunnels[tunnel_id]
            
            # 1. 關閉並釋放 Server Socket
            if t_data["server"]:
                t_data["server"].close()
            
            # 2. 關閉 SSH Client，這會終止所有與該 Pi 的連線
            if t_data["client_instance"]:
                try:
                    t_data["client_instance"].close()
                except:
                    pass

    def _handle_finished(self, tunnel_id):
        if tunnel_id in self.active_tunnels:
            del self.active_tunnels[tunnel_id]
            root = self.tree.invisibleRootItem()
            for i in range(root.childCount()):
                item = root.child(i)
                if item and item.text(0) == tunnel_id:
                    root.removeChild(item)
                    break

    def _handle_error(self, tunnel_id, err_msg):
        self._show_message(QMessageBox.Icon.Critical, "通道錯誤提示", f"通道 [{tunnel_id}] 發生錯誤：\n{err_msg}")

    def on_deactivated(self):
        if self.active_tunnels:
            msg = QMessageBox(self)
            msg.setWindowTitle("確認中斷")
            msg.setText("切換功能或關閉將會切斷目前所有運行的 SSH Tunnel 通道，是否確定？")
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setStyleSheet("""
                QMessageBox { background-color: #252526; }
                QLabel { color: #f0f0f0; font-size: 13px; min-width: 260px; }
                QPushButton { background-color: #3e3e42; color: #f0f0f0; border: 1px solid #555555; border-radius: 4px; padding: 5px 16px; min-width: 65px; }
                QPushButton:hover { background-color: #4a9eff; border-color: #4a9eff; color: #ffffff; }
            """)
            if msg.exec() == QMessageBox.StandardButton.Yes:
                for tid in list(self.active_tunnels.keys()):
                    self._stop_tunnel(tid)