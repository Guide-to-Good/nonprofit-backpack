"""How the piping folds into a web app: a form in, a result page with the step log and a download link out.
Not hosted; styled with one Pico CSS link.

    pip install fastapi uvicorn python-multipart
    OPENROUTER_API_KEY=... uvicorn examples.integrate_fastapi:app --reload --port 8765

Everything the CLI does is the same calls: Intake -> create_backpack -> Backpack.to_bytes().
Two things an integrator must get right, both shown here:
  * the handler is a plain `def`, not `async def`: the crawler drives a real browser with Playwright's
    synchronous API, which cannot run inside an event loop. FastAPI runs sync handlers in a thread pool.
  * pass a `log` and show `backpack.issues`, so a failed lookup or crawl is visible rather than silent.
Your app supplies the creator identity (your user id) and, if you store documents yourself, a Storage
adapter (see storage_s3.py).
"""
from __future__ import annotations

import html
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import HTMLResponse, Response

from nonprofit_backpack import DocumentInput, Intake, create_backpack

app = FastAPI()
RESULTS: dict[str, tuple[str, bytes]] = {}      # id -> (filename, zip bytes); in-memory, demo only

HEAD = """<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Nonprofit Backpack</title><link rel=stylesheet href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css"></head><body><main class=container>"""
FORM = HEAD + """<hgroup><h1>Nonprofit Backpack</h1><p>Fill in what you have. Typed values win; the EIN and website fill the rest. You get a zip.</p></hgroup>
<form method=post enctype=multipart/form-data>
<article><h2>1. Essentials</h2>
<div class=grid><label>Organization name <input name=name></label><label>Organization legal name <input name=legal_name></label></div>
<div class=grid><label>Country (ISO code) <input name=country placeholder="US"></label>
<label>Access for organization.md <select name=access_org><option>public<option>private</select></label></div>
<label>Summary <textarea name=summary rows=3 placeholder="2-3 sentences: who you are and what you do"></textarea></label>
<div class=grid><label>Access for about.md <select name=access_about><option>public<option>private</select></label>
<label><input type=checkbox name=redraft value=1> Let the LLM redraft my summary using everything found</label></div></article>
<article><h2>2. EIN and 3. Website <small>(optional)</small></h2>
<div class=grid><label>EIN (US) <input name=ein placeholder="12-3456789"></label><label>Website <input name=website placeholder="example.org"></label></div></article>
<article><h2>4. Document <small>(optional)</small></h2>
<div class=grid><label>File <input type=file name=document></label><label>Kind <input name=kind placeholder="audit, registration certificate"></label>
<label>Access <select name=access><option>private<option>public</select></label></div></article>
<button>Create backpack</button> <small>The website crawl takes about a minute; this page will wait.</small>
</form></main></body></html>"""


@app.get("/", response_class=HTMLResponse)
def form():
    return FORM


@app.post("/", response_class=HTMLResponse)
def create(name: str = Form(""), legal_name: str = Form(""), country: str = Form(""), summary: str = Form(""),
           access_org: str = Form("public"), access_about: str = Form("public"), redraft: str = Form(""),
           ein: str = Form(""), website: str = Form(""), kind: str = Form(""), access: str = Form("private"),
           document: UploadFile | None = None):
    intake = Intake(typed={"name": name, "legal_name": legal_name, "country": country, "summary": summary},
                    ein=ein, website=website, access={"organization": access_org, "about": access_about})
    if document and document.filename:
        tmp = Path(tempfile.mkdtemp()) / document.filename
        tmp.write_bytes(document.file.read())
        intake.documents.append(DocumentInput(path=str(tmp), kind=kind, access=access))

    steps: list[str] = []
    backpack = create_backpack(intake, creator="human:your-user-id-here", redraft=bool(redraft), log=steps.append)
    rid = str(uuid.uuid4())
    RESULTS[rid] = (f"{backpack.title or 'backpack'}-backpack.zip", backpack.to_bytes())

    issues = "".join(f"<li>{html.escape(i)}</li>" for i in backpack.issues)
    return HEAD + f"""<h1>Backpack built</h1>
<p><a role=button href="/download/{rid}">Download {html.escape(RESULTS[rid][0])}</a> &nbsp; <a href="/">Start again</a></p>
{f'<article><h3>Steps that did not succeed</h3><ul>{issues}</ul></article>' if issues else ''}
<article><h3>Step log</h3><pre>{html.escape(chr(10).join(steps))}</pre></article>
<p>Backpack id <code>{backpack.id}</code></p></main></body></html>"""


@app.get("/download/{rid}")
def download(rid: str):
    filename, data = RESULTS.pop(rid)
    return Response(data, media_type="application/zip", headers={"content-disposition": f'attachment; filename="{filename}"'})
