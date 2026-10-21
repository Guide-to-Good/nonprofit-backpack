"""How the piping folds into a web app: a form in, a live step log while it runs, a download when done.
Not hosted; styled with one Pico CSS link.

    pip install fastapi uvicorn python-multipart
    OPENROUTER_API_KEY=... uvicorn examples.integrate_fastapi:app --reload --port 8765

Everything the CLI does is the same calls: Intake -> create_backpack -> Backpack.to_bytes().
Three things an integrator must get right, all shown here:
  * run the funnel in a worker thread, never in the request handler: the crawl takes a minute, and the
    crawler drives a real browser with Playwright's synchronous API, which cannot run inside an event loop.
  * pass a `log` callable and show `backpack.issues`, so a failed lookup or crawl is visible, not silent.
  * supply the creator identity. Here it is the same saved creator ID the CLI uses; a real app passes
    its own user id, e.g. f"human:{user.id}".
Documents go to LocalStorage (inside the zip) unless you pass a Storage adapter (see storage_s3.py).
"""
from __future__ import annotations

import html
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from nonprofit_backpack import DocumentInput, Intake, create_backpack, get_creator_id

app = FastAPI()
JOBS: dict[str, dict] = {}          # id -> {lines, done, error, issues, filename, data, backpack_id}; in-memory, demo only

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
<button>Create backpack</button> <small>Creator: <code>CREATOR</code></small>
</form></main></body></html>"""
PROGRESS = HEAD + """<h1 id=title aria-busy=true>Building your backpack…</h1>
<p id=done hidden><a role=button id=dl href="#">Download</a> &nbsp; <a href="/">Start again</a></p>
<article id=issues hidden><h3>Steps that did not succeed</h3><ul id=issuelist></ul></article>
<article><h3>Step log</h3><pre id=log></pre></article>
<p id=meta></p>
<script>
const id = location.pathname.split("/").pop();
async function tick() {
  const j = await (await fetch(`/job/${id}/status`)).json();
  document.getElementById("log").textContent = j.lines.join("\\n");
  if (!j.done) return setTimeout(tick, 1000);
  const t = document.getElementById("title"); t.removeAttribute("aria-busy");
  t.textContent = j.error ? "Something went wrong" : "Backpack built";
  if (j.issues.length) { document.getElementById("issues").hidden = false;
    document.getElementById("issuelist").innerHTML = j.issues.map(i => `<li>${i}</li>`).join(""); }
  if (!j.error) { document.getElementById("dl").href = `/download/${id}`; document.getElementById("dl").textContent = `Download ${j.filename}`;
    document.getElementById("done").hidden = false; document.getElementById("meta").innerHTML = `Backpack id <code>${j.backpack_id}</code> · creator <code>${j.creator}</code>`; }
}
tick();
</script></main></body></html>"""


@app.get("/", response_class=HTMLResponse)
def form():
    return FORM.replace("CREATOR", get_creator_id())


@app.post("/")
def start(name: str = Form(""), legal_name: str = Form(""), country: str = Form(""), summary: str = Form(""),
          access_org: str = Form("public"), access_about: str = Form("public"), redraft: str = Form(""),
          ein: str = Form(""), website: str = Form(""), kind: str = Form(""), access: str = Form("private"),
          document: UploadFile | None = None):
    intake = Intake(typed={"name": name, "legal_name": legal_name, "country": country, "summary": summary},
                    ein=ein, website=website, access={"organization": access_org, "about": access_about})
    if document and document.filename:
        tmp = Path(tempfile.mkdtemp()) / document.filename
        tmp.write_bytes(document.file.read())
        intake.documents.append(DocumentInput(path=str(tmp), kind=kind, access=access))
    job_id = str(uuid.uuid4())
    job = JOBS[job_id] = {"lines": [], "done": False, "error": "", "issues": [], "creator": get_creator_id()}

    def run():
        try:
            bp = create_backpack(intake, creator=job["creator"], redraft=bool(redraft), log=job["lines"].append)
            job.update(issues=bp.issues, filename=f"{bp.title or 'backpack'}-backpack.zip", data=bp.to_bytes(), backpack_id=bp.id)
        except Exception as e:          # a bug or an unreadable document; show it rather than hang
            job["error"] = f"{type(e).__name__}: {e}"; job["lines"].append(job["error"])
        job["done"] = True

    threading.Thread(target=run, daemon=True).start()
    return RedirectResponse(f"/job/{job_id}", status_code=303)


@app.get("/job/{job_id}", response_class=HTMLResponse)
def progress(job_id: str):
    return PROGRESS


@app.get("/job/{job_id}/status")
def status(job_id: str):
    j = JOBS[job_id]
    return JSONResponse({k: j.get(k) for k in ("lines", "done", "error", "issues", "filename", "backpack_id", "creator")})


@app.get("/download/{job_id}")
def download(job_id: str):
    j = JOBS[job_id]
    return Response(j["data"], media_type="application/zip", headers={"content-disposition": f'attachment; filename="{j["filename"]}"'})
