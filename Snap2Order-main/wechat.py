import tls_support
"""Native WeChat Mini Program adapters; AppSecret stays on the server."""
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

class WeChatError(Exception):
    pass

_cache={'value':'','expires':0}
_lock=threading.Lock()

def credentials():
    appid,secret=os.getenv('WECHAT_APP_ID'),os.getenv('WECHAT_APP_SECRET')
    if not appid or not secret:
        raise WeChatError('小程序接口未配置。请在服务器设置 WECHAT_APP_ID 和 WECHAT_APP_SECRET。')
    return appid,secret

def fetch(url,payload=None):
    req=urllib.request.Request(url,data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=15,context=tls_support.context()) as r:
            data=r.read(1024*1024+1)
            if len(data)>1024*1024:
                raise WeChatError('微信返回内容过大，请重试。')
            return data
    except (urllib.error.URLError,TimeoutError):
        # Never include URLs containing secret/token in an error message.
        raise WeChatError('微信接口暂不可用，请稍后重试。')

def exchange_code(code):
    appid,secret=credentials()
    params=urllib.parse.urlencode({'appid':appid,'secret':secret,'js_code':code,'grant_type':'authorization_code'})
    try:
        d=json.loads(fetch('https://api.weixin.qq.com/sns/jscode2session?'+params))
        if not d.get('openid') or d.get('errcode',0):
            raise WeChatError('微信登录凭证已失效或配置有误，请重新登录。')
        return d['openid']
    except (ValueError,KeyError):
        raise WeChatError('微信登录返回格式异常，请重试。')

def access_token():
    appid,secret=credentials()
    with _lock:
        if _cache['expires']>time.time():
            return _cache['value']
        params=urllib.parse.urlencode({'grant_type':'client_credential','appid':appid,'secret':secret})
        try:
            d=json.loads(fetch('https://api.weixin.qq.com/cgi-bin/token?'+params))
            token=d.get('access_token')
            if not token:
                raise WeChatError('无法获取小程序服务凭证，请检查 AppID、AppSecret 和服务器 IP 白名单。')
            _cache.update(value=token,expires=time.time()+max(0,int(d.get('expires_in',7200))-300))
            return token
        except (ValueError,KeyError):
            raise WeChatError('微信服务凭证返回格式异常。')

def store_code(store_id):
    env=os.getenv('WECHAT_CODE_ENV','release')
    if env not in ('release','trial','develop'):
        raise WeChatError('WECHAT_CODE_ENV 须为 release、trial 或 develop。')
    body=fetch('https://api.weixin.qq.com/wxa/getwxacodeunlimit?'+urllib.parse.urlencode({'access_token':access_token()}),
               {'scene':store_id,'page':'pages/menu/index','width':430,'check_path':env=='release','env_version':env})
    if not body.startswith(b'\x89PNG') and not body.startswith(b'\xff\xd8'):
        raise WeChatError('小程序码生成失败，请检查发布版本、页面路径和微信平台配置。')
    return body
