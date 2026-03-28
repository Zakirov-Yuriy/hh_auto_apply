"""Вкладка конфигурации UI."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QSpinBox, QDoubleSpinBox, QCheckBox, QFileDialog, 
    QPushButton, QGroupBox, QFormLayout, QComboBox, QTextEdit
)
from PyQt6.QtCore import pyqtSignal

from hh_auto_apply.config import Config


class ConfigPanel(QWidget):
    """Вкладка конфигурации."""
    
    config_changed = pyqtSignal(Config)
    
    def __init__(self, initial_config: Config):
        super().__init__()
        self.config = initial_config
        self.init_ui()
        self.load_config(initial_config)
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # ==== Группа "Поиск" ====
        search_group = QGroupBox("Параметры поиска")
        search_form = QFormLayout()
        
        self.query_input = QLineEdit()
        search_form.addRow("Поисковый запрос:", self.query_input)
        
        self.region_input = QLineEdit()
        search_form.addRow("ID регионов (через запятую):", self.region_input)
        
        self.remote_only_check = QCheckBox("Только удаленная работа")
        search_form.addRow(self.remote_only_check)
        
        self.max_applies_spin = QSpinBox()
        self.max_applies_spin.setMinimum(1)
        self.max_applies_spin.setMaximum(10000)
        search_form.addRow("Макс. откликов:", self.max_applies_spin)
        
        search_group.setLayout(search_form)
        layout.addWidget(search_group)
        
        # ==== Группа "Резюме" ====
        resume_group = QGroupBox("Резюме")
        resume_form = QFormLayout()
        
        self.resume_match_input = QLineEdit()
        resume_form.addRow("Название резюме (маска):", self.resume_match_input)
        
        self.fail_if_not_found_check = QCheckBox("Ошибка если резюме не найдено")
        resume_form.addRow(self.fail_if_not_found_check)
        
        resume_group.setLayout(resume_form)
        layout.addWidget(resume_group)
        
        # ==== Группа "Сопроводительное письмо" ====
        cover_group = QGroupBox("Сопроводительное письмо")
        cover_form = QFormLayout()
        
        self.cover_letter_path_input = QLineEdit()
        cover_letter_browse = QPushButton("Обзор...")
        cover_letter_browse.clicked.connect(self.browse_cover_letter)
        cover_path_layout = QHBoxLayout()
        cover_path_layout.addWidget(self.cover_letter_path_input)
        cover_path_layout.addWidget(cover_letter_browse)
        cover_form.addRow("Файл писма:", cover_path_layout)
        
        self.require_cover_check = QCheckBox("Обязательно требовать письмо")
        cover_form.addRow(self.require_cover_check)
        
        cover_group.setLayout(cover_form)
        layout.addWidget(cover_group)
        
        # ==== Группа "AI (OpenRouter)" ====
        ai_group = QGroupBox("AI - Генерация писем")
        ai_form = QFormLayout()
        
        self.use_ai_check = QCheckBox("Использовать AI для писем")
        self.use_ai_check.stateChanged.connect(self.on_ai_enabled_changed)
        ai_form.addRow(self.use_ai_check)
        
        self.openrouter_key_input = QLineEdit()
        self.openrouter_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        ai_form.addRow("OpenRouter API ключ:", self.openrouter_key_input)
        
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.addItems([
            "mistralai/mistral-7b-instruct:free",
            "google/gemma-7b-it:free",
            "nousresearch/nous-hermes-2-mixtral-8x7b-dpo",
            "meta-llama/llama-2-7b-chat",
        ])
        ai_form.addRow("AI модель:", self.ai_model_combo)
        
        self.ai_prompt_text = QTextEdit()
        self.ai_prompt_text.setMaximumHeight(150)
        ai_form.addRow("Промпт для AI:", self.ai_prompt_text)
        
        ai_group.setLayout(ai_form)
        layout.addWidget(ai_group)
        
        # ==== Группа "Браузер" ====
        browser_group = QGroupBox("Браузер")
        browser_form = QFormLayout()
        
        self.headless_check = QCheckBox("Headless режим (без UI)")
        browser_form.addRow(self.headless_check)
        
        self.min_sleep_spin = QDoubleSpinBox()
        self.min_sleep_spin.setMinimum(0.5)
        self.min_sleep_spin.setMaximum(60)
        self.min_sleep_spin.setValue(3.0)
        browser_form.addRow("Мин. задержка (сек):", self.min_sleep_spin)
        
        self.max_sleep_spin = QDoubleSpinBox()
        self.max_sleep_spin.setMinimum(0.5)
        self.max_sleep_spin.setMaximum(60)
        self.max_sleep_spin.setValue(7.0)
        browser_form.addRow("Макс. задержка (сек):", self.max_sleep_spin)
        
        browser_group.setLayout(browser_form)
        layout.addWidget(browser_group)
        
        # ==== Кнопки ====
        buttons_layout = QHBoxLayout()
        
        save_btn = QPushButton("💾 Сохранить")
        save_btn.clicked.connect(self.save_config)
        buttons_layout.addWidget(save_btn)
        
        reset_btn = QPushButton("🔄 Сброс")
        reset_btn.clicked.connect(lambda: self.load_config(self.config))
        buttons_layout.addWidget(reset_btn)
        
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def browse_cover_letter(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать файл письма", "", "Text files (*.txt)")
        if path:
            self.cover_letter_path_input.setText(path)
    
    def on_ai_enabled_changed(self):
        enabled = self.use_ai_check.isChecked()
        self.openrouter_key_input.setEnabled(enabled)
        self.ai_model_combo.setEnabled(enabled)
        self.ai_prompt_text.setEnabled(enabled)
    
    def load_config(self, cfg: Config):
        """Загружает конфигурацию в UI."""
        self.config = cfg
        self.query_input.setText(cfg.search_query)
        self.region_input.setText(",".join(cfg.region_ids) if cfg.region_ids else "")
        self.remote_only_check.setChecked(cfg.remote_only)
        self.max_applies_spin.setValue(cfg.max_applies)
        
        self.resume_match_input.setText(cfg.resume_match)
        self.fail_if_not_found_check.setChecked(cfg.fail_if_resume_not_found)
        
        self.cover_letter_path_input.setText(str(cfg.cover_letter_path))
        self.require_cover_check.setChecked(cfg.require_cover_letter)
        
        self.use_ai_check.setChecked(cfg.use_ai_cover_letter)
        self.openrouter_key_input.setText(cfg.openrouter_api_key or "")
        self.ai_model_combo.setCurrentText(cfg.ai_model)
        
        if cfg.ai_prompt_path and cfg.ai_prompt_path.exists():
            self.ai_prompt_text.setText(cfg.ai_prompt_path.read_text(encoding="utf-8"))
        
        self.headless_check.setChecked(cfg.headless)
        self.min_sleep_spin.setValue(cfg.min_sleep)
        self.max_sleep_spin.setValue(cfg.max_sleep)
        
        self.on_ai_enabled_changed()
    
    def get_config(self) -> Config:
        """Возвращает обновленную конфигурацию."""
        # Сохраняем промпт в файл (всегда используем prompt.txt)
        prompt_path = Path("prompt.txt")
        prompt_text = self.ai_prompt_text.toPlainText().strip()
        if prompt_text and self.use_ai_check.isChecked():
            try:
                prompt_path.write_text(prompt_text, encoding="utf-8")
            except Exception:
                pass  # Игнорируем ошибки сохранения
        
        return Config(
            search_query=self.query_input.text(),
            region_ids=[r.strip() for r in self.region_input.text().split(",") if r.strip()],
            remote_only=self.remote_only_check.isChecked(),
            max_applies=self.max_applies_spin.value(),
            
            resume_match=self.resume_match_input.text(),
            fail_if_resume_not_found=self.fail_if_not_found_check.isChecked(),
            
            cover_letter_path=Path(self.cover_letter_path_input.text()),
            require_cover_letter=self.require_cover_check.isChecked(),
            
            use_ai_cover_letter=self.use_ai_check.isChecked(),
            openrouter_api_key=self.openrouter_key_input.text() or None,
            ai_model=self.ai_model_combo.currentText(),
            ai_prompt_path=prompt_path,
            
            headless=self.headless_check.isChecked(),
            min_sleep=self.min_sleep_spin.value(),
            max_sleep=self.max_sleep_spin.value(),
        )
    
    def save_config(self):
        """Сохраняет конфигурацию."""
        self.config = self.get_config()
        self.config_changed.emit(self.config)
