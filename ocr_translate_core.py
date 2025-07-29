import pytesseract
import requests

# 设置语言（只保留你需要识别的语言）
OCR_LANG = 'eng'
overlay_windows = []
last_texts = []

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

# # 创建悬浮窗显示翻译
# def show_translation_window(root, x, y, text):
#     win = tk.Toplevel(root)
#     win.overrideredirect(True)
#     win.attributes("-topmost", True)
#     win.attributes("-alpha", 0.85)
#     win.configure(bg="black")
#     label = tk.Label(win, text=text, fg="white", bg="black", font=("Microsoft YaHei", 12))
#     label.pack()
#     win.geometry(f"+{x}+{y}")
#     win.lift()
#     return win
#
# cap = cv2.VideoCapture(2)
#
# # 主检测循环
# def monitor_loop(root):
#     global cap
#     overlay_windows = []
#
#     while True:
#         time.sleep(1)
#         ret, frame = cap.read()
#         if not ret:
#             print("摄像头读取失败")
#             time.sleep(1)
#             continue
#         cv2.imwrite("debug_frame.png", frame)
#
#         # 转换为 PIL 图像
#         frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#         pil_img = Image.fromarray(frame_rgb)
#         image_width, image_height = pil_img.size
#
#         blocks = get_text_blocks(pil_img)
#         texts = [b['text'] for b in blocks]
#
#         global last_texts
#         if texts == last_texts:
#             continue
#         last_texts = texts.copy()  # 保存本轮内容
#
#         translations = translate_batch(texts)
#         print(translations)
#
#         root.after(0, update_translations, root, blocks, translations, image_width, image_height)
#
#         time.sleep(1.0)
#
#
# def update_translations(root, blocks, translations, image_width, image_height):
#     global overlay_windows
#
#     # 获取主屏幕尺寸
#     screen = NSScreen.mainScreen()
#     screen_width = int(screen.frame().size.width)
#     screen_height = int(screen.frame().size.height)
#
#
#     scale_x = screen_width / image_width
#     scale_y = screen_height / image_height
#
#     def is_overlapping(x1, y1, w1, h1, zones):
#         for x2, y2, w2, h2 in zones:
#             if (x1 < x2 + w2 and x1 + w1 > x2 and
#                     y1 < y2 + h2 and y1 + h1 > y2):
#                 return True
#         return False
#
#     # 清除旧窗口
#     for win in overlay_windows:
#         win.destroy()
#     overlay_windows.clear()
#
#     occupied_zones = []
#
#     for block, translation in zip(blocks, translations):
#         x = int(block['left'] * scale_x)
#         y = int(block['top'] * scale_y)
#         w = int(block['width'] * scale_x)
#         h = int(block['height'] * scale_y)
#
#         # 避开原文上方，且不出屏幕
#         y = max(y - 40, 0)
#
#         # 避免重叠
#         while is_overlapping(x, y, w, h, occupied_zones):
#             y += 50
#             if y > screen_height - h:
#                 break
#
#         # 限制不超出屏幕边界
#         x = min(x, screen_width - w - 10)
#         y = min(y, screen_height - h - 10)
#
#         clean_translation = translation.strip().replace("\n\n", "\n")
#         win = show_translation_window(root, x, y, clean_translation)
#         overlay_windows.append(win)
#         occupied_zones.append((x, y, w, h))
#
# # 启动主窗口
# def main():
#     root = tk.Tk()
#     root.withdraw()  # 隐藏主窗口
#     t = threading.Thread(target=monitor_loop, args=(root,), daemon=True)
#     t.start()
#     root.mainloop()
#     cap.release()
#
# if __name__ == "__main__":
#     main()
