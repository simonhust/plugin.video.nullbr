# -*- coding: utf-8 -*-
import time, json, requests, xbmc, xbmcgui, xbmcvfs, os, urllib.parse, xbmcaddon, threading

ADDON = xbmcaddon.Addon()
PROFILE_PATH = xbmcvfs.translatePath(f"special://profile/addon_data/plugin.video.nullbr/")
if not xbmcvfs.exists(PROFILE_PATH): xbmcvfs.mkdir(PROFILE_PATH)

VIDEO_EXTS = ['.mkv', '.mp4', '.avi', '.wmv', '.mov', '.flv', '.ts', '.m2ts', '.iso']
UA_WEB = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) 115Browser/27.0.6.1"

class QRDialog(xbmcgui.WindowDialog):
    def __init__(self, img_path, text=""):
        self.bg = xbmcgui.ControlImage(0, 0, 1280, 720, "") 
        self.addControl(self.bg)
        self.qr = xbmcgui.ControlImage(440, 160, 400, 400, img_path)
        self.addControl(self.qr)
        self.txt = xbmcgui.ControlLabel(440, 580, 400, 40, text, 'font13', '0xFFFFFFFF', alignment=2)
        self.addControl(self.txt)

class P115Transfer:
    def __init__(self, cookie):
        self.cookie = cookie
        self.headers = {"User-Agent": UA_WEB, "Cookie": self.cookie}

    def get_share_snap(self, share_code, receive_code, cid="0"):
        url = "https://115cdn.com/webapi/share/snap"
        params = {"share_code": share_code, "receive_code": receive_code, "cid": cid, "limit": 100}
        headers = self.headers.copy()
        headers["Referer"] = f"https://115cdn.com/s/{share_code}"
        try:
            r = requests.get(url, params=params, headers=headers, timeout=12).json()
            if r.get("state"):
                items = []
                for f in r['data']['list']:
                    is_dir = 'fid' not in f
                    if is_dir:
                        items.append({"n": f.get('n'), "cid": f.get('cid'), "is_dir": True})
                    else:
                        fname = f.get('n', '')
                        if any(fname.lower().endswith(ext) for ext in VIDEO_EXTS):
                            items.append({"n": fname, "fid": f.get('fid'), "is_dir": False, "size": f"{round(f.get('s', 0)/1024**2, 2)} MB"})
                return True, items
            return False, r.get("msg", "115 Snap 错误")
        except: return False, "115 网络超时"

    def run_transfer_and_locate(self, share_code, receive_code, fid, target_name):
        try:
            receive_url = "https://115cdn.com/webapi/share/receive"
            headers = self.headers.copy()
            headers["Referer"] = f"https://115cdn.com/s/{share_code}"
            data = {"share_code": share_code, "receive_code": receive_code, "file_id": fid}
            
            res = requests.post(receive_url, headers=headers, data=data, timeout=10).json()
            if not res.get("state") and "无需重复接收" not in res.get("msg", ""):
                return False, res.get("msg")
            
            time.sleep(2)
            r_root = requests.get("https://webapi.115.com/files?cid=0", headers=self.headers).json()
            rec_cid = next((i['cid'] for i in r_root.get('data', []) if i['n'] == "最近接收"), "0")
            
            r_files = requests.get("https://webapi.115.com/files", 
                                   params={"cid": rec_cid, "o": "user_ptime", "asc": 0, "limit": 15}, 
                                   headers=self.headers).json()
            
            if r_files.get("state"):
                clean_name = os.path.splitext(target_name)[0]
                for f in r_files.get('data', []):
                    if clean_name in f.get('n', ''): 
                        return True, {"name": f.get('n'), "fid": f.get('fid')}
            return True, {"name": target_name, "fid": None}
        except: return False, "转存寻址失败"

    def delete_task(self, fid, filename, delay=60):
        if not fid: return
        def _worker():
            time.sleep(delay)
            try:
                requests.post("https://webapi.115.com/rb/delete", data={"fid[0]": fid, "ignore_error": 1}, headers=self.headers)
            except: pass
        t = threading.Thread(target=_worker)
        t.daemon = True
        t.start()

class OpenList:
    def __init__(self):
        self.url = ADDON.getSetting("alist_url").rstrip('/')
        self.user = ADDON.getSetting("alist_user")
        self.pwd = ADDON.getSetting("alist_pwd")
        self.headers = {}
        self.cloud_info = {"path": "/115Cloud", "cookie": "", "active": False}
        self.open_info = {"path": "/115Open", "active": False}

    def login(self):
        try:
            r = requests.post(f"{self.url}/api/auth/login", json={"username": self.user, "password": self.pwd}, timeout=5).json()
            if r.get('code') == 200:
                self.headers = {"Authorization": r['data']['token']}
                return True
        except: pass
        return False

    def prepare_storages(self):
        """优先搜索已有挂载点并获取其实际路径"""
        if not self.login(): return False
        try:
            r = requests.get(f"{self.url}/api/admin/storage/list", headers=self.headers).json()
            storages = r.get('data', {}).get('content', [])
            
            # 1. 115 Cloud 处理
            s_cloud = next((s for s in storages if s.get('driver') == "115 Cloud"), None)
            if s_cloud:
                self.cloud_info["path"] = s_cloud['mount_path']
                ck = json.loads(s_cloud.get('addition', '{}')).get('cookie')
                if self._check_cookie(ck):
                    self.cloud_info.update({"cookie": ck, "active": True})
                else:
                    new_ck = self.do_wechat_flow(s_cloud)
                    if new_ck: self.cloud_info.update({"cookie": new_ck, "active": True})
            else:
                if self.do_wechat_flow(None): self.cloud_info["active"] = True

            # 2. 115 Open 处理
            s_open = next((s for s in storages if s.get('driver') == "115 Open"), None)
            if s_open:
                self.open_info.update({"path": s_open['mount_path'], "active": True})
            else:
                if self.do_open_auth(): self.open_info["active"] = True
            
            return self.cloud_info["active"]
        except: return False

    def _check_cookie(self, cookie):
        if not cookie: return False
        try:
            r = requests.get("https://webapi.115.com/user/vip_limit?feature=2", headers={"Cookie": cookie}, timeout=5).json()
            return r.get("state") is True
        except: return False

    def do_wechat_flow(self, storage_item=None):
        try:
            t = requests.get("https://qrcodeapi.115.com/api/1.0/web/1.0/token/").json()["data"]
            qr_path = os.path.join(PROFILE_PATH, "qr_cloud.png")
            qr_url = f"https://uapis.cn/api/v1/image/qrcode?text={urllib.parse.quote(t['qrcode'])}"
            with open(qr_path, 'wb') as f: f.write(requests.get(qr_url).content)
            
            dialog = QRDialog(qr_path, "115 Cloud 扫码 (微信小程序)")
            dialog.show()
            start, new_cookie = time.time(), None
            while time.time() - start < 180 and dialog.bg:
                s = requests.get(f"https://qrcodeapi.115.com/get/status/?uid={t['uid']}&time={t['time']}&sign={t['sign']}").json()
                if s.get("data", {}).get("status") == 2:
                    l = requests.post("https://passportapi.115.com/app/1.0/wechatmini/1.0/login/qrcode/", data={"app": "wechatmini", "account": t["uid"]}).json()
                    if l.get("state"):
                        new_cookie = "; ".join([f"{k}={v}" for k, v in l["data"]["cookie"].items()])
                        break
                time.sleep(2)
            dialog.close()

            if new_cookie:
                if storage_item:
                    add = json.loads(storage_item.get('addition', '{}'))
                    add['cookie'] = new_cookie
                    storage_item['addition'] = json.dumps(add)
                    requests.post(f"{self.url}/api/admin/storage/update", json=storage_item, headers=self.headers)
                    self.cloud_info["path"] = storage_item['mount_path']
                else:
                    # 按照 Addition 结构体补全字段
                    addition = {
                        "root_folder_id": "0",
                        "cookie": new_cookie,
                        "qrcode_token": "",
                        "qrcode_source": "wechatmini",
                        "page_size": 1000,
                        "limit_rate": 2.0
                    }
                    payload = {
                        "mount_path": self.cloud_info["path"], 
                        "driver": "115 Cloud", 
                        "addition": json.dumps(addition)
                    }
                    requests.post(f"{self.url}/api/admin/storage/create", json=payload, headers=self.headers)
                self.cloud_info["cookie"] = new_cookie
                return new_cookie
        except: pass
        return None

    def do_open_auth(self):
        try:
            res = requests.get("https://api.alistgo.com/alist/115/auth_device_code").json()
            cv, uid, qurl = res["code_verifier"], res["resp"]["uid"], res["resp"]["qrcode"]
            qr_path = os.path.join(PROFILE_PATH, "qr_open.png")
            qr_api_url = f"https://uapis.cn/api/v1/image/qrcode?text={urllib.parse.quote(qurl)}"
            with open(qr_path, 'wb') as f: f.write(requests.get(qr_api_url).content)
            dialog = QRDialog(qr_path, "115 Open 未挂载，请扫码")
            dialog.show()
            start = time.time()
            while time.time() - start < 180 and dialog.bg:
                t_res = requests.post("https://api.alistgo.com/alist/115/get_token", json={"code_verifier": cv, "uid": uid}).json()
                resp = t_res.get("resp", {})
                if resp.get("refresh_token"):
                    # 按照 Addition 结构体补全字段
                    addition = {
                        "root_folder_id": "0",
                        "order_by": "user_utime",
                        "order_direction": "desc",
                        "limit_rate": 1.0,
                        "page_size": 200,
                        "access_token": resp["access_token"],
                        "refresh_token": resp["refresh_token"]
                    }
                    payload = {
                        "mount_path": self.open_info["path"], 
                        "driver": "115 Open", 
                        "addition": json.dumps(addition)
                    }
                    requests.post(f"{self.url}/api/admin/storage/create", json=payload, headers=self.headers)
                    dialog.close(); return True
                time.sleep(3)
            dialog.close()
        except: pass
        return False
