'use strict';
let store, ocr, publicURL='', stage=1, draft=[], sourceID=null, preview='', uploadBlob=null, busy=false, warning='',dirty=false,removed=null;
let imageLibrary=[];
const photoUploads=new Set();
const sampleRows=[['招牌牛肉面',28,'主食'],['番茄鸡蛋面',18,'主食'],['红油抄于',16,'小吃'],['凉拌黄瓜',12,'小吃'],['酸梅汤',6,'饮品'],['冰豆浆',5,'饮品']];
function sample() {return sampleRows.map((r,n)=>({id:uid(),name:r[0],price:r[1],category:r[2],checked:false,available:true,confidence:n===2?.42:.95}));}
function sourceImage() {return preview || (sourceID?'/api/merchant/sources/'+sourceID:'');}
function publicLink() {return (publicURL||location.origin)+'/s/'+store.id;}
function render() {
  header('merchant');
  $('#app').innerHTML=heading('MY MENU','让纸上的菜单，开始接单。','你的店铺、菜单和订单，只属于你的账号。')+`<div class="steps"><span class="${stage===1?'current':''}">01 拍下菜单</span><span class="${stage===2?'current':''}">02 检查菜品</span><span class="${stage===3?'current':''}">03 分享小店</span></div>`+(stage===1?uploadView():stage===2?editView():publishedView());
  bind();
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

function editRow(i,n) {return `<article class="item-edit ${i.checked?'':'needs-check'}" data-row="${n}"><div class="item-title"><b>菜品 ${String(n+1).padStart(2,'0')}</b><span class="check-state">${i.checked?'✓ 已确认':i.price===null?'价格未识别，请填写':i.confidence!=null&&i.confidence<.8?'识别不确定，请检查':'请检查后确认'}</span></div><label>菜名<input data-edit="name" data-n="${n}" value="${esc(i.name)}" maxlength="80" required></label><label>价格（元）<input type="number" data-edit="price" data-n="${n}" value="${i.price===null?'':i.price}" min="0.01" max="9999.99" step="0.01" required inputmode="decimal"></label><label>分类<input data-edit="category" data-n="${n}" value="${esc(i.category)}" maxlength="30" required list="categories"></label>${dishPhotoEditor(i,n)}<div class="options"><label><input type="checkbox" data-edit="available" data-n="${n}" ${i.available?'checked':''}> 上架</label><label><input type="checkbox" data-edit="checked" data-n="${n}" ${i.checked?'checked':''}> 已检查</label><button type="button" class="quiet danger" data-delete="${n}" aria-label="删除${esc(i.name||'菜品'+(n+1))}">删除</button></div></article>`;}
function editView() {return `<section class="panel"><div class="row"><h2>检查一下，就可以开店了</h2><button type="button" id="uploadAgain">重新选图</button></div><p>核对每道菜，再勾选“已检查”。修改内容后需要重新确认。</p>${warning?`<div class="warn">${esc(warning)}</div>`:''}<form id="menuForm"><label>店铺名称<input id="storeName" value="${esc(store.name)}" maxlength="50" required autocomplete="organization"></label><datalist id="categories"><option value="主食"><option value="小吃"><option value="饮品"><option value="其他"></datalist><div class="layout editor-layout"><div><div id="rows">${draft.map(editRow).join('')}</div>${draft.length?'':'<p class="empty">还没有菜品，点击下方添加。</p>'}${removed?'<button type="button" id="undo">撤销刚才的删除</button>':''}<div class="actions"><button type="button" id="add">＋ 添加一道菜</button><button type="button" id="saveDraft">保存草稿</button><button type="submit" class="primary" id="publish">确认并发布菜单 →</button></div><p id="saveState" class="hint">${dirty?'有未保存的修改':'草稿已保存'}</p></div><aside class="source-panel"><h3>对照菜单原图</h3>${sourceImage()?`<img src="${esc(sourceImage())}" alt="当前店铺的菜单原图，用于检查菜名价格">`:'<p>当前为手动录入或演示菜单，没有原图。</p>'}<p class="hint">每道菜可上传实拍、选择插画素材，或暂不放图。图片修改保存为草稿，发布后才会展示给顾客。</p></aside></div></form></section>`;}
function publishedView() {return `<section class="panel published"><div class="good">✓ 菜单已发布，${esc(store.name)}准备好了</div><h2>把你的小店，分享给顾客。</h2><p>每家店都有固定的二维码和独立链接，顾客扫码后直接点餐。</p><div class="qr-share"><div><img class="store-qr" src="/api/merchant/qrcode" alt="当前店铺的专属点单二维码"><p class="hint">扫码进入这家店 · 无需顾客注册</p><a class="button" href="/api/merchant/qrcode" download="店铺点单二维码.svg">下载点单二维码</a></div><div><label>店铺专属点单链接<input id="shareLink" value="${esc(publicLink())}" readonly></label><div class="actions"><a class="button primary" href="${esc(publicLink())}" target="_blank" rel="noopener">打开顾客点餐页 ↗</a><button id="copy">复制链接</button><a class="button" href="/merchant/orders">去接单工作台</a></div></div></div><p class="caption">已上架 ${store.items.filter(i=>i.available).length} 道菜。修改菜单不会改变点单链接和二维码。手机扫码需要使用已部署的公网域名。</p>${publicLink().includes('localhost')||publicLink().includes('127.0.0.1')?'<p class="warn">当前二维码指向本机地址，其他手机无法访问。部署后设置 PUBLIC_URL，或本地测试时用电脑局域网 IP 打开商家页再生成二维码。</p>':''}<button id="editPublished">编辑菜单</button><button id="newPhoto">拍一张新菜单</button></section>`;}
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
    try {const d=await api('merchant/ocr',uploadBlob,{raw:true});draft=d.items;sourceID=d.source_id;warning='识别结果已按菜名和价格配对，请逐项核对；不确定的内容可手动修改。';stage=2;dirty=false;}
    catch(e) {warning=e.message;if(e.data?.source_id)sourceID=e.data.source_id;}
    finally {busy=false;render();}
  });
  bindAction('#manual',()=>{draft=[{id:uid(),name:'',price:null,category:'其他',checked:false,available:true,confidence:null}];stage=2;warning='';dirty=true;render();});
  bindAction('#sample',()=>{draft=sample();sourceID=null;preview='';stage=2;warning='这是演示数据，不是真实识别结果。“红油抄于”特意保留了一个错误，请修正为“红油抄手”。';dirty=true;render();});
  document.querySelectorAll('[data-photo-file]').forEach(input=>input.onchange=()=>{
    const item=draft[Number(input.dataset.photoFile)];
    if(input.files[0])uploadDishPhoto(item,input.files[0]).catch(fail);
  });
  document.querySelectorAll('[data-photo-library]').forEach(b=>b.onclick=()=>openImageLibrary(draft[Number(b.dataset.photoLibrary)],b));
  document.querySelectorAll('[data-photo-camera]').forEach(b=>b.onclick=()=>openMenuCamera(file=>uploadDishPhoto(draft[Number(b.dataset.photoCamera)],file)));
  document.querySelectorAll('[data-photo-none]').forEach(b=>b.onclick=()=>{const item=draft[Number(b.dataset.photoNone)];item.image_url=null;dirty=true;render();message('已设为暂不放图，保存或发布后生效');});
  const name=$('#storeName');if(name)name.oninput=()=>{store.name=name.value;dirty=true;$('#saveState').textContent='有未保存的修改';};
  document.querySelectorAll('[data-edit]').forEach(input=>{
    const change=()=>{const n=Number(input.dataset.n),key=input.dataset.edit;draft[n][key]=input.type==='checkbox'?input.checked:key==='price'?(input.value===''?null:Number(input.value)):input.value;
      if(key!=='checked')draft[n].checked=false;updateRow(n);};
    input.addEventListener(input.type==='checkbox'?'change':'input',change);
  });
  document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>{let n=Number(b.dataset.delete);removed={item:draft[n],n};draft.splice(n,1);dirty=true;render();});
  bindAction('#undo',()=>{draft.splice(removed.n,0,removed.item);removed=null;dirty=true;render();});
  bindAction('#add',()=>{if(draft.length>=100)throw Error('最多添加 100 道菜');draft.push({id:uid(),name:'',price:null,category:'其他',checked:false,available:true,confidence:null});dirty=true;render();$('[data-row="'+(draft.length-1)+'"] input').focus();});
  bindAction('#saveDraft',async()=>{if(photoUploads.size)throw Error('请等待菜品照片上传完成');const d=await api('merchant/draft',{name:store.name,items:draft,source_id:sourceID});store=d.store;draft=store.draft;dirty=false;message('草稿已保存，刷新后可以继续编辑');render();});
  const form=$('#menuForm');if(form)form.onsubmit=async e=>{e.preventDefault();await action($('#publish'),async()=>{
    if(photoUploads.size)throw Error('请等待菜品照片上传完成');
    if(draft.some(i=>!i.checked)){const row=document.querySelector('[data-edit=checked]:not(:checked)');row?.focus();throw Error('请检查每道菜后勾选“已检查”');}
    const d=await api('merchant/publish',{name:store.name,items:draft,source_id:sourceID});store=d.store;stage=3;dirty=false;render();message('菜单已发布');
  });};
  bindAction('#uploadAgain',()=>{stage=1;render();});
  bindAction('#editPublished',()=>{draft=structuredClone(store.draft.length?store.draft:store.items);stage=2;warning='';dirty=false;render();});
  bindAction('#newPhoto',()=>{stage=1;render();});
  bindAction('#copy',async()=>{try{await navigator.clipboard.writeText(publicLink());message('点单链接已复制');}catch{$('#shareLink').focus();$('#shareLink').select();message('浏览器无法自动复制，已选中链接，请手动复制。');}});
}
async function start() {if(!await session('merchant'))return;const data=await api('merchant/store');store=data.store;ocr=data.ocr;publicURL=data.public_url;try{imageLibrary=(await api('image-library')).images;}catch{imageLibrary=[];}draft=store.draft;sourceID=store.source_id;stage=store.published?3:draft.length?2:1;render();}
start().catch(e=>{$('#app').innerHTML=`<section class="panel empty"><h1>暂时无法打开小店</h1><p>${esc(e.message)}</p><a href="/merchant/menu">重新加载</a></section>`;});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
