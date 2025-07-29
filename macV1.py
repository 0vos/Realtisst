import sys
import objc
import time
import threading
import cv2
from objc import selector
from PIL import Image
from AppKit import (
    NSApplication, NSWindow, NSBackingStoreBuffered,
    NSBorderlessWindowMask, NSMakeRect, NSColor, NSTextField,
    NSScreenSaverWindowLevel, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary, NSScreen
)
from Foundation import NSObject, NSAutoreleasePool, NSArray, NSLock
from ocr_translate_core import get_text_blocks, translate_batch


class OverlayManager(NSObject):
    def init(self):
        self = objc.super(OverlayManager, self).init()
        if self is None:
            return None
        self.active_windows = []
        self.lock = NSLock.alloc().init()
        return self

    def showTranslatedBlocksTranslations_(self, userInfo):
        self.lock.lock()
        try:
            self._clearAllWindows()
            blocks, translations, image_width, image_height = userInfo

            screen = NSScreen.mainScreen()
            screen_width = int(screen.frame().size.width)
            screen_height = int(screen.frame().size.height)

            # 如果图像已经是全屏，就不用 scale
            # 只需加少量偏移以避开原文
            offset_x = 0
            offset_y = 0

            occupied_zones = []

            def is_overlapping(x1, y1, w1, h1, zones):
                for x2, y2, w2, h2 in zones:
                    if x1 < x2 + w2 and x1 + w1 > x2 and y1 < y2 + h2 and y1 + h1 > y2:
                        return True
                return False

            for block, translation in zip(blocks, translations):
                # 直接使用原始坐标
                x = int(block['left'] + offset_x)
                y = int(block['top'] + offset_y)
                clean_text = translation.strip().replace("\n\n", "\n")

                # 获取窗口的实际宽高（不显示）
                actual_w, actual_h = self._create_overlay_window(x, y, clean_text, test_mode=True)

                # 避开原文上方
                y = max(y - 40, 0)

                # 避免与已有窗口重叠
                while is_overlapping(x, y, actual_w, actual_h, occupied_zones):
                    y += 50
                    if y > screen_height - actual_h:
                        break

                # 限制在屏幕内
                x = min(max(0, x), screen_width - actual_w - 10)
                y = min(max(0, y), screen_height - actual_h - 10)

                # 正式创建窗口
                win = self._create_overlay_window(x, y, clean_text, test_mode=False)
                self.active_windows.append(win)
                occupied_zones.append((x, y, actual_w, actual_h))
        finally:
            self.lock.unlock()

    def _clearAllWindows(self):
        for win in self.active_windows:
            if win.isVisible():
                win.orderOut_(None)
        self.active_windows.clear()

    def _create_overlay_window(self, x, y, text, test_mode=False):
        screen = NSScreen.mainScreen()
        screen_width = int(screen.frame().size.width)
        screen_height = int(screen.frame().size.height)

        font_size = 16
        char_width = font_size * 0.6
        max_line_chars = 50
        padding = 20
        max_width = screen_width * 0.9
        max_height = screen_height * 0.9

        # 估算行数
        lines = [text[i:i + max_line_chars] for i in range(0, len(text), max_line_chars)]
        num_lines = len(lines)

        width = min(max(len(line) for line in lines), max_line_chars) * char_width + padding
        height = num_lines * font_size * 1.5 + padding

        if test_mode:
            rect = NSMakeRect(0, 0, width, height)
            return width, height

            # 正常显示窗口（完整保留你已有逻辑）
        rect = NSMakeRect(x, y, width, height)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSBorderlessWindowMask,
            NSBackingStoreBuffered,
            False
        )

        # 如果超出最大范围，缩放字体直到适应
        while (width > max_width or height > max_height) and font_size > 10:
            font_size -= 1
            char_width = font_size * 0.6
            lines = [text[i:i + max_line_chars] for i in range(0, len(text), max_line_chars)]
            num_lines = len(lines)
            width = min(max(len(line) for line in lines), max_line_chars) * char_width + padding
            height = num_lines * font_size * 1.5 + padding

        # 限制最终位置不超屏幕边界
        x = min(x, screen_width - width - 10)
        y = min(y, screen_height - height - 10)

        rect = NSMakeRect(x, y, width, height)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSBorderlessWindowMask,
            NSBackingStoreBuffered,
            False
        )
        win.setLevel_(NSScreenSaverWindowLevel)
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setIgnoresMouseEvents_(True)
        win.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces |
            NSWindowCollectionBehaviorFullScreenAuxiliary
        )

        semi_black = NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.5)
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        field.setStringValue_(text)
        field.setEditable_(False)
        field.setBezeled_(False)
        field.setDrawsBackground_(True)
        field.setBackgroundColor_(semi_black)
        field.setTextColor_(NSColor.whiteColor())
        field.setFont_(field.font().fontWithSize_(font_size))
        field.setUsesSingleLineMode_(False)
        field.cell().setWraps_(True)
        field.cell().setLineBreakMode_(0)

        win.setContentView_(field)
        win.orderFrontRegardless()
        return win


OverlayManager.showTranslatedBlocks_translations_ = selector(
    OverlayManager.showTranslatedBlocksTranslations_,
    selector=b'showTranslatedBlocks:translations:',
    signature=b'v@:@'
)

cap = cv2.VideoCapture(2)

def background_loop(manager):
    while True:
        ret, frame = cap.read()
        if not ret:
            print("摄像头读取失败")
            time.sleep(1)
            continue

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)
        image_width, image_height = pil_img.size
        blocks = get_text_blocks(pil_img)
        texts = [b['text'] for b in blocks]
        if not texts:
            time.sleep(1)
            continue

        translations = translate_batch(texts)

        manager.performSelectorOnMainThread_withObject_waitUntilDone_(
            'showTranslatedBlocks:translations:',
            [blocks, translations, image_width, image_height],
            True
        )

        time.sleep(1.5)

def main():
    pool = NSAutoreleasePool.alloc().init()
    app = NSApplication.sharedApplication()

    manager = OverlayManager.alloc().init()
    if manager is None:
        print("Failed to initialize OverlayManager")
        sys.exit(1)

    threading.Thread(target=background_loop, args=(manager,), daemon=True).start()

    app.run()
    del pool
    cap.release()

if __name__ == '__main__':
    main()