"""Standalone OCR integration test for a locally owned synthetic form only."""
from __future__ import annotations

import io
import secrets
import threading
from pathlib import Path

import pytesseract
from flask import Flask, Response, render_template_string, request
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

HOST = "127.0.0.1"
PORT = 8765
app = Flask(__name__)
EXPECTED = ""

PAGE = """<!doctype html><html lang='ru'><meta charset='utf-8'>
<title>Локальная проверка OCR</title><body style='font:18px Arial;max-width:500px;margin:60px auto'>
<h2>Тестовая форма распознавания</h2><p>Введите текст с картинки:</p>
<img data-qa='local-test-picture' src='/picture' alt='Тестовый текст'>
<form method='post' action='/check'><input data-qa='local-test-input' name='text' autocomplete='off'>
<button type='submit'>Отправить</button></form></body></html>"""

@app.get("/")
def index():
    return render_template_string(PAGE)

@app.get("/picture")
def picture():
    image = Image.new("RGB", (270, 90), "white")
    draw = ImageDraw.Draw(image)
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 46) if font_path.exists() else ImageFont.load_default()
    draw.text((24, 15), EXPECTED, font=font, fill="black")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return Response(stream.getvalue(), mimetype="image/png")

@app.post("/check")
def check():
    matched = request.form.get("text", "").strip().upper() == EXPECTED
    return ("SUCCESS" if matched else "FAILED"), (200 if matched else 400)


def main():
    global EXPECTED
    EXPECTED = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(5))
    server = make_server(HOST, PORT, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            try:
                page = browser.new_page()
                page.goto(f"http://{HOST}:{PORT}/")
                image_bytes = page.locator('[data-qa="local-test-picture"]').screenshot()
                image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                recognized = pytesseract.image_to_string(image, config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
                recognized = "".join(c for c in recognized.upper() if c.isalnum())
                print("OCR result:", recognized)
                page.locator('[data-qa="local-test-input"]').fill(recognized)
                page.get_by_role("button", name="Отправить").click()
                page.wait_for_load_state("domcontentloaded")
                print("Result:", page.locator("body").inner_text())
            finally:
                browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
