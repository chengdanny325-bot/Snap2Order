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
  $('#app').innerHTML=`<div class="auth-layout"><section class="auth-story"><div class="eyebrow">YOUR SHOP STARTS HERE</div><h1>让你的小店，<br>在线上也有自己的样子。</h1><p class="lead">从现有菜单和品牌想法出发。<br>无需产品和开发团队，也能创建自己的数字门店。</p><div class="story-line"><span>01</span><div><b>品牌与店铺</b><p>选一个符合业态的风格，呈现自己的品牌。</p></div></div><div class="story-line"><span>02</span><div><b>菜单与商品</b><p>导入纸质菜单，核对菜品、价格与规格。</p></div></div><div class="story-line"><span>03</span><div><b>功能模块</b><p>按经营需要，选择点单、会员与优惠功能。</p></div></div><div class="story-line"><span>04</span><div><b>预览与发布</b><p>看看顾客眼中的门店，确认后发布。</p></div></div></section><section class="panel auth-panel"><div class="auth-tabs"><button id="loginTab" class="${register?'':'selected'}">登录</button><button id="registerTab" class="${register?'selected':''}">创建门店</button></div><h2>${register?'创建你的数字门店':'欢迎回来'}</h2><p>${register?'先创建账号，再添加你的菜单与品牌资料。':'继续打造你的门店，管理菜单与订单。'}</p><form id="authForm">${register?'<label>店铺名称<input name="store_name" maxlength="50" required placeholder="例如：阿芳的小馆" autocomplete="organization"></label>':''}<label>账号<input name="username" minlength="3" maxlength="32" required pattern="[A-Za-z0-9_]{3,32}" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="3～32 位字母、数字或下划线"></label><label>密码<input name="password" type="password" minlength="8" maxlength="128" required autocomplete="${register?'new-password':'current-password'}" placeholder="至少 8 位"></label>${register?'<label>再次输入密码<input name="confirm" type="password" minlength="8" required autocomplete="new-password"></label>':''}<div id="formError" class="form-error" role="alert" tabindex="-1"></div><button type="submit" class="primary full">${register?'开始创建门店':'登录'}</button></form><p class="caption">商家建店入口 · 顾客通过门店专属链接或二维码访问。</p></section></div>`;
  $('#loginTab').onclick=()=>{mode='login';renderAuth();};$('#registerTab').onclick=()=>{mode='register';renderAuth();};
  $('#authForm').onsubmit=async e=>{
    e.preventDefault();const form=e.currentTarget, values=Object.fromEntries(new FormData(form));values.role='merchant';const error=$('#formError');error.textContent='';
    if(register&&values.password!==values.confirm){error.textContent='两次密码不一致，请重新检查。';error.focus();return;}
    await action(form.querySelector('[type=submit]'),async()=>{try{const d=await api('auth/'+(register?'register':'login'),values);location.replace(destination(d.user));}catch(err){error.textContent=err.message;error.focus();}});
  };
}
if(params.get('role')==='customer'){const next=params.get('next')||'/customer/orders';location.replace(/^\/s\/[a-f0-9]{24}(?:\?[^#]*)?$/.test(next)?next:'/customer/orders');}else session().then(()=>{if(me)location.replace(destination(me));else renderAuth();}).catch(fail);
