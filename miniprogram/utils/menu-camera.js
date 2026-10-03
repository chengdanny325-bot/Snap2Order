// Native merchant camera adapter. Call from a user-initiated button tap.
async function takeMenuPhoto(){
 if(wx.requirePrivacyAuthorize)await new Promise((resolve,reject)=>wx.requirePrivacyAuthorize({success:resolve,fail:reject}));
 try{const result=await new Promise((resolve,reject)=>wx.chooseMedia({count:1,mediaType:['image'],sourceType:['camera'],camera:'back',success:resolve,fail:reject}));return result.tempFiles[0].tempFilePath;}
 catch(e){if(String(e.errMsg).includes('cancel'))return null;
  wx.showModal({title:'相机暂不可用',content:'可以从相册选择菜单。若相机权限被拒绝，请在微信或系统设置中允许相机访问。',confirmText:'查看设置',success:r=>{if(r.confirm){if(wx.openAppAuthorizeSetting)wx.openAppAuthorizeSetting({});else wx.openSetting({});}}});
  throw new Error('无法拍摄菜单，可改用相册。');
 }
}
async function chooseMenuPhoto(){const result=await new Promise((resolve,reject)=>wx.chooseMedia({count:1,mediaType:['image'],sourceType:['album'],success:resolve,fail:reject}));return result.tempFiles[0].tempFilePath;}
module.exports={takeMenuPhoto,chooseMenuPhoto};
