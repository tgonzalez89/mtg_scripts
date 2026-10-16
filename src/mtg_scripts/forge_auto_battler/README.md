Controls Forge Adventure matches between AI decks and records simulation results through desktop automation.

The command module is a lightweight launcher with `main(argv=None) -> int`. Import and `--help` do not load
Windows desktop automation or OCR packages. Actual runs require Windows, at least four deck names, the automation
dependencies, `tesserocr`, Tesseract data, and an installed/running Forge instance. Missing prerequisites return status 1.

Set `MTG_SCRIPTS_TESSDATA_DIR` or pass `--tessdata-dir PATH` to select the validated tessdata directory; the default
remains `C:\Program Files\Tesseract-OCR\tessdata`. OCR helpers live in `ocr.py`, and the focused Forge window is
owned by a per-run session rather than module-global state. The ordinary test suite covers configuration and pure OCR
helpers only; it does not start Forge or automate the desktop.

Desktop, keep-awake, and match orchestration remain in the feature-local `runtime.py`, imported only after validation.
Match selection, statistics, existing asset paths, and debug behavior are unchanged. Do not import the runtime
to inspect command arguments or run it on a headless/non-Windows host.
