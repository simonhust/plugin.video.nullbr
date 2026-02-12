# -*- coding: utf-8 -*-
import sys, urllib.parse, xbmc, xbmcgui, xbmcplugin, requests, xbmcaddon
from resources.lib.op_manager import OpenList, P115Transfer

# 初始化插件常量
ADDON = xbmcaddon.Addon()
BASE_URL = sys.argv[0]
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 else -1
NULLBR_HDR = {
    "X-APP-ID": "QZisWzxhk", 
    "X-API-KEY": "YVnViJKuT044bnGR16vzFRjlWlT42OgM", 
    "User-Agent": "Mozilla/5.0"
}

def main():
    arg_str = sys.argv[2][1:] if len(sys.argv) > 2 else ""
    qs = dict(urllib.parse.parse_qsl(arg_str))
    mode = qs.get('mode')
    
    # 路由逻辑控制
    if not mode:
        # 首页：强制显示搜索入口
        add_search_entry()
        xbmcplugin.endOfDirectory(HANDLE)

    elif mode == 'do_search':
        # 触发键盘输入
        kb = xbmc.Keyboard('', 'NullBR 搜索 (电影/剧集)', False)
        kb.doModal()
        if kb.isConfirmed() and kb.getText():
            search_items(kb.getText())
        else:
            xbmc.executebuiltin("Action(ParentDir)")

    elif mode == 'links':
        list_links(qs.get('id'), qs.get('type'))

    elif mode == 'browse_share':
        list_share_contents(qs.get('url'), qs.get('cid', '0'))
        
    elif mode == 'play_115_file':
        play_video_via_alist(qs.get('url'), qs.get('fid'), qs.get('name'))

def add_search_entry():
    """创建一个固定的搜索按钮入口，确保每次都能触发新搜索"""
    li = xbmcgui.ListItem("[ 点击发起新搜索 ]")
    li.setArt({'icon': "DefaultAddonsSearch.png"})
    u = f"{BASE_URL}?mode=do_search"
    xbmcplugin.addDirectoryItem(HANDLE, u, li, True)

def search_items(query):
    """搜索并显示资源列表"""
    add_search_entry() # 结果页顶部也保留搜索入口
    
    url = f"https://api.nullbr.eu.org/search?query={urllib.parse.quote(query)}&page=1"
    try:
        resp = requests.get(url, headers=NULLBR_HDR, verify=False).json()
        for i in resp.get('items', []):
            if i.get('115-flg') == 1:
                title = i.get('title')
                li = xbmcgui.ListItem(title)
                img = "https://wsrv.nl/?url=https://image.tmdb.org/t/p/w500" + (i.get('poster') or "")
                li.setArt({'poster': img, 'thumb': img, 'icon': img})
                li.setInfo('video', {'title': title, 'plot': i.get('overview', '')})
                
                u = f"{BASE_URL}?mode=links&id={i['tmdbid']}&type={i['media_type']}"
                xbmcplugin.addDirectoryItem(HANDLE, u, li, True)
        
        xbmcplugin.setContent(HANDLE, 'movies')
        xbmcplugin.endOfDirectory(HANDLE)
    except Exception as e:
        xbmcgui.Dialog().notification("搜索失败", str(e))

def list_links(tid, mtype):
    """获取该影视条目的 115 分享链接列表"""
    url = f"https://api.nullbr.eu.org/{mtype}/{tid}/115"
    try:
        resp = requests.get(url, headers=NULLBR_HDR, verify=False).json()
        for l in resp.get('115', []):
            label = f"[{l.get('resolution', 'HD')}] {l.get('size', '')} - {l.get('title')}"
            li = xbmcgui.ListItem(label)
            u = f"{BASE_URL}?mode=browse_share&url={urllib.parse.quote(l['share_link'])}"
            xbmcplugin.addDirectoryItem(HANDLE, u, li, True)
        xbmcplugin.endOfDirectory(HANDLE)
    except: pass

def list_share_contents(share_url, cid='0'):
    """解析 115 分享链接内的文件列表"""
    xbmc.executebuiltin('ActivateWindow(busydialog)')
    try:
        ol = OpenList()
        if not ol.prepare_storages(): return
        
        # 解析 ShareCode 和 Password
        sc = share_url.split('/s/')[1].split('?')[0].replace('#', '').strip() if '/s/' in share_url else share_url.split('/')[-1].split('?')[0]
        rc = urllib.parse.parse_qs(urllib.parse.urlparse(share_url).query).get('password', [''])[0].replace('#', '').strip()
        
        transfer = P115Transfer(ol.cloud_info["cookie"])
        success, items = transfer.get_share_snap(sc, rc, cid)
        
        if not success: return
        
        for i in items:
            if i['is_dir']:
                li = xbmcgui.ListItem(f"{i['n']}")
                u = f"{BASE_URL}?mode=browse_share&url={urllib.parse.quote(share_url)}&cid={i['cid']}"
                xbmcplugin.addDirectoryItem(HANDLE, u, li, True)
            else:
                li = xbmcgui.ListItem(f"[{i['size']}] {i['n']}")
                li.setInfo('video', {'title': i['n']})
                li.setProperty('IsPlayable', 'true')
                u = f"{BASE_URL}?mode=play_115_file&url={urllib.parse.quote(share_url)}&fid={i['fid']}&name={urllib.parse.quote(i['n'])}"
                xbmcplugin.addDirectoryItem(HANDLE, u, li, False)
        xbmcplugin.endOfDirectory(HANDLE)
    finally:
        xbmc.executebuiltin('Dialog.Close(busydialog)')

def play_video_via_alist(share_url, fid, filename):
    """转存并使用 OpenList 识别出的挂载点进行播放"""
    xbmc.executebuiltin('ActivateWindow(busydialog)')
    try:
        ol = OpenList()
        # prepare_storages 会自动获取现有的 115 Cloud 和 115 Open 挂载路径
        if not ol.prepare_storages(): return

        sc = share_url.split('/s/')[1].split('?')[0].replace('#', '').strip() if '/s/' in share_url else share_url.split('/')[-1].split('?')[0]
        rc = urllib.parse.parse_qs(urllib.parse.urlparse(share_url).query).get('password', [''])[0].replace('#', '').strip()

        transfer = P115Transfer(ol.cloud_info["cookie"])
        success, res_data = transfer.run_transfer_and_locate(sc, rc, fid, filename)
        
        if not success:
            xbmcgui.Dialog().ok("播放失败", f"错误: {res_data}")
            return

        final_name = res_data["name"]
        final_fid = res_data["fid"]

        # --- 关键修改：动态识别挂载点 ---
        # 优先使用 115 Open 驱动（播放更稳），如果没有则退回到 115 Cloud 驱动路径
        target_mount = ol.open_info["path"] if ol.open_info["active"] else ol.cloud_info["path"]
        
        alist_url = ADDON.getSetting("alist_url").rstrip('/')
        host = urllib.parse.urlparse(alist_url).netloc
        auth = f"{urllib.parse.quote_plus(ol.user)}:{urllib.parse.quote_plus(ol.pwd)}@"
        
        # 115 默认接收目录是“最近接收”
        # 这里 target_mount 已经是来自 AList API 的真实路径（如 /aliyun/115）
        play_path = f"/dav{target_mount}/{urllib.parse.quote('最近接收')}/{urllib.parse.quote(final_name)}"
        play_url = f"http://{auth}{host}{play_path}"

        li = xbmcgui.ListItem(path=play_url)
        li.setInfo('video', {'title': final_name})
        xbmcplugin.setResolvedUrl(HANDLE, True, li)

        # 延迟清理
        if final_fid:
            transfer.delete_task(final_fid, final_name, delay=60)

    finally:
        xbmc.executebuiltin('Dialog.Close(busydialog)')

if __name__ == '__main__':
    main()
