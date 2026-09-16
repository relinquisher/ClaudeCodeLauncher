"""モデルごとのキャラクターアイコンを自動生成するモジュール"""
from PIL import Image, ImageDraw

# モデルID: (表示名, 説明, 本体色, 頬色, 目の色)
MODELS = {
    "opus": {
        "label": "Opus",
        "desc": "最高性能・じっくり思考",
        "body": (155, 89, 214),      # 紫
        "cheek": (230, 190, 255),
        "accent": (255, 215, 0),      # 王冠っぽい金
    },
    "sonnet": {
        "label": "Sonnet",
        "desc": "バランス型・普段使い",
        "body": (255, 140, 66),       # オレンジ
        "cheek": (255, 210, 170),
        "accent": (255, 255, 255),
    },
    "haiku": {
        "label": "Haiku",
        "desc": "高速・軽量",
        "body": (74, 192, 216),       # 水色
        "cheek": (200, 240, 250),
        "accent": (255, 255, 255),
    },
    "fable": {
        "label": "Fable",
        "desc": "最新・物語る者",
        "body": (76, 187, 138),       # 緑
        "cheek": (200, 240, 220),
        "accent": (255, 255, 255),
    },
    "kimi": {
        "label": "KIMI",
        "desc": "Moonshot AI",
        "body": (100, 110, 230),      # Moonshot ブルー
        "cheek": (200, 205, 255),
        "accent": (255, 210, 80),     # 星のようなアクセント
    },
}


def _draw_character(body, cheek, accent, size=160):
    """丸っこい顔キャラを1枚描画してPIL Imageを返す"""
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    margin = int(s * 0.06)
    d.ellipse([margin, margin, s - margin, s - margin], fill=body + (255,))

    # 頭頂のアクセント(星やてっぺんの丸)
    accent_r = int(s * 0.06)
    d.ellipse(
        [s // 2 - accent_r, margin - accent_r // 2,
         s // 2 + accent_r, margin + accent_r],
        fill=accent + (255,),
    )

    # ほっぺ
    cheek_r = int(s * 0.09)
    cy = int(s * 0.62)
    d.ellipse([int(s * 0.18) - cheek_r, cy - cheek_r,
               int(s * 0.18) + cheek_r, cy + cheek_r], fill=cheek + (200,))
    d.ellipse([int(s * 0.82) - cheek_r, cy - cheek_r,
               int(s * 0.82) + cheek_r, cy + cheek_r], fill=cheek + (200,))

    # 目
    eye_r = int(s * 0.055)
    ey = int(s * 0.46)
    for ex in (int(s * 0.36), int(s * 0.64)):
        d.ellipse([ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r],
                   fill=(40, 30, 20, 255))
        hl_r = int(eye_r * 0.35)
        d.ellipse([ex - hl_r, ey - eye_r, ex - hl_r + hl_r * 2,
                   ey - eye_r + hl_r * 2], fill=(255, 255, 255, 255))

    # 口(にっこりカーブ)
    mw = int(s * 0.16)
    my = int(s * 0.62)
    d.arc([s // 2 - mw, my - mw // 2, s // 2 + mw, my + mw],
          start=20, end=160, fill=(60, 40, 30, 255), width=int(s * 0.02))

    return img.resize((size, size), Image.LANCZOS)


def get_avatar(model_id, size=160):
    m = MODELS[model_id]
    return _draw_character(m["body"], m["cheek"], m["accent"], size=size)
