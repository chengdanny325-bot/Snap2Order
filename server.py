"""Snap2Order: authenticated multi-store demo, standard-library runtime."""
import base64
import store_config
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(ROOT / 'vendor'))
# Recover a key entered in the example file, a common first-run mistake.
# Never overwrite an existing .env or expose credentials in logs.
example = ROOT / '.env.example'
if not (ROOT / '.env').exists() and example.exists():
    example_text = example.read_text(encoding='utf-8-sig')
    if re.search(r'^OCR_API_KEY[ \t]*=[ \t]*[^\s#]+', example_text, re.M):
        (ROOT / '.env').write_text(example_text, encoding='utf-8')
        (ROOT / '.env').chmod(0o600)
        print('已将 .env.example 中的配置保存到 .env。', flush=True)
# Small .env reader, no shell execution. Existing environment variables win.
if (ROOT / '.env').exists():
    for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            if re.fullmatch(r'[A-Z_][A-Z0-9_]*', key):
                os.environ.setdefault(key, value.strip().strip('"\''))

import ocr_cloud
import dish_media
DB_PATH = Path(os.getenv('DATABASE_PATH', str(ROOT / 'data' / 'snap2order.sqlite3')))
SECURE_COOKIE = os.getenv('COOKIE_SECURE', '0') == '1'
PUBLIC_URL = os.getenv('PUBLIC_URL', '').rstrip('/')
PASSWORD_ROUNDS = 600_000

class APIError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def now():
    return datetime.now(timezone.utc).isoformat()


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=15000')
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > 6:
            raise RuntimeError('数据库版本较新，请使用对应版本的服务')
        db.executescript((ROOT / 'schema.sql').read_text())
        columns = {r['name'] for r in db.execute('PRAGMA table_info(menu_items)')}
        if 'image_url' not in columns:
            db.execute('ALTER TABLE menu_items ADD COLUMN image_url TEXT')
        store_columns = {r['name'] for r in db.execute('PRAGMA table_info(stores)')}
        for column, ddl in [('draft_name', 'ALTER TABLE stores ADD COLUMN draft_name TEXT'),
                            ('brand_json', "ALTER TABLE stores ADD COLUMN brand_json TEXT NOT NULL DEFAULT '{}'"),
                            ('brand_draft_json', "ALTER TABLE stores ADD COLUMN brand_draft_json TEXT NOT NULL DEFAULT '{}'")]:
            if column not in store_columns:
                db.execute(ddl)
        additions = {
            'stores': [('config_json', "TEXT NOT NULL DEFAULT '{}'"), ('config_draft_json', "TEXT NOT NULL DEFAULT '{}'" )],
            'menu_items': [('details_json', "TEXT NOT NULL DEFAULT '{}'"), ('stock', 'INTEGER')],
            'orders': [('resolution', 'TEXT'), ('reason', "TEXT NOT NULL DEFAULT ''"), ('discount_cents', 'INTEGER NOT NULL DEFAULT 0'), ('coupon_id', 'TEXT'), ('points_awarded', 'INTEGER NOT NULL DEFAULT 0')],
        }
        for table, columns_to_add in additions.items():
            existing = {r['name'] for r in db.execute('PRAGMA table_info('+table+')')}
            for column, definition in columns_to_add:
                if column not in existing: db.execute('ALTER TABLE '+table+' ADD COLUMN '+column+' '+definition)
        db.execute('PRAGMA user_version=6')
        db.execute('UPDATE stores SET draft_name=name WHERE draft_name IS NULL')
        # Interrupted OCR jobs can be retried; never show an endless processing state.
        db.execute("UPDATE ocr_sources SET status='failed', error='识别被服务重启中断，请重试。' WHERE status='processing'")
        db.execute('DELETE FROM sessions WHERE expires_at < ?', (int(time.time()),))
        db.execute('DELETE FROM rate_limits WHERE window < ?', (int(time.time()) - 86400,))


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), PASSWORD_ROUNDS).hex()
    return f'pbkdf2_sha256${PASSWORD_ROUNDS}${salt}${value}'


def verify_password(password, stored):
    try:
        method, rounds, salt, value = stored.split('$')
        if method != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, value)
    except (ValueError, TypeError):
        return False


def text(value, label, maximum, required=True):
    if not isinstance(value, str):
        raise APIError(f'{label}格式不正确')
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise APIError(f'请填写{label}（最多 {maximum} 字）')
    return value


def cents(value):
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError()
        d = Decimal(str(value))
        if not d.is_finite() or d <= 0 or d > Decimal('9999.99') or d != d.quantize(Decimal('0.01')):
            raise ValueError()
        return int(d * 100)
    except (ValueError, InvalidOperation):
        raise APIError('价格须为 0.01～9999.99 元，最多两位小数')


def normalized_items(raw, publish=False):
    if not isinstance(raw, list) or len(raw) > 100 or (publish and not raw):
        raise APIError('菜单须包含 1～100 道菜')
    result, ids = [], set()
    for item in raw:
        if not isinstance(item, dict):
            raise APIError('菜品格式错误')
        name = text(item.get('name', ''), '菜名', 80, required=publish)
        category = text(item.get('category') or '其他', '分类', 30)
        checked = item.get('checked') is True
        if publish and not checked:
            raise APIError('请逐项检查菜名和价格，并勾选“已检查”')
        value = item.get('price')
        amount = cents(value) / 100 if publish else None
        if not publish and value not in (None, ''):
            try:
                amount = cents(value) / 100
            except APIError:
                amount = None
                checked = False
        identifier = item.get('id')
        if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', identifier):
            identifier = secrets.token_hex(16)
        if identifier in ids:
            raise APIError('菜品编号重复，请重新加载菜单')
        ids.add(identifier)
        confidence = item.get('confidence')
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            confidence = None
        image_url = item.get('image_url') or None
        if image_url is not None and (not isinstance(image_url,str) or not (image_url in dish_media.STOCK_URLS or re.fullmatch(r'/api/dish-images/[a-f0-9]{32}',image_url))):
            raise APIError('菜品图片地址无效，请重新上传或从素材库选择')
        try:
            details = store_config.item_details(item)
        except ValueError as e:
            raise APIError(str(e))
        result.append({**details, 'image_url': image_url, 'id': identifier, 'name': name, 'price': amount, 'category': category,
                       'stock_update': item.get('stock_update') is True, 'available': item.get('available', True) is True, 'checked': checked,
                       'confidence': confidence})
    if publish and not any(i['available'] for i in result):
        raise APIError('请至少上架一道菜后再发布')
    return result


BRAND_THEMES = store_config.THEMES


def parse_brand(raw):
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    theme = data.get('theme')
    logo_url = data.get('logo_url')
    return {'logo_url': logo_url if isinstance(logo_url, str) and re.fullmatch(r'/api/store-logos/[a-f0-9]{32}', logo_url) else None,
            'theme': theme if theme in BRAND_THEMES else 'fresh'}


def normalized_brand(raw, db, store_id):
    if raw is None:
        return {'logo_url': None, 'theme': 'fresh'}
    if not isinstance(raw, dict):
        raise APIError('品牌配置格式错误')
    theme = raw.get('theme', 'fresh')
    if theme not in BRAND_THEMES:
        raise APIError('品牌风格无效，请重新选择')
    logo_url = raw.get('logo_url') or None
    if logo_url is not None:
        if not isinstance(logo_url, str) or not re.fullmatch(r'/api/store-logos/[a-f0-9]{32}', logo_url):
            raise APIError('Logo 地址无效，请重新上传')
        if not db.execute('SELECT id FROM store_logos WHERE id=? AND store_id=?', (logo_url.rsplit('/', 1)[1], store_id)).fetchone():
            raise APIError('Logo 不属于当前店铺', 403)
    return {'logo_url': logo_url, 'theme': theme}


def get_store(db, user_id):
    store = db.execute('SELECT * FROM stores WHERE owner_id=?', (user_id,)).fetchone()
    if not store:
        raise APIError('店铺不存在', 404)
    return store


def serialize_store(db, store, merchant=False):
    rows = db.execute('SELECT * FROM menu_items WHERE store_id=? AND active=1 ORDER BY position', (store['id'],)).fetchall()
    items = [{'id': i['id'], 'name': i['name'], 'price': i['price_cents']/100, 'category': i['category'],
              **json.loads(i['details_json']), 'stock': i['stock'], 'image_url': i['image_url'], 'available': bool(i['available']), 'checked': True, 'confidence': i['confidence']} for i in rows if merchant or i['available']]
    result = {'id': store['id'], 'name': store['name'], 'published': bool(store['published']),
              'brand': parse_brand(store['brand_json']), 'config': store_config.normalize(json.loads(store['config_json'])), 'items': items}
    if merchant:
        result.update(draft=json.loads(store['draft_json']), source_id=store['draft_source_id'],
                      config_draft=store_config.normalize(json.loads(store['config_draft_json'])), draft_name=store['draft_name'] or store['name'], brand_draft=parse_brand(store['brand_draft_json']))
    return result


def serialize_order(db, order):
    rows = db.execute('SELECT * FROM order_items WHERE order_id=? ORDER BY id', (order['id'],)).fetchall()
    store = db.execute('SELECT name FROM stores WHERE id=?', (order['store_id'],)).fetchone()
    return {'id': order['id'], 'store_id': order['store_id'], 'store_name': store['name'],
            'total': order['total_cents']/100, 'note': order['note'], 'status': order['resolution'] or order['status'], 'reason': order['reason'], 'discount': order['discount_cents']/100,
            'payment': order['payment_status'], 'created': order['created_at'],
            'items': [{'name': i['name_snapshot'], 'price': i['price_cents_snapshot']/100, 'qty': i['quantity']} for i in rows]}


def release_order(db, order, resolution, reason):
    # Transactional and idempotent: a terminal resolution can release inventory only once.
    if order['resolution'] or order['status'] == 'completed':
        raise APIError('订单已结束，请刷新',409)
    for row in db.execute('SELECT menu_item_id,quantity FROM order_items WHERE order_id=?',(order['id'],)):
        db.execute('UPDATE menu_items SET stock=stock+? WHERE id=? AND stock IS NOT NULL',(row['quantity'],row['menu_item_id']))
    if order['points_awarded']:
        db.execute('UPDATE members SET points=MAX(0,points-?) WHERE store_id=? AND customer_id=?',(order['points_awarded'],order['store_id'],order['customer_id']))
    if order['coupon_id']:
        db.execute('UPDATE coupons SET used_order=NULL WHERE id=? AND used_order=?',(order['coupon_id'],order['id']))
    db.execute('UPDATE orders SET resolution=?,reason=?,updated_at=? WHERE id=?',(resolution,reason,now(),order['id']))

def expire_orders(db):
    cutoff = datetime.fromtimestamp(time.time()-1800, timezone.utc).isoformat()
    for order in db.execute("SELECT * FROM orders WHERE status='pending' AND resolution IS NULL AND payment_status='unpaid' AND created_at<?",(cutoff,)).fetchall():
        release_order(db,order,'expired','30 分钟未完成支付，订单已关闭')



class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Do not log images, tokens, passwords, or request bodies.
        if not self.path.startswith('/api/'):
            super().log_message(fmt, *args)

    def send(self, data, status=200, cookie=None):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.common_headers()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def common_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'SAMEORIGIN' if urlsplit(self.path).path=='/merchant/preview' else 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors "+("'self'" if urlsplit(self.path).path=='/merchant/preview' else "'none'")+"; form-action 'self'; base-uri 'self'")

    def body(self, image=False):
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise APIError('请求大小无效')
        limit = 8 * 1024 * 1024 if image else 128 * 1024
        if not 0 < length <= limit:
            raise APIError('图片请小于 8MB' if image else '请求内容为空或过大', 413)
        if self.headers.get('Transfer-Encoding'):
            raise APIError('不支持此上传方式', 400)
        raw = self.rfile.read(length)
        if image:
            return raw
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            raise APIError('需要 JSON 请求', 415)
        try:
            data = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, UnicodeDecodeError):
            raise APIError('请求格式错误')

    def check_origin(self):
        origin = self.headers.get('Origin')
        allowed = PUBLIC_URL or ('http://' + self.headers.get('Host', ''))
        if origin and origin != allowed:
            raise APIError('请从本站页面提交操作', 403)
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise APIError('不接受跨站请求', 403)

    def session(self, db, role=None, optional=False, csrf=False):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
            customer_scope = role == 'customer' or (role is None and self.headers.get('X-Client-Type') == 'customer')
            cookie_name = 'snap_guest' if customer_scope else 'snap_session'
            token = cookies[cookie_name].value if cookie_name in cookies else ''
            if self.headers.get('Authorization', '').startswith('Bearer '):
                token = self.headers['Authorization'][7:]
        except Exception:
            token = ''
        row = db.execute('SELECT s.*,u.username,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=? AND expires_at>?',
                         (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone() if token else None
        if not row:
            if optional:
                return None
            raise APIError('请先登录', 401)
        if role and row['role'] != role:
            raise APIError('该操作需要' + ('商家' if role == 'merchant' else '顾客') + '账号', 403)
        if csrf and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), row['csrf_token']):
            raise APIError('登录状态已更新，请刷新页面后重试', 403)
        return row

    def limit(self, bucket, maximum, seconds):
        # Commit counters separately, including rejected/failed authentication requests.
        window = int(time.time()) // seconds * seconds
        with connect() as db:
            db.execute('INSERT INTO rate_limits(bucket,window,count) VALUES(?,?,1) ON CONFLICT(bucket,window) DO UPDATE SET count=count+1', (bucket, window))
            count = db.execute('SELECT count FROM rate_limits WHERE bucket=? AND window=?', (bucket, window)).fetchone()[0]
        if count > maximum:
            raise APIError('操作太频繁，请稍后重试', 429)

    def ip_bucket(self):
        # Trust the network peer, not arbitrary forwarded headers.
        return hashlib.sha256(self.client_address[0].encode()).hexdigest()

    def start_session(self, db, user_id, customer=False):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, int(time.time()) + 7*86400))
        cookie_name = 'snap_guest' if customer else 'snap_session'
        cookie = f'{cookie_name}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800' + ('; Secure' if SECURE_COOKIE else '')
        return csrf, cookie, token

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path.startswith('/api/'):
                return self.get_api(path)
            routes = {'/': 'index.html', '/login': 'login.html', '/merchant/menu': 'merchant-menu.html',
                      '/merchant/preview': 'customer.html', '/merchant/orders': 'merchant-orders.html', '/customer/orders': 'customer-orders.html', '/shops': 'shops.html'}
            if re.fullmatch(r'/s/[a-f0-9]{24}', path):
                filename = 'customer.html'
            elif path in routes:
                filename = routes[path]
            elif path in dish_media.STOCK_URLS:
                filename = path.removeprefix('/')
            elif re.fullmatch(r'/assets/oc/[a-z]+\.(svg|png)', path):
                filename = path[1:]
            elif path in ('/style.css', '/common.js', '/auth.js', '/merchant.js', '/orders.js', '/customer.js', '/camera.js', '/shops.js', '/favicon.svg'):
                filename = path[1:]
            else:
                raise APIError('页面不存在', 404)
            file = ROOT / 'static' / filename
            types = {'.png':'image/png', '.html':'text/html; charset=utf-8', '.css':'text/css; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.svg':'image/svg+xml'}
            body = file.read_bytes()
            self.send_response(200)
            self.common_headers()
            self.send_header('Content-Type', types[file.suffix])
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except APIError as e:
            self.send({'error': e.message}, e.status)
        except Exception:
            logging.exception('GET failed')
            self.send({'error': '服务暂时不可用，请重试'}, 500)

    def get_api(self, path):
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            expire_orders(db)
            db.commit()
            if path == '/api/merchant/preview':
                user = self.session(db,'merchant')
                store = get_store(db,user['user_id'])
                result = serialize_store(db,store,True)
                result.update(name=result['draft_name'],brand=result['brand_draft'],config=result['config_draft'],items=[i for i in result['draft'] if i.get('available',True)])
                return self.send({'store':result})
            marketing = re.fullmatch(r'/api/stores/([a-f0-9]{24})/benefits',path)
            if marketing:
                user = self.session(db,'customer')
                store = db.execute('SELECT * FROM stores WHERE id=? AND published=1',(marketing[1],)).fetchone()
                if not store: raise APIError('店铺不存在',404)
                member = db.execute('SELECT * FROM members WHERE store_id=? AND customer_id=?',(store['id'],user['user_id'])).fetchone()
                coupons = db.execute('SELECT * FROM coupons WHERE store_id=? AND customer_id=? AND used_order IS NULL',(store['id'],user['user_id'])).fetchall()
                day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                claims = db.execute('SELECT kind FROM benefit_claims WHERE store_id=? AND customer_id=? AND day=?',(store['id'],user['user_id'],day)).fetchall()
                result = {'member':dict(member) if member else None,'coupons':[dict(c) for c in coupons],'claims':[c['kind'] for c in claims]}
                config = store_config.normalize(json.loads(store['config_json']))
                if config['modules']['oc']:
                    owned = db.execute('SELECT item_id FROM oc_purchases WHERE store_id=?',(store['id'],)).fetchall()
                    result['oc'] = {'owned':[r['item_id'] for r in owned]}
                return self.send(result)
            if path == '/api/image-library':
                return self.send({'images':dish_media.CATALOG})
            if path == '/api/oc-catalog':
                import oc_catalog
                return self.send(oc_catalog.catalog())
            image_match = re.fullmatch(r'/api/dish-images/([a-f0-9]{32})',path)
            if image_match:
                image = db.execute('SELECT * FROM dish_images WHERE id=?',(image_match[1],)).fetchone()
                if not image:
                    raise APIError('图片不存在',404)
                live = db.execute('SELECT 1 FROM menu_items m JOIN stores s ON s.id=m.store_id WHERE m.image_url=? AND m.active=1 AND m.available=1 AND s.published=1',(path,)).fetchone()
                if not live:
                    live = db.execute('SELECT 1 FROM stores WHERE published=1 AND config_json LIKE ?',('%'+path+'%',)).fetchone()
                if not live:
                    user = self.session(db,optional=True)
                    owner = db.execute('SELECT owner_id FROM stores WHERE id=?',(image['store_id'],)).fetchone()
                    if not user or user['user_id']!=owner['owner_id']:
                        raise APIError('图片不存在',404)
                self.send_response(200);self.common_headers()
                self.send_header('Content-Type',image['mime'])
                self.send_header('Cache-Control','private, no-store')
                self.send_header('Content-Length',str(len(image['image'])))
                self.end_headers();self.wfile.write(image['image']);return
            logo_match = re.fullmatch(r'/api/store-logos/([a-f0-9]{32})',path)
            if logo_match:
                logo = db.execute('SELECT * FROM store_logos WHERE id=?',(logo_match[1],)).fetchone()
                if not logo:
                    raise APIError('图片不存在',404)
                live = db.execute('SELECT 1 FROM stores WHERE id=? AND published=1 AND brand_json LIKE ?',(logo['store_id'],'%'+path+'%')).fetchone()
                if not live:
                    user = self.session(db,optional=True)
                    owner = db.execute('SELECT owner_id FROM stores WHERE id=?',(logo['store_id'],)).fetchone()
                    if not user or user['user_id']!=owner['owner_id']:
                        raise APIError('图片不存在',404)
                self.send_response(200);self.common_headers()
                self.send_header('Content-Type',logo['mime'])
                self.send_header('Cache-Control','private, no-store')
                self.send_header('Content-Length',str(len(logo['image'])))
                self.end_headers();self.wfile.write(logo['image']);return
            oc_match = re.fullmatch(r'/api/oc-images/([a-f0-9]{24})',path)
            if oc_match:
                image = db.execute('SELECT * FROM store_oc WHERE store_id=?',(oc_match[1],)).fetchone()
                if not image:
                    raise APIError('图片不存在',404)
                live = db.execute('SELECT 1 FROM stores WHERE id=? AND published=1',(oc_match[1],)).fetchone()
                if not live:
                    user = self.session(db,optional=True)
                    owner = db.execute('SELECT owner_id FROM stores WHERE id=?',(oc_match[1],)).fetchone()
                    if not user or user['user_id']!=owner['owner_id']:
                        raise APIError('图片不存在',404)
                self.send_response(200);self.common_headers()
                self.send_header('Content-Type',image['mime'])
                self.send_header('Cache-Control','private, no-store')
                self.send_header('Content-Length',str(len(image['image'])))
                self.end_headers();self.wfile.write(image['image']);return
            if path == '/api/stores':
                rows = db.execute('SELECT id,name,brand_json FROM stores WHERE published=1 ORDER BY created_at DESC LIMIT 100').fetchall()
                return self.send({'stores':[{'id':r['id'],'name':r['name'],**parse_brand(r['brand_json'])} for r in rows]})
            if path == '/api/me':
                user = self.session(db, optional=True)
                return self.send({'user': None} if not user else {'user': {'id':user['user_id'], 'username':'本设备顾客' if user['username'].startswith('guest_') else user['username'], 'role':user['role']}, 'csrf':user['csrf_token']})
            if path == '/api/merchant/store':
                user = self.session(db, 'merchant')
                return self.send({'store':serialize_store(db,get_store(db,user['user_id']),True), 'ocr':ocr_cloud.configuration(), 'public_url':PUBLIC_URL, 'ai_configured':bool(os.getenv('STORE_AI_API_KEY')), 'ai_logo_configured':store_config.logo_configured()})
            if path == '/api/merchant/orders':
                user = self.session(db, 'merchant')
                store = get_store(db, user['user_id'])
                rows = db.execute('SELECT * FROM orders WHERE store_id=? ORDER BY created_at DESC LIMIT 200',(store['id'],)).fetchall()
                return self.send({'store': {'id':store['id'],'name':store['name']}, 'orders':[serialize_order(db,o) for o in rows]})
            if path == '/api/customer/orders':
                user = self.session(db, 'customer')
                rows = db.execute('SELECT * FROM orders WHERE customer_id=? ORDER BY created_at DESC LIMIT 200',(user['user_id'],)).fetchall()
                return self.send({'orders':[serialize_order(db,o) for o in rows]})
            if path in ('/api/merchant/qrcode','/api/merchant/qrcode-daka'):
                user = self.session(db, 'merchant')
                store = get_store(db,user['user_id'])
                if not store['published']:
                    raise APIError('请先发布菜单',400)
                if path.endswith('-daka'):
                    config = store_config.normalize(json.loads(store['config_json']))
                    if not config['modules']['membership']:
                        raise APIError('请先在模块设置中启用会员积分',400)
                import segno
                origin = PUBLIC_URL or ('http://' + self.headers.get('Host','localhost:8765'))
                link = origin + '/s/' + store['id'] + ('?daka=1' if path.endswith('-daka') else '')
                qr = segno.make(link, error='m', micro=False)
                import io
                buffer = io.BytesIO(); qr.save(buffer, kind='svg', scale=7, border=4)
                body = buffer.getvalue()
                self.send_response(200); self.common_headers()
                self.send_header('Content-Type','image/svg+xml')
                self.send_header('Content-Disposition', 'attachment; filename="store-'+store['id']+('-daka' if path.endswith('-daka') else '')+'.svg"')
                self.send_header('Cache-Control','private, no-store')
                self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
            if path == '/api/merchant/minicode':
                user = self.session(db,'merchant')
                store = get_store(db,user['user_id'])
                if not store['published']:
                    raise APIError('请先发布菜单')
                import wechat
                try:
                    body = wechat.store_code(store['id'])
                except wechat.WeChatError as e:
                    raise APIError(str(e),503)
                self.send_response(200); self.common_headers(); self.send_header('Content-Type','image/png')
                self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
            match = re.fullmatch(r'/api/stores/([a-f0-9]{24})',path)
            if match:
                store = db.execute('SELECT * FROM stores WHERE id=? AND published=1',(match[1],)).fetchone()
                if not store:
                    raise APIError('这家小店尚未发布菜单，或链接无效',404)
                return self.send({'store':serialize_store(db,store)})
            match = re.fullmatch(r'/api/orders/([a-f0-9]{24})',path)
            if match:
                user = self.session(db)
                order = self.owned_order(db,user,match[1])
                return self.send({'order':serialize_order(db,order)})
            match = re.fullmatch(r'/api/merchant/sources/([a-f0-9]{24})', path)
            if match:
                user = self.session(db, 'merchant')
                store = get_store(db,user['user_id'])
                source = db.execute('SELECT image,mime FROM ocr_sources WHERE id=? AND store_id=?',(match[1],store['id'])).fetchone()
                if not source:
                    raise APIError('图片不存在',404)
                self.send_response(200); self.common_headers(); self.send_header('Content-Type',source['mime'])
                self.send_header('Cache-Control','private, no-store'); self.send_header('Content-Length',str(len(source['image'])))
                self.end_headers(); self.wfile.write(source['image']); return
            raise APIError('接口不存在',404)

    def owned_order(self, db, user, identifier):
        if user['role'] == 'customer':
            order = db.execute('SELECT * FROM orders WHERE id=? AND customer_id=?',(identifier,user['user_id'])).fetchone()
        else:
            order = db.execute('SELECT o.* FROM orders o JOIN stores s ON s.id=o.store_id WHERE o.id=? AND s.owner_id=?',(identifier,user['user_id'])).fetchone()
        if not order:
            raise APIError('订单不存在',404)
        return order

    def do_POST(self):
        try:
            self.check_origin()
            path = urlsplit(self.path).path
            if path == '/api/merchant/dish-images':
                return self.upload_dish_image()
            if path == '/api/merchant/logo':
                return self.upload_logo()
            if path == '/api/merchant/ocr':
                return self.upload_ocr()
            data = self.body()
            if path == '/api/customer/session':
                return self.guest_session()
            if path == '/api/auth/wechat':
                return self.wechat_login(data)
            if path in ('/api/auth/register','/api/auth/login'):
                return self.auth(path, data)
            with connect() as db:
                # Serialize write transactions and price reads to avoid TOCTOU price changes.
                db.execute('BEGIN IMMEDIATE')
                user = self.session(db,csrf=True)
                if path == '/api/auth/logout':
                    db.execute('DELETE FROM sessions WHERE token_hash=?',(user['token_hash'],))
                    db.commit()
                    return self.send({'ok':True},cookie='snap_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0'+('; Secure' if SECURE_COOKIE else ''))
                expire_orders(db)
                db.commit()
                db.execute('BEGIN IMMEDIATE')
                if path == '/api/merchant/logo-generate':
                    if user['role'] != 'merchant': raise APIError('需要商家账号',403)
                    db.commit()
                    self.limit('logo-ai:'+user['user_id'],10,3600)
                    try: result=store_config.generate_logo(data.get('name',''),data.get('theme','universal'),data.get('prompt',''))
                    except ValueError as e: raise APIError(str(e),400)
                    return self.send(result)
                if path == '/api/merchant/oc-generate':
                    if user['role'] != 'merchant': raise APIError('需要商家账号',403)
                    db.commit()
                    self.limit('oc-ai:'+user['user_id'],10,3600)
                    store = get_store(db,user['user_id'])
                    name = text(data.get('name',''),'OC 名字',30)
                    description = text(data.get('description',''),'OC 描述',500)
                    try: result=store_config.generate_oc(name,description)
                    except ValueError as e: raise APIError(str(e),400)
                    db.execute('BEGIN IMMEDIATE')
                    db.execute('INSERT OR REPLACE INTO store_oc(store_id,name,description,mime,image,created_at) VALUES(?,?,?,?,?,?)',(store['id'],name,description,result['mime'],result['image'],now()))
                    db.commit()
                    return self.send({'image_url':'/api/oc-images/'+store['id'],'name':name,'description':description})
                if path == '/api/merchant/recommend':
                    if user['role'] != 'merchant': raise APIError('需要商家账号',403)
                    db.commit()
                    self.limit('recommend:'+user['user_id'],20,3600)
                    store = get_store(db,user['user_id'])
                    images = []
                    if data.get('use_images') is True and os.getenv('STORE_AI_API_KEY'):
                        for table, url in [('store_logos',data.get('logo_url')),('dish_images',data.get('banner_url'))]:
                            if url:
                                row = db.execute('SELECT mime,image FROM '+table+' WHERE id=? AND store_id=?',(str(url).rsplit('/',1)[-1],store['id'])).fetchone()
                                if not row: raise APIError('参考图片不属于当前门店',403)
                                images.append('data:'+row['mime']+';base64,'+base64.b64encode(row['image']).decode())
                    db.commit()
                    try: result = store_config.recommendation(data.get('description',''),images)
                    except ValueError as e: raise APIError(str(e))
                    return self.send(result)
                marketing = re.fullmatch(r'/api/stores/([a-f0-9]{24})/(join|claim|spin|checkin|daka)',path)
                if marketing:
                    if user['role'] != 'customer': raise APIError('需要顾客会话',403)
                    store = db.execute('SELECT * FROM stores WHERE id=? AND published=1',(marketing[1],)).fetchone()
                    if not store: raise APIError('店铺不存在',404)
                    config = store_config.normalize(json.loads(store['config_json']))
                    action = marketing[2]; module = {'join':'membership','claim':'coupons','spin':'wheel','checkin':'membership','daka':'membership'}[action]
                    if not config['modules'][module]: raise APIError('门店尚未启用此模块',403)
                    if action == 'join':
                        bonus = config['points']['register_bonus'] if config['points']['register_bonus'] > 0 else 0
                        joined = db.execute('INSERT OR IGNORE INTO members(store_id,customer_id,points,created_at) VALUES(?,?,?,?)',(store['id'],user['user_id'],bonus,now())).rowcount
                        db.commit()
                        if joined and bonus: return self.send({'message':'已加入本店会员，注册赠送 '+str(bonus)+' 积分。','points':bonus})
                        return self.send({'message':'已加入本店会员，消费可获得积分。','points':bonus if joined else None})
                    if action in ('checkin','daka'):
                        member = db.execute('SELECT points FROM members WHERE store_id=? AND customer_id=?',(store['id'],user['user_id'])).fetchone()
                        if not member: raise APIError('请先加入本店会员',409)
                        day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                        try: db.execute('INSERT INTO benefit_claims(store_id,customer_id,kind,day) VALUES(?,?,?,?)',(store['id'],user['user_id'],action,day))
                        except sqlite3.IntegrityError: raise APIError('今天已参与，请明天再来',409)
                        gain = config['points'][action]
                        db.execute('UPDATE members SET points=points+? WHERE store_id=? AND customer_id=?',(gain,store['id'],user['user_id']))
                        db.commit()
                        label = '签到' if action == 'checkin' else '打卡'
                        return self.send({'won':True,'points':member['points']+gain,'message':label+'成功，获得 '+str(gain)+' 积分。'})
                    day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                    try: db.execute('INSERT INTO benefit_claims(store_id,customer_id,kind,day) VALUES(?,?,?,?)',(store['id'],user['user_id'],action,day))
                    except sqlite3.IntegrityError: raise APIError('今天已参与，请明天再来',409)
                    win = action == 'claim' or secrets.randbelow(2) == 0
                    if win:
                        db.execute('INSERT INTO coupons(id,store_id,customer_id,amount_cents,minimum_cents,created_at) VALUES(?,?,?,?,?,?)',(secrets.token_hex(12),store['id'],user['user_id'],store_config.amount(config['coupon']['amount']),store_config.amount(config['coupon']['minimum']),now()))
                    db.commit(); return self.send({'won':win,'message':'已获得优惠券，下单时可使用。' if win else '谢谢参与，明天再来。'})
                oc_buy = re.fullmatch(r'/api/stores/([a-f0-9]{24})/oc/buy',path)
                if oc_buy:
                    if user['role'] != 'customer': raise APIError('需要顾客会话',403)
                    store = db.execute('SELECT * FROM stores WHERE id=? AND published=1',(oc_buy[1],)).fetchone()
                    if not store: raise APIError('店铺不存在',404)
                    config = store_config.normalize(json.loads(store['config_json']))
                    if not config['modules']['oc']: raise APIError('门店尚未启用此模块',403)
                    import oc_catalog
                    item_id = data.get('item_id')
                    item = oc_catalog.find(item_id)
                    if not item: raise APIError('商品不存在',400)
                    member = db.execute('SELECT points FROM members WHERE store_id=? AND customer_id=?',(store['id'],user['user_id'])).fetchone()
                    if not member: raise APIError('请先加入本店会员',409)
                    try: db.execute('INSERT INTO oc_purchases(store_id,item_id,buyer_id,created_at) VALUES(?,?,?,?)',(store['id'],item_id,user['user_id'],now()))
                    except sqlite3.IntegrityError: raise APIError('该商品已解锁，全店共享',409)
                    deducted = db.execute('UPDATE members SET points=points-? WHERE store_id=? AND customer_id=? AND points>=?',(item['price'],store['id'],user['user_id'],item['price'])).rowcount
                    if not deducted: raise APIError('积分不足，还差 '+str(item['price']-member['points'])+' 分',409)
                    db.commit()
                    owned = [r['item_id'] for r in db.execute('SELECT item_id FROM oc_purchases WHERE store_id=?',(store['id'],))]
                    return self.send({'points':member['points']-item['price'],'owned':owned,'message':'已为 '+(config['oc']['name'] or 'OC')+' 解锁「'+item['name']+'」'})
                if path in ('/api/merchant/draft','/api/merchant/publish'):
                    if user['role'] != 'merchant':
                        raise APIError('需要商家账号',403)
                    store = get_store(db,user['user_id'])
                    publishing = path.endswith('/publish')
                    name = text(data.get('name',store['draft_name'] or store['name']), '店铺名称', 50)
                    brand = normalized_brand(data.get('brand'), db, store['id'])
                    items = normalized_items(data.get('items'), publish=publishing)
                    try: config = store_config.normalize(data.get('config',json.loads(store['config_draft_json'])))
                    except ValueError as e: raise APIError(str(e))
                    if config['banner_url'] and not db.execute('SELECT id FROM dish_images WHERE id=? AND store_id=?',(config['banner_url'].rsplit('/',1)[-1],store['id'])).fetchone():
                        raise APIError('店铺封面不属于当前店铺',403)
                    if config['oc']['image_url'] and config['oc']['image_url'] != '/api/oc-images/'+store['id']:
                        raise APIError('OC 形象不属于当前店铺',403)
                    for item in items:
                        url = item['image_url']
                        if url and url.startswith('/api/dish-images/') and not db.execute('SELECT id FROM dish_images WHERE id=? AND store_id=?',(url.rsplit('/',1)[1],store['id'])).fetchone():
                            raise APIError('菜品照片不属于当前店铺',403)
                    source_id = data.get('source_id')
                    if source_id and not db.execute('SELECT id FROM ocr_sources WHERE id=? AND store_id=?',(source_id,store['id'])).fetchone():
                        raise APIError('菜单原图不属于当前店铺',403)
                    stamp = now()
                    if publishing:
                        published_ids={row['id'] for row in db.execute('SELECT id FROM menu_items WHERE store_id=?',(store['id'],))}
                        # Existing dishes remain as inactive rows, preserving historical foreign keys.
                        db.execute('UPDATE menu_items SET active=0 WHERE store_id=?',(store['id'],))
                        for position,item in enumerate(items):
                            existing = db.execute('SELECT store_id FROM menu_items WHERE id=?',(item['id'],)).fetchone()
                            if existing and existing['store_id'] != store['id']:
                                raise APIError('菜品编号不属于当前店铺',403)
                            db.execute('''INSERT INTO menu_items(id,store_id,name,price_cents,category,available,active,position,confidence,source_id,image_url,updated_at)
                                VALUES(?,?,?,?,?,?,1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,price_cents=excluded.price_cents,
                                category=excluded.category,available=excluded.available,active=1,position=excluded.position,
                                confidence=excluded.confidence,source_id=excluded.source_id,image_url=excluded.image_url,updated_at=excluded.updated_at''',
                                (item['id'],store['id'],item['name'],cents(item['price']),item['category'],int(item['available']),position,item['confidence'],source_id,item['image_url'],stamp))
                        db.execute('UPDATE stores SET name=?,brand_json=?,published=1 WHERE id=?',(name,json.dumps(brand,ensure_ascii=False),store['id']))
                        db.execute('UPDATE stores SET config_json=? WHERE id=?',(json.dumps(config,ensure_ascii=False),store['id']))
                    for item in items:
                        if publishing:
                            current = db.execute('SELECT stock FROM menu_items WHERE id=?',(item['id'],)).fetchone()
                            stock = item['stock'] if item['stock_update'] or item['id'] not in published_ids else current['stock']
                            db.execute('UPDATE menu_items SET details_json=?,stock=? WHERE id=?',(json.dumps({'description':item['description'],'options':item['options']},ensure_ascii=False),stock,item['id']))
                            item['stock']=stock; item['stock_update']=False
                    db.execute('UPDATE stores SET config_draft_json=? WHERE id=?',(json.dumps(config,ensure_ascii=False),store['id']))
                    db.execute('UPDATE stores SET draft_name=?,draft_json=?,draft_source_id=?,brand_draft_json=?,updated_at=? WHERE id=?',
                               (name,json.dumps(items,ensure_ascii=False),source_id,json.dumps(brand,ensure_ascii=False),stamp,store['id']))
                    db.commit()
                    return self.send({'ok':True,'store':serialize_store(db,get_store(db,user['user_id']),True)})
                if path == '/api/customer/orders':
                    if user['role'] != 'customer':
                        raise APIError('请使用顾客账号下单',403)
                    return self.create_order(db,user,data)
                match = re.fullmatch(r'/api/orders/([a-f0-9]{24})/(pay|status|cancel|reject)',path)
                if match:
                    order = self.owned_order(db,user,match[1])
                    if order['resolution']: raise APIError('订单已结束，无法继续操作',409)
                    if match[2] in ('cancel','reject'):
                        if match[2] == 'cancel' and (user['role'] != 'customer' or order['status'] != 'pending'): raise APIError('仅可取消待确认订单',409)
                        if match[2] == 'reject' and user['role'] != 'merchant': raise APIError('只有商家可以拒单',403)
                        reason = text(data.get('reason','顾客取消' if match[2]=='cancel' else ''),'取消/拒单原因',200)
                        release_order(db,order,'cancelled' if match[2]=='cancel' else 'rejected',reason)
                    elif match[2] == 'pay':
                        if user['role'] != 'customer':
                            raise APIError('只有下单顾客可以模拟支付',403)
                        payment_store = db.execute('SELECT config_json FROM stores WHERE id=?',(order['store_id'],)).fetchone()
                        payment_config = store_config.normalize(json.loads(payment_store['config_json']))
                        if order['payment_status'] == 'unpaid' and payment_config['modules']['membership']:
                            per_spend_cents = store_config.amount(payment_config['points']['per_spend'])
                            earned = (order['total_cents']//per_spend_cents)*payment_config['points']['earn'] if per_spend_cents > 0 else 0
                            awarded = db.execute('UPDATE members SET points=points+? WHERE store_id=? AND customer_id=?',(earned,order['store_id'],order['customer_id'])).rowcount
                            if awarded: db.execute('UPDATE orders SET points_awarded=? WHERE id=?',(earned,order['id']))
                        db.execute("UPDATE orders SET payment_status='demo_paid',updated_at=? WHERE id=?",(now(),order['id']))
                    else:
                        if user['role'] != 'merchant':
                            raise APIError('只有本店商家可以处理订单',403)
                        next_status = {'pending':'preparing','preparing':'completed'}.get(order['status'])
                        if data.get('status') != next_status or next_status is None:
                            raise APIError('订单状态已变化，请刷新后重试',409)
                        if order['payment_status'] != 'demo_paid':
                            raise APIError('顾客尚未完成模拟支付')
                        db.execute('UPDATE orders SET status=?,updated_at=? WHERE id=?',(next_status,now(),order['id']))
                    db.commit()
                    return self.send({'order':serialize_order(db,db.execute('SELECT * FROM orders WHERE id=?',(order['id'],)).fetchone())})
                raise APIError('接口不存在',404)
        except APIError as e:
            self.send({'error':e.message},e.status)
        except Exception:
            logging.exception('POST failed')
            self.send({'error':'服务暂时不可用，数据未提交，请重试'},500)

    def guest_session(self):
        with connect() as db:
            user = self.session(db,'customer',optional=True)
            if user:
                return self.send({'user':{'id':user['user_id'],'username':'本设备顾客','role':'customer'},'csrf':user['csrf_token']})
        self.limit('guest:'+self.ip_bucket(),120,3600)
        with connect() as db:
            identifier = secrets.token_hex(16)
            db.execute('INSERT INTO users VALUES(?,?,?,?,?)',(identifier,'guest_'+identifier,'!guest','customer',now()))
            csrf,cookie,token = self.start_session(db,identifier,customer=True)
            db.commit()
            result={'user':{'id':identifier,'username':'本设备顾客','role':'customer'},'csrf':csrf}
            if self.headers.get('X-Client-Type')=='mini-customer': result['token']=token
            self.send(result,cookie=cookie)

    def wechat_login(self, data):
        self.limit('wechat:'+self.ip_bucket(),60,3600)
        code = text(data.get('code',''),'微信登录凭证',256)
        import wechat
        try:
            openid = wechat.exchange_code(code)
        except wechat.WeChatError as e:
            raise APIError(str(e),503)
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            found = db.execute('SELECT user_id FROM wechat_identities WHERE openid=?',(openid,)).fetchone()
            identifier = found['user_id'] if found else secrets.token_hex(16)
            if not found:
                db.execute('INSERT INTO users VALUES(?,?,?,?,?)',(identifier,'guest_wx_'+identifier,'!wechat','customer',now()))
                db.execute('INSERT INTO wechat_identities(openid,user_id) VALUES(?,?)',(openid,identifier))
            csrf,cookie,token = self.start_session(db,identifier,customer=True)
            db.commit()
            self.send({'user':{'id':identifier,'username':'微信顾客','role':'customer'},'csrf':csrf,'token':token},cookie=cookie)

    def auth(self, path, data):
        username = text(data.get('username',''), '账号', 32)
        if not re.fullmatch(r'[A-Za-z0-9_]{3,32}',username):
            raise APIError('账号须为 3～32 位字母、数字或下划线')
        password = data.get('password','')
        if not isinstance(password,str) or not 8 <= len(password) <= 128:
            raise APIError('密码须为 8～128 位')
        self.limit('auth:'+self.ip_bucket(),30,900)
        self.limit('account:'+username.lower(),10,900)
        with connect() as db:
            if path.endswith('/register'):
                role = 'merchant'
                if data.get('role', 'merchant') != 'merchant':
                    raise APIError('注册入口仅用于商家，顾客扫码即可点单')
                identifier = secrets.token_hex(16)
                hashed = password_hash(password)
                try:
                    db.execute('INSERT INTO users VALUES(?,?,?,?,?)',(identifier,username,hashed,role,now()))
                except sqlite3.IntegrityError:
                    raise APIError('这个账号已注册，请登录或换一个账号',409)
                if role == 'merchant':
                    name = text(data.get('store_name','我的小店'),'店铺名称',50)
                    db.execute('INSERT INTO stores(id,owner_id,name,created_at,updated_at) VALUES(?,?,?,?,?)',
                               (secrets.token_hex(12),identifier,name,now(),now()))
            else:
                row = db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
                # Equivalent hashing work on unknown usernames.
                if not row:
                    password_hash(password)
                    raise APIError('账号或密码不正确',401)
                if not verify_password(password,row['password_hash']):
                    raise APIError('账号或密码不正确',401)
                identifier,role = row['id'],row['role']
                if role != 'merchant':
                    raise APIError('顾客无需账号登录，请直接打开店铺点单链接')
            csrf,cookie,token = self.start_session(db,identifier)
            db.commit()
            result={'user':{'id':identifier,'username':username,'role':role},'csrf':csrf}
            if self.headers.get('X-Client-Type')=='mini-merchant': result['token']=token
            self.send(result,cookie=cookie)

    def create_order(self, db, user, data):
        key = text(data.get('idempotency_key',''),'提交编号',64)
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,64}',key):
            raise APIError('提交编号无效')
        existing = db.execute('SELECT * FROM orders WHERE customer_id=? AND idempotency_key=?',(user['user_id'],key)).fetchone()
        if existing:
            return self.send({'order':serialize_order(db,existing)})
        store_id = data.get('store_id')
        store = db.execute('SELECT * FROM stores WHERE id=? AND published=1',(store_id,)).fetchone()
        if not store:
            raise APIError('店铺尚未发布菜单',404)
        config = store_config.normalize(json.loads(store['config_json']))
        if not config['modules']['ordering']: raise APIError('本店暂未开启在线点单',403)
        cart = data.get('cart')
        if not isinstance(cart,dict) or not 1 <= len(cart) <= 100:
            raise APIError('请先选择菜品')
        rows, total = [], 0
        for line_id, quantity in cart.items():
            if not isinstance(line_id,str): raise APIError('菜品编号无效')
            identifier = line_id.split('::')[0]
            if not isinstance(quantity,int) or isinstance(quantity,bool) or not 1 <= quantity <= 99:
                raise APIError('每道菜数量须为 1～99')
            item = db.execute('SELECT * FROM menu_items WHERE id=? AND store_id=? AND active=1 AND available=1',(identifier,store_id)).fetchone()
            if not item:
                raise APIError('菜品已下架，请刷新菜单后重新选择',409)
            # Reject stale displayed prices instead of charging an unexpected new total.
            details = json.loads(item['details_json'])
            groups = details.get('options',[])
            selections = data.get('selections',{}).get(line_id,[]) if isinstance(data.get('selections',{}),dict) else []
            if not isinstance(selections,list) or len(selections)!=len(groups): raise APIError('请选择完整规格',409)
            labels=[]; unit_price=item['price_cents']
            for group, choice_index in zip(groups,selections):
                if isinstance(choice_index,bool) or not isinstance(choice_index,int) or not 0<=choice_index<len(group['choices']): raise APIError('规格已变化，请重新选择',409)
                choice=group['choices'][choice_index]; unit_price+=store_config.amount(choice['extra']); labels.append(group['name']+':'+choice['name'])
            if item['stock'] is not None:
                changed = db.execute('UPDATE menu_items SET stock=stock-? WHERE id=? AND stock>=?',(quantity,item['id'],quantity)).rowcount
                if not changed: raise APIError('库存不足，请减少数量或选择其他菜品',409)
            expected = data.get('prices',{}).get(line_id) if isinstance(data.get('prices'),dict) else None
            if expected is None or cents(expected) != unit_price:
                raise APIError('菜单价格已更新，请刷新并确认新价格后下单',409)
            total += unit_price * quantity
            rows.append((item,quantity,unit_price,item['name']+('（'+'，'.join(labels)+'）' if labels else '')))
        coupon = None; discount = 0
        if data.get('coupon_id'):
            if not (config['modules']['coupons'] or config['modules']['wheel']): raise APIError('门店未启用优惠券')
            coupon = db.execute('SELECT * FROM coupons WHERE id=? AND store_id=? AND customer_id=? AND used_order IS NULL',(data['coupon_id'],store_id,user['user_id'])).fetchone()
            if not coupon or total < coupon['minimum_cents']: raise APIError('优惠券不可用或未达到使用门槛',409)
            discount = min(coupon['amount_cents'],total-1); total-=discount
        note = text(data.get('note',''),'备注',300,required=False)
        identifier,stamp = secrets.token_hex(12),now()
        db.execute('INSERT INTO orders(id,store_id,customer_id,total_cents,note,idempotency_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                   (identifier,store_id,user['user_id'],total,note,key,stamp,stamp))
        db.execute('UPDATE orders SET discount_cents=?,coupon_id=? WHERE id=?',(discount,coupon['id'] if coupon else None,identifier))
        if coupon: db.execute('UPDATE coupons SET used_order=? WHERE id=?',(identifier,coupon['id']))
        for item,qty,price,label in rows:
            db.execute('INSERT INTO order_items(order_id,menu_item_id,name_snapshot,price_cents_snapshot,quantity) VALUES(?,?,?,?,?)',
                       (identifier,item['id'],label,price,qty))
        db.commit()
        self.send({'order':serialize_order(db,db.execute('SELECT * FROM orders WHERE id=?',(identifier,)).fetchone())},201)

    def upload_dish_image(self):
        with connect() as db:
            user = self.session(db,'merchant',csrf=True)
            store = get_store(db,user['user_id'])
        raw = self.body(image=True)
        try:
            mime = dish_media.raster_type(raw)
        except dish_media.MediaError as e:
            raise APIError(str(e),415 if len(raw)<=2*1024*1024 else 413)
        self.limit('dish-photo:'+store['id'],100,3600)
        identifier = secrets.token_hex(32)[:32]
        with connect() as db:
            db.execute('INSERT INTO dish_images(id,store_id,mime,image,created_at) VALUES(?,?,?,?,?)',
                       (identifier,store['id'],mime,raw,now()))
        self.send({'image_url':'/api/dish-images/'+identifier},201)

    def upload_logo(self):
        with connect() as db:
            user = self.session(db,'merchant',csrf=True)
            store = get_store(db,user['user_id'])
        raw = self.body(image=True)
        try:
            mime = dish_media.raster_type(raw,'Logo 图片')
        except dish_media.MediaError as e:
            raise APIError(str(e),415 if len(raw)<=2*1024*1024 else 413)
        self.limit('logo:'+store['id'],30,3600)
        identifier = secrets.token_hex(32)[:32]
        with connect() as db:
            db.execute('INSERT INTO store_logos(id,store_id,mime,image,created_at) VALUES(?,?,?,?,?)',
                       (identifier,store['id'],mime,raw,now()))
        self.send({'logo_url':'/api/store-logos/'+identifier},201)

    def upload_ocr(self):
        with connect() as db:
            user = self.session(db,'merchant',csrf=True)
            store = get_store(db,user['user_id'])
        raw = self.body(image=True)
        if raw.startswith(b'\xff\xd8\xff'):
            mime = 'image/jpeg'
        elif raw.startswith(b'\x89PNG\r\n\x1a\n'):
            mime = 'image/png'
        elif raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
            mime = 'image/webp'
        else:
            raise APIError('请上传 JPG、PNG 或 WebP 图片',415)
        self.limit('ocr:'+user['user_id'],20,3600)
        identifier = secrets.token_hex(12)
        provider = ocr_cloud.configuration()['provider']
        with connect() as db:
            db.execute('INSERT INTO ocr_sources(id,store_id,mime,image,status,provider,created_at) VALUES(?,?,?,?,?,?,?)',
                       (identifier,store['id'],mime,raw,'processing',provider,now()))
            db.execute('UPDATE stores SET draft_source_id=? WHERE id=?',(identifier,store['id']))
        try:
            items = ocr_cloud.recognize(raw,mime)
            for item in items:
                item['id'] = secrets.token_hex(16)
            with connect() as db:
                db.execute("UPDATE ocr_sources SET status='done',result_json=? WHERE id=?",(json.dumps(items,ensure_ascii=False),identifier))
                db.execute('UPDATE stores SET draft_json=?,updated_at=? WHERE id=?',(json.dumps(items,ensure_ascii=False),now(),store['id']))
            self.send({'items':items,'source_id':identifier,'provider':provider})
        except ocr_cloud.OCRError as e:
            with connect() as db:
                db.execute("UPDATE ocr_sources SET status='failed',error=? WHERE id=?",(str(e),identifier))
            self.send({'error':str(e),'source_id':identifier},503)


if __name__ == '__main__':
    init_db()
    port = int(os.getenv('PORT','8765'))
    print(f'一扫开店：http://localhost:{port} · 数据库：{DB_PATH}',flush=True)
    ThreadingHTTPServer((os.getenv('HOST','0.0.0.0'),port),Handler).serve_forever()
