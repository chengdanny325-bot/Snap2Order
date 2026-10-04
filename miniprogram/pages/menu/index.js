const {API_BASE}=require('../../config');
const menuItem=i=>({...i,imageURL:i.image_url?API_BASE.replace(/\/$/,'')+i.image_url:'',imageLabel:i.image_url?(i.image_url.startsWith('/assets/dishes/')?'素材示意图':'商家实拍'):'',qty:0,displayPrice:i.price.toFixed(2)});
const key=()=>Date.now().toString(36)+Math.random().toString(36).slice(2)+Math.random().toString(36).slice(2);
const {withLanguage}=require('../../i18n');
Page(withLanguage({
 data:{store:null,items:[],total:'0.00',note:'',order:null,error:'',busy:false,orderStatus:''},cart:{},requestKey:'',
 async onLoad(options){this.storeID=decodeURIComponent(options.scene||options.store||'');this.requestKey=key();if(!/^[a-f0-9]{24}$/.test(this.storeID)){this.setData({error:'店铺链接无效'});return;}try{const d=await getApp().request('stores/'+this.storeID);this.setData({store:d.store,items:d.store.items.map(menuItem)});}catch(e){this.setData({error:e.message});}},
 onShow(){if(this.data.order)this.startPolling();},onHide(){clearInterval(this.poll);},onUnload(){clearInterval(this.poll);},
 change(e){const id=e.currentTarget.dataset.id,delta=Number(e.currentTarget.dataset.delta);this.cart[id]=Math.min(99,Math.max(0,(this.cart[id]||0)+delta));if(!this.cart[id])delete this.cart[id];this.requestKey=key();const items=this.data.items.map(i=>({...i,qty:this.cart[i.id]||0}));const total=items.reduce((s,i)=>s+Math.round(i.price*100)*i.qty,0)/100;this.setData({items,total:total.toFixed(2)});},
 note(e){this.requestKey=key();this.setData({note:e.detail.value});},
 updateOrder(o){const status={pending:'待确认',preparing:'制作中',completed:'已完成 / 待取餐'};this.setData({order:{...o,displayTotal:o.total.toFixed(2),number:o.id.slice(-6).toUpperCase()},orderStatus:status[o.status]});},
 async submit(){if(this.data.busy)return;if(!Object.keys(this.cart).length){this.setData({error:'请先选择菜品'});return;}this.setData({busy:true,error:''});try{const prices={};this.data.items.forEach(i=>{if(this.cart[i.id])prices[i.id]=i.price;});const d=await getApp().customerRequest('customer/orders',{store_id:this.storeID,cart:this.cart,prices,note:this.data.note,idempotency_key:this.requestKey},'POST');this.updateOrder(d.order);this.cart={};this.startPolling();}catch(e){this.setData({error:e.message});if(e.status===409){const d=await getApp().request('stores/'+this.storeID);this.cart={};this.requestKey=key();this.setData({items:d.store.items.map(menuItem),total:'0.00'});}}finally{this.setData({busy:false});}},
 async pay(){if(this.data.busy)return;this.setData({busy:true,error:''});try{const d=await getApp().customerRequest('orders/'+this.data.order.id+'/pay',{},'POST');this.updateOrder(d.order);}catch(e){this.setData({error:e.message});}finally{this.setData({busy:false});}},
 startPolling(){clearInterval(this.poll);this.poll=setInterval(async()=>{try{const d=await getApp().customerRequest('orders/'+this.data.order.id);this.updateOrder(d.order);}catch{}},5000);},
 orders(){wx.navigateTo({url:'/pages/orders/index'});}
}));
