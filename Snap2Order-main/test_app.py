"""Isolated integration tests. No real credentials or paid OCR calls."""
import base64
import http.cookiejar
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import server
import ocr_cloud

class Client:
    def __init__(self,base):
        self.base=base; self.csrf=''; self.customer=False; self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def request(self,path,data=None,raw=False,csrf=True):
        headers={'Content-Type':'image/png' if raw else 'application/json'}
        if self.customer: headers['X-Client-Type']='customer'
        if csrf: headers['X-CSRF-Token']=self.csrf
        req=urllib.request.Request(self.base+path,data=data if raw else None if data is None else json.dumps(data).encode(),headers=headers)
        try:
            with self.opener.open(req,timeout=5) as r:
                body=r.read()
                result=json.loads(body) if 'application/json' in r.headers['Content-Type'] else body
                return r.status,result
        except urllib.error.HTTPError as e:
            with e:
                return e.code,json.load(e)
    def signup(self,name,role):
        self.customer=role=='customer'
        code,d=self.request('/api/customer/session',{}) if self.customer else self.request('/api/auth/register',{'username':name,'password':'test-pass-123','store_name':'小店'+name})
        assert code==200,d
        self.csrf=d['csrf'];return d

class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();server.DB_PATH=Path(cls.temp.name)/'test.sqlite3'
        server.init_db();cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.http.server_port)
        cls.ma=Client(cls.base);cls.mb=Client(cls.base);cls.ca=Client(cls.base);cls.cb=Client(cls.base)
        for c,name,role in [(cls.ma,'merchant_a','merchant'),(cls.mb,'merchant_b','merchant'),(cls.ca,'customer_a','customer'),(cls.cb,'customer_b','customer')]: c.signup(name,role)
        _,d=cls.ma.request('/api/merchant/store');cls.store=d['store']['id']
        cls.items=[{'id':'test-dish-'+str(n),'name':name,'price':price,'category':'主食','available':True,'checked':True} for n,(name,price) in enumerate([('牛肉面',28),('酸梅汤',6),('拌面',18)])]
        code,d=cls.ma.request('/api/merchant/publish',{'name':'测试小店','items':cls.items});assert code==200,d
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.temp.cleanup()
    def new_order(self,key):
        return self.ca.request('/api/customer/orders',{'store_id':self.store,'cart':{'test-dish-0':1,'test-dish-1':1},'prices':{'test-dish-0':28,'test-dish-1':6},'note':'少辣','idempotency_key':key})
    def test_01_new_merchant_is_empty(self):
        _,d=self.mb.request('/api/merchant/store');self.assertEqual(d['store']['items'],[]);self.assertEqual(d['store']['draft'],[]);self.assertFalse(d['store']['published'])
        _,d=self.mb.request('/api/merchant/orders');self.assertEqual(d['orders'],[])
    def test_02_auth_and_csrf(self):
        guest=Client(self.base);self.assertEqual(guest.request('/api/merchant/store')[0],401)
        self.assertEqual(self.ca.request('/api/merchant/store')[0],401)
        self.assertEqual(self.ma.request('/api/merchant/draft',{'items':[]},csrf=False)[0],403)
        code,d=guest.request('/api/auth/login',{'username':'merchant_a','password':'wrong-password'});self.assertEqual(code,401)
        code,d=guest.request('/api/auth/login',{'username':'merchant_a','password':'test-pass-123'});self.assertEqual(code,200)
        guest.csrf=d['csrf'];self.assertEqual(guest.request('/api/auth/logout',{})[0],200);self.assertEqual(guest.request('/api/me')[1]['user'],None)
    def test_03_order_flow_and_isolation(self):
        code,d=self.new_order('order-flow-00000001');self.assertEqual(code,201);o=d['order'];self.assertEqual(o['total'],34);self.assertEqual(o['note'],'少辣')
        oid=o['id'];self.assertEqual(self.cb.request('/api/orders/'+oid)[0],404)
        self.assertEqual(self.mb.request('/api/orders/'+oid+'/status',{'status':'preparing'})[0],404)
        self.assertEqual(self.cb.request('/api/orders/'+oid+'/pay',{})[0],404)
        self.assertEqual(self.ca.request('/api/orders/'+oid+'/status',{'status':'preparing'})[0],403)
        self.assertEqual(self.ma.request('/api/orders/'+oid+'/status',{'status':'preparing'})[0],400)
        self.assertEqual(self.ca.request('/api/orders/'+oid+'/pay',{})[0],200)
        self.assertEqual(self.ma.request('/api/orders/'+oid+'/status',{'status':'preparing'})[0],200)
        self.assertEqual(self.ma.request('/api/orders/'+oid+'/status',{'status':'completed'})[1]['order']['status'],'completed')
        self.assertEqual(self.ma.request('/api/orders/'+oid+'/status',{'status':'pending'})[0],409)
        self.assertEqual(self.cb.request('/api/customer/orders')[1]['orders'],[])
    def test_04_idempotent_orders(self):
        _,a=self.new_order('order-repeat-000001');_,b=self.new_order('order-repeat-000001');self.assertEqual(a['order']['id'],b['order']['id'])
    def test_05_prices_and_menu_validation(self):
        self.assertEqual(self.ca.request('/api/customer/orders',{'store_id':self.store,'cart':{},'idempotency_key':'invalid-empty-0001'})[0],400)
        self.assertEqual(self.ca.request('/api/customer/orders',{'store_id':self.store,'cart':{'test-dish-0':1},'prices':{'test-dish-0':.01},'idempotency_key':'invalid-price-0001'})[0],409)
        items=[dict(i,checked=False) for i in self.items];self.assertEqual(self.ma.request('/api/merchant/publish',{'name':'小店','items':items})[0],400)
        items=[dict(i,price=-1) for i in self.items];self.assertEqual(self.ma.request('/api/merchant/publish',{'name':'小店','items':items})[0],400)
        self.assertEqual(self.mb.request('/api/merchant/publish',{'name':'盗用菜品','items':self.items})[0],403)
    def test_06_snapshot_survives_edit(self):
        _,d=self.new_order('order-snapshot-0001');oid=d['order']['id']
        edited=[dict(i,price=30,name='新牛肉面') if i['id']=='test-dish-0' else i for i in self.items]
        self.assertEqual(self.ma.request('/api/merchant/publish',{'name':'测试小店','items':edited})[0],200)
        _,d=self.ca.request('/api/orders/'+oid);self.assertEqual(d['order']['total'],34);self.assertEqual(d['order']['items'][0]['name'],'牛肉面')
        self.ma.request('/api/merchant/publish',{'name':'测试小店','items':self.items})
    def test_07_ocr_missing_key_and_source_is_private(self):
        image=b'\x89PNG\r\n\x1a\n'+b'test-image'
        with patch.dict(os.environ,{'OCR_API_KEY':''}):
            code,d=self.ma.request('/api/merchant/ocr',image,raw=True)
        self.assertEqual(code,503);sid=d['source_id'];self.assertIn('尚未配置',d['error'])
        self.assertEqual(self.ma.request('/api/merchant/sources/'+sid)[0],200)
        self.assertEqual(self.mb.request('/api/merchant/sources/'+sid)[0],404)
        self.assertEqual(self.ca.request('/api/merchant/sources/'+sid)[0],401)
        self.assertEqual(self.ma.request('/api/merchant/ocr',b'not an image',raw=True)[0],415)
    def test_08_ocr_success_saves_unconfirmed_draft(self):
        output=[{'name':'牛肉面','price':28,'category':'主食','confidence':.8,'available':True,'checked':False}]
        with patch('server.ocr_cloud.recognize',return_value=output):
            code,d=self.ma.request('/api/merchant/ocr',b'\x89PNG\r\n\x1a\nmock',raw=True)
        self.assertEqual(code,200);self.assertFalse(d['items'][0]['checked'])
        draft=self.ma.request('/api/merchant/store')[1]['store']['draft'];self.assertEqual(draft[0]['name'],'牛肉面')
    def test_09_public_api_and_private_files(self):
        guest=Client(self.base);_,d=guest.request('/api/stores/'+self.store)
        self.assertNotIn('orders',d['store']);self.assertNotIn('owner_id',d['store']);self.assertNotIn('draft',d['store'])
        for p in ['/api/state','/data.json','/.env','/data/snap2order.sqlite3','/server.py']:
            self.assertEqual(guest.request(p)[0],404,p)
        for p in ['/login','/merchant/menu','/merchant/orders','/customer/orders','/s/'+self.store]:
            with urllib.request.urlopen(self.base+p) as req: self.assertEqual(req.status,200)
    def test_11_signup_is_merchant_only(self):
        client=Client(self.base)
        self.assertEqual(client.request('/api/auth/register',{'username':'invalid_customer','password':'test-pass-123','role':'customer'})[0],400)
    def test_12_guest_session_repeat_and_cookie_scope(self):
        first=self.ca.request('/api/customer/session',{})[1]
        again=self.ca.request('/api/customer/session',{})[1]
        self.assertEqual(first['user']['id'],again['user']['id'])
        self.assertNotEqual(first['user']['id'],self.cb.request('/api/customer/session',{})[1]['user']['id'])
        self.assertTrue(any(c.name=='snap_guest' for c in self.ca.jar))
        self.assertTrue(any(c.name=='snap_session' for c in self.ma.jar))
    def test_13_directory_qr_and_wechat_missing_config(self):
        import segno, io
        public=Client(self.base)
        code,d=public.request('/api/stores');self.assertEqual(code,200)
        self.assertIn(self.store,[s['id'] for s in d['stores']])
        self.assertEqual(public.request('/api/merchant/qrcode')[0],401)
        code,body=self.ma.request('/api/merchant/qrcode');self.assertEqual(code,200)
        expected=io.BytesIO();segno.make(self.base+'/s/'+self.store,error='m',micro=False).save(expected,kind='svg',scale=7,border=4)
        self.assertEqual(body,expected.getvalue())
        with patch.dict(os.environ,{'WECHAT_APP_ID':'','WECHAT_APP_SECRET':''}):
            self.assertEqual(public.request('/api/auth/wechat',{'code':'test-code'})[0],503)
    def test_14_wechat_identity_reuses_user(self):
        client=Client(self.base)
        with patch('wechat.exchange_code',return_value='mock-openid'):
            _,a=client.request('/api/auth/wechat',{'code':'mock-1'})
            _,b=client.request('/api/auth/wechat',{'code':'mock-2'})
        self.assertEqual(a['user']['id'],b['user']['id'])
        self.assertNotEqual(a['token'],b['token'])
        self.assertNotIn('openid',a);self.assertNotIn('session_key',a)

    def test_15_brand_draft_isolation_and_logo(self):
        photo=(server.ROOT/'static/assets/dishes/noodles.png').read_bytes()
        outsider=Client(self.base)
        self.assertEqual(outsider.request('/api/merchant/logo',photo,raw=True)[0],401)
        self.assertEqual(self.ma.request('/api/merchant/logo',photo,raw=True,csrf=False)[0],403)
        self.assertEqual(self.ma.request('/api/merchant/logo',b'<svg/>',raw=True)[0],415)
        code,data=self.ma.request('/api/merchant/logo',photo,raw=True)
        self.assertEqual(code,201);logo=data['logo_url']
        try:
            # Saving a draft must not change the public storefront.
            draft={'name':'品牌测试店','items':self.items,'brand':{'logo_url':logo,'theme':'vibrant'}}
            self.assertEqual(self.ma.request('/api/merchant/draft',draft)[0],200)
            _,d=outsider.request('/api/stores/'+self.store)
            self.assertEqual(d['store']['name'],'测试小店')
            self.assertEqual(d['store']['brand'],{'logo_url':None,'theme':'fresh'})
            self.assertEqual(outsider.request(logo)[0],404)
            self.assertEqual(self.mb.request(logo)[0],404)
            self.assertEqual(self.ma.request(logo)[1],photo)
            # Publishing applies name, theme and logo together.
            self.assertEqual(self.ma.request('/api/merchant/publish',draft)[0],200)
            _,d=outsider.request('/api/stores/'+self.store)
            self.assertEqual(d['store']['name'],'品牌测试店')
            self.assertEqual(d['store']['brand'],{'logo_url':logo,'theme':'vibrant'})
            self.assertEqual(outsider.request(logo)[1],photo)
            _,listing=outsider.request('/api/stores')
            row=[s for s in listing['stores'] if s['id']==self.store][0]
            self.assertEqual(row['theme'],'vibrant');self.assertEqual(row['logo_url'],logo)
            # Validation: bad theme, foreign or malformed logo references.
            self.assertEqual(self.ma.request('/api/merchant/draft',{'items':self.items,'brand':{'theme':'neon'}})[0],400)
            for theme in ('fresh','minimal','vibrant','classic','cute','luxury'):
                self.assertEqual(self.ma.request('/api/merchant/draft',{'items':self.items,'brand':{'theme':theme}})[0],200,theme)
            self.assertEqual(self.mb.request('/api/merchant/draft',{'items':[dict(i,id='mb-'+i['id']) for i in self.items],'brand':{'logo_url':logo,'theme':'fresh'}})[0],403)
            self.assertEqual(self.ma.request('/api/merchant/draft',{'items':self.items,'brand':{'logo_url':'https://example.com/x.png'}})[0],400)
            self.assertEqual(self.ma.request('/api/merchant/draft',{'items':self.items,'brand':{'logo_url':'/api/store-logos/'+'0'*32}})[0],403)
        finally:
            self.ma.request('/api/merchant/publish',{'name':'测试小店','items':self.items,'brand':{'logo_url':None,'theme':'fresh'}})
        _,d=outsider.request('/api/stores/'+self.store)
        self.assertEqual(d['store']['name'],'测试小店')
        self.assertEqual(d['store']['brand'],{'logo_url':None,'theme':'fresh'})
        self.assertEqual(outsider.request(logo)[0],404)

    def test_10_password_storage_and_integrity(self):
        with server.connect() as db:
            stored=db.execute('SELECT password_hash FROM users WHERE username=?',('merchant_a',)).fetchone()[0]
            self.assertTrue(stored.startswith('pbkdf2_sha256$'));self.assertNotIn('test-pass',stored)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')


    def test_20_dish_images_and_library(self):
        photo=(server.ROOT/'static/assets/dishes/noodles.png').read_bytes()
        outsider=Client(self.base)
        self.assertEqual(outsider.request('/api/merchant/dish-images',photo,raw=True)[0],401)
        self.assertEqual(self.ma.request('/api/merchant/dish-images',photo,raw=True,csrf=False)[0],403)
        self.assertEqual(self.ma.request('/api/merchant/dish-images',b'<svg/>',raw=True)[0],415)
        self.assertEqual(self.ma.request('/api/merchant/dish-images',b'x'*(2*1024*1024+1),raw=True)[0],413)
        code,data=self.ma.request('/api/merchant/dish-images',photo,raw=True)
        self.assertEqual(code,201);url=data['image_url']
        self.assertEqual(self.ma.request(url)[1],photo)
        self.assertEqual(outsider.request(url)[0],404)
        self.assertEqual(self.mb.request(url)[0],404)
        code,library=outsider.request('/api/image-library')
        self.assertEqual(code,200);self.assertEqual(len(library['images']),6)
        for image in library['images']:
            self.assertTrue(outsider.request(image['url'])[1].startswith(b'\x89PNG'))
        stolen=[{**self.items[0],'id':'other-store-image','image_url':url}]
        self.assertEqual(self.mb.request('/api/merchant/draft',{'items':stolen})[0],403)
        self.assertEqual(self.ma.request('/api/merchant/draft',{'items':[{**self.items[0],'image_url':'https://example.com/a.png'}]})[0],400)
        items=[{**item,'image_url':url if n==0 else library['images'][1]['url'] if n==1 else None} for n,item in enumerate(self.items)]
        try:
            self.assertEqual(self.ma.request('/api/merchant/draft',{'items':items})[0],200)
            self.assertEqual(outsider.request(url)[0],404)
            _,draft=self.ma.request('/api/merchant/store');self.assertEqual(draft['store']['draft'][0]['image_url'],url)
            self.assertEqual(self.ma.request('/api/merchant/publish',{'items':items})[0],200)
            self.assertEqual(outsider.request(url)[1],photo)
            _,live=outsider.request('/api/stores/'+self.store)
            self.assertEqual([i['image_url'] for i in live['store']['items']],[i['image_url'] for i in items])
            self.assertEqual(self.ma.request('/api/merchant/publish',{'items':self.items})[0],200)
            self.assertEqual(outsider.request(url)[0],404)
        finally:
            self.ma.request('/api/merchant/publish',{'items':self.items})


class CloudAdapter(unittest.TestCase):
    def test_parse_low_confidence_and_unknown_prices(self):
        payload={'choices':[{'message':{'content':'```json\n'+json.dumps({'items':[{'name':'龙虾','price':None,'category':'其他','confidence':.3},{'name':'面','price':28,'confidence':.9}]})+'\n```'}}]}
        items=ocr_cloud.normalize_response(payload);self.assertIsNone(items[0]['price']);self.assertFalse(items[1]['checked'])
    def test_bad_response(self):
        for payload in [{},{'choices':[{'message':{'content':'not json'}}]},{'choices':[{'message':{'content':'{"items":[]}'}}]}]:
            with self.assertRaises(ocr_cloud.OCRError):ocr_cloud.normalize_response(payload)
    def test_mocked_http_contract(self):
        import io
        result=io.BytesIO(json.dumps({'choices':[{'message':{'content':'{"items":[{"name":"面","price":28}]}'}}]}).encode())
        with patch.dict(os.environ,{'OCR_API_KEY':'test-key-not-real','OCR_PROVIDER':'vision'}),patch('ocr_cloud.urllib.request.urlopen',return_value=result) as call:
            self.assertEqual(ocr_cloud.recognize(b'PNG','image/png')[0]['price'],28)
            request=call.call_args[0][0];body=json.loads(request.data)
            self.assertEqual(request.get_header('Authorization'),'Bearer test-key-not-real')
            self.assertTrue(body['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))

class OCRSpaceAdapter(unittest.TestCase):
    def test_text_to_menu(self):
        rows=ocr_cloud.normalize_ocrspace({'OCRExitCode':1,'IsErroredOnProcessing':False,'ParsedResults':[{'FileParseExitCode':1,'ParsedText':'主食\n牛肉面 28元\n番茄面 ¥18\n小吃\n黄瓜 12\n饮品\n可乐 330ml 6元\n龙虾 时价\n地址 南京路28号'}]})
        self.assertEqual(len(rows),5);self.assertEqual(rows[0]['price'],28)
        self.assertEqual(rows[3]['name'],'可乐 330ml');self.assertIsNone(rows[4]['price'])
        self.assertTrue(all(not i['checked'] for i in rows));self.assertTrue(all(i['confidence'] is None for i in rows))
    def test_overlay_same_row_pair(self):
        overlay={'Lines':[{'MinTop':10,'MaxHeight':12,'Words':[{'WordText':'28','Left':200,'Top':10,'Height':12}]},{'MinTop':10,'MaxHeight':12,'Words':[{'WordText':'牛肉面','Left':10,'Top':10,'Height':12}]}]}
        rows=ocr_cloud.normalize_ocrspace({'OCRExitCode':1,'ParsedResults':[{'TextOverlay':overlay}]})
        self.assertEqual(rows[0]['name'],'牛肉面');self.assertEqual(rows[0]['price'],28)
    def test_request_contract(self):
        import io,urllib.parse
        body=io.BytesIO(json.dumps({'OCRExitCode':1,'ParsedResults':[{'ParsedText':'牛肉面 28'}]}).encode())
        with patch.dict(os.environ,{'OCR_API_KEY':'not-real','OCR_PROVIDER':'ocrspace','OCR_LANGUAGE':'auto','OCR_ENGINE':'2','OCR_API_URL':'https://api.ocr.space/parse/image'}),patch('ocr_cloud.urllib.request.urlopen',return_value=body) as call:
            self.assertEqual(ocr_cloud.recognize(b'PNG','image/png')[0]['price'],28)
            req=call.call_args[0][0];fields=urllib.parse.parse_qs(req.data.decode())
            self.assertEqual(req.get_header('Apikey'),'not-real');self.assertEqual(fields['language'],['auto'])
            self.assertEqual(fields['OCREngine'],['2']);self.assertEqual(fields['isOverlayRequired'],['true'])
    def test_multiple_currency_columns(self):
        rows=ocr_cloud.parse_menu_lines(['牛肉面 $28 番茄面 $18','Coffee €6','Tea £5'])
        self.assertEqual([(r['name'],r['price']) for r in rows],[('牛肉面',28),('番茄面',18),('Coffee',6),('Tea',5)])
    def test_bundled_tls(self):
        import ssl,tls_support
        ctx=tls_support.context()
        self.assertEqual(ctx.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)
        self.assertGreater(ctx.cert_store_stats()['x509_ca'],0)
    def test_error_and_ambiguous(self):
        for payload in [{},{'IsErroredOnProcessing':True,'ErrorMessage':['API key invalid']},{'OCRExitCode':3},{'ParsedResults':[{'ParsedText':'电话 13800138000\n面 18 28'}]}]:
            with self.assertRaises(ocr_cloud.OCRError):ocr_cloud.normalize_ocrspace(payload)
    def test_size_rejected_before_network(self):
        with patch.dict(os.environ,{'OCR_API_KEY':'not-real','OCR_PROVIDER':'ocrspace','OCR_MAX_IMAGE_BYTES':'50000'}),patch('ocr_cloud.urllib.request.urlopen') as call:
            with self.assertRaises(ocr_cloud.OCRError):ocr_cloud.recognize(b'x'*50001,'image/png')
            call.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
