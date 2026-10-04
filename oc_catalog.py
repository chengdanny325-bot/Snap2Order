"""Built-in OC mascot shop catalog: fixed decorations and actions priced in member points."""

DECORATIONS = {
    'hat':     {'kind': 'decoration', 'name': '绅士礼帽', 'price': 50,  'asset': '/assets/oc/hat.svg',     'asset_png': '/assets/oc/hat.png'},
    'bow':     {'kind': 'decoration', 'name': '蝴蝶结',   'price': 30,  'asset': '/assets/oc/bow.svg',     'asset_png': '/assets/oc/bow.png'},
    'glasses': {'kind': 'decoration', 'name': '圆框眼镜', 'price': 40,  'asset': '/assets/oc/glasses.svg', 'asset_png': '/assets/oc/glasses.png'},
    'scarf':   {'kind': 'decoration', 'name': '红围巾',   'price': 60,  'asset': '/assets/oc/scarf.svg',   'asset_png': '/assets/oc/scarf.png'},
    'crown':   {'kind': 'decoration', 'name': '小皇冠',   'price': 120, 'asset': '/assets/oc/crown.svg',   'asset_png': '/assets/oc/crown.png'},
    'apron':   {'kind': 'decoration', 'name': '店主围裙', 'price': 80,  'asset': '/assets/oc/apron.svg',   'asset_png': '/assets/oc/apron.png'},
}

ACTIONS = {
    'jump':  {'kind': 'action', 'name': '开心跳跃', 'price': 40,  'animation': 'oc-anim-jump'},
    'spin':  {'kind': 'action', 'name': '原地转圈', 'price': 40,  'animation': 'oc-anim-spin'},
    'wave':  {'kind': 'action', 'name': '招手问好', 'price': 60,  'animation': 'oc-anim-wave'},
    'dance': {'kind': 'action', 'name': '庆祝舞蹈', 'price': 100, 'animation': 'oc-anim-dance'},
}


def find(item_id):
    if not isinstance(item_id, str):
        return None
    return DECORATIONS.get(item_id) or ACTIONS.get(item_id)


def catalog():
    return {'decorations': [{'id': key, **value} for key, value in DECORATIONS.items()],
            'actions': [{'id': key, **value} for key, value in ACTIONS.items()]}
