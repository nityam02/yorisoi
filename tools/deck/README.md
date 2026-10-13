# Pitch deck builder

Fills the AI Builder Cup's prescribed template (`template.pptx`, downloaded from the submission page) with the Yorisoi
content and exports a PDF for the dashboard (limit 5 MB).

```bash
uv run --no-project --with python-pptx --with pillow python tools/deck/build_deck.py --pdf \
    --prototype-url https://YOUR-SERVICE.a.run.app
```

Output: `tools/deck/out/Yorisoi-Pitch-Deck.pptx` and `.pdf`. Without `--prototype-url` the links slide says
"Live link: added at deployment".

The PDF step uses LibreOffice. For the template's look, LibreOffice must see the fonts: copy Google Sans Flex
(Regular, Medium, SemiBold) and Noto Sans JP (Regular, Medium) from Google Fonts into
`~/Library/Application Support/LibreOffice/4/user/fonts/` (macOS). Screenshots in `assets/` come from the demo
recordings; all residents shown are fictional.
