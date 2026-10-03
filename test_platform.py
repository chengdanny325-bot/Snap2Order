"""Store configuration, inventory, lifecycle and benefits regression tests."""
import io
import json
import secrets
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import server
import store_config
from test_app import Client

class Platform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_db=server.DB_PATH;cls.temp=tempfile.TemporaryDirectory();server.DB_PATH=Path(cls.temp.name)/'platform.sqlite3';server.init_db()
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=cls.http.serve_forever,daemon=True).start();cls.base='http://127.0.0.1:'+str(cls.http.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();server.DB_PATH=cls.old_db;cls.temp.cleanup()
    def setUp(self):
        self.m=Client(self.base);self.c=Client(self.base);self.other=Client(self.base)
        self.m.signup('m'+secrets.token_hex(5),'merchant');self.c.signup('c','customer');self.other.signup('o','customer')
        self.store=self.m.request('/api/merchant/store')[1]['store']['id']
        self.items=[{'id':secrets.token_hex(8),'name':'奶茶','price':10,'category':'饮品','checked':True,'stock':5,'options':[{'name':'大小','choices':[{'name':'小','extra':0},{'name':'大','extra':3}]},{'name':'加料','choices':[{'name':'无','extra':0},{'name':'珍珠','extra':2}]}]}]
        self.config=store_config.normalize({'modules':dict.fromkeys(store_config.MODULES,True),'profile':{'description':'社区茶店'},'coupon':{'amount':5,'minimum':20}})
        self.publish()
    def publish(self,config=None,items=None):
        code,d=self.m.request('/api/merchant/publish',{'name':'茶店','items':items or self.items,'config':config or self.config});self.assertEqual(code,200,d);return d
    def order(self,qty=1,choices=None,key=None,coupon=None):
        return self.c.request('/api/customer/orders',{'store_id':self.store,'cart':{self.items[0]['id']+'::1_1':qty},'prices':{self.items[0]['id']+'::1_1':15},'selections':{self.items[0]['id']+'::1_1':[1,1] if choices is None else choices},'coupon_id':coupon,'idempotency_key':key or secrets.token_hex(16)})
    def stock(self):return self.c.request('/api/stores/'+self.store)[1]['store']['items'][0]['stock']
    def test_config_draft_and_preview_private(self):
        config=store_config.normalize({'modules':{'ordering':False},'profile':{'description':'草稿资料'},'layout':'list'})
        code,d=self.m.request('/api/merchant/draft',{'name':'草稿茶店','items':self.items,'config':config});self.assertEqual(code,200,d)
        self.assertEqual(self.c.request('/api/stores/'+self.store)[1]['store']['config']['profile']['description'],'社区茶店')
        self.assertEqual(self.c.request('/api/merchant/preview')[0],401)
        preview=self.m.request('/api/merchant/preview')[1]['store'];self.assertEqual(preview['name'],'草稿茶店');self.assertFalse(preview['config']['modules']['ordering'])
        self.publish(config);self.assertEqual(self.order()[0],403)
    def test_options_price_stock_and_idempotency(self):
        key=secrets.token_hex(16);code,d=self.order(2,key=key);self.assertEqual(code,201,d);self.assertEqual(d['order']['total'],30);self.assertIn('大小:大',d['order']['items'][0]['name']);self.assertEqual(self.stock(),3)
        self.assertEqual(self.order(2,key=key)[1]['order']['id'],d['order']['id']);self.assertEqual(self.stock(),3)
        self.assertEqual(self.order(4)[0],409);self.assertEqual(self.stock(),3)
        self.assertEqual(self.order(1,choices=[99,1])[0],409);self.assertEqual(self.stock(),3)
        self.publish();self.assertEqual(self.stock(),3)
        changed=[dict(self.items[0],stock=12,stock_update=True)];self.publish(items=changed);self.assertEqual(self.stock(),12)
    def test_cancel_reject_timeout_release_once(self):
        _,d=self.order(2);oid=d['order']['id'];self.assertEqual(self.stock(),3)
        self.assertEqual(self.other.request('/api/orders/'+oid+'/cancel',{})[0],404)
        self.assertEqual(self.c.request('/api/orders/'+oid+'/cancel',{'reason':'不需要了'})[1]['order']['status'],'cancelled');self.assertEqual(self.stock(),5)
        self.assertEqual(self.c.request('/api/orders/'+oid+'/pay',{})[0],409);self.assertEqual(self.stock(),5)
        _,d=self.order();oid=d['order']['id'];self.c.request('/api/orders/'+oid+'/pay',{})
        self.m.request('/api/orders/'+oid+'/status',{'status':'preparing'})
        self.assertEqual(self.c.request('/api/orders/'+oid+'/cancel',{})[0],409)
        self.assertEqual(self.m.request('/api/orders/'+oid+'/reject',{'reason':'原料缺货'})[1]['order']['status'],'rejected');self.assertEqual(self.stock(),5)
        _,d=self.order();oid=d['order']['id']
        with server.connect() as db:db.execute('UPDATE orders SET created_at=? WHERE id=?',(datetime.fromtimestamp(time.time()-1900,timezone.utc).isoformat(),oid))
        self.assertEqual(self.c.request('/api/orders/'+oid)[1]['order']['status'],'expired');self.assertEqual(self.stock(),5)
    def test_members_coupons_and_limits(self):
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/join',{})[0],200)
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/claim',{})[0],200)
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/claim',{})[0],409)
        coupon=self.c.request('/api/stores/'+self.store+'/benefits')[1]['coupons'][0]['id']
        self.assertEqual(self.order(coupon=coupon)[0],409);self.assertEqual(self.stock(),5)
        _,d=self.order(2,coupon=coupon);self.assertEqual(d['order']['total'],25);self.assertEqual(d['order']['discount'],5);oid=d['order']['id']
        self.c.request('/api/orders/'+oid+'/pay',{});self.c.request('/api/orders/'+oid+'/pay',{})
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/benefits')[1]['member']['points'],25)
        self.c.request('/api/orders/'+oid+'/cancel',{'reason':'取消'})
        benefits=self.c.request('/api/stores/'+self.store+'/benefits')[1];self.assertEqual(benefits['member']['points'],0);self.assertEqual(len(benefits['coupons']),1)
        with patch('server.secrets.randbelow',return_value=0):self.assertTrue(self.c.request('/api/stores/'+self.store+'/spin',{})[1]['won'])
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/spin',{})[0],409)
    def test_invalid_config_and_recommendation(self):
        self.assertEqual(self.m.request('/api/merchant/draft',{'items':self.items,'config':{'modules':{'wheel':'true'}}})[0],400)
        with patch.dict('os.environ',{'STORE_AI_API_KEY':''}):
            code,d=self.m.request('/api/merchant/recommend',{'description':'奶茶店，希望会员复购和优惠拉新'});self.assertEqual(code,200,d);self.assertEqual(d['source'],'rules');self.assertTrue(d['modules']['membership'])
        self.assertEqual(self.c.request('/api/merchant/recommend',{'description':'奶茶'})[0],403)

    def test_disabled_modules_and_model_validation(self):
        self.c.request('/api/stores/'+self.store+'/join',{})
        cfg=store_config.normalize({'modules':{'ordering':True}});self.publish(cfg)
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/claim',{})[0],403)
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/spin',{})[0],403)
        _,d=self.order();self.c.request('/api/orders/'+d['order']['id']+'/pay',{})
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/benefits')[1]['member']['points'],0)
        output={'theme':'minimal','modules':{'ordering':True,'membership':False,'coupons':False,'wheel':False},'description':'社区咖啡','reason':'简洁风格'}
        response=io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(output)}}]}).encode())
        with patch.dict('os.environ',{'STORE_AI_API_KEY':'test-only'}),patch('store_config.urllib.request.urlopen',return_value=response):
            result=store_config.recommendation('社区咖啡');self.assertEqual(result['source'],'model');self.assertEqual(result['theme'],'minimal')
        with patch.dict('os.environ',{'STORE_AI_API_KEY':'test-only'}),patch('store_config.urllib.request.urlopen',side_effect=OSError()):
            result=store_config.recommendation('社区咖啡');self.assertEqual(result['source'],'rules');self.assertTrue(result['fallback'])

    def test_points_rules_checkin_daka_register_bonus(self):
        cfg=store_config.normalize({'modules':dict.fromkeys(store_config.MODULES,True),'points':{'per_spend':10,'earn':5,'register_bonus':20,'checkin':3,'daka':8}})
        self.publish(cfg)
        code,d=self.c.request('/api/stores/'+self.store+'/join',{});self.assertEqual(code,200,d);self.assertEqual(d['points'],20)
        code,d=self.c.request('/api/stores/'+self.store+'/join',{});self.assertEqual(code,200,d);self.assertIsNone(d['points'])
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/benefits')[1]['member']['points'],20)
        code,d=self.c.request('/api/stores/'+self.store+'/checkin',{});self.assertEqual(code,200,d);self.assertEqual(d['points'],23)
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/checkin',{})[0],409)
        code,d=self.c.request('/api/stores/'+self.store+'/daka',{});self.assertEqual(code,200,d);self.assertEqual(d['points'],31)
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/daka',{})[0],409)
        self.assertEqual(self.other.request('/api/stores/'+self.store+'/checkin',{})[0],409)
        self.assertEqual(self.other.request('/api/stores/'+self.store+'/daka',{})[0],409)
        _,d=self.order(2);oid=d['order']['id'];self.assertEqual(d['order']['total'],30)
        self.c.request('/api/orders/'+oid+'/pay',{})
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/benefits')[1]['member']['points'],46)
        self.c.request('/api/orders/'+oid+'/cancel',{'reason':'取消'})
        benefits=self.c.request('/api/stores/'+self.store+'/benefits')[1]
        self.assertEqual(benefits['member']['points'],31);self.assertIn('checkin',benefits['claims']);self.assertIn('daka',benefits['claims'])
    def test_points_config_validation_and_threshold(self):
        self.assertEqual(self.m.request('/api/merchant/draft',{'items':self.items,'config':{'modules':{'membership':True},'points':{'per_spend':0}}})[0],400)
        self.assertEqual(self.m.request('/api/merchant/draft',{'items':self.items,'config':{'modules':{'membership':True},'points':{'earn':-1}}})[0],400)
        self.assertEqual(self.m.request('/api/merchant/draft',{'items':self.items,'config':{'modules':{'membership':True},'points':{'earn':1.5}}})[0],400)
        self.assertEqual(self.m.request('/api/merchant/draft',{'items':self.items,'config':{'modules':{'membership':True},'points':{'bogus':1}}})[0],400)
        cfg=store_config.normalize({'modules':dict.fromkeys(store_config.MODULES,True),'points':{'per_spend':20,'earn':5}})
        self.publish(cfg)
        self.c.request('/api/stores/'+self.store+'/join',{})
        _,d=self.order();self.assertEqual(d['order']['total'],15)
        self.c.request('/api/orders/'+d['order']['id']+'/pay',{})
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/benefits')[1]['member']['points'],0)
        cfg=store_config.normalize({'modules':{'ordering':True}})
        self.publish(cfg)
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/checkin',{})[0],403)
        self.assertEqual(self.c.request('/api/stores/'+self.store+'/daka',{})[0],403)
    def test_restaurant_themes_and_custom_category(self):
        for theme in ('universal','western','hotpot'):
            code,d=self.m.request('/api/merchant/publish',{'name':'餐厅','items':[dict(self.items[0],category='自定义烧烤')],'config':self.config,'brand':{'theme':theme}})
            self.assertEqual(code,200,d)
            live=self.c.request('/api/stores/'+self.store)[1]['store']
            self.assertEqual(live['brand']['theme'],theme);self.assertEqual(live['items'][0]['category'],'自定义烧烤')
    def test_logo_generation_requires_merchant_and_valid_raster(self):
        self.assertEqual(self.c.request('/api/merchant/logo-generate',{'name':'餐厅'})[0],403)
        with patch.dict('os.environ',{'AI_LOGO_API_KEY':'','STORE_AI_API_KEY':'','AI_LOGO_API_URL':'','AI_LOGO_MODEL':''}):
            self.assertEqual(self.m.request('/api/merchant/logo-generate',{'name':'餐厅'})[0],400)
        import base64
        raw=Path('static/assets/dishes/drink.png').read_bytes()
        response=io.BytesIO(json.dumps({'data':[{'b64_json':base64.b64encode(raw).decode()}]}).encode())
        with patch.dict('os.environ',{'AI_LOGO_API_KEY':'test-only','AI_LOGO_API_URL':'https://example.test/images/generations','AI_LOGO_MODEL':'test-model'}),patch('store_config.urllib.request.urlopen',return_value=response) as call:
            code,d=self.m.request('/api/merchant/logo-generate',{'name':'餐厅','theme':'western','prompt':'餐具徽标'})
            self.assertEqual(code,200,d);self.assertEqual(base64.b64decode(d['image_base64']),raw);self.assertEqual(d['mime'],'image/png')
            request=call.call_args.args[0];self.assertIn('restaurant logo',json.loads(request.data)['prompt'])
        response=io.BytesIO(json.dumps({'data':[{'b64_json':base64.b64encode(b'<svg>invalid</svg>').decode()}]}).encode())
        with patch.dict('os.environ',{'AI_LOGO_API_KEY':'test-only','AI_LOGO_API_URL':'https://example.test/images/generations','AI_LOGO_MODEL':'test-model'}),patch('store_config.urllib.request.urlopen',return_value=response):
            self.assertEqual(self.m.request('/api/merchant/logo-generate',{'name':'餐厅'})[0],400)

if __name__=='__main__':unittest.main()
