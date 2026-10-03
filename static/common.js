'use strict';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = n => '¥' + Number(n).toFixed(2);
const uid = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), x => x.toString(16).padStart(2,'0')).join('');
let me = null, csrf = '';
class RequestError extends Error { constructor(message, status, data) { super(message); this.status=status; this.data=data; } }
async function api(path, data, options={}) {
  const headers = {'Accept':'application/json'};
  if(location.pathname.startsWith('/s/')||location.pathname==='/customer/orders'||location.pathname==='/shops')headers['X-Client-Type']='customer';
  if (data !== undefined) { headers['Content-Type']=options.raw ? (data.type || 'application/octet-stream') : 'application/json'; headers['X-CSRF-Token']=csrf; }
  const r=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers,body:data===undefined?undefined:options.raw?data:JSON.stringify(data),credentials:'same-origin'});
  const d=await r.json();
  if(!r.ok) throw new RequestError(d.error || '操作失败，请重试',r.status,d);
  return d;
}
function message(text, isError=false) {
  const box=$('#notice'); box.textContent=text; box.className=isError?'visible error':'visible';
  clearTimeout(window.noticeTimer); window.noticeTimer=setTimeout(()=>box.className='',9000);
}
function fail(err) { message(err.message || '操作失败，请重试',true); }
function loginURL(role='customer', next=location.pathname+location.search) {return '/login?role='+role+'&next='+encodeURIComponent(next);}
async function session(requiredRole) {
  const result=await api('me'); me=result.user; csrf=result.csrf||'';
  if(requiredRole && !me) {location.replace(loginURL(requiredRole));return false;}
  if(requiredRole && me.role!==requiredRole) {
    $('#app').innerHTML=`<section class="panel empty"><h1>这个页面需要${requiredRole==='merchant'?'商家':'顾客'}账号</h1><p>当前登录为${me.role==='merchant'?'商家':'顾客'}。请退出后用对应账号登录。</p><button id="logoutRole">退出当前账号</button></section>`;
    $('#logoutRole').onclick=async()=>{await api('auth/logout',{});location.replace(loginURL(requiredRole));};
    header(requiredRole);return false;
  }
  return true;
}
function header(kind='public', name='') {
  let nav='';
  document.body.classList.toggle('merchant-shell',kind==='merchant');
  document.querySelector('.merchant-sidebar')?.remove();
  if(kind==='merchant'){const side=document.createElement('aside');side.className='merchant-sidebar';const links=[['brand','品牌与店铺资料'],['import','菜单与商品'],['modules','功能模块'],['preview','预览与发布']];side.innerHTML='<div class=eyebrow>门店管理</div><nav aria-label=商家功能分区>'+links.map(([id,name],n)=>`<a href="/merchant/menu#${id}" ${location.pathname==='/merchant/menu'&&(location.hash.slice(1)||'brand')===id?'aria-current=page':''}><small>0${n+1}</small>${name}</a>`).join('')+`<a href="/merchant/orders" ${location.pathname==='/merchant/orders'?'aria-current=page':''}><small>05</small>订单工作台</a></nav><p class=hint>草稿保存后可继续编辑。<br>发布后顾客看到整店新版本。</p>`;document.body.insertBefore(side,$('#app'));}
  if(kind==='merchant') nav=`<a href="/merchant/menu" ${location.pathname==='/merchant/menu'?'aria-current="page"':''}>我的菜单</a><a href="/merchant/orders" ${location.pathname==='/merchant/orders'?'aria-current="page"':''}>接单工作台</a>`;
  if(kind==='customer') nav='<a href="/shops">选择小店</a><a href="/customer/orders">本设备订单</a>';
  const home=kind==='merchant'?'/merchant/menu':'/';
  $('#header').innerHTML=`<a class="brand" href="${home}"><span class="brand-symbol" aria-hidden="true">▧</span><span>一扫开店<small>${kind==='merchant'?'商家工作台':name?esc(name):'SNAP2ORDER'}</small></span></a><nav aria-label="页面导航">${nav}</nav><div class="account">${kind==='customer'?'<span class="hint">扫码点单 · 无需注册</span>':me?`<span>${esc(me.username)}</span><button class="quiet" id="logout">退出</button>`:`<a href="${loginURL('merchant')}">登录 / 注册</a>`}</div>`;
  const logout=$('#logout'); if(logout)logout.onclick=async()=>{try{await api('auth/logout',{});for(const key of Object.keys(sessionStorage)){if(key.startsWith('snap_cart_')||key==='snap_pending_cart')sessionStorage.removeItem(key);}me=null;csrf='';location.href=kind==='merchant'?'/login?role=merchant':location.pathname.startsWith('/s/')?location.pathname:'/';}catch(e){fail(e);}};
}
function heading(tag,title,description) {return `<div class="eyebrow">${tag}</div><h1>${title}</h1><p class="lead">${description}</p>`;}
const statusName=s=>({cancelled:'已取消',rejected:'商家拒单',expired:'超时关闭',pending:'待确认',preparing:'制作中',completed:'已完成 / 待取餐'}[s]||s);
function lines(o) {return o.items.map(i=>`<div class="row cart-row"><span>${esc(i.name)} × ${i.qty}</span><b>${money(i.price*i.qty)}</b></div>`).join('');}
function displayTime(t) {return new Date(t).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});}
async function action(button, fn) {
  if(button.disabled)return;button.disabled=true;button.setAttribute('aria-busy','true');
  try{await fn();}catch(e){fail(e);}finally{if(button.isConnected){button.disabled=false;button.removeAttribute('aria-busy');}}
}
function bindAction(selector, fn) {const b=$(selector);if(b)b.onclick=()=>action(b,fn);}

async function customerSession(){const d=await api('customer/session',{});me=d.user;csrf=d.csrf;return true;}

const BRAND_THEMES=[
  {id:'fresh',name:'清新自然',desc:'竹韵绿意，清爽亲切',swatches:['#235c43','#fffefa','#f3f4ed']},
  {id:'minimal',name:'极简黑白',desc:'去彩色，突出内容本身',swatches:['#222222','#ffffff','#f7f7f7']},
  {id:'vibrant',name:'潮流暖橙',desc:'高饱和暖色，年轻有活力',swatches:['#e0492f','#fffaf4','#fdeee2']},
  {id:'classic',name:'中式典雅',desc:'深红米金，衬线标题',swatches:['#8c3b2e','#faf5ea','#f0e7d4']},
  {id:'cute',name:'可爱粉嫩',desc:'圆润字体与波点，活泼亲切',swatches:['#e5568f','#fff7fb','#ffeef5']},
  {id:'luxury',name:'奢华黑金',desc:'深色底配金色，高端质感',swatches:['#c9a15a','#1e1a15','#131110']},
];
BRAND_THEMES.unshift(
  {id:'universal',name:'简约通用',desc:'大方留白，适合各类门店',swatches:['#293e38','#fffefa','#f4f3ee']},
  {id:'western',name:'高端西餐',desc:'深色金边，优雅餐厅气质',swatches:['#c9a15a','#1e1a15','#131110']},
  {id:'hotpot',name:'中式火锅',desc:'暖红米白，热闹清晰的菜单',swatches:['#a73324','#fff9ee','#f9eadb']}
);
for(const theme of BRAND_THEMES)theme.types={universal:['通用'],western:['西餐咖啡'],hotpot:['中式餐饮'],minimal:['通用','西餐咖啡'],classic:['中式餐饮'],luxury:['西餐咖啡'],cute:['茶饮甜品'],vibrant:['中式餐饮','茶饮甜品'],fresh:['通用','茶饮甜品']}[theme.id];
const themeName=id=>(BRAND_THEMES.find(t=>t.id===id)||BRAND_THEMES[0]).name;
function applyBrand(brand){
  const theme=BRAND_THEMES.find(t=>t.id===((brand&&brand.theme)||'fresh'))||BRAND_THEMES[0];
  document.documentElement.dataset.theme=theme.id;
  const meta=document.querySelector('meta[name=theme-color]');if(meta)meta.content=theme.swatches[0];
}
