# Local OCR test inside hh_auto_apply

The test is integrated into the existing `run.py` entrypoint. It only uses
127.0.0.1 and does not interact with hh.ru or any third-party CAPTCHA.

1. Install Tesseract OCR and add `tesseract.exe` to PATH.
2. From the project root, run `pip install -r requirements-ocr-demo.txt`.
3. If Chromium is not installed, run `python -m playwright install chromium`.
4. Run `python run.py --local-ocr-demo`.

The normal `python run.py` command is unchanged. Existing `.env`, credentials,
and other user configuration files are not included in this update.

The demo displays a local form, reads a synthetic image, enters the OCR result,
submits the form, and prints SUCCESS or FAILED. OCR accuracy is not guaranteed.
