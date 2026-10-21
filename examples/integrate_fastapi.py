"""How the piping folds into a web app: a form in, a backpack zip out. Not hosted; styled with one Pico CSS link.

    pip install fastapi uvicorn python-multipart
    OPENROUTER_API_KEY=... uvicorn examples.integrate_fastapi:app --reload --port 8765

Everything the CLI does is the same three calls: Intake -> create_backpack -> Backpack.to_bytes().
Your app supplies the creator identity (your user id) and, if you store documents yourself,
a Storage adapter (see storage_s3.py).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import HTMLResponse, Response

from nonprofit_backpack import DocumentInput, Intake, create_backpack

app = FastAPI()

FORM = """<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Nonprofit Backpack</title><link rel=stylesheet href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css"></head>
<body><main class=container>
<hgroup><h1>Nonprofit Backpack</h1><p>Fill in what you have. Typed values win; the EIN and website fill the rest. You get a zip.</p></hgroup>
<form method=post enctype=multipart/form-data>
<article><h2>1. Essentials</h2>
<div class=grid><label>Organization name <input name=name></label><label>Organization legal name <input name=legal_name></label></div>
<div class=grid><label>Country (ISO code) <input name=country placeholder="US"></label>
<label>Access for organization.md <select name=access_org><option>public<option>private</select></label></div>
<label>Summary <textarea name=summary rows=3 placeholder="2-3 sentences: who you are and what you do"></textarea></label>
<label>Access for about.md <select name=access_about><option>public<option>private</select></label></article>
<article><h2>2. EIN and 3. Website <small>(optional)</small></h2>
<div class=grid><label>EIN (US) <input name=ein placeholder="12-3456789"></label><label>Website <input name=website placeholder="example.org"></label></div></article>
<article><h2>4. Document <small>(optional)</small></h2>
<div class=grid><label>File <input type=file name=document></label><label>Kind <input name=kind placeholder="audit, registration certificate"></label>
<label>Access <select name=access><option>private<option>public</select></label></div></article>
<button>Create backpack</button> <small>The website crawl takes about a minute.</small>
</form></main></body></html>"""


@app.get("/", response_class=HTMLResponse)
def form():
    return FORM


@app.post("/")
async def create(name: str = Form(""), legal_name: str = Form(""), country: str = Form(""), summary: str = Form(""),
                 access_org: str = Form("public"), access_about: str = Form("public"),
                 ein: str = Form(""), website: str = Form(""), kind: str = Form(""), access: str = Form("private"),
                 document: UploadFile | None = None):
    intake = Intake(typed={"name": name, "legal_name": legal_name, "country": country, "summary": summary},
                    ein=ein, website=website, access={"organization": access_org, "about": access_about})
    tmp = None
    if document and document.filename:
        tmp = Path(tempfile.mkdtemp()) / document.filename
        tmp.write_bytes(await document.read())
        intake.documents.append(DocumentInput(path=str(tmp), kind=kind, access=access))
    backpack = create_backpack(intake, creator=f"human:{'your-user-id-here'}")
    return Response(backpack.to_bytes(), media_type="application/zip",
                    headers={"content-disposition": f'attachment; filename="{backpack.title or "backpack"}-backpack.zip"'})
