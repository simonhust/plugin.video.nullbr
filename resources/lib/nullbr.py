import requests

APP_ID = "QZisWzxhk"
API_KEY = "YVnViJKuT044bnGR16vzFRjlWlT42OgM"
BASE_URL = "https://api.nullbr.eu.org"
TMDB_IMG = "https://wsrv.nl/?url=https://image.tmdb.org/t/p/w500"

def get_headers():
    return {
        "X-APP-ID": APP_ID,
        "X-API-KEY": API_KEY,
        "User-Agent": "Mozilla/5.0"
    }

def search_meta(query):
    """搜索并过滤出有 115 资源的电影或剧集"""
    url = f"{BASE_URL}/search"
    params = {"query": query, "page": 1}
    try:
        resp = requests.get(url, headers=get_headers(), params=params)
        if resp.status_code == 200:
            all_items = resp.json().get("items", [])
            return [
                item for item in all_items 
                if item.get("media_type") in ["movie", "tv"] and item.get("115-flg") == 1
            ]
    except: return []

def get_115_details(tmdbid, media_type):
    """获取具体的 115 分享链接列表"""
    url = f"{BASE_URL}/{media_type}/{tmdbid}/115"
    try:
        resp = requests.get(url, headers=get_headers())
        if resp.status_code == 200:
            return resp.json().get("115", [])
    except: return []
