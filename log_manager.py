import sys
import logging
import os
from datetime import datetime, timedelta
import tkinter.messagebox as messagebox
import Eingabe.config as config # Importiere das komplette config-Modul

class LogManager:
    def __init__(self, logfile_path='meinlog.log'):
        self.logfile_path = logfile_path
        self._patch_messagebox_done = False
        
        self.setup_logging()
        self.patch_messagebox()
        
    def cleanup_old_log_entries(self):
        if not os.path.exists(self.logfile_path):
            return
        one_week_ago = datetime.now() - timedelta(minutes=5)
        kept_lines = []
        with open(self.logfile_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    timestamp_str = line.split(' - ')[0]
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                    if timestamp >= one_week_ago:
                        kept_lines.append(line)
                except Exception:
                    # Falls Zeile kein Datum enthält, behalten
                    kept_lines.append(line)
        with open(self.logfile_path, 'w', encoding='utf-8') as f:
            f.writelines(kept_lines)

    def patch_messagebox(self):
        if self._patch_messagebox_done:
            return
        self._patch_messagebox_done = True

        def logged_showinfo(title, message, **kwargs):
            logging.info(f"{title}: {message}")
            return original_showinfo(title, message, **kwargs)

        def logged_showwarning(title, message, **kwargs):
            logging.warning(f"{title}: {message}")
            return original_showwarning(title, message, **kwargs)

        def logged_showerror(title, message, **kwargs):
            logging.error(f"{title}: {message}")
            return original_showerror(title, message, **kwargs)

        global original_showinfo, original_showwarning, original_showerror
        original_showinfo = messagebox.showinfo
        original_showwarning = messagebox.showwarning
        original_showerror = messagebox.showerror

        messagebox.showinfo = logged_showinfo
        messagebox.showwarning = logged_showwarning
        messagebox.showerror = logged_showerror

    def setup_logging(self):
        self.cleanup_old_log_entries()

        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        if logger.hasHandlers():
            logger.handlers.clear()

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')

        file_handler = logging.FileHandler(self.logfile_path, mode='a', encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        class StreamToLogger:
            def __init__(self, logger, level):
                self.logger = logger
                self.level = level
                self._buffer = ""

            def write(self, buf):
                self._buffer += buf
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    if line.strip():
                        self.logger.log(self.level, line.strip())

            def flush(self):
                if self._buffer.strip():
                    self.logger.log(self.level, self._buffer.strip())
                self._buffer = ""

        sys.stdout = StreamToLogger(logger, logging.INFO)
        sys.stderr = StreamToLogger(logger, logging.ERROR)
