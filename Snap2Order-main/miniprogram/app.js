const config = require('./config');
App({
 globalData: { config },
 request(path, data, method='GET', session=null) {
  return new Promise((resolve,reject)=>wx.request({url:config.API_BASE+'/api/'+path,method,data,
   header:{'Content-Type':'application/json','X-Client-Type':'mini-customer',...(session?{'Authorization':'Bearer '+session.token,'X-CSRF-Token':session.csrf}:{})},
   success:r=>{if(r.statusCode>=200&&r.statusCode<300)resolve(r.data);else {const e=new Error(r.data.error||'请求失败');e.status=r.statusCode;reject(e);}},fail:()=>reject(new Error('无法连接服务，请检查 HTTPS 域名与网络。'))}));
 },
 async customerSession(force=false){
  let current=wx.getStorageSync('snap_customer_session');
  if(current&&!force)return current;
  let result;
  if(config.USE_WECHAT_LOGIN){const login=await new Promise((resolve,reject)=>wx.login({success:resolve,fail:reject}));result=await this.request('auth/wechat',{code:login.code},'POST');}
  else result=await this.request('customer/session',{},'POST');
  if(!result.token)throw new Error('服务端未返回有效会话，请更新服务。');
  wx.setStorageSync('snap_customer_session',result);return result;
 },
 async customerRequest(path,data,method='GET'){
  let session=await this.customerSession();
  try{return await this.request(path,data,method,session);}catch(e){if(e.status!==401)throw e;session=await this.customerSession(true);return this.request(path,data,method,session);}
 }
});
