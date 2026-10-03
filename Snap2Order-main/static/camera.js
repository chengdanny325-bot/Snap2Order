'use strict';
let cameraStream=null;
function closeCamera(){if(cameraStream){cameraStream.getTracks().forEach(t=>t.stop());cameraStream=null;}const dialog=$('#cameraDialog');if(dialog?.open)dialog.close();dialog?.remove();}
function openMenuCamera(onPhoto){
 closeCamera();
 const dialog=document.createElement('dialog');dialog.id='cameraDialog';dialog.className='camera-dialog';dialog.setAttribute('aria-labelledby','cameraTitle');
 dialog.innerHTML='<h2 id="cameraTitle">拍下菜单</h2><p>点击下方按钮后，浏览器会请求相机权限。仅用于拍菜单，不录音；照片确认后才上传。</p><video id="cameraVideo" autoplay muted playsinline></video><p id="cameraError" class="form-error" role="status"></p><div class="actions"><button type="button" class="primary" id="allowCamera">开启相机</button><button type="button" class="primary" id="takePhoto" disabled>拍摄菜单</button><button type="button" id="closeCamera">关闭</button></div><div class="caption"><label class="button">改用系统相机<input id="systemCamera" class="file-cover" type="file" accept="image/*" capture="environment" aria-label="改用系统相机"></label><p>如权限已被拒绝，请在浏览器或微信的应用设置中允许相机，或关闭后从相册选择。</p></div>';
 document.body.append(dialog);dialog.addEventListener('close',closeCamera,{once:true});dialog.showModal();
 $('#closeCamera').onclick=closeCamera;
 $('#systemCamera').onchange=async e=>{const file=e.target.files[0];if(file){closeCamera();try{await onPhoto(file);}catch(err){fail(err);}}};
 $('#allowCamera').onclick=()=>action($('#allowCamera'),async()=>{
  const error=$('#cameraError');error.textContent='';
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){error.textContent='当前环境不能直接调用相机。请使用 HTTPS 打开，或点击“改用系统相机”。';return;}
  try{
   const grantedStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
   if(!dialog.isConnected||document.hidden){grantedStream.getTracks().forEach(t=>t.stop());return;}
   cameraStream=grantedStream;
   const video=$('#cameraVideo');video.srcObject=cameraStream;await video.play();$('#takePhoto').disabled=false;
   $('#allowCamera').hidden=true;error.textContent='相机已开启，请让菜名与价格完整入镜。';
  }catch(e){error.textContent=e.name==='NotAllowedError'?'相机权限未获允许。请在应用设置中开启权限，或从相册选择菜单。':e.name==='NotFoundError'?'未找到摄像头，请使用相册上传。':'相机暂不可用，可能被其他应用占用。请使用系统相机或相册。';}
 });
 $('#takePhoto').onclick=()=>action($('#takePhoto'),async()=>{const video=$('#cameraVideo');if(!video.videoWidth)throw Error('相机画面尚未准备好，请稍候。');const canvas=document.createElement('canvas');canvas.width=video.videoWidth;canvas.height=video.videoHeight;canvas.getContext('2d').drawImage(video,0,0);const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.92));closeCamera();if(blob)await onPhoto(blob);});
}
window.addEventListener('pagehide',closeCamera);
