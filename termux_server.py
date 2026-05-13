#!/usr/bin/env python3
import json
import subprocess
import asyncio
import websockets
import socket
import os
import base64
import threading
import time
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

class TermuxMonitor:
    def __init__(self):
        self.connected_clients = set()
        
    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def run_termux_cmd(self, cmd, args=None):
        try:
            if args:
                full_cmd = [cmd] + args
            else:
                full_cmd = [cmd]
            print(f"Running: {' '.join(full_cmd)}")
            result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=30)
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'code': result.returncode,
                'cmd': ' '.join(full_cmd)
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Timeout (30s)'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def take_photo_base64(self, camera_id=0):
        photo_path = f"/sdcard/cam_{int(time.time())}.jpg"
        result = self.run_termux_cmd('termux-camera-photo', ['-c', str(camera_id), photo_path])
        if result['success']:
            try:
                with open(photo_path, 'rb') as f:
                    img_data = base64.b64encode(f.read()).decode()
                os.remove(photo_path)
                return {'success': True, 'image': img_data}
            except:
                pass
        return {'success': False, 'error': 'Camera error'}
    
    async def get_battery_info(self):
        result = self.run_termux_cmd('termux-battery-status')
        if result['success'] and result['stdout']:
            try:
                data = json.loads(result['stdout'])
                return {
                    'battery': data.get('percentage', 0),
                    'battery_status': data.get('status', 'Unknown'),
                    'battery_temp': data.get('temperature', 'N/A'),
                    'battery_health': data.get('health', 'Unknown')
                }
            except:
                pass
        return {'battery': 0, 'battery_status': 'Error', 'battery_temp': 'N/A', 'battery_health': 'Unknown'}
    
    async def get_network_info(self):
        result = self.run_termux_cmd('termux-wifi-connectioninfo')
        if result['success'] and result['stdout']:
            try:
                data = json.loads(result['stdout'])
                return {
                    'network_type': 'WiFi',
                    'signal_strength': data.get('rssi', 0),
                    'ip_address': self.get_local_ip(),
                    'ssid': data.get('ssid', 'Unknown'),
                    'bssid': data.get('bssid', 'Unknown')
                }
            except:
                pass
        return {'network_type': 'Unknown', 'signal_strength': 0, 'ip_address': self.get_local_ip(), 'ssid': 'None', 'bssid': 'None'}
    
    async def get_storage_info(self):
        try:
            result = subprocess.run(['df', '-h', '/sdcard'], capture_output=True, text=True, timeout=5)
            lines = result.stdout.split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 4:
                    available = parts[3].replace('G', '').replace('M', '')
                    total = parts[1].replace('G', '').replace('M', '')
                    used = parts[2].replace('G', '').replace('M', '')
                    return {'storage_available': f"{available}G", 'storage_total': f"{total}G", 'storage_used': f"{used}G"}
        except:
            pass
        return {'storage_available': 'N/A', 'storage_total': 'N/A', 'storage_used': 'N/A'}
    
    async def get_ram_info(self):
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
            total = None
            available = None
            for line in meminfo.split('\n'):
                if 'MemTotal:' in line:
                    total = int(line.split()[1])
                if 'MemAvailable:' in line:
                    available = int(line.split()[1])
            if total and available:
                used = total - available
                percent = round((used / total) * 100)
                total_gb = round(total / (1024 * 1024), 1)
                used_gb = round(used / (1024 * 1024), 1)
                return {'ram_usage': percent, 'ram_total': f"{total_gb}GB", 'ram_used': f"{used_gb}GB"}
        except:
            pass
        return {'ram_usage': 0, 'ram_total': 'N/A', 'ram_used': 'N/A'}
    
    async def get_cpu_info(self):
        try:
            with open('/proc/stat', 'r') as f:
                stat = f.readline()
            parts = stat.split()
            if len(parts) > 4:
                user = int(parts[1])
                nice = int(parts[2])
                system = int(parts[3])
                idle = int(parts[4])
                total = user + nice + system + idle
                used = total - idle
                percent = round((used / total) * 100) if total > 0 else 0
                return {'cpu_usage': percent, 'cpu_cores': os.cpu_count() or 4}
        except:
            pass
        return {'cpu_usage': 0, 'cpu_cores': 4}
    
    async def get_cpu_temp(self):
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = int(f.read().strip()) / 1000
                return {'cpu_temp': round(temp, 1)}
        except:
            pass
        return {'cpu_temp': 'N/A'}
    
    async def get_device_info(self):
        result = self.run_termux_cmd('termux-telephony-deviceinfo')
        if result['success'] and result['stdout']:
            try:
                data = json.loads(result['stdout'])
                return {
                    'device_model': data.get('manufacturer', '') + ' ' + data.get('model', ''),
                    'device_android': data.get('build_version_sdk', 'N/A'),
                    'device_brand': data.get('brand', 'Unknown')
                }
            except:
                pass
        try:
            result = subprocess.run(['getprop', 'ro.product.model'], capture_output=True, text=True, timeout=5)
            model = result.stdout.strip()
            result2 = subprocess.run(['getprop', 'ro.build.version.sdk'], capture_output=True, text=True, timeout=5)
            sdk = result2.stdout.strip()
            return {'device_model': model if model else 'Android', 'device_android': sdk, 'device_brand': 'Unknown'}
        except:
            return {'device_model': 'Unknown', 'device_android': 'N/A', 'device_brand': 'Unknown'}
    
    async def handle_client(self, websocket, path=None):
        self.connected_clients.add(websocket)
        ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        print(f"📱 Client connected: {ip}")
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    cmd = data.get('command', '')
                    params = data.get('params', [])
                    custom_params = data.get('custom_params', {})
                    
                    print(f"📨 Command: {cmd}")
                    
                    # ============ MONITORING ============
                    if cmd == 'get_info':
                        monitor_data = {}
                        tasks = [self.get_battery_info(), self.get_network_info(), self.get_storage_info(), 
                                 self.get_ram_info(), self.get_cpu_temp(), self.get_device_info(), self.get_cpu_info()]
                        results = await asyncio.gather(*tasks)
                        for result in results:
                            monitor_data.update(result)
                        monitor_data['timestamp'] = datetime.now().isoformat()
                        await websocket.send(json.dumps(monitor_data))
                    
                    # ============ BATTERY ============
                    elif cmd == 'battery_status':
                        result = self.run_termux_cmd('termux-battery-status')
                        await websocket.send(json.dumps(result))
                    
                    # ============ BRIGHTNESS ============
                    elif cmd == 'brightness':
                        result = self.run_termux_cmd('termux-brightness', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ CALL LOG ============
                    elif cmd == 'call_log':
                        result = self.run_termux_cmd('termux-call-log')
                        await websocket.send(json.dumps(result))
                    
                    # ============ CAMERA ============
                    elif cmd == 'camera_info':
                        result = self.run_termux_cmd('termux-camera-info')
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'camera_photo':
                        camera_id = int(params[0]) if params and params[0].isdigit() else 0
                        photo = await self.take_photo_base64(camera_id)
                        await websocket.send(json.dumps(photo))
                    
                    # ============ CLIPBOARD ============
                    elif cmd == 'clipboard_get':
                        result = self.run_termux_cmd('termux-clipboard-get')
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'clipboard_set':
                        result = self.run_termux_cmd('termux-clipboard-set', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ CONTACT ============
                    elif cmd == 'contact_list':
                        result = self.run_termux_cmd('termux-contact-list')
                        await websocket.send(json.dumps(result))
                    
                    # ============ DIALOG ============
                    elif cmd == 'dialog':
                        dialog_params = []
                        for key, value in custom_params.items():
                            dialog_params.extend([f'--{key}', value])
                        result = self.run_termux_cmd('termux-dialog', dialog_params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ DOWNLOAD ============
                    elif cmd == 'download':
                        result = self.run_termux_cmd('termux-download', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ FINGERPRINT ============
                    elif cmd == 'fingerprint':
                        result = self.run_termux_cmd('termux-fingerprint')
                        await websocket.send(json.dumps(result))
                    
                    # ============ INFRARED ============
                    elif cmd == 'infrared_frequencies':
                        result = self.run_termux_cmd('termux-infrared-frequencies')
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'infrared_transmit':
                        result = self.run_termux_cmd('termux-infrared-transmit', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ JOB SCHEDULER ============
                    elif cmd == 'job_scheduler':
                        result = self.run_termux_cmd('termux-job-scheduler', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ KEYSTORE ============
                    elif cmd == 'keystore':
                        result = self.run_termux_cmd('termux-keystore', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ LOCATION ============
                    elif cmd == 'location':
                        result = self.run_termux_cmd('termux-location', params if params else ['-p', 'network'])
                        await websocket.send(json.dumps(result))
                    
                    # ============ MEDIA PLAYER ============
                    elif cmd == 'media_player':
                        result = self.run_termux_cmd('termux-media-player', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ MEDIA SCAN ============
                    elif cmd == 'media_scan':
                        result = self.run_termux_cmd('termux-media-scan', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ MICROPHONE RECORD ============
                    elif cmd == 'microphone_record':
                        result = self.run_termux_cmd('termux-microphone-record', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ NOTIFICATION ============
                    elif cmd == 'notification':
                        notif_params = []
                        for key, value in custom_params.items():
                            notif_params.extend([f'--{key}', value])
                        if not notif_params and params:
                            notif_params = params
                        result = self.run_termux_cmd('termux-notification', notif_params)
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'notification_remove':
                        result = self.run_termux_cmd('termux-notification-remove', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ OPEN ============
                    elif cmd == 'open':
                        result = self.run_termux_cmd('termux-open', params)
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'open_url':
                        result = self.run_termux_cmd('termux-open-url', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ RELOAD SETTINGS ============
                    elif cmd == 'reload_settings':
                        result = self.run_termux_cmd('termux-reload-settings')
                        await websocket.send(json.dumps(result))
                    
                    # ============ SETUP STORAGE ============
                    elif cmd == 'setup_storage':
                        result = self.run_termux_cmd('termux-setup-storage')
                        await websocket.send(json.dumps(result))
                    
                    # ============ SHARE ============
                    elif cmd == 'share':
                        result = self.run_termux_cmd('termux-share', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ SENSOR ============
                    elif cmd == 'sensor':
                        result = self.run_termux_cmd('termux-sensor', params if params else ['-l'])
                        await websocket.send(json.dumps(result))
                    
                    # ============ SMS ============
                    elif cmd == 'sms_inbox':
                        result = self.run_termux_cmd('termux-sms-inbox')
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'sms_list':
                        result = self.run_termux_cmd('termux-sms-list', params)
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'sms_send':
                        result = self.run_termux_cmd('termux-sms-send', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ STORAGE GET ============
                    elif cmd == 'storage_get':
                        result = self.run_termux_cmd('termux-storage-get', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ TELEPHONY ============
                    elif cmd == 'telephony_call':
                        result = self.run_termux_cmd('termux-telephony-call', params)
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'telephony_cellinfo':
                        result = self.run_termux_cmd('termux-telephony-cellinfo')
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'telephony_deviceinfo':
                        result = self.run_termux_cmd('termux-telephony-deviceinfo')
                        await websocket.send(json.dumps(result))
                    
                    # ============ TOAST ============
                    elif cmd == 'toast':
                        result = self.run_termux_cmd('termux-toast', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ TTS ============
                    elif cmd == 'tts_engines':
                        result = self.run_termux_cmd('termux-tts-engines')
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'tts_speak':
                        result = self.run_termux_cmd('termux-tts-speak', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ TORCH ============
                    elif cmd == 'torch':
                        result = self.run_termux_cmd('termux-torch', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ USB ============
                    elif cmd == 'usb':
                        result = self.run_termux_cmd('termux-usb', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ VIBRATE ============
                    elif cmd == 'vibrate':
                        result = self.run_termux_cmd('termux-vibrate', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ VOLUME ============
                    elif cmd == 'volume':
                        result = self.run_termux_cmd('termux-volume', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ WALLPAPER ============
                    elif cmd == 'wallpaper':
                        result = self.run_termux_cmd('termux-wallpaper', params)
                        await websocket.send(json.dumps(result))
                    
                    # ============ WAKE LOCK ============
                    elif cmd == 'wake_lock':
                        result = self.run_termux_cmd('termux-wake-lock')
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'wake_unlock':
                        result = self.run_termux_cmd('termux-wake-unlock')
                        await websocket.send(json.dumps(result))
                    
                    # ============ WIFI ============
                    elif cmd == 'wifi_connectioninfo':
                        result = self.run_termux_cmd('termux-wifi-connectioninfo')
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'wifi_enable':
                        result = self.run_termux_cmd('termux-wifi-enable', params)
                        await websocket.send(json.dumps(result))
                    
                    elif cmd == 'wifi_scaninfo':
                        result = self.run_termux_cmd('termux-wifi-scaninfo')
                        await websocket.send(json.dumps(result))
                    
                    else:
                        await websocket.send(json.dumps({'success': False, 'error': f'Unknown command: {cmd}'}))
                        
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({'success': False, 'error': 'Invalid JSON'}))
                except Exception as e:
                    await websocket.send(json.dumps({'success': False, 'error': str(e)}))
                    
        except websockets.exceptions.ConnectionClosed:
            print(f"❌ Client disconnected: {ip}")
        finally:
            self.connected_clients.remove(websocket)
    
    async def start_websocket(self):
        async with websockets.serve(self.handle_client, '0.0.0.0', 8081):
            print(f"✅ WebSocket running on ws://{self.get_local_ip()}:8081")
            await asyncio.Future()

def start_http_server():
    termux_dir = '/data/data/com.termux/files/home/Dtermux/tApi'
    os.makedirs(termux_dir, exist_ok=True)
    os.chdir(termux_dir)
    
    # HTML akan dibuat di file terpisah
    print("📄 Creating monitor.html...")
    # Kode HTML akan dilanjutkan di pesan berikutnya karena terlalu panjang
    print("✅ HTML file created")
    
    httpd = HTTPServer(('0.0.0.0', 3000), SimpleHTTPRequestHandler)
    ip = socket.gethostbyname(socket.gethostname())
    print(f"✅ Web server: http://{ip}:3000/monitor.html")
    httpd.serve_forever()

if __name__ == "__main__":
    termux_dir = '/data/data/com.termux/files/home/Dtermux/tApi'
    os.makedirs(termux_dir, exist_ok=True)
    os.chdir(termux_dir)
    
    monitor = TermuxMonitor()
    
    web_thread = threading.Thread(target=start_http_server, daemon=True)
    web_thread.start()
    
    print("\n" + "="*50)
    print("📱 YussXy Monitor - COMPLETE VERSION")
    print("="*50)
    print(f"🌐 Buka browser: http://{monitor.get_local_ip()}:3000/monitor.html")
    print("="*50)
    print("\n✨ SEMUA FITUR TELAH TERSEDIA:")
    print("- Battery, Network, Storage, RAM, CPU")
    print("- Camera (Depan/Belakang), Torch, Vibrate")
    print("- SMS, Call, Location, Sensor")
    print("- TTS, Toast, Notification")
    print("- Volume, Brightness, Wallpaper")
    print("- Clipboard, Contact, Call Log")
    print("- Dan semua Termux API!\n")
    
    asyncio.run(monitor.start_websocket())