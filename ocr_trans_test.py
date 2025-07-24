from PIL import ImageGrab
import pytesseract

img = ImageGrab.grab(bbox=(100, 100, 800, 1000))  # 屏幕区域
text = pytesseract.image_to_string(img, lang="eng")
print(text)