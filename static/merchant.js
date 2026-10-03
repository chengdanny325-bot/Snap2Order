'use strict';
let store, ocr, publicURL='', stage=1, draft=[], sourceID=null, preview='', uploadBlob=null, busy=false, warning='',dirty=false,removed=null;
let brand={logo_url:null,theme:'fresh'}, draftName='', logoUploading=false;
let imageLibrary=[], config=null, showImport=false, showShare=false;
const stageNames=['brand','import','modules','preview'];
const CATEGORY_PRESETS=['主食','热菜','凉菜','火锅锅底','肉类','海鲜','蔬菜','小吃','甜品','饮品','套餐','其他'];
let themeCategory='全部',logoPrompt='',aiLogoConfigured=false;
const photoUploads=new Set();
const sampleRows=[['招牌牛肉面',28,'主食'],['番茄鸡蛋面',18,'主食'],['红油抄于',16,'小吃'],['凉拌黄瓜',12,'小吃'],['酸梅汤',6,'饮品'],['冰豆浆',5,'饮品']];
function sample() {return sampleRows.map((r,n)=>({id:uid(),name:r[0],price:r[1],category:r[2],checked:false,available:true,confidence:n===2?.42:.95}));}
function sourceImage() {return preview || (sourceID?'/api/merchant/sources/'+sourceID:'');}
function publicLink() {return (publicURL||location.origin)+'/s/'+store.id;}
function render() {
  header('merchant');
  const titles=['配置品牌与资料','导入并核对菜单','组合门店功能','预览并发布门店'];
  const content=stage===1?brandView():stage===2?(showImport||!draft.length?uploadView():editView()):stage===3?moduleView():previewView();
  $('#app').innerHTML=heading('STORE BUILDER',titles[stage-1],'一步步配置你的线上门店。草稿只对你可见，发布后统一生效。')+`<nav class="steps builder-steps" aria-label="建店步骤">${titles.map((t,n)=>`<button data-stage="${n+1}" aria-current="${stage===n+1?'step':'false'}"><small>0${n+1}</small>${t}</button>`).join('')}</nav>`+content+`<div class="builder-bar"><span id="saveState" role="status">${dirty?'有未保存的修改':'草稿已保存'}</span><div class="actions"><button id="saveDraft">保存草稿</button>${stage>1?'<button id="previous">上一步</button>':''}${stage<4?'<button id="next" class="primary">下一步 →</button>':'<button id="publishStore" class="primary">确认并发布整店 →</button>'}</div></div>`;
  bind();bindBuilder();
}
function moveStage(next) {stage=next;showShare=false;history.replaceState(null,'','#'+stageNames[stage-1]);render();$('#app').focus();}
function payload(){return {name:draftName,items:draft,source_id:sourceID,brand,config};}
async function saveDraft(){
  for(const input of document.querySelectorAll('[data-options]'))if(!input.checkValidity()){input.reportValidity();throw Error('请修正规格格式后保存');}
  if(photoUploads.size||logoUploading)throw Error('请等待图片上传完成');
  const d=await api('merchant/draft',payload());store=d.store;draft=store.draft;draftName=store.draft_name;brand=store.brand_draft;config=store.config_draft;dirty=false;
}
function brandView(){return `<section class="panel"><div class="row"><h2>让门店有自己的品牌</h2><span class="hint">01 / 04</span></div><div class="profile-grid"><label>店铺名称<input id="storeName" value="${esc(draftName)}" maxlength="50" required></label><label>联系电话<input data-profile="phone" value="${esc(config.profile.phone)}" maxlength="40" type="tel"></label><label>地址<input data-profile="address" value="${esc(config.profile.address)}" maxlength="200"></label><label>营业时间<input data-profile="hours" value="${esc(config.profile.hours)}" maxlength="100" placeholder="例如：每天 10:00–21:00"></label></div><label>品牌介绍<textarea data-profile="description" maxlength="500" rows="3">${esc(config.profile.description)}</textarea></label><div class="banner-editor">${config.banner_url?`<img src="${esc(config.banner_url)}" alt="店铺封面预览">`:'<p class="hint">店铺封面可选，推荐横向实拍照片。</p>'}<label class="button photo-file">上传店铺封面<input id="bannerFile" class="file-cover" type="file" accept="image/jpeg,image/png,image/webp"></label><button id="bannerRemove" ${config.banner_url?'':'disabled'}>移除封面</button></div>${brandEditor()}</section>`;}
function moduleView(){const labels={ordering:['在线点单','购物车、规格选择与提交订单'],membership:['会员积分','顾客加入本店会员，模拟支付每满一元积一分'],coupons:['优惠券','顾客每日可领一张，按门槛抵扣订单金额'],wheel:['幸运转盘','每设备顾客每天一次，50% 概率获得本店优惠券']};return `<section class="panel"><h2>选择适合你经营的功能</h2><p>开关和参数随整店发布生效。顾客身份依赖浏览器会话；当前支付为模拟支付。</p><div class="module-list">${Object.entries(labels).map(([id,[name,desc]])=>`<label class="module-option"><input type="checkbox" data-module="${id}" ${config.modules[id]?'checked':''}><span><b>${name}</b><small>${desc}</small></span></label>`).join('')}</div><fieldset><legend>优惠券与转盘奖品</legend><div class="profile-grid"><label>优惠金额（元）<input data-coupon="amount" type="number" min="0.01" step="0.01" value="${config.coupon.amount}"></label><label>使用门槛（元）<input data-coupon="minimum" type="number" min="0.02" step="0.01" value="${config.coupon.minimum}"></label></div><p class="hint">使用门槛须高于优惠金额。已领取的券保留领取时的金额和门槛。</p></fieldset><label>菜单布局<select id="menuLayout"><option value="grid" ${config.layout==='grid'?'selected':''}>图片网格</option><option value="list" ${config.layout==='list'?'selected':''}>紧凑列表</option></select></label></section>`;}
function previewView(){return `<section class="panel"><div class="row"><div><h2>发布前，看看整家店</h2><p>使用顾客端相同页面渲染草稿。预览可选规格、加入会员、领取测试券和体验转盘；这些操作不会写入正式数据。</p></div><button id="refreshPreview">保存并刷新预览</button></div><iframe id="storePreview" class="store-preview" src="/merchant/preview" title="未发布门店完整预览"></iframe></section>${showShare?publishedView():''}`;}
function parseOptions(value){return value.split('\n').map(s=>s.trim()).filter(Boolean).map(line=>{const [name,raw]=line.split(/[:：]/);if(!raw)throw Error('规格格式：大小份：小份+0,大份+5');return {name:name.trim(),choices:raw.split(/[,，]/).map(v=>{const parts=v.trim().split('+');return {name:parts[0].trim(),extra:Number(parts[1]||0)};})};});}
function optionsText(i){return (i.options||[]).map(g=>g.name+'：'+g.choices.map(c=>c.name+'+'+c.extra).join(',')).join('\n');}
function bindBuilder(){
  document.querySelectorAll('[data-stage]').forEach(b=>b.onclick=()=>action(b,async()=>{await saveDraft();moveStage(Number(b.dataset.stage));}));
  bindAction('#saveDraft',async()=>{await saveDraft();render();message('整店草稿已保存');});
  bindAction('#next',async()=>{await saveDraft();moveStage(stage+1);});
  bindAction('#previous',async()=>{await saveDraft();moveStage(stage-1);});
  bindAction('#refreshPreview',async()=>{await saveDraft();$('#storePreview').src='/merchant/preview?t='+Date.now();message('预览已更新');});
  bindAction('#publishStore',async()=>{if(draft.some(i=>!i.checked))throw Error('请返回菜单导入，核对并确认每道菜');await saveDraft();const d=await api('merchant/publish',payload());store=d.store;dirty=false;showShare=true;render();message('门店已发布，链接和二维码保持不变');});
  document.querySelectorAll('[data-profile]').forEach(i=>i.oninput=()=>{config.profile[i.dataset.profile]=i.value;dirty=true;});
  document.querySelectorAll('[data-module]').forEach(i=>i.onchange=()=>{config.modules[i.dataset.module]=i.checked;dirty=true;});
  document.querySelectorAll('[data-coupon]').forEach(i=>i.oninput=()=>{config.coupon[i.dataset.coupon]=Number(i.value);dirty=true;});
  if($('#menuLayout'))$('#menuLayout').onchange=e=>{config.layout=e.target.value;dirty=true;};
  if($('#bannerFile'))$('#bannerFile').onchange=async e=>{if(!e.target.files[0])return;try{logoUploading=true;const blob=await compressDishPhoto(e.target.files[0]);config.banner_url=(await api('merchant/dish-images',blob,{raw:true})).image_url;dirty=true;}catch(e){fail(e);}finally{logoUploading=false;render();}};
  bindAction('#bannerRemove',()=>{config.banner_url=null;dirty=true;render();});
  document.querySelectorAll('[data-stock]').forEach(i=>i.oninput=()=>{const item=draft[Number(i.dataset.stock)];item.stock=i.value===''?null:Number(i.value);item.stock_update=true;item.checked=false;updateRow(Number(i.dataset.stock));});
  document.querySelectorAll('[data-description]').forEach(i=>i.oninput=()=>{draft[Number(i.dataset.description)].description=i.value;dirty=true;});
  document.querySelectorAll('[data-options]').forEach(i=>i.oninput=()=>{try{draft[Number(i.dataset.options)].options=parseOptions(i.value);i.setCustomValidity('');i.closest('details').querySelector('.option-error').textContent='';}catch(e){i.setCustomValidity(e.message);i.closest('details').querySelector('.option-error').textContent=e.message;}draft[Number(i.dataset.options)].checked=false;updateRow(Number(i.dataset.options));});
}
function uploadView() {return `<div class="layout"><section class="panel"><h2>先把菜单拍下来</h2><p>清晰拍下菜名和价格，剩下的交给识别服务。</p><div class="upload">${sourceImage()?`<img src="${esc(sourceImage())}" alt="已选择的菜单照片">`:'<div class="symbol" aria-hidden="true">▧</div>'}<h3>${sourceImage()?'照片已经准备好了':'拍照，或从相册选择'}</h3><p>支持 JPG、PNG、WebP。手机照片会先压缩，保持文字清晰。</p><div class="photo-actions"><button type="button" id="openCamera">手机拍照</button><label class="button">选择菜单图片<input id="file" class="file-cover" type="file" accept="image/jpeg,image/png,image/webp" aria-label="选择菜单图片"></label></div>${uploadBlob?`<button id="recognize" class="primary secondary" ${busy?'disabled':''}>${busy?'正在识别，请稍候…':'开始云端识别'}</button>`:''}</div><p class="hint secondary">拍照前会请求相机权限，仅使用摄像头、不录音；拒绝后仍可选择相册图片。</p><p class="hint secondary">点击“开始云端识别”会把菜单照片交给${esc(ocr.provider)}处理。请避免拍入个人资料。</p>${warning?`<div class="warn">${esc(warning)}</div>`:''}<div class="actions"><button id="manual">手动添加菜品</button><button id="sample">载入演示菜单</button></div><p class="caption">${ocr.configured?'云端识别已配置，可尝试你的菜单照片。':'云端识别未配置。管理员需在服务器设置 API Key，当前可手动录入。'}</p></section><aside class="panel guide"><div class="eyebrow">YOUR SHOP STARTS HERE</div><h2>一次拍照，<br>少一点录入。</h2><ol><li><b>照片尽量清晰</b><p>正对菜单拍摄，避开反光和阴影。</p></li><li><b>检查菜名和价格</b><p>不确定的内容会提示检查，发布前由你确认。</p></li><li><b>分享专属链接</b><p>顾客打开你的店铺页，选择菜品即可下单。</p></li></ol><div class="good">${esc(store.name)}<br><small>${store.published?'已有菜单上线，重新识别不会立即覆盖。':'这是一家新店，目前没有发布菜品。'}</small></div></aside></div>`;}

function imageKind(item) {
  return !item.image_url?'暂不放图':item.image_url.startsWith('/assets/dishes/')?'素材示意图':'商家实拍';
}
function dishPhotoEditor(item,n) {
  const uploading=photoUploads.has(item.id);
  return `<div class="dish-photo-editor"><div class="photo-preview">${item.image_url?`<img src="${esc(item.image_url)}" alt="${esc(item.name||'菜品')}的${imageKind(item)}">`:'<span>暂无图片</span>'}</div><div class="photo-settings"><b>菜品图片 <small>可选</small></b><p class="hint photo-state" role="status">${uploading?'正在压缩并上传照片…':imageKind(item)}</p><div class="photo-options"><label class="button photo-file ${uploading?'disabled':''}">上传实拍<input class="file-cover" type="file" data-photo-file="${n}" accept="image/jpeg,image/png,image/webp" aria-label="上传${esc(item.name||'菜品')}实拍图" ${uploading?'disabled':''}></label><button type="button" data-photo-camera="${n}" ${uploading?'disabled':''}>拍照</button><button type="button" data-photo-library="${n}" ${uploading?'disabled':''}>选推荐素材</button><button type="button" data-photo-none="${n}" aria-pressed="${!item.image_url}" ${uploading?'disabled':''}>暂不放图</button></div><p class="hint photo-note">实拍照片会自动压缩；素材图片仅为插画示意。</p></div></div>`;
}
async function compressDishPhoto(file) {
  if(file.size>25*1024*1024)throw Error('原照片请小于 25MB，或先裁剪后上传。');
  const url=URL.createObjectURL(file);
  try {
    const image=new Image();image.src=url;await image.decode();
    const canvas=document.createElement('canvas');const scale=Math.min(1,1600/Math.max(image.width,image.height));
    canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale));
    const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0,canvas.width,canvas.height);
    let blob;
    for(const quality of [.85,.7,.55]){blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',quality));if(blob&&blob.size<=2*1024*1024)break;}
    if(!blob||blob.size>2*1024*1024)throw Error('照片仍大于 2MB，请裁剪后上传。');
    return blob;
  } catch(e) {throw Error(e.name==='EncodingError'?'无法读取照片，请使用 JPG / PNG，或截图后上传。':e.message);}
  finally {URL.revokeObjectURL(url);}
}
async function uploadDishPhoto(item,file) {
  if(!item||photoUploads.has(item.id))return;
  photoUploads.add(item.id);dirty=true;render();
  try {
    const blob=await compressDishPhoto(file);const data=await api('merchant/dish-images',blob,{raw:true});
    if(draft.includes(item)){item.image_url=data.image_url;message('实拍图已上传，请保存草稿或发布菜单');}
  } finally {photoUploads.delete(item.id);render();}
}
async function uploadLogo(file) {
  if(logoUploading)return;
  logoUploading=true;dirty=true;render();
  try {
    const blob=await compressDishPhoto(file);const data=await api('merchant/logo',blob,{raw:true});
    brand.logo_url=data.logo_url;message('Logo 已上传，请保存草稿或发布菜单');
  } finally {logoUploading=false;render();}
}
function brandEditor() {
  return `<fieldset class="brand-editor"><legend>店铺品牌</legend><div class="logo-editor"><div class="logo-preview">${brand.logo_url?`<img src="${esc(brand.logo_url)}" alt="店铺 Logo 预览">`:'<span>暂无 Logo</span>'}</div><div class="logo-settings"><b>店铺 Logo <small>可选</small></b><p class="hint" role="status">${logoUploading?'正在压缩并上传 Logo…':brand.logo_url?'已上传，保存草稿或发布后生效':'未设置 Logo，顾客页只显示店名'}</p><div class="photo-options"><label class="button photo-file ${logoUploading?'disabled':''}">上传 Logo<input id="logoFile" class="file-cover" type="file" accept="image/jpeg,image/png" aria-label="上传店铺 Logo" ${logoUploading?'disabled':''}></label><button type="button" id="logoRemove" ${brand.logo_url?'':'disabled'} ${logoUploading?'disabled':''}>移除 Logo</button></div><p class="hint photo-note">支持 JPG、PNG，上传前自动压缩为不超过 2MB 的 JPEG。</p></div></div><section class="ai-logo-tools"><h3>AI 设计 Logo</h3><p class="hint">${aiLogoConfigured?'根据店名、当前风格与图形描述生成一张 Logo，可能产生模型服务费用。':'尚未配置图像生成服务，仍可手动上传 Logo。'}</p><label>Logo 图形描述<input id="logoPrompt" value="${esc(logoPrompt)}" maxlength="500" placeholder="例如：简洁的餐具与圆形徽记，避免复杂文字"></label><button id="generateLogo" ${logoUploading||!aiLogoConfigured?'disabled':''}>AI 生成 Logo</button></section><div class="row"><b>品牌风格</b><label>按餐饮类型筛选<select id="themeCategory">${['全部','通用','西餐咖啡','中式餐饮','茶饮甜品'].map(c=>`<option value="${esc(c)}" ${themeCategory===c?'selected':''}>${esc(c)}</option>`).join('')}</select></label></div><div class="theme-picker">${BRAND_THEMES.filter(t=>themeCategory==='全部'||t.types.includes(themeCategory)).map(t=>`<button type="button" class="theme-card" data-theme-id="${t.id}" aria-pressed="${brand.theme===t.id}"><span class="swatches"><i></i><i></i><i></i></span>${esc(t.name)}<small>${esc(t.desc)}</small></button>`).join('')}</div><div class="brand-preview" data-theme="${esc(brand.theme)}"><div class="preview-body"><div class="preview-head">${brand.logo_url?`<img src="${esc(brand.logo_url)}" alt="">`:''}<b>${esc(draftName||store.name)}<span class="brand-mark" aria-hidden="true"></span></b></div><div class="preview-dish">示例菜品<span>¥28.00</span></div><span class="preview-button">提交订单 →</span></div></div><p class="hint">Logo 与风格随草稿保存，发布后顾客才能看到。</p></fieldset>`;
}
function openImageLibrary(item,trigger) {
  const dialog=document.createElement('dialog');dialog.className='image-library';
  const scores=new Map(imageLibrary.map(image=>[image.id,image.keywords.some(word=>item.name.toLowerCase().includes(word))?2:image.category===item.category?1:0]));
  const images=[...imageLibrary].sort((a,b)=>scores.get(b.id)-scores.get(a.id));
  dialog.setAttribute('aria-labelledby','imageLibraryTitle');
  dialog.innerHTML=`<div class="row"><h2 id="imageLibraryTitle">给${esc(item.name||'这道菜')}选张素材</h2><button type="button" data-close aria-label="关闭素材库">关闭</button></div><p>按菜名与分类推荐。以下为插画素材，顾客端会注明“素材示意图”。</p><div class="library-grid">${images.map(image=>`<button type="button" class="library-option" data-asset="${esc(image.id)}" aria-pressed="${item.image_url===image.url}"><img src="${esc(image.url)}" alt="${esc(image.name)}插画" loading="lazy"><span>${esc(image.name)}</span>${scores.get(image.id)>0?'<small>推荐</small>':''}</button>`).join('')||'<p>素材库暂时不可用，你可以上传实拍或暂不放图。</p>'}</div>`;
  document.body.append(dialog);dialog.showModal();
  dialog.querySelector('[data-close]').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{dialog.remove();if(trigger.isConnected)trigger.focus();},{once:true});
  dialog.querySelectorAll('[data-asset]').forEach(button=>button.onclick=()=>{
    item.image_url=imageLibrary.find(image=>image.id===button.dataset.asset).url;dirty=true;dialog.close();render();
    $(`[data-photo-library="${draft.indexOf(item)}"]`)?.focus();message('素材已选择，请保存草稿或发布菜单');
  });
}

function editRow(i,n) {return `<article class="item-edit ${i.checked?'':'needs-check'}" data-row="${n}"><div class="item-title"><b>菜品 ${String(n+1).padStart(2,'0')}</b><span class="check-state">${i.checked?'✓ 已确认':i.price===null?'价格未识别，请填写':i.confidence!=null&&i.confidence<.8?'识别不确定，请检查':'请检查后确认'}</span></div><label>菜名<input data-edit="name" data-n="${n}" value="${esc(i.name)}" maxlength="80" required></label><label>价格（元）<input type="number" data-edit="price" data-n="${n}" value="${i.price===null?'':i.price}" min="0.01" max="9999.99" step="0.01" required inputmode="decimal"></label><label>分类候选<select data-category-preset="${n}">${CATEGORY_PRESETS.map(c=>`<option value="${esc(c)}" ${i.category===c?'selected':''}>${esc(c)}</option>`).join('')}<option value="custom" ${CATEGORY_PRESETS.includes(i.category)?'':'selected'}>自定义分类</option></select></label><label>分类名称（可自定义）<input data-edit="category" data-n="${n}" value="${esc(i.category)}" maxlength="30" required list="categories"></label><label>菜品描述<input data-description="${n}" value="${esc(i.description||'')}" maxlength="200"></label><label>库存（留空不限量）<input data-stock="${n}" type="number" min="0" max="99999" step="1" value="${i.stock??''}"></label><details class="spec-editor"><summary>规格与加料 · ${(i.options||[]).length} 组</summary><label>每行一组：名称：选项+加价,选项+加价<textarea data-options="${n}" rows="3" placeholder="大小份：小份+0,大份+5&#10;温度：热+0,冷+0&#10;加料：不加+0,鸡蛋+2">${esc(optionsText(i))}</textarea></label><p class="option-error" role="alert"></p></details>${dishPhotoEditor(i,n)}<div class="options"><label><input type="checkbox" data-edit="available" data-n="${n}" ${i.available?'checked':''}> 上架</label><label><input type="checkbox" data-edit="checked" data-n="${n}" ${i.checked?'checked':''}> 已检查</label><button type="button" class="quiet danger" data-delete="${n}" aria-label="删除${esc(i.name||'菜品'+(n+1))}">删除</button></div></article>`;}
function editView() {return `<section class="panel"><div class="row"><h2>检查一下，就可以开店了</h2><button type="button" id="uploadAgain">重新选图</button></div><p>核对每道菜，再勾选“已检查”。修改内容后需要重新确认。</p>${warning?`<div class="warn">${esc(warning)}</div>`:''}<form id="menuForm"><label>店铺名称<input id="storeName" value="${esc(draftName)}" maxlength="50" required autocomplete="organization"></label><datalist id="categories">${[...new Set([...CATEGORY_PRESETS,...draft.map(i=>i.category)])].map(c=>`<option value="${esc(c)}">`).join('')}</datalist><div class="layout editor-layout"><div><div id="rows">${draft.map(editRow).join('')}</div>${draft.length?'':'<p class="empty">还没有菜品，点击下方添加。</p>'}${removed?'<button type="button" id="undo">撤销刚才的删除</button>':''}<div class="actions"><button type="button" id="add">＋ 添加一道菜</button><button type="button" id="checkAll" ${draft.length?'':'disabled'}>✓ 一键已检查</button></div></div><aside class="source-panel"><h3>对照菜单原图</h3>${sourceImage()?`<img src="${esc(sourceImage())}" alt="当前店铺的菜单原图，用于检查菜名价格">`:'<p>当前为手动录入或演示菜单，没有原图。</p>'}<p class="hint">每道菜可上传实拍、选择插画素材，或暂不放图。图片修改保存为草稿，发布后才会展示给顾客。</p></aside></div></form></section>`;}
function publishedView() {return `<section class="panel published"><div class="good">✓ 菜单已发布，${esc(store.name)}准备好了</div><p class="hint store-brand" data-theme="${esc(store.brand.theme)}">${store.brand.logo_url?`<img src="${esc(store.brand.logo_url)}" alt="店铺 Logo">`:''}<span>品牌风格：${esc(themeName(store.brand.theme))}${store.brand.logo_url?' · 已设置 Logo':' · 未设置 Logo'}<span class="brand-mark" aria-hidden="true"></span></span></p><h2>把你的小店，分享给顾客。</h2><p>每家店都有固定的二维码和独立链接，顾客扫码后直接点餐。</p><div class="qr-share"><div><img class="store-qr" src="/api/merchant/qrcode" alt="当前店铺的专属点单二维码"><p class="hint">扫码进入这家店 · 无需顾客注册</p><a class="button" href="/api/merchant/qrcode" download="店铺点单二维码.svg">下载点单二维码</a></div><div><label>店铺专属点单链接<input id="shareLink" value="${esc(publicLink())}" readonly></label><div class="actions"><a class="button primary" href="${esc(publicLink())}" target="_blank" rel="noopener">打开顾客点餐页 ↗</a><button id="copy">复制链接</button><a class="button" href="/merchant/orders">去接单工作台</a></div></div></div><p class="caption">已上架 ${store.items.filter(i=>i.available).length} 道菜。修改菜单不会改变点单链接和二维码。手机扫码需要使用已部署的公网域名。</p>${publicLink().includes('localhost')||publicLink().includes('127.0.0.1')?'<p class="warn">当前二维码指向本机地址，其他手机无法访问。部署后设置 PUBLIC_URL，或本地测试时用电脑局域网 IP 打开商家页再生成二维码。</p>':''}<button id="editPublished">编辑菜单</button><button id="newPhoto">拍一张新菜单</button></section>`;}
function updateRow(n) {
  const i=draft[n],row=$(`[data-row="${n}"]`);if(!row)return;
  row.classList.toggle('needs-check',!i.checked);row.querySelector('.check-state').textContent=i.checked?'✓ 已确认':i.price===null?'价格未识别，请填写':'请检查后确认';
  row.querySelector('[data-edit=checked]').checked=i.checked;
  dirty=true;const save=$('#saveState');if(save)save.textContent='有未保存的修改';
}
async function preparePhoto(file) {
  if(!file)return;
  if(file.size>25*1024*1024)throw Error('原图请小于 25MB，或先裁剪后再上传。');
  let url=URL.createObjectURL(file);
  try {
    const img=new Image();img.src=url;await img.decode();
    const canvas=document.createElement('canvas');let scale=Math.min(1,2200/Math.max(img.width,img.height));
    canvas.width=Math.round(img.width*scale);canvas.height=Math.round(img.height*scale);
    const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);
    let blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.9));
    const maxBytes=ocr.max_image_bytes||950000;
    for(const quality of [.8,.7,.6,.5]){if(blob&&blob.size<=maxBytes)break;blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',quality));}
    for(let attempt=0;blob&&blob.size>maxBytes&&attempt<4;attempt++){const smaller=document.createElement('canvas');smaller.width=Math.round(canvas.width*.8);smaller.height=Math.round(canvas.height*.8);smaller.getContext('2d').drawImage(canvas,0,0,smaller.width,smaller.height);canvas.width=smaller.width;canvas.height=smaller.height;canvas.getContext('2d').drawImage(smaller,0,0);blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.8));}
    if(!blob||blob.size>maxBytes)throw Error('图片超过识别服务大小上限，请裁剪菜单后重试。');
    if(!blob||blob.size>8*1024*1024)throw Error('压缩后图片仍过大，请裁剪菜单后重试。');
    if(preview)URL.revokeObjectURL(preview);preview=URL.createObjectURL(blob);uploadBlob=blob;sourceID=null;warning='';render();
  } catch(e) {throw Error(e.name==='EncodingError'?'无法读取这张照片。请换成 JPG / PNG 图片，或先截图再上传。':e.message||'照片处理失败，请裁剪后重试。');}
  finally {URL.revokeObjectURL(url);}
}
function bind() {
  bindAction('#openCamera',()=>openMenuCamera(preparePhoto));
  ['file'].forEach(id=>{const input=$('#'+id);if(input)input.onchange=()=>preparePhoto(input.files[0]).catch(fail);});
  bindAction('#recognize',async()=>{
    busy=true;render();
    try {const d=await api('merchant/ocr',uploadBlob,{raw:true});draft=d.items;sourceID=d.source_id;warning='识别结果已按菜名和价格配对，请逐项核对；不确定的内容可手动修改。';stage=2;showImport=false;dirty=true;}
    catch(e) {warning=e.message;if(e.data?.source_id)sourceID=e.data.source_id;}
    finally {busy=false;render();}
  });
  bindAction('#manual',()=>{draft=[{id:uid(),name:'',price:null,category:'其他',checked:false,available:true,confidence:null}];stage=2;showImport=false;warning='';dirty=true;render();});
  bindAction('#sample',()=>{draft=sample();sourceID=null;preview='';stage=2;showImport=false;warning='这是演示数据，不是真实识别结果。“红油抄于”特意保留了一个错误，请修正为“红油抄手”。';dirty=true;render();});
  document.querySelectorAll('[data-photo-file]').forEach(input=>input.onchange=()=>{
    const item=draft[Number(input.dataset.photoFile)];
    if(input.files[0])uploadDishPhoto(item,input.files[0]).catch(fail);
  });
  document.querySelectorAll('[data-photo-library]').forEach(b=>b.onclick=()=>openImageLibrary(draft[Number(b.dataset.photoLibrary)],b));
  document.querySelectorAll('[data-photo-camera]').forEach(b=>b.onclick=()=>openMenuCamera(file=>uploadDishPhoto(draft[Number(b.dataset.photoCamera)],file)));
  document.querySelectorAll('[data-photo-none]').forEach(b=>b.onclick=()=>{const item=draft[Number(b.dataset.photoNone)];item.image_url=null;dirty=true;render();message('已设为暂不放图，保存或发布后生效');});
  const name=$('#storeName');if(name)name.oninput=()=>{draftName=name.value;dirty=true;$('#saveState').textContent='有未保存的修改';};
  const logoInput=$('#logoFile');if(logoInput)logoInput.onchange=()=>{if(logoInput.files[0])uploadLogo(logoInput.files[0]).catch(fail);};
  bindAction('#logoRemove',()=>{brand.logo_url=null;dirty=true;render();message('已移除 Logo，保存草稿或发布后生效');});
  if($('#themeCategory'))$('#themeCategory').onchange=e=>{themeCategory=e.target.value;render();};
  if($('#logoPrompt'))$('#logoPrompt').oninput=e=>{logoPrompt=e.target.value;};
  bindAction('#generateLogo',async()=>{if(!aiLogoConfigured)throw Error('请先在服务器 .env 配置 AI_LOGO_API_KEY、AI_LOGO_API_URL 和 AI_LOGO_MODEL');$('#generateLogo').textContent='正在生成 Logo…';let d;try{d=await api('merchant/logo-generate',{name:draftName,theme:brand.theme,prompt:logoPrompt});}catch(e){$('#generateLogo').textContent='AI 生成 Logo';throw e;}const bytes=Uint8Array.from(atob(d.image_base64),c=>c.charCodeAt(0));await uploadLogo(new File([bytes],'ai-logo.png',{type:d.mime}));message('AI Logo 已生成到草稿，发布后顾客可见');});
  document.querySelectorAll('[data-category-preset]').forEach(select=>select.onchange=()=>{const n=Number(select.dataset.categoryPreset),input=$(`[data-edit=category][data-n="${n}"]`);if(select.value==='custom'){input.focus();input.select();return;}draft[n].category=select.value;input.value=select.value;draft[n].checked=false;updateRow(n);});
  document.querySelectorAll('[data-theme-id]').forEach(b=>b.onclick=()=>{brand.theme=b.dataset.themeId;dirty=true;render();message('风格已选择，保存草稿或发布后生效');});
  document.querySelectorAll('[data-edit]').forEach(input=>{
    const change=()=>{const n=Number(input.dataset.n),key=input.dataset.edit;draft[n][key]=input.type==='checkbox'?input.checked:key==='price'?(input.value===''?null:Number(input.value)):input.value;
      if(key==='category'){const preset=$(`[data-category-preset="${n}"]`);if(preset)preset.value=CATEGORY_PRESETS.includes(input.value)?input.value:'custom';}if(key!=='checked')draft[n].checked=false;updateRow(n);};
    input.addEventListener(input.type==='checkbox'?'change':'input',change);
  });
  document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>{let n=Number(b.dataset.delete);removed={item:draft[n],n};draft.splice(n,1);dirty=true;render();});
  bindAction('#undo',()=>{draft.splice(removed.n,0,removed.item);removed=null;dirty=true;render();});
  bindAction('#add',()=>{if(draft.length>=100)throw Error('最多添加 100 道菜');draft.push({id:uid(),name:'',price:null,category:'其他',checked:false,available:true,confidence:null});dirty=true;render();$('[data-row="'+(draft.length-1)+'"] input').focus();});
  bindAction('#checkAll',()=>{let skipped=0;draft.forEach(i=>{if(i.name&&i.price!=null)i.checked=true;else skipped++;});dirty=true;render();message(skipped?`已勾选 ${draft.length-skipped} 道；还有 ${skipped} 道缺少菜名或价格，请补充后再勾选`:'全部菜品已标记为已检查');});
  bindAction('#saveDraft',async()=>{if(photoUploads.size||logoUploading)throw Error('请等待图片上传完成');const d=await api('merchant/draft',payload());store=d.store;draft=store.draft;draftName=store.draft_name;brand=store.brand_draft;dirty=false;message('草稿已保存，刷新后可以继续编辑');render();});
  const form=$('#menuForm');if(form)form.onsubmit=async e=>{e.preventDefault();try{await saveDraft();moveStage(3);}catch(e){fail(e);}};
  bindAction('#uploadAgain',()=>{showImport=true;stage=2;render();});
  bindAction('#editPublished',()=>{draft=structuredClone(store.draft.length?store.draft:store.items);stage=2;showImport=false;warning='';dirty=false;render();});
  bindAction('#newPhoto',()=>{showImport=true;stage=2;render();});
  bindAction('#copy',async()=>{try{await navigator.clipboard.writeText(publicLink());message('点单链接已复制');}catch{$('#shareLink').focus();$('#shareLink').select();message('浏览器无法自动复制，已选中链接，请手动复制。');}});
}
async function start() {if(!await session('merchant'))return;const data=await api('merchant/store');store=data.store;ocr=data.ocr;publicURL=data.public_url;try{imageLibrary=(await api('image-library')).images;}catch{imageLibrary=[];}draft=store.draft.map(i=>{const live=store.items.find(v=>v.id===i.id);return live&&!i.stock_update?{...i,stock:live.stock}:i;});sourceID=store.source_id;draftName=store.draft_name||store.name;brand=store.brand_draft||store.brand;if(!store.published&&!draft.length&&!brand.logo_url)brand.theme='universal';config=store.config_draft;aiLogoConfigured=data.ai_logo_configured;stage=Math.max(1,stageNames.indexOf(location.hash.slice(1))+1);showImport=!draft.length;render();}
window.addEventListener('hashchange',async()=>{const n=stageNames.indexOf(location.hash.slice(1));if(n>=0){try{await saveDraft();stage=n+1;render();$('#app').focus();}catch(e){history.replaceState(null,'','#'+stageNames[stage-1]);fail(e);}}});
start().catch(e=>{$('#app').innerHTML=`<section class="panel empty"><h1>暂时无法打开小店</h1><p>${esc(e.message)}</p><a href="/merchant/menu">重新加载</a></section>`;});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
