import sys
import objc
import time
import threading
from objc import selector
from AppKit import (
    NSApplication, NSWindow, NSBackingStoreBuffered,
    NSBorderlessWindowMask, NSMakeRect, NSColor, NSTextField,
    NSScreenSaverWindowLevel, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary, NSScreen
)
from Foundation import NSObject, NSAutoreleasePool, NSArray, NSLock
from ocr_translate_core import get_text_blocks, translate_batch

# import Quartz
# import AppKit
# from Cocoa import NSEvent

is_lock = True

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

            for i, (block, translation) in enumerate(zip(blocks, translations)):
                print(f"[{i}] 坐标: ({block['left']:.1f}, {block['top']:.1f}) 原文: {block['text']} 翻译: {translation}")
                # 直接使用原始坐标
                x = int(block['left'])
                # Flip Y coordinate to match macOS bottom-up coordinate system
                screen_height = int(screen.frame().size.height)
                y = screen_height - int(block['top']) - int(block['height'])
                w = int(block['width'])
                h = int(block['height'])
                clean_text = translation.strip().replace("\n\n", "\n")

                win = self._create_overlay_window(x, y, clean_text, max_width=w, max_height=h)
                self.active_windows.append(win)
                # self.active_windows.append(win)
                # occupied_zones.append((x, y, actual_w, actual_h))
        finally:
            self.lock.unlock()

    def hide_all_windows(self):
        for win in self.active_windows:
            win.orderOut_(None)

    def show_all_windows(self):
        for win in self.active_windows:
            win.orderFrontRegardless()

    def _clearAllWindows(self):
        for win in self.active_windows:
            if win.isVisible():
                win.orderOut_(None)
        self.active_windows.clear()

    def _create_overlay_window(self, x, y, text, test_mode=False, max_width=None, max_height=None):
        screen = NSScreen.mainScreen()
        screen_width = int(screen.frame().size.width)
        screen_height = int(screen.frame().size.height)

        # 初始字体设置
        font_size = 20
        char_width = font_size * 0.6
        padding = 20

        if max_width is None:
            max_width = screen_width * 0.9
        if max_height is None:
            max_height = screen_height * 0.9

        def split_text_by_width(text, max_width, char_width):
            words = text.split()
            lines = []
            current_line = ""
            for word in words:
                if len(current_line) == 0:
                    tentative_line = word
                else:
                    tentative_line = current_line + " " + word
                if len(tentative_line) * char_width <= max_width:
                    current_line = tentative_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            return lines

        width = max_width
        height = max_height

        min_font_size = 8
        max_font_size = 40
        font_size = max_font_size

        def fits(text, width, height, font_size):
            char_width = font_size * 0.6
            line_height = font_size * 1.5
            lines = split_text_by_width(text, width - padding, char_width)
            total_height = len(lines) * line_height + padding
            max_line_width = max((len(line) * char_width for line in lines), default=0) + padding
            return total_height <= height and max_line_width <= width, lines

        while font_size >= min_font_size:
            ok, lines = fits(text, width, height, font_size)
            if ok:
                break
            font_size -= 1

        if font_size < min_font_size:
            font_size = min_font_size
            _, lines = fits(text, width, height, font_size)

        if test_mode:
            rect = NSMakeRect(0, 0, width, height)
            return width, height

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

# sct = mss()  # 用于全屏截图
def background_loop(manager):
    global is_lock
    while True:
        if is_lock:
            manager.hide_all_windows()
            time.sleep(0.2)
            continue

        if not manager.continuous_mode and not manager.toggle_display:
            # manager.hide_all_windows()
            time.sleep(0.2)
            continue

        manager.hide_all_windows()
        time.sleep(0.1)

        pil_img = capture_fullscreen()
        if pil_img is None:
            continue

        image_width, image_height = pil_img.size
        screen = NSScreen.mainScreen()
        screen_width = int(screen.frame().size.width)
        screen_height = int(screen.frame().size.height)
        blocks = get_text_blocks(pil_img, screen_width=screen_width, screen_height=screen_height)
        texts = [b['text'] for b in blocks]
        if not texts:
            time.sleep(0.5)
            continue

        translations = translate_batch(texts)
        manager.performSelectorOnMainThread_withObject_waitUntilDone_(
            'showTranslatedBlocks:translations:',
            [blocks, translations, image_width, image_height],
            True
        )

        # 如果是单次翻译模式，显示一次后重置 toggle
        if not manager.continuous_mode:
            manager.toggle_display = False

        time.sleep(3)

def capture_fullscreen():
    from Quartz import (
        CGWindowListCreateImage,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
        kCGWindowImageDefault,
        CGRectMake
    )
    from AppKit import NSImage, NSBitmapImageRep
    from PIL import Image

    screen = NSScreen.mainScreen()
    screen_width = int(screen.frame().size.width)
    screen_height = int(screen.frame().size.height)

    rect = CGRectMake(0, 0, screen_width, screen_height)
    cg_image = CGWindowListCreateImage(
        rect,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
        kCGWindowImageDefault
    )

    # 将 CGImage 转换为 NSImage
    ns_image = NSImage.alloc().initWithCGImage_size_(cg_image, (screen_width, screen_height))
    bitmap_rep = NSBitmapImageRep.imageRepWithData_(ns_image.TIFFRepresentation())
    if bitmap_rep is None:
        print("无法从 NSImage 中获取位图表示")
        return None

    width = bitmap_rep.pixelsWide()
    height = bitmap_rep.pixelsHigh()
    raw_data = bitmap_rep.bitmapData()
    pil_img = Image.frombuffer("RGBA", (width, height), raw_data, "raw", "RGBA", 0, 1)
    pil_img.save("debug_frame.png")
    return pil_img

def global_key_listener(manager):
    """
    使用 Quartz 创建 CGEventTap 监听全局键盘事件。
    现在需要同时按下 command + control，再按 y 或 h 才触发行为。
    """
    import Quartz
    import ctypes

    # 定义回调
    def tap_callback(proxy, type_, event, refcon):
        global is_lock
        # 10 = kCGEventKeyDown
        if type_ == Quartz.kCGEventKeyDown:
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            flags = Quartz.CGEventGetFlags(event)
            # 检查是否同时按下 command 和 control
            command_mask = Quartz.kCGEventFlagMaskCommand
            control_mask = Quartz.kCGEventFlagMaskControl
            if (flags & command_mask) and (flags & control_mask):
                if keycode == 16 and is_lock:  # y
                    manager.toggle_display = not manager.toggle_display
                    is_lock = False
                    print("切换一次翻译显示，当前状态：", manager.toggle_display)
                elif keycode == 16 and not is_lock:  # y
                    # manager.toggle_display = not manager.toggle_display
                    is_lock = True
                    print("切换一次翻译显示，当前状态：", manager.toggle_display)
                elif keycode == 4 and is_lock:  # h
                    manager.continuous_mode = not manager.continuous_mode
                    is_lock = False
                    print("切换持续翻译模式，当前状态：", manager.continuous_mode)
                elif keycode == 4 and not is_lock:  # h
                    # manager.continuous_mode = not manager.continuous_mode
                    is_lock = True
                    print("切换持续翻译模式，当前状态：", manager.continuous_mode)
        return event

    # 设置事件掩码为键盘事件
    event_mask = (1 << Quartz.kCGEventKeyDown)
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        event_mask,
        tap_callback,
        None
    )
    if not tap:
        print("无法创建全局键盘事件监听（需要辅助功能权限）")
        return
    run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    loop = Quartz.CFRunLoopGetCurrent()
    Quartz.CFRunLoopAddSource(loop, run_loop_source, Quartz.kCFRunLoopCommonModes)
    Quartz.CGEventTapEnable(tap, True)
    Quartz.CFRunLoopRun()

def main():
    pool = NSAutoreleasePool.alloc().init()
    app = NSApplication.sharedApplication()

    manager = OverlayManager.alloc().init()
    if manager is None:
        print("Failed to initialize OverlayManager")
        sys.exit(1)

    # 控制变量
    manager.toggle_display = False
    manager.continuous_mode = False

    # 启动全局键盘监听线程
    threading.Thread(target=global_key_listener, args=(manager,), daemon=True).start()

    threading.Thread(target=background_loop, args=(manager,), daemon=True).start()

    app.run()
    del pool
    # cap.release()

if __name__ == '__main__':
    main()
