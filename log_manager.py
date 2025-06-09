import sys
import logging
import os
from datetime import datetime, timedelta
import tkinter.messagebox as messagebox

class LogManager:
    def __init__(self, logfile_path='meinlog.log',  extra_logfile=None):
        self.logfile_path = logfile_path
        self.extra_logfile = extra_logfile
        self._patch_messagebox_done = False
        self.setup_logging()
        self.patch_messagebox()

    def cleanup_old_log_entries(self):
        if not os.path.exists(self.logfile_path):
            return
        one_week_ago = datetime.now() - timedelta(days=2)
        kept_lines = []
        with open(self.logfile_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    timestamp_str = line.split(' - ')[0]
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                    if timestamp >= one_week_ago:
                        kept_lines.append(line)
                except Exception:
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

        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Haupt-Logdatei
        file_handler = logging.FileHandler(self.logfile_path, mode='a', encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Optionales zusätzliches Log
        if self.extra_logfile:
            with open(self.extra_logfile, 'w', encoding='utf-8') as f:
                pass  # Immer leeren
            extra_handler = logging.FileHandler(self.extra_logfile, mode='a', encoding='utf-8')
            extra_handler.setFormatter(formatter)
            logger.addHandler(extra_handler)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        class StreamToLogger:
            def __init__(self, logger, level):
                self.logger = logger
                self.level = level
                self._buffer = ""
                self._in_write = False

            def write(self, buf):
                if self._in_write:
                    return
                try:
                    self._in_write = True
                    self._buffer += buf
                    while "\n" in self._buffer:
                        line, self._buffer = self._buffer.split("\n", 1)
                        if line.strip():
                            self.logger.log(self.level, line.strip())
                finally:
                    self._in_write = False

            def flush(self):
                if self._buffer.strip():
                    self.logger.log(self.level, self._buffer.strip())
                self._buffer = ""

        class TeeStream:
            def __init__(self, stream1, stream2):
                self.stream1 = stream1
                self.stream2 = stream2

            def write(self, data):
                self.stream1.write(data)
                self.stream1.flush()
                self.stream2.write(data)
                self.stream2.flush()

            def flush(self):
                self.stream1.flush()
                self.stream2.flush()

        original_stdout = sys.stdout
        original_stderr = sys.stderr

        stream_logger_out = StreamToLogger(logger, logging.INFO)
        stream_logger_err = StreamToLogger(logger, logging.ERROR)

        sys.stdout = TeeStream(original_stdout, stream_logger_out)
        sys.stderr = TeeStream(original_stderr, stream_logger_err)


# --- Optional: Testlauf, wenn das Skript direkt ausgeführt wird ---

if __name__ == "__main__":
    log_manager = LogManager('meinlog.log', extra_logfile='extra.log')
    logging.info("Logger ist bereit.")
    print("Dies wird mit INFO geloggt.")
    logging.warning("Warnung vom Logger.")
    print("Noch eine Ausgabe, die mitgeloggt wird.")
