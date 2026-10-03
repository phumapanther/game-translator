"""โปรแกรมแปลเกมด้วย Claude — หน้าต่างหลัก. Logic lives in gt/; this file only wires buttons to it."""
import json
import queue
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from gt.book import build_lines, save_book
from gt.install import InstallError, install
from gt.memory import Memory
from gt.scan import NeedLocres, ScanError, scan
from gt.steam import installed_games, steam_root
from gt.translate import MODELS, TranslateError, Translator, estimate_usd, load_done, remember, split_tm

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'settings.json'
MODE = {'mod': 'ต่อยอดม็อดไทยที่มีอยู่', 'base': 'ข้อความอังกฤษจากไฟล์เกม', 'manual': 'ไฟล์ Game.locres ที่เลือกเอง'}
ENGINE = {'unreal': 'Unreal', 'unity': 'Unity — ยังไม่รองรับ', '?': 'ไม่ทราบเอนจิน'}


class App:
    def __init__(self, root):
        self.root = root
        root.title('แปลเกมด้วย Claude')
        root.geometry('960x720')
        self.memory = Memory(ROOT / 'memory')
        self.q = queue.Queue()
        self.scan = None
        self.manual_locres = None
        self.lines = []
        self.teachings = []
        self.last_translator = None
        self.stop = threading.Event()
        self.busy = threading.Event()
        s = self._load_settings()

        f = ttk.Frame(root, padding=10)
        f.pack(fill='both', expand=True)
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text='API key').grid(row=0, column=0, sticky='w')
        self.key = tk.StringVar(value=s.get('api_key', ''))
        ttk.Entry(f, textvariable=self.key, show='•').grid(row=0, column=1, sticky='ew')
        self.remember = tk.BooleanVar(value=bool(s.get('api_key')))
        ttk.Checkbutton(f, text='จำไว้ในเครื่องนี้', variable=self.remember).grid(row=0, column=2, columnspan=2, sticky='w')

        ttk.Label(f, text='รุ่น Claude').grid(row=1, column=0, sticky='w')
        self.labels = {v[0]: k for k, v in MODELS.items()}
        self.model = tk.StringVar(value=MODELS[s.get('model', 'claude-opus-5-5')][0])
        ttk.Combobox(f, textvariable=self.model, values=list(self.labels), state='readonly').grid(row=1, column=1, sticky='ew')

        ttk.Label(f, text='เกมใน Steam').grid(row=2, column=0, sticky='w')
        self.steam_games = {f'{name}  ({ENGINE[engine]})': str(path) for name, path, engine in installed_games()}
        self.steam_pick = tk.StringVar()
        pick = ttk.Combobox(f, textvariable=self.steam_pick, values=list(self.steam_games), state='readonly')
        pick.grid(row=2, column=1, sticky='ew')
        pick.bind('<<ComboboxSelected>>', lambda _e: self._use_game(self.steam_games[self.steam_pick.get()]))

        ttk.Label(f, text='โฟลเดอร์เกม').grid(row=3, column=0, sticky='w')
        self.game = tk.StringVar(value=s.get('game_dir', ''))
        ttk.Entry(f, textvariable=self.game).grid(row=3, column=1, sticky='ew')
        ttk.Button(f, text='เลือก…', command=self.pick_game).grid(row=3, column=2)
        ttk.Button(f, text='สแกน', command=self.do_scan).grid(row=3, column=3)

        self.summary = tk.StringVar(value='เลือกเกมใน Steam (หรือโฟลเดอร์เกม) แล้วกด "สแกน"')
        ttk.Label(f, textvariable=self.summary, justify='left').grid(row=4, column=0, columnspan=4, sticky='w', pady=6)

        bar = ttk.Frame(f)
        bar.grid(row=5, column=0, columnspan=4, sticky='w')
        self.buttons = {}
        for text, cmd in [('ลองแปล 10 ข้อความ', lambda: self.do_translate(trial=True)),
                          ('แปลทั้งหมด', self.do_translate), ('หยุด', self.stop.set),
                          ('ติดตั้งลงเกม', self.do_install), ('สรุปบทเรียน', self.do_lessons)]:
            b = ttk.Button(bar, text=text, command=cmd)
            b.pack(side='left', padx=2)
            self.buttons[text] = b

        self.progress = ttk.Progressbar(f, maximum=1)
        self.progress.grid(row=6, column=0, columnspan=4, sticky='ew', pady=4)
        self.cost = tk.StringVar(value='ค่าใช้จ่าย: $0.00')
        ttk.Label(f, textvariable=self.cost).grid(row=7, column=0, columnspan=4, sticky='w')

        ttk.Label(f, text='สอนเพิ่ม').grid(row=8, column=0, sticky='w')
        self.tip = tk.StringVar()
        ttk.Entry(f, textvariable=self.tip).grid(row=8, column=1, columnspan=2, sticky='ew')
        ttk.Button(f, text='สอน', command=self.do_teach).grid(row=8, column=3)
        ttk.Label(f, text='เช่น "Infamy = ค่าหัว" (คำศัพท์) หรือ "พีทพูดหยาบ ใช้ กู/มึง" (กฎสไตล์)',
                  foreground='gray').grid(row=9, column=1, columnspan=3, sticky='w')

        self.log_box = ScrolledText(f, height=18)
        self.log_box.grid(row=10, column=0, columnspan=4, sticky='nsew', pady=6)
        f.rowconfigure(10, weight=1)
        root.after(100, self._poll)

    # --- plumbing -----------------------------------------------------------
    def model_id(self):
        return self.labels[self.model.get()]

    def log(self, text):
        self.q.put(('log', text))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == 'log':
                    self.log_box.insert('end', val + '\n')
                    self.log_box.see('end')
                elif kind == 'summary':
                    self.summary.set(val)
                elif kind == 'progress':
                    done, total, cost = val
                    self.progress.configure(maximum=max(total, 1), value=done)
                    self.cost.set(f'ค่าใช้จ่าย: ${cost:.2f}   ({done:,}/{total:,} ข้อความ)')
                elif kind == 'error':
                    messagebox.showerror('ผิดพลาด', val)
                elif kind == 'ask_locres':
                    self._ask_locres()
                elif kind == 'lessons':
                    self._show_lessons(val)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _bg(self, fn):
        """Run fn in a worker thread. Only one job at a time - a second click must never bill twice."""
        if self.busy.is_set():
            self.log('⏳ มีงานกำลังทำอยู่ — รอให้เสร็จก่อน (หรือกด "หยุด")')
            return False
        self.busy.set()

        def run():
            try:
                fn()
            except (ScanError, TranslateError, InstallError) as e:
                self.q.put(('error', str(e)))
            except Exception as e:  # last resort: never die silently in a worker thread
                self.q.put(('error', f'เกิดข้อผิดพลาดที่ไม่คาดคิด: {e!r}'))
            finally:
                self.busy.clear()
        threading.Thread(target=run, daemon=True).start()
        return True

    def _load_settings(self):
        try:
            return json.loads(SETTINGS.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def _save_settings(self):
        s = {'model': self.model_id(), 'game_dir': self.game.get().strip()}
        if self.remember.get():
            s['api_key'] = self.key.get().strip()
        SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding='utf-8')

    # --- actions --------------------------------------------------------------
    def _use_game(self, path):
        self.game.set(path)
        self.manual_locres = None

    def pick_game(self):
        path = filedialog.askdirectory(initialdir=str(steam_root() / 'steamapps' / 'common'), title='เลือกโฟลเดอร์เกม')
        if path:
            self._use_game(path)

    def do_scan(self):
        game, model = self.game.get().strip(), self.model_id()
        self._save_settings()

        def work():
            try:
                s = scan(game, manual_locres=self.manual_locres)
            except NeedLocres as e:
                self.log(str(e))
                self.q.put(('ask_locres', None))
                return
            self.scan = s
            items, hits = split_tm(s, self.memory)
            usd = estimate_usd(items, model, len(self.memory.system_prompt(s.game_id, s.project)))
            skipped = sum(1 for line in s.lines if line.skip)
            modded = sum(1 for line in s.lines if line.mod_text)
            self.q.put(('summary',
                        f'เกม: {s.project}   แหล่งข้อความ: {MODE[s.mode]}\n'
                        f'ทั้งหมด {len(s.lines):,} · แปลแล้ว (ม็อด) {modded:,} · ข้าม {skipped:,} · '
                        f'ใช้คลังคำแปลเดิม {len(hits):,} · ต้องแปล {len(items):,}\n'
                        f'ค่าใช้จ่ายประมาณ ${usd:.2f} ด้วย {MODELS[model][0]}'))
            for note in s.notes:
                self.log('⚠ ' + note)
        self._bg(work)

    def _ask_locres(self):
        path = filedialog.askopenfilename(title='เลือกไฟล์ Game.locres (ภาษา en) ที่แตกด้วย FModel',
                                          filetypes=[('Unreal locres', '*.locres')])
        if path:
            self.manual_locres = path
            self.do_scan()

    def do_translate(self, trial=False):
        if not self.scan:
            return messagebox.showinfo('', 'กดสแกนก่อน')
        key = self.key.get().strip()
        if not key:
            return messagebox.showinfo('', 'ใส่ API key ก่อน')
        self._save_settings()
        self.stop.clear()
        s, model = self.scan, self.model_id()

        def work():
            items, hits = split_tm(s, self.memory)
            if trial:
                work_dir = ROOT / 'work' / s.game_id / 'trial'
                shutil.rmtree(work_dir, ignore_errors=True)
                t = Translator(key, model, self.memory, s.game_id, s.project, work_dir, log=self.log)
                res = t.run(items[:10])
                for it in items[:10]:
                    self.log(f"{it['en']}\n   → {res.get(it['id'], {}).get('th', '(ไม่ผ่านตัวตรวจ)')}")
                self.log(f'ลองแปลเสร็จ ค่าใช้จ่าย ${t.cost:.3f}')
                return
            t = Translator(key, model, self.memory, s.game_id, s.project, ROOT / 'work' / s.game_id / 'main',
                           log=self.log)
            self.last_translator = t
            res = t.run(items, stop=self.stop, progress=lambda d, n, c: self.q.put(('progress', (d, n, c))))
            self._finish(s, model, res, hits)
            if self.stop.is_set():
                self.log('หยุดแล้ว — กด "แปลทั้งหมด" อีกครั้งเพื่อทำต่อ (ส่วนที่เสร็จแล้วไม่เสียเงินซ้ำ)')
            else:
                self.log(f'แปลเสร็จ {len(res):,}/{len(items):,} ข้อความ · ไม่ผ่านตัวตรวจ {len(t.issues)} '
                         f'(คงอังกฤษ จะลองใหม่ตอนกดแปลรอบหน้า) · ค่าใช้จ่ายรอบนี้ ${t.cost:.2f}')
        self._bg(work)

    def _finish(self, s, model, res, hits):
        remember(self.memory, s, res, model)
        self.lines = build_lines(s, res, hits)
        self.log(f'บันทึกหนังสือ: {save_book(ROOT / "books", s, self.lines, model)}')

    def do_install(self):
        if not self.scan:
            return messagebox.showinfo('', 'กดสแกนก่อน')
        s, model = self.scan, self.model_id()

        def work():
            _, hits = split_tm(s, self.memory)
            lines = build_lines(s, load_done(ROOT / 'work' / s.game_id / 'main'), hits)
            target = install(s, lines, ROOT / 'work' / s.game_id)
            save_book(ROOT / 'books', s, lines, model)
            self.log(f'ติดตั้งแล้ว: {target}  (ไฟล์เดิมสำรองไว้ที่ work/{s.game_id}/backup)')
            if s.signed:
                self.log('⚠ เกมนี้ตรวจลายเซ็นไฟล์ — ต้องมีตัวข้ามลายเซ็น ม็อดถึงจะโหลด')
        self._bg(work)

    def do_teach(self):
        tip = self.tip.get().strip()
        if not tip:
            return
        if not self.scan:
            return messagebox.showinfo('', 'สแกนเกมก่อน (คำศัพท์จะถูกเก็บแยกตามเกม)')
        self.log(self.memory.teach(self.scan.game_id, tip))
        self.teachings.append(tip)
        self.tip.set('')

    def do_lessons(self):
        t = self.last_translator
        if not t:
            return messagebox.showinfo('', 'กด "แปลทั้งหมด" ก่อน แล้วค่อยสรุปบทเรียน')
        samples = [(line['en'], line['th']) for line in self.lines if line['status'] == 'claude'][:40]
        self._bg(lambda: self.q.put(('lessons', t.propose_lessons(self.teachings, samples))))

    def _show_lessons(self, lessons):
        if not lessons:
            return messagebox.showinfo('', 'Claude ไม่มีบทเรียนใหม่จากรอบนี้')
        win = tk.Toplevel(self.root)
        win.title('บทเรียนใหม่ — ติ๊กข้อที่ต้องการบันทึก')
        chosen = []
        for lesson in lessons:
            v = tk.BooleanVar(value=False)
            chosen.append((v, lesson))
            label = 'สไตล์' if lesson['target'] == 'style' else 'เทคนิค'
            ttk.Checkbutton(win, text=f"[{label}] {lesson['text']}", variable=v).pack(anchor='w', padx=8, pady=2)

        def save():
            picked = [lesson for v, lesson in chosen if v.get()]
            for target, name in (('style', 'style_th.md'), ('lessons', 'lessons.md')):
                texts = [lesson['text'] for lesson in picked if lesson['target'] == target]
                if texts:
                    self.memory.append(name, texts, f'บทเรียนจาก {self.scan.project}')
            self.log(f'บันทึกบทเรียน {len(picked)} ข้อ')
            win.destroy()
        ttk.Button(win, text='บันทึกข้อที่ติ๊ก', command=save).pack(pady=8)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
