'use strict';
const storeID=location.pathname.split('/')[2],query=new URLSearchParams(location.search);
let shop, cart={}, note='', filter='全部',order=null, cartOpen=false, submitting=false;
let requestKey=uid();
let storageKey='snap_cart_'+storeID+'_guest';
function readCart() {try{const d=JSON.parse(sessionStorage.getItem(storageKey)||'{}');cart=d.cart||{};note=d.note||'';requestKey=d.requestKey||uid();}catch{}}
function persistCart() {sessionStorage.setItem(storageKey,JSON.stringify({cart,note,requestKey}));}
function totalCents() {return shop.items.reduce((sum,i)=>sum+Math.round(i.price*100)*(cart[i.id]||0),0);}
function storeBrand() {
  const b=shop.brand||{};
  return `<div class="store-brand">${b.logo_url?`<img src="${esc(b.logo_url)}" alt="${esc(shop.name)}的店铺 Logo">`:''}<div><div class="eyebrow">FRESHLY MADE, SIMPLY ORDERED</div><h1>${esc(shop.name)}<span class="brand-mark" aria-hidden="true"></span></h1><p class="lead">现点现做，好好吃饭。选好喜欢的菜，我们来准备。</p></div></div>`;
}
function renderCustomer() {
  header('customer',shop?.name||'');
  if(order){renderOrder();return;}
  const items=shop.items,categories=['全部',...new Set(items.map(i=>i.category))];
  const total=totalCents()/100,quantity=Object.values(cart).reduce((s,n)=>s+n,0);
  $('#app').innerHTML=storeBrand()+`<div class="filters menu-filters">${categories.map(c=>`<button data-filter="${esc(c)}" class="${filter===c?'selected':''}">${esc(c)}</button>`).join('')}</div><div class="customer-layout"><section><h2 class="sr-only">菜品菜单</h2><div class="menu-grid">${items.filter(i=>filter==='全部'||i.category===filter).map(i=>`<article class="dish">${i.image_url?`<img class="dish-photo" src="${esc(i.image_url)}" alt="${esc(i.name)}的${i.image_url.startsWith('/assets/dishes/')?'素材示意图':'商家实拍图'}" loading="lazy" decoding="async">`:''}<div class="dish-info"><small>${esc(i.category)}${i.image_url?' · '+(i.image_url.startsWith('/assets/dishes/')?'素材示意图':'商家实拍'):''}</small><h3>${esc(i.name)}</h3><div class="price">${money(i.price)}</div></div><div class="qty"><button data-id="${i.id}" data-delta="-1" aria-label="减少${esc(i.name)}" ${cart[i.id]?'':'disabled'}>−</button><span>${cart[i.id]||0}</span><button data-id="${i.id}" data-delta="1" aria-label="增加${esc(i.name)}" ${(cart[i.id]||0)>=99?'disabled':''}>＋</button></div></article>`).join('')||'<section class="panel empty"><h3>暂时没有上架菜品</h3><p>请稍后再来看看。</p></section>'}</div></section><aside id="cart" class="panel cart"><h2>这一单，吃点什么？</h2>${items.filter(i=>cart[i.id]).map(i=>`<div class="row cart-row"><span>${esc(i.name)} × ${cart[i.id]}</span><b>${money(i.price*cart[i.id])}</b></div>`).join('')||'<p>选一道喜欢的菜，开始点单。</p>'}<label class="secondary">口味备注<textarea id="note" rows="3" maxlength="300" placeholder="例如：少辣，不要葱">${esc(note)}</textarea></label><div class="row secondary"><span>合计 ${quantity} 份</span><span class="total">${money(total)}</span></div><button id="submitOrder" class="primary full secondary">提交订单 →</button><p class="caption">当前为演示支付，不会实际扣款。</p></aside></div><a class="mobile-cart" href="#cart"><span>查看已选 ${quantity} 份</span><b>${money(total)} · 去下单 →</b></a>`;
  document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;renderCustomer();});
  document.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>{const id=b.dataset.id;cart[id]=Math.min(99,Math.max(0,(cart[id]||0)+Number(b.dataset.delta)));if(!cart[id])delete cart[id];requestKey=uid();persistCart();const selector=`[data-id="${id}"][data-delta="${b.dataset.delta}"]`;renderCustomer();$(selector)?.focus({preventScroll:true});});
  $('#note').oninput=e=>{note=e.target.value;requestKey=uid();persistCart();};
  bindAction('#submitOrder',async()=>{
    if(!quantity)throw Error('先选一道喜欢的菜吧');
    persistCart();await customerSession();
    const prices=Object.fromEntries(items.filter(i=>cart[i.id]).map(i=>[i.id,i.price]));
    try {
      const d=await api('customer/orders',{store_id:storeID,cart,prices,note,idempotency_key:requestKey});order=d.order;cart={};note='';sessionStorage.removeItem(storageKey);
      history.replaceState(null,'',location.pathname+'?order='+order.id);renderCustomer();$('#app').focus();
    } catch(e) {
      if(e.status===409){shop=(await api('stores/'+storeID)).store;applyBrand(shop.brand);cart=Object.fromEntries(Object.entries(cart).filter(([id])=>shop.items.some(i=>i.id===id)));requestKey=uid();persistCart();renderCustomer();}
      if(e.status===401){await customerSession();throw Error('点单会话已更新，请重试。');}else throw e;
    }
  });
}
function renderOrder() {
  const o=order;$('#app').innerHTML=heading('YOUR ORDER','订单已经送到小店。','付款和制作进度会在这里更新。')+`<section class="panel order-detail"><span id="orderStatus" class="badge">${statusName(o.status)}</span><p class="secondary">取餐订单号</p><div class="order-num">${o.id.slice(-6).toUpperCase()}</div><p class="hint">${esc(o.store_name)} · ${displayTime(o.created)}</p>${lines(o)}<p class="secondary">口味备注：${esc(o.note||'无')}</p><div class="row"><b>合计</b><span class="total">${money(o.total)}</span></div>${o.payment==='unpaid'?`<div class="warn secondary">演示支付，不会实际扣款。</div><button id="pay" class="primary full secondary">模拟支付 ${money(o.total)}</button>`:'<div class="good secondary">✓ 已支付（Demo） · 无真实扣款</div>'}<div class="actions"><a class="button" href="/s/${storeID}">再点一单</a><a class="button" href="/customer/orders">查看本设备订单</a></div></section>`;
  bindAction('#pay',async()=>{order=(await api('orders/'+o.id+'/pay',{})).order;renderOrder();message('模拟支付成功，没有真实扣款。');});
}
async function start() {
  await customerSession();if(me){storageKey='snap_cart_'+storeID+'_'+me.id;if(sessionStorage.getItem('snap_pending_cart')===storeID){const guest=sessionStorage.getItem('snap_cart_'+storeID+'_guest');if(guest)sessionStorage.setItem(storageKey,guest);sessionStorage.removeItem('snap_cart_'+storeID+'_guest');sessionStorage.removeItem('snap_pending_cart');}}shop=(await api('stores/'+storeID)).store;
  if(query.get('order')) {
    if(!me)await customerSession();
    order=(await api('orders/'+query.get('order'))).order;
    if(order.store_id!==storeID)throw Error('这笔订单不属于当前店铺');
  } else {
    readCart();cart=Object.fromEntries(Object.entries(cart).filter(([id,n])=>Number.isInteger(n)&&n>0&&n<=99&&shop.items.some(i=>i.id===id)));persistCart();
  }
  applyBrand(shop.brand);
  renderCustomer();
}
start().catch(e=>{header('customer');$('#app').innerHTML=`<section class="panel empty"><h1>暂时无法打开这张菜单</h1><p>${esc(e.message)}</p><a href="/customer/orders">查看本设备订单</a></section>`;});
setInterval(async()=>{if(document.hidden||!order||!me)return;try{const d=await api('orders/'+order.id);if(JSON.stringify(d.order)!==JSON.stringify(order)){order=d.order;renderOrder();}}catch(e){if(e.status===401)message('点单会话已过期，请刷新页面。',true);}},5000);
