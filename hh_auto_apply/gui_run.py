"""Вкладка запуска и логирования."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QLabel, QProgressBar, QCheckBox, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt, QTimer


class RunPanel(QWidget):
    """Вкладка запуска приложения."""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # ==== Кнопки управления ====
        control_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("▶️ Запустить")
        self.start_btn.setStyleSheet("QPushButton { padding: 10px; font-size: 14px; background-color: #4CAF50; color: white; border-radius: 5px; }")
        self.start_btn.setMinimumHeight(40)
        control_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏹️ Остановить")
        self.stop_btn.setStyleSheet("QPushButton { padding: 10px; font-size: 14px; background-color: #f44336; color: white; border-radius: 5px; }")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)
        
        self.dry_run_check = QCheckBox("📋 Dry-run (только сканирование)")
        self.dry_run_check.setStyleSheet("QCheckBox { font-size: 12px; }")
        control_layout.addWidget(self.dry_run_check)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # ==== Статистика ====
        stats_group = QGroupBox("Статистика")
        stats_form = QFormLayout()
        
        self.found_label = QLabel("0")
        stats_form.addRow("Найдено вакансий:", self.found_label)
        
        self.opened_label = QLabel("0")
        stats_form.addRow("Открыто:", self.opened_label)
        
        self.applied_label = QLabel("0")
        stats_form.addRow("Откликов отправлено:", self.applied_label)
        
        self.skipped_label = QLabel("0")
        stats_form.addRow("Пропущено:", self.skipped_label)
        
        self.errors_label = QLabel("0")
        stats_form.addRow("Ошибок:", self.errors_label)
        
        stats_group.setLayout(stats_form)
        layout.addWidget(stats_group)
        
        # ==== Progress bar ====
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # ==== Логи ====
        logs_label = QLabel("📋 Логи:")
        logs_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(logs_label)
        
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #00ff00;
                font-family: 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        self.logs_text.setMinimumHeight(300)
        layout.addWidget(self.logs_text)
        
        self.setLayout(layout)
    
    def add_log(self, message: str):
        """Добавляет сообщение в логи."""
        self.logs_text.append(message)
        # Автоскролл вниз
        self.logs_text.verticalScrollBar().setValue(
            self.logs_text.verticalScrollBar().maximum()
        )
    
    def update_stats(self, stats: dict):
        """Обновляет статистику."""
        self.found_label.setText(str(stats.get("found_links", 0)))
        self.opened_label.setText(str(stats.get("opened", 0)))
        self.applied_label.setText(str(stats.get("applies_done", 0)))
        self.skipped_label.setText(str(stats.get("skipped_seen", 0) + stats.get("skipped_already", 0)))
        self.errors_label.setText(str(stats.get("errors", 0)))
        
        # Обновляем progress bar (простая логика)
        max_applies = 200  # TODO: получить из конфига
        applied = stats.get("applies_done", 0)
        progress = min(100, int((applied / max_applies) * 100)) if max_applies > 0 else 0
        self.progress_bar.setValue(progress)
    
    def clear_logs(self):
        """Очищает логи."""
        self.logs_text.clear()
    
    def reset_stats(self):
        """Сбрасывает статистику."""
        self.found_label.setText("0")
        self.opened_label.setText("0")
        self.applied_label.setText("0")
        self.skipped_label.setText("0")
        self.errors_label.setText("0")
        self.progress_bar.setValue(0)
        self.clear_logs()
    
    def set_running(self, running: bool):
        """Устанавливает состояние запуска."""
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.dry_run_check.setEnabled(not running)
