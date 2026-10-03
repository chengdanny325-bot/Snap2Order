"""Validated, versioned storefront configuration and optional model generation."""
import json
import os
import urllib.request
from decimal import Decimal, InvalidOperation

MODULES = ('ordering', 'membership', 'coupons', 'wheel', 'oc')
THEMES = ('universal', 'western', 'hotpot', 'fresh', 'minimal', 'vibrant', 'classic', 'cute', 'luxury')

def short(value, maximum):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError('资料长度或格式不正确')
    return value.strip()

def amount(value, maximum=999999):
    try:
        if isinstance(value, bool): raise ValueError()
        n = Decimal(str(value)) * 100
        if not n.is_finite() or n != n.to_integral_value() or not 0 <= n <= maximum: raise ValueError()
        return int(n)
    except (ValueError, InvalidOperation):
        raise ValueError('金额须为非负数，最多两位小数')

def points_count(value, label, maximum=100000):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError(label+'须为 0～'+str(maximum)+' 的整数')
    return value

def normalize(raw):
    raw = raw or {}
    if not isinstance(raw, dict): raise ValueError('门店配置格式错误')
    profile = raw.get('profile') or {}
    if not isinstance(profile, dict): raise ValueError('店铺资料格式错误')
    profile = {key: short(profile.get(key, ''), length) for key, length in
               [('description', 500), ('address', 200), ('hours', 100), ('phone', 40), ('business', 1000)]}
    banner = raw.get('banner_url') or None
    if banner is not None and (not isinstance(banner, str) or not banner.startswith('/api/dish-images/')):
        raise ValueError('请上传店铺封面')
    modules = raw.get('modules', {'ordering': True})
    if not isinstance(modules, dict) or any(key not in MODULES for key in modules): raise ValueError('模块配置错误')
    if any(not isinstance(value, bool) for value in modules.values()): raise ValueError('模块开关须为布尔值')
    layout = raw.get('layout', 'grid')
    if layout not in ('grid', 'list'): raise ValueError('请选择支持的菜单布局')
    coupon = raw.get('coupon') or {}
    if not isinstance(coupon, dict): raise ValueError('优惠券配置错误')
    value = amount(coupon.get('amount', 5), 100000) / 100
    threshold = amount(coupon.get('minimum', 30), 999999) / 100
    if modules.get('coupons') or modules.get('wheel'):
        if value <= 0 or threshold <= value: raise ValueError('优惠金额须大于零，使用门槛须高于优惠金额')
    points = raw.get('points') or {}
    if not isinstance(points, dict): raise ValueError('积分规则格式错误')
    if any(key not in ('per_spend', 'earn', 'register_bonus', 'checkin', 'daka') for key in points): raise ValueError('积分规则格式错误')
    per_spend = amount(points.get('per_spend', 1), 1000000) / 100
    if modules.get('membership') and per_spend <= 0: raise ValueError('消费积分门槛须大于零')
    points = {'per_spend': per_spend,
              'earn': points_count(points.get('earn', 1), '消费积分'),
              'register_bonus': points_count(points.get('register_bonus', 0), '注册赠送积分'),
              'checkin': points_count(points.get('checkin', 1), '签到积分'),
              'daka': points_count(points.get('daka', 2), '打卡积分')}
    oc = raw.get('oc') or {}
    if not isinstance(oc, dict): raise ValueError('OC 配置格式错误')
    oc_image = oc.get('image_url') or None
    if oc_image is not None and (not isinstance(oc_image, str) or not oc_image.startswith('/api/oc-images/')):
        raise ValueError('请先生成 OC 形象')
    oc = {'name': short(oc.get('name', ''), 30), 'description': short(oc.get('description', ''), 500), 'image_url': oc_image}
    if modules.get('oc') and not oc['image_url']: raise ValueError('启用 OC 模块前请先生成 OC 形象')
    if modules.get('oc') and not modules.get('membership'): raise ValueError('OC 装扮使用会员积分，请同时开启会员积分模块')
    return {'version': 1, 'profile': profile, 'banner_url': banner, 'layout': layout,
            'modules': {key: modules.get(key, key == 'ordering') for key in MODULES},
            'coupon': {'amount': value, 'minimum': threshold}, 'points': points, 'oc': oc}

def item_details(item):
    stock = item.get('stock')
    if stock is not None and (isinstance(stock, bool) or not isinstance(stock, int) or not 0 <= stock <= 99999):
        raise ValueError('库存须为 0～99999 的整数，留空表示不限量')
    groups = item.get('options') or []
    if not isinstance(groups, list) or len(groups) > 6: raise ValueError('最多设置六组规格')
    result = []
    for group in groups:
        if not isinstance(group, dict): raise ValueError('规格格式错误')
        name = short(group.get('name', ''), 30)
        choices = group.get('choices')
        if not name or not isinstance(choices, list) or not 1 <= len(choices) <= 12: raise ValueError('规格须填写名称和 1～12 个选项')
        normalized = []
        for choice in choices:
            if not isinstance(choice, dict): raise ValueError('规格选项格式错误')
            label = short(choice.get('name', ''), 30)
            if not label or any(c['name'] == label for c in normalized): raise ValueError('规格选项名称不能为空或重复')
            normalized.append({'name': label, 'extra': amount(choice.get('extra', 0), 100000) / 100})
        if any(g['name'] == name for g in result): raise ValueError('规格组名称不能重复')
        result.append({'name': name, 'choices': normalized})
    return {'description': short(item.get('description', ''), 200), 'stock': stock, 'options': result}

def recommendation(description, images=None):
    """No API key: honestly identified rules. Configured model: validated JSON only."""
    description = short(description, 1000)
    if not description: raise ValueError('请先描述业态、客群和经营目标')
    theme = 'cute' if any(w in description for w in ('奶茶', '甜品', '可爱')) else 'classic' if any(w in description for w in ('中式', '面馆', '传统')) else 'minimal' if '咖啡' in description else 'fresh'
    modules = {'ordering': True, 'membership': any(w in description for w in ('复购', '会员', '熟客')),
               'coupons': any(w in description for w in ('优惠', '拉新', '促销')), 'wheel': any(w in description for w in ('抽奖', '转盘', '活动'))}
    fallback = {'theme': theme, 'modules': modules, 'description': description[:200],
                'reason': '根据业态关键词选择主题，根据经营目标推荐模块；可继续手动修改。', 'source': 'rules'}
    key = os.getenv('STORE_AI_API_KEY', '')
    if not key: return fallback
    endpoint = os.getenv('STORE_AI_API_URL', 'https://api.openai.com/v1/chat/completions')
    if not endpoint.startswith('https://'): raise ValueError('AI 服务地址须使用 HTTPS')
    prompt = '为餐饮商家建议门店配置。只输出 JSON：theme（fresh/minimal/vibrant/classic/cute/luxury），modules（ordering/membership/coupons/wheel 布尔值），description（中文品牌介绍），reason（中文推荐理由）。经营描述：' + description
    content = [{'type': 'text', 'text': prompt}] + [{'type': 'image_url', 'image_url': {'url': image}} for image in (images or [])]
    payload = {'model': os.getenv('STORE_AI_MODEL', 'gpt-4o-mini'), 'messages': [{'role': 'user', 'content': content}], 'max_tokens': 600}
    try:
        req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
        import tls_support
        with urllib.request.urlopen(req, timeout=25, context=tls_support.context()) as response:
            data = json.load(response)
        response_text = data['choices'][0]['message']['content'].strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
        result = json.loads(response_text)
        if result.get('theme') not in THEMES: raise ValueError()
        config = normalize({'modules': result.get('modules')})
        return {'theme': result['theme'], 'modules': config['modules'], 'description': short(result.get('description', ''), 500), 'reason': short(result.get('reason', ''), 500), 'source': 'model'}
    except Exception:
        fallback['reason'] = 'AI 服务暂时不可用，已改用规则推荐。请核对后应用。'
        fallback['fallback'] = True
        return fallback

def logo_configured():
    return bool((os.getenv('AI_LOGO_API_KEY') or os.getenv('STORE_AI_API_KEY')) and os.getenv('AI_LOGO_API_URL') and os.getenv('AI_LOGO_MODEL'))

def generate_oc(name, description):
    """Mascot image generation; shares the AI_LOGO_* image service configuration."""
    import base64
    import dish_media
    import tls_support
    if not logo_configured():
        raise ValueError('OC 生成尚未配置，请设置 AI_LOGO_API_KEY、AI_LOGO_API_URL、AI_LOGO_MODEL（与 AI Logo 共用图像服务）。也可暂时关闭 OC 模块。')
    name = short(name, 30)
    description = short(description, 500)
    if not description: raise ValueError('请先描述 OC 形象，例如：一只橘色小猫，圆圆的眼睛，性格活泼')
    endpoint = os.getenv('AI_LOGO_API_URL', '')
    if not endpoint.startswith('https://'): raise ValueError('图像生成服务地址须使用 HTTPS')
    key = os.getenv('AI_LOGO_API_KEY') or os.getenv('STORE_AI_API_KEY')
    payload = {'model': os.getenv('AI_LOGO_MODEL'), 'n': 1, 'size': '1024x1024',
               'prompt': 'Full-body mascot character for a small restaurant, standing pose, centered, plain solid light background. Character: '+description+'. Name: '+name+'. Cute, friendly, clean vector-like rendering. Keep clear space above the head and around the neck so accessories can be added later. No text, no mockup scenes.'}
    try:
        request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=120, context=tls_support.context()) as response:
            body = response.read(20*1024*1024+1)
        if len(body)>20*1024*1024: raise ValueError()
        result = json.loads(body)
        encoded = result['data'][0]['b64_json']
        raw = base64.b64decode(encoded, validate=True)
        mime = dish_media.raster_type(raw,'OC 形象',max_bytes=12*1024*1024)
        return {'image':raw, 'mime':mime}
    except Exception:
        raise ValueError('OC 生成失败。请检查图像模型配置；接口需返回 PNG/JPEG 的 b64_json。原形象保留，可重试。') from None

def generate_logo(name, theme, prompt):
    """Image-generations adapter. The browser compresses and uploads the returned raster."""
    import base64
    import dish_media
    import tls_support
    if not logo_configured():
        raise ValueError('AI Logo 尚未配置，请设置 AI_LOGO_API_KEY、AI_LOGO_API_URL、AI_LOGO_MODEL。仍可手动上传。')
    name = short(name, 50)
    prompt = short(prompt, 500)
    if not name: raise ValueError('请先填写店铺名称')
    if theme not in THEMES: raise ValueError('品牌风格无效')
    endpoint = os.getenv('AI_LOGO_API_URL', '')
    if not endpoint.startswith('https://'): raise ValueError('图像生成服务地址须使用 HTTPS')
    key = os.getenv('AI_LOGO_API_KEY') or os.getenv('STORE_AI_API_KEY')
    payload = {'model': os.getenv('AI_LOGO_MODEL'), 'n': 1, 'size': '1024x1024',
               'prompt': 'Design a clean, professional restaurant logo for '+name+'. Visual direction: '+theme+'. '+prompt+'. Centered emblem, generous whitespace, simple background. Avoid intricate lettering and mockup scenes.'}
    try:
        request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=120, context=tls_support.context()) as response:
            body = response.read(20*1024*1024+1)
        if len(body)>20*1024*1024: raise ValueError()
        result = json.loads(body)
        encoded = result['data'][0]['b64_json']
        raw = base64.b64decode(encoded, validate=True)
        mime = dish_media.raster_type(raw,'AI Logo',max_bytes=12*1024*1024)
        return {'image_base64':base64.b64encode(raw).decode(), 'mime':mime}
    except Exception:
        raise ValueError('Logo 生成失败。请检查图像模型配置；接口需返回 PNG/JPEG 的 b64_json。原 Logo 保留，可重试或手动上传。') from None
