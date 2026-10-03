import importlib.machinery
import importlib.util
import tkinter as tk

from tests.paths import ROOT


def test_window_builds_and_closes():
    loader = importlib.machinery.SourceFileLoader('app', str(ROOT / 'app.pyw'))
    spec = importlib.util.spec_from_loader('app', loader)
    app_mod = importlib.util.module_from_spec(spec)
    loader.exec_module(app_mod)
    root = tk.Tk()
    try:
        app = app_mod.App(root)
        root.update()
        assert set(app.buttons) == {'ลองแปล 10 ข้อความ', 'แปลทั้งหมด', 'หยุด', 'ติดตั้งลงเกม', 'สรุปบทเรียน'}
        assert app.model_id() in app_mod.MODELS
        assert any(label.startswith('Maneater') for label in app.steam_games) or not app.steam_games
    finally:
        root.destroy()
