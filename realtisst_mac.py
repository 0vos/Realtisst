import sys
import objc
import time
import threading
from objc import selector
from AppKit import (
    NSApplication, NSWindow, NSBackingStoreBuffered,
    NSBorderlessWindowMask, NSMakeRect, NSColor, NSTextField,
    NSScreenSaverWindowLevel, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary
)
from Foundation import NSObject, NSAutoreleasePool, NSArray, NSLock

class OverlayManager(NSObject):
    def init(self):
        self = objc.super(OverlayManager, self).init()
        if self is None:
            return None
        self.active_windows = []
        self.lock = NSLock.alloc().init()
        return self

    def showTranslations_(self, ns_lines):
        # 确保多线程安全
        self.lock.lock()
        try:
            print(">>> 清理旧窗口")
            self._clearAllWindows()

            print(">>> 显示新翻译:", ns_lines)
            base_y = 600
            for i, line in enumerate(ns_lines):
                win = self._create_overlay_window(200, base_y - i * 30, str(line))
                self.active_windows.append(win)
        finally:
            self.lock.unlock()

    def _clearAllWindows(self):
        # 不直接close，先orderOut_避免立刻释放引发崩溃
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

        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 800, 30))
        field.setStringValue_(text)
        field.setEditable_(False)
        field.setBezeled_(False)
        field.setDrawsBackground_(False)
        field.setTextColor_(NSColor.greenColor())
        field.setFont_(field.font().fontWithSize_(20))
        win.setContentView_(field)
        win.orderFrontRegardless()
        return win

def background_loop(manager):
    while True:
        lines = ["翻译更新啦", f"时间: {time.strftime('%H:%M:%S')}"]
        ns_lines = NSArray.arrayWithArray_([str(l) for l in lines])
        manager.performSelectorOnMainThread_withObject_waitUntilDone_(
            'showTranslations:', ns_lines, True
        )
        time.sleep(3)

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

if __name__ == '__main__':
    main()