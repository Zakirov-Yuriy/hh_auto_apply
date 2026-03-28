"""Worker thread для запуска приложения без блокирования UI."""
from __future__ import annotations

import sys
import io
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from loguru import logger

from hh_auto_apply.app import App
from hh_auto_apply.config import Config


class LogCapture(io.StringIO):
    """Capture логов для перенаправления в сигналы."""
    
    def __init__(self, signal_callback):
        super().__init__()
        self.signal_callback = signal_callback
    
    def write(self, msg):
        if msg and msg.strip():
            self.signal_callback(msg.strip())
        return len(msg)


class AppWorkerThread(QThread):
    """Запускает App.run() в отдельном потоке."""
    
    # Signals для UI обновлений
    log_updated = pyqtSignal(str)  # сигнал с новым логом
    stats_updated = pyqtSignal(dict)  # сигнал со статистикой
    finished = pyqtSignal(int)  # сигнал завершения (exit code)
    error_occurred = pyqtSignal(str)  # сигнал об ошибке
    
    def __init__(self, cfg: Config, dry_run: bool = False):
        super().__init__()
        self.cfg = cfg
        self.dry_run = dry_run
        self._stop_flag = False
        self.app = None
        
    def run(self):
        """Основной метод потока."""
        try:
            # Создаем колбэк для логирования
            def log_callback(msg: str):
                self.log_updated.emit(msg)
            
            self.app = App(self.cfg, dry_run=self.dry_run, on_log=log_callback)
            
            # Переназначаем логер для перехвата
            self._setup_logging(log_callback)
            
            exit_code = self.app.run()
            self.finished.emit(exit_code)
        except Exception as e:
            logger.error(f"Ошибка в worker потоке: {e}")
            self.error_occurred.emit(str(e))
            self.finished.emit(1)
    
    def _setup_logging(self, callback):
        """Настраивает логер для перехвата в сигналы."""
        # Удаляем стандартный логер
        logger.remove()
        
        # Добавляем функцию обработчика
        def log_handler(message):
            try:
                # Формируем сообщение логов
                log_text = message.record["message"]
                callback(log_text)
            except Exception:
                pass
        
        logger.add(log_handler, level="DEBUG", format="{message}")
    
    def stop(self):
        """Останавливает приложение."""
        self._stop_flag = True
        if self.app:
            self.app.stop()
    
    def request_interrupt(self):
        """Запросить прерывание приложения."""
        self.stop()

