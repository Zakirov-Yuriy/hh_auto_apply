"""Главное окно PyQt6 приложения."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QIcon

from hh_auto_apply.config import Config
from hh_auto_apply.gui_config import ConfigPanel
from hh_auto_apply.gui_run import RunPanel
from hh_auto_apply.gui_worker import AppWorkerThread
import pandas as pd


class MainWindow(QMainWindow):
    """Главное окно приложения."""
    
    def __init__(self):
        super().__init__()
        self.config = Config.from_env()
        self.worker_thread = None
        self.init_ui()
        self.setWindowTitle("🚀 HH Auto Apply - Desktop")
        self.setGeometry(100, 100, 1200, 800)
    
    def init_ui(self):
        """Инициализирует UI."""
        # Основной виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Табы
        self.tabs = QTabWidget()
        
        # Вкладка 1: Конфигурация
        self.config_panel = ConfigPanel(self.config)
        self.config_panel.config_changed.connect(self.on_config_changed)
        self.tabs.addTab(self.config_panel, "⚙️ Конфигурация")
        
        # Вкладка 2: Запуск
        self.run_panel = RunPanel()
        self.run_panel.start_btn.clicked.connect(self.start_application)
        self.run_panel.stop_btn.clicked.connect(self.stop_application)
        self.tabs.addTab(self.run_panel, "▶️ Запуск")
        
        # Вкладка 3: История
        self.history_panel = self.create_history_panel()
        self.tabs.addTab(self.history_panel, "📊 История")
        
        layout.addWidget(self.tabs)
        
        # Счетчик для обновления истории
        self.history_timer = QTimer()
        self.history_timer.timeout.connect(self.refresh_history)
        self.history_timer.start(5000)  # Обновление каждые 5 сек
    
    def create_history_panel(self) -> QWidget:
        """Создает вкладку истории."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        label = QLabel("📋 История откликов (vacancies.csv):")
        label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(label)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(2)
        self.history_table.setHorizontalHeaderLabels(["Вакансия", "Ссылка"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.history_table)
        
        widget.setLayout(layout)
        return widget
    
    def refresh_history(self):
        """Обновляет таблицу истории из CSV."""
        csv_path = Path(self.config.vacancies_csv)
        if not csv_path.exists():
            return
        
        try:
            df = pd.read_csv(csv_path)
            self.history_table.setRowCount(0)
            
            for idx, row in df.iterrows():
                self.history_table.insertRow(idx)
                self.history_table.setItem(idx, 0, QTableWidgetItem(row.get("title", "")))
                self.history_table.setItem(idx, 1, QTableWidgetItem(row.get("link", "")))
        except Exception as e:
            pass  # Игнорируем ошибки при чтении CSV
    
    def on_config_changed(self, new_config: Config):
        """Обновляет конфигурацию."""
        self.config = new_config
        QMessageBox.information(self, "✅ Сохранено", "Конфигурация сохранена!")
    
    def start_application(self):
        """Запускает приложение."""
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.warning(self, "⚠️ Ошибка", "Приложение уже запущено!")
            return
        
        # Переключаемся на вкладку запуска
        self.tabs.setCurrentIndex(1)
        
        # Получаем конфигурацию из панели
        self.config = self.config_panel.get_config()
        
        # Создаем и запускаем worker
        self.worker_thread = AppWorkerThread(
            self.config,
            dry_run=self.run_panel.dry_run_check.isChecked()
        )
        
        # Подключаем сигналы
        self.worker_thread.log_updated.connect(self.on_log_updated)
        self.worker_thread.stats_updated.connect(self.on_stats_updated)
        self.worker_thread.error_occurred.connect(self.on_error_occurred)
        self.worker_thread.finished.connect(self.on_worker_finished)
        
        # UI обновления
        self.run_panel.set_running(True)
        self.run_panel.reset_stats()
        
        # Запускаем worker
        self.worker_thread.start()
    
    def stop_application(self):
        """Останавливает приложение."""
        if self.worker_thread:
            self.worker_thread.stop()
            self.run_panel.add_log("⏹️ Получен сигнал остановки...")
    
    @pyqtSlot(str)
    def on_log_updated(self, message: str):
        """Обновляет логи."""
        if message.strip():
            self.run_panel.add_log(message)
    
    @pyqtSlot(dict)
    def on_stats_updated(self, stats: dict):
        """Обновляет статистику."""
        self.run_panel.update_stats(stats)
    
    @pyqtSlot(str)
    def on_error_occurred(self, error: str):
        """Обрабатывает ошибку."""
        self.run_panel.add_log(f"❌ ОШИБКА: {error}")
        QMessageBox.critical(self, "❌ Ошибка", f"Произошла ошибка: {error}")
    
    @pyqtSlot(int)
    def on_worker_finished(self, exit_code: int):
        """Обрабатывает завершение worker'а."""
        self.run_panel.set_running(False)
        
        if exit_code == 0:
            self.run_panel.add_log("✅ Приложение завершено успешно!")
            QMessageBox.information(self, "✅ Готово", "Приложение завершено успешно!")
        else:
            self.run_panel.add_log(f"❌ Приложение завершено с кодом: {exit_code}")
        
        # Обновляем историю
        self.refresh_history()


def main():
    """Точка входа GUI приложения."""
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
