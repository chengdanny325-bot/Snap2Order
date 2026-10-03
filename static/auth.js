'use strict';
const params=new URLSearchParams(location.search);
let mode=params.get('mode')==='register'?'register':'login', role=params.get('role')==='customer'?'customer':'merchant';
function destination(user) {
  const next=params.get('next')||'';
  if(user.role==='merchant')return /^\/merchant\/(menu|orders)$/.test(next)?next:'/merchant/menu';
  return /^\/s\/[a-f0-9]{24}(?:\?[^#]*)?$/.test(next)?next:'/customer/orders';
}
function renderAuth() {
  header('public');
  const register=mode==='register';
  $('#app').innerHTML=`<div class="auth-layout"><section class="auth-story"><div class="eyebrow">A SMALL SHOP, A SIMPLE START</div><h1>从一张菜单，<br>开始一门小生意。</h1><p class="lead">导入菜单，配置品牌与功能，发布你的门店。<br>每个账号都有自己的空间。</p><div class="story-line"><span>01</span><div><b>品牌与店铺</b><p>选择风格，完善店铺资料。</p></div></div><div class="story-line"><span>02</span><div><b>菜单与商品</b><p>拍照识别，核对菜品和规格。</p></div></div><div class="story-line"><span>03</span><div><b>功能模块</b><p>选择点单、会员与营销功能。</p></div></div><div class="story-line"><span>04</span><div><b>预览与发布</b><p>体验完整门店，确认后统一发布。</p></div></div></section><section class="panel auth-panel"><div class="auth-tabs"><button id="loginTab" class="${register?'':'selected'}">登录</button><button id="registerTab" class="${register?'selected':''}">注册小店</button></div><h2>${register?'第一次来，开一家小店':'欢迎回来'}</h2><p>${register?'新账号从空白开始，不会载入别人的菜单或订单。':'登录后继续管理店铺配置、菜单和订单。'}</p><form id="authForm">${register?'<label>店铺名称<input name="store_name" maxlength="50" required placeholder="例如：阿芳的小馆" autocomplete="organization"></label>':''}<label>账号<input name="username" minlength="3" maxlength="32" required pattern="[A-Za-z0-9_]{3,32}" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="3～32 位字母、数字或下划线"></label><label>密码<input name="password" type="password" minlength="8" maxlength="128" required autocomplete="${register?'new-password':'current-password'}" placeholder="至少 8 位"></label>${register?'<label>再次输入密码<input name="confirm" type="password" minlength="8" required autocomplete="new-password"></label>':''}<div id="formError" class="form-error" role="alert" tabindex="-1"></div><button type="submit" class="primary full">${register?'创建小店并进入':'登录'}</button></form><p class="caption">这里是商家入口。顾客扫码即可点单，无需注册。当前仅提供模拟支付。</p></section></div>`;
  $('#loginTab').onclick=()=>{mode='login';renderAuth();};$('#registerTab').onclick=()=>{mode='register';renderAuth();};
  $('#authForm').onsubmit=async e=>{
    e.preventDefault();const form=e.currentTarget, values=Object.fromEntries(new FormData(form));values.role='merchant';const error=$('#formError');error.textContent='';
    if(register&&values.password!==values.confirm){error.textContent='两次密码不一致，请重新检查。';error.focus();return;}
    await action(form.querySelector('[type=submit]'),async()=>{try{const d=await api('auth/'+(register?'register':'login'),values);location.replace(destination(d.user));}catch(err){error.textContent=err.message;error.focus();}});
  };
}
if(params.get('role')==='customer'){const next=params.get('next')||'/customer/orders';location.replace(/^\/s\/[a-f0-9]{24}(?:\?[^#]*)?$/.test(next)?next:'/customer/orders');}else session().then(()=>{if(me)location.replace(destination(me));else renderAuth();}).catch(fail);
