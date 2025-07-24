import cv2
import pytesseract
from PIL import Image, ImageTk
import tkinter as tk
import threading
import time
import requests
from collections import defaultdict
# 可调整：截取的区域（屏幕左上角起点 + 宽高）
# REGION = {'left': 100, 'top': 100, 'width': 800, 'height': 400}

# 设置语言（只保留你需要识别的语言）
OCR_LANG = 'eng'
overlay_windows = []
last_texts = []

def translate_batch(text_list):
    if not text_list:
        return []

    clean_texts = [t if t.strip() else "[空]" for t in text_list]  # 防止空串
    sep = "|||+++|||"
    joined = sep.join(clean_texts)
    url = "http://127.0.0.1:5000/translate"
    payload = {
        "q": joined,
        "source": "auto",
        "target": "zh",
        "format": "text"
    }
    response = requests.post(url, data=payload)
    result = response.json()["translatedText"]
    split_result = result.split(sep)

    # 安全检查长度
    if len(split_result) != len(clean_texts):
        print("[⚠️警告] 翻译数量不匹配，正在回退单句翻译")
        return [translate_batch([t])[0] for t in clean_texts]
    return split_result

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
def get_text_blocks(img):
    data = pytesseract.image_to_data(img, lang=OCR_LANG, output_type=pytesseract.Output.DICT)
    lines = defaultdict(list)

    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        if text != "" and int(data['conf'][i]) > 60:
            # 用 (block, paragraph, line) 三元组作为 key 分组
            line_key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
            lines[line_key].append({
                'text': text,
                'left': data['left'][i],
                'top': data['top'][i],
                'width': data['width'][i],
                'height': data['height'][i]
            })
    results = []
    for group in lines.values():
        if not group:
            continue
        full_text = " ".join([w['text'] for w in group])
        left = min(w['left'] for w in group)
        top = min(w['top'] for w in group)
        width = max(w['left'] + w['width'] for w in group) - left
        height = max(w['top'] + w['height'] for w in group) - top
        results.append({
            'text': full_text,
            'left': left,
            'top': top,
            'width': width,
            'height': height
        })
        print(f"OCR LINE: {repr(full_text)} at ({left}, {top})")
    return results

# 创建悬浮窗显示翻译
def show_translation_window(root, x, y, text):
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.attributes("-alpha", 0.85)
    win.configure(bg="black")
    label = tk.Label(win, text=text, fg="white", bg="black", font=("Microsoft YaHei", 12))
    label.pack()
    win.geometry(f"+{x}+{y}")
    win.lift()
    return win

cap = cv2.VideoCapture(2)

# 主检测循环
def monitor_loop(root):
    global cap
    overlay_windows = []

    while True:
        time.sleep(1)
        ret, frame = cap.read()
        if not ret:
            print("摄像头读取失败")
            time.sleep(1)
            continue
        cv2.imwrite("debug_frame.png", frame)

        # 转换为 PIL 图像
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)

        blocks = get_text_blocks(pil_img)
        texts = [b['text'] for b in blocks]

        global last_texts
        if texts == last_texts:
            continue
        last_texts = texts.copy()  # 保存本轮内容

        translations = translate_batch(texts)
        print(translations)

        root.after(0, update_translations, root, blocks, translations)

        time.sleep(1.0)

def update_translations(root, blocks, translations):
    global overlay_windows

    # 清除旧窗口
    for win in overlay_windows:
        win.destroy()
    overlay_windows.clear()

    # 创建新窗口
    for block, translation in zip(blocks, translations):
        x = block['left']
        y = block['top'] - 200
        win = show_translation_window(root, x, y, translation)
        overlay_windows.append(win)

# 启动主窗口
def main():
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    t = threading.Thread(target=monitor_loop, args=(root,), daemon=True)
    t.start()
    root.mainloop()
    cap.release()

if __name__ == "__main__":
    main()
