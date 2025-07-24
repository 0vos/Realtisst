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
    NSWindowCollectionBehaviorFullScreenAuxiliary
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
            blocks, translations = userInfo
            base_offset = 40  # 防止挡住原文
            for block, translation in zip(blocks, translations):
                x = block['left']
                y = block['top'] - base_offset
                win = self._create_overlay_window(x, y, translation)
                self.active_windows.append(win)
        finally:
            self.lock.unlock()

    def _clearAllWindows(self):
        for win in self.active_windows:
            if win.isVisible():
                win.orderOut_(None)
        self.active_windows.clear()

    def _create_overlay_window(self, x, y, text):
        rect = NSMakeRect(x, y, 800, 30)
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

        semi_black = NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.5)  # 半透明黑
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 800, 30))
        field.setStringValue_(text)
        field.setEditable_(False)
        field.setBezeled_(False)
        field.setDrawsBackground_(True)
        field.setBackgroundColor_(semi_black)
        field.setTextColor_(NSColor.whiteColor())
        field.setFont_(field.font().fontWithSize_(20))
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

        blocks = get_text_blocks(pil_img)
        texts = [b['text'] for b in blocks]
        if not texts:
            time.sleep(1)
            continue

        translations = translate_batch(texts)

        manager.performSelectorOnMainThread_withObject_waitUntilDone_(
            'showTranslatedBlocks:translations:',
            [blocks, translations],
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