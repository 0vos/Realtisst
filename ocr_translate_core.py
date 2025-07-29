import pytesseract
import requests
import Quartz
import AppKit
from Cocoa import NSEvent

# 设置语言（只保留你需要识别的语言）
OCR_LANG = 'eng'
overlay_windows = []
last_texts = []
def global_key_listener(manager):
    def tap_callback(proxy, type_, event, refcon):
        if type_ != Quartz.kCGEventKeyDown:
            return event

        keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)

        # 检测是否按住 command 和 control
        command_pressed = (flags & Quartz.kCGEventFlagMaskCommand) != 0
        control_pressed = (flags & Quartz.kCGEventFlagMaskControl) != 0

        # keycode 16 是 y，4 是 h
        if command_pressed and control_pressed and (keycode == 16 or keycode == 4):
            # 这里触发你想要的动作
            manager.trigger_action(keycode)
            return None  # 阻止事件传递

        return event

    event_mask = (1 << Quartz.kCGEventKeyDown)
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        event_mask,
        tap_callback,
        None
    )

    run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    loop = Quartz.CFRunLoopGetCurrent()
    Quartz.CFRunLoopAddSource(loop, run_loop_source, Quartz.kCFRunLoopDefaultMode)
    Quartz.CGEventTapEnable(tap, True)
    Quartz.CFRunLoopRun()

def translate_batch(text_list):
    if not text_list:
        return []

    url = "http://127.0.0.1:5000/translate"
    results = []
    for text in text_list:
        payload = {
            "q": text if text.strip() else "[空]",
            "source": "auto",
            "target": "zh",
            "format": "text"
        }
        try:
            response = requests.post(url, data=payload)
            result = response.json().get("translatedText", "")
        except Exception as e:
            print("翻译失败：", e)
            result = "[翻译失败]"
        results.append(result)
    return results

# 本地翻译 API 示例（替换为你自己的）
# def translate_ocr(text):
#     url = "http://127.0.0.1:5000/translate"
#     payload = {
#         "q": text,
#         "source": "auto",
#         "target": "zh",
#         "format": "text"
#     }
#     response = requests.post(url, data=payload)
#     print("TRANSLATION: ", response.json()["translatedText"])
#     return response.json()["translatedText"]
#
# print(translate_ocr("Press any key to continue"))

# 获取 OCR 文本 + 位置信息

def get_text_blocks(img, screen_width=None, screen_height=None):
    image_width, image_height = img.size

    # macOS Quartz 截图为 Retina 2x 分辨率，坐标需缩放 0.5
    scale_x = 0.5
    scale_y = 0.5

    data = pytesseract.image_to_data(img, lang=OCR_LANG, output_type=pytesseract.Output.DICT)
    words = []

    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        if text != "" and int(data['conf'][i]) > 60:
            words.append({
                'text': text,
                'left': data['left'][i],
                'top': data['top'][i],
                'width': data['width'][i],
                'height': data['height'][i],
                'right': data['left'][i] + data['width'][i],
                'bottom': data['top'][i] + data['height'][i]
            })

    # 按 top 排序，再按 left 排序
    words.sort(key=lambda w: (w['top'], w['left']))

    paragraphs = []
    current_para = []
    threshold = 40

    for word in words:
        if not current_para:
            current_para.append(word)
            continue

        last_word = current_para[-1]
        vertical_gap = abs(word['top'] - last_word['bottom'])

        if vertical_gap > threshold:
            paragraphs.append(current_para)
            current_para = [word]
        else:
            current_para.append(word)

    if current_para:
        paragraphs.append(current_para)

    # Build a list of tuples with group and top coordinate
    paragraph_with_top = []
    for group in paragraphs:
        if not group:
            continue
        top = min(w['top'] for w in group)
        paragraph_with_top.append((top, group))

    # Sort paragraphs by top coordinate
    paragraph_with_top.sort(key=lambda x: x[0])

    results = []
    for group in paragraphs:
        if not group:
            continue

        # 把这段的坐标和内容一起保存（先不排序）
        full_text = " ".join([w['text'] for w in group])
        # 使用第一个词作为 anchor 显示点
        anchor = group[0]
        left = anchor['left']
        top = anchor['top']
        right = max(w['right'] for w in group)
        bottom = max(w['bottom'] for w in group)

        results.append({
            'text': full_text,
            'left': left * scale_x,
            'top': top * scale_y,
            'width': (right - left) * scale_x,
            'height': (bottom - top) * scale_y,
            'original_top': top
        })

    # ✅ 按原始 top 排序（再也不会丢失映射）
    results.sort(key=lambda b: b['original_top'])

    # ✅ 最后删除辅助字段
    for b in results:
        del b['original_top']

    return results

