"""Standalone Windows GUI and batch entry point for the preprocessing engine."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import queue
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

import preprocess


class App:
    def __init__(self, root, smoke=None):
        self.root = root
        self.smoke = smoke
        self.messages = queue.Queue()
        self.running = False
        self.output = None
        root.title("视频图像预处理工具")
        root.geometry("820x600")
        root.minsize(760, 560)
        root.configure(bg="#eef2f7")
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#eef2f7")
        style.configure("TLabel", background="#eef2f7", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(12, 7))
        style.configure("TEntry", padding=7)
        self.video = tk.StringVar()
        self.folder = tk.StringVar(value=str(Path.home() / "Desktop"))
        self.fps = tk.StringVar(value="2")
        self.status = tk.StringVar(value="请选择视频和保存位置")
        self.percent = tk.DoubleVar(value=0)
        main = ttk.Frame(root, padding=28)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        ttk.Label(main, text="把视频整理成可追溯的图像", font=("Microsoft YaHei UI", 22, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        ttk.Label(main, text="选择素材 → 自动抽帧与初筛 → 查看图像和报告", foreground="#49617b").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 24))
        ttk.Label(main, text="输入视频").grid(row=2, column=0, sticky="w")
        self.video_entry = ttk.Entry(main, textvariable=self.video)
        self.video_entry.grid(row=3, column=0, sticky="ew", pady=(5, 16), padx=(0, 10))
        self.video_button = ttk.Button(main, text="选择视频…", command=self.choose_video)
        self.video_button.grid(row=3, column=1, pady=(5, 16))
        ttk.Label(main, text="保存到文件夹").grid(row=4, column=0, sticky="w")
        self.folder_entry = ttk.Entry(main, textvariable=self.folder)
        self.folder_entry.grid(row=5, column=0, sticky="ew", pady=(5, 8), padx=(0, 10))
        self.folder_button = ttk.Button(main, text="选择文件夹…", command=self.choose_folder)
        self.folder_button.grid(row=5, column=1, pady=(5, 8))
        ttk.Label(main, text="将在这里新建独立结果文件夹，原视频和已有结果都会保留。", foreground="#49617b").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(0, 14))
        options = ttk.Frame(main)
        options.grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Label(options, text="每秒抽取").pack(side="left")
        self.fps_box = ttk.Combobox(options, textvariable=self.fps, values=("0.5", "1", "2", "3", "4", "5"),
                                    width=5, state="readonly")
        self.fps_box.pack(side="left", padx=8)
        ttk.Label(options, text="张图像    建议先用 2 张；模糊帧会标记供复核。").pack(side="left")
        buttons = ttk.Frame(main)
        buttons.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(22, 15))
        self.start_button = ttk.Button(buttons, text="开始处理", command=self.start)
        self.start_button.pack(side="left")
        self.open_button = ttk.Button(buttons, text="打开结果文件夹", command=self.open_folder, state="disabled")
        self.open_button.pack(side="left", padx=12)
        self.report_button = ttk.Button(buttons, text="查看图文报告", command=self.open_report, state="disabled")
        self.report_button.pack(side="left")
        ttk.Progressbar(main, variable=self.percent, maximum=100).grid(row=9, column=0, columnspan=2, sticky="ew")
        ttk.Label(main, textvariable=self.status, wraplength=740).grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 12))
        self.log = tk.Text(main, height=6, relief="flat", font=("Microsoft YaHei UI", 9), bg="white", wrap="word")
        self.log.grid(row=11, column=0, columnspan=2, sticky="nsew")
        main.rowconfigure(11, weight=1)
        self.write_log("图像、质量评分、来源清单和训练/检验列表会一起保存。")
        root.after(80, self.poll)
        if smoke:
            self.video.set(str(smoke["video"]))
            self.folder.set(str(smoke["folder"]))
            root.after(500, self.start)
        elif len(sys.argv) == 2 and Path(sys.argv[1]).is_file():
            self.video.set(str(Path(sys.argv[1]).resolve()))

    def write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def choose_video(self):
        path = filedialog.askopenfilename(title="选择视频", filetypes=[
            ("视频文件", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"), ("全部文件", "*.*")])
        if path:
            self.video.set(path)

    def choose_folder(self):
        path = filedialog.askdirectory(title="选择结果保存位置", mustexist=True)
        if path:
            self.folder.set(path)

    def set_running(self, state):
        self.running = state
        for widget in (self.video_entry, self.folder_entry, self.video_button, self.folder_button, self.start_button):
            widget.configure(state="disabled" if state else "normal")
        self.fps_box.configure(state="disabled" if state else "readonly")

    def start(self):
        if self.running:
            return
        video = Path(self.video.get().strip().strip('"'))
        parent = Path(self.folder.get().strip().strip('"'))
        if not video.is_file() or not parent.is_dir():
            messagebox.showerror("请检查路径", "请选择有效的视频文件和已有保存文件夹。")
            return
        output = parent / (video.stem[:60] + "_图像_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        serial = 1
        while output.exists():
            output = parent / (video.stem[:60] + "_图像_" + datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{serial}")
            serial += 1
        self.output = output
        args = preprocess.parser().parse_args(["--input", str(video), "--output", str(output),
                                               "--sample-fps", self.fps.get(),
                                               "--source-description", "桌面工具导入的视频素材"])
        self.percent.set(0)
        self.status.set("准备处理…")
        self.open_button.configure(state="disabled")
        self.report_button.configure(state="disabled")
        self.set_running(True)
        self.write_log("输入：" + str(video))
        self.write_log("结果：" + str(output))

        def work():
            try:
                result = preprocess.run(args, progress=lambda n, s: self.messages.put(("progress", n, s)))
                self.messages.put(("done", result))
            except Exception as exc:
                self.messages.put(("error", str(exc), traceback.format_exc()))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                event = self.messages.get_nowait()
                if event[0] == "progress":
                    self.percent.set(event[1])
                    self.status.set(event[2])
                elif event[0] == "done":
                    self.set_running(False)
                    counts = event[1]["counts"]
                    text = (f"完成：候选 {counts['candidates']} 张，保留 {counts['selected']} 张；"
                            f"训练 {counts['train']} 张，检验 {counts['val']} 张。")
                    self.status.set(text)
                    self.write_log(text)
                    self.write_log("图片位于结果目录的 images 文件夹；查看报告可复核排除项。")
                    self.open_button.configure(state="normal")
                    self.report_button.configure(state="normal")
                    if self.smoke:
                        record = {"status": "passed", "output": str(self.output), "counts": counts,
                                  "progress": self.percent.get(),
                                  "open_result_enabled": str(self.open_button["state"]) == "normal",
                                  "open_report_enabled": str(self.report_button["state"]) == "normal",
                                  "packaged": bool(getattr(sys, "frozen", False))}
                        Path(self.smoke["report"]).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                        self.root.after(250, self.root.destroy)
                elif event[0] == "error":
                    self.set_running(False)
                    self.status.set("处理失败：" + event[1])
                    self.write_log(event[2])
                    if self.smoke:
                        Path(self.smoke["report"]).write_text(json.dumps({"status": "failed", "error": event[2]},
                                                                       ensure_ascii=False, indent=2), encoding="utf-8")
                        self.root.after(100, self.root.destroy)
                    else:
                        messagebox.showerror("处理失败", event[1])
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    def open_folder(self):
        if self.output:
            os.startfile(str(self.output))

    def open_report(self):
        if self.output:
            webbrowser.open((self.output / "report.html").resolve().as_uri())

    def close(self):
        if self.running and not messagebox.askyesno("正在处理", "关闭工具会中止当前任务，是否关闭？"):
            return
        self.root.destroy()


def main():
    # Windowed executables do not have a console stream.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if "--batch" in sys.argv:
        sys.argv.remove("--batch")
        return preprocess.main()
    smoke = None
    if "--gui-smoke-test" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--gui-smoke-test", action="store_true")
        parser.add_argument("--video", required=True, type=Path)
        parser.add_argument("--folder", required=True, type=Path)
        parser.add_argument("--report", required=True, type=Path)
        smoke = vars(parser.parse_args())
    root = tk.Tk()
    App(root, smoke)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
