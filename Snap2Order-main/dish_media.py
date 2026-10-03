"""Local illustration library and bounded raster-photo validation."""
import struct
class MediaError(ValueError):
 pass

CATALOG = [
 {'id':'noodles','name':'面食','keywords':['面','粉','拉面','noodle'],'category':'主食'},
 {'id':'rice','name':'米饭与盖饭','keywords':['饭','盖浇','rice'],'category':'主食'},
 {'id':'dumplings','name':'饺子与馄饨','keywords':['饺','馄饨','抄手','dumpling'],'category':'主食'},
 {'id':'salad','name':'凉菜与蔬菜','keywords':['黄瓜','凉拌','蔬菜','沙拉','salad'],'category':'小吃'},
 {'id':'snack','name':'小吃','keywords':['薯条','鸡翅','小吃','炸','snack'],'category':'小吃'},
 {'id':'drink','name':'饮品','keywords':['茶','汤','豆浆','可乐','咖啡','汁','drink','coffee','tea'],'category':'饮品'},
]
for item in CATALOG:
 item['url']='/assets/dishes/'+item['id']+'.png'
STOCK_URLS={i['url'] for i in CATALOG}

def raster_type(raw, label='菜品照片'):
 """Check format, dimensions and basic structure; browsers encode uploads as JPEG."""
 if not 0 < len(raw) <= 2*1024*1024:
  raise MediaError(label + '请小于 2MB。')
 width=height=0
 if raw.startswith(b'\x89PNG\r\n\x1a\n'):
  if len(raw)<33 or raw[12:16]!=b'IHDR' or b'IEND' not in raw[-20:]:
   raise MediaError('PNG 图片不完整，请重新选择。')
  width,height=struct.unpack('>II',raw[16:24]);mime='image/png'
 elif raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9'):
  mime='image/jpeg';p=2
  try:
   while p<len(raw):
    if raw[p]!=255:break
    while raw[p]==255:p+=1
    marker=raw[p];p+=1
    if marker in (0xD8,0xD9) or 0xD0<=marker<=0xD7:continue
    if marker==0xDA:break
    length=int.from_bytes(raw[p:p+2],'big')
    if length<2 or p+length>len(raw):break
    if marker in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF):
     height,width=struct.unpack('>HH',raw[p+3:p+7]);break
    p+=length
  except (IndexError,struct.error):pass
 else:raise MediaError('请上传 JPG 或 PNG 照片，不能上传 SVG 或其他文件。')
 if not 1<=width<=10000 or not 1<=height<=10000 or width*height>40000000:
  raise MediaError('图片尺寸无效或过大，请裁剪后上传。')
 return mime
