"""How the piping folds into a web app: a form in, a backpack zip out. Not hosted, not styled.

    pip install fastapi uvicorn python-multipart
    OPENROUTER_API_KEY=... uvicorn examples.integrate_fastapi:app --reload

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

FORM = """<form method=post enctype=multipart/form-data>
<p>Organization name <input name=name> Legal name <input name=legal_name> Country <input name=country size=3></p>
<p>Summary <textarea name=summary rows=3 cols=60></textarea></p>
<p>EIN <input name=ein> Website <input name=website></p>
<p>Document <input type=file name=document> kind <input name=kind> access <select name=access><option>private<option>public</select></p>
<button>Create backpack</button></form>"""


@app.get("/", response_class=HTMLResponse)
def form():
    return FORM


@app.post("/")
async def create(name: str = Form(""), legal_name: str = Form(""), country: str = Form(""), summary: str = Form(""),
                 ein: str = Form(""), website: str = Form(""), kind: str = Form(""), access: str = Form("private"),
                 document: UploadFile | None = None):
    intake = Intake(typed={"name": name, "legal_name": legal_name, "country": country, "summary": summary},
                    ein=ein, website=website)
    tmp = None
    if document and document.filename:
        tmp = Path(tempfile.mkdtemp()) / document.filename
        tmp.write_bytes(await document.read())
        intake.documents.append(DocumentInput(path=str(tmp), kind=kind, access=access))
    backpack = create_backpack(intake, creator=f"human:{'your-user-id-here'}")
    return Response(backpack.to_bytes(), media_type="application/zip",
                    headers={"content-disposition": f'attachment; filename="{backpack.title or "backpack"}-backpack.zip"'})
