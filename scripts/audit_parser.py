#!/usr/bin/env python3
"""감사보고서 원문(document.xml) 파서 — 설정 기반. ★ 계정명 문자열 리터럴을 코드에 두지 않는다.

계정명 사전은 config/account_aliases.yaml 에서 읽는다(하드코딩 금지 규칙 준수).
표준 라이브러리만. 스파이크/진단 스크립트가 공용으로 import 한다.
"""
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://opendart.fss.or.kr/api"
ROOT = Path(__file__).resolve().parents[1]
ALIASES_PATH = ROOT / "config" / "account_aliases.yaml"

TAG_RE = re.compile(r"<[^>]+>")
ROW_RE = re.compile(r"<TR[ >].*?</TR>", re.I | re.S)
CELL_RE = re.compile(r"<T[DEHU][ >].*?</T[DEHU]>", re.I | re.S)
# 화폐성 숫자: 콤마 그룹(1,234) 또는 4자리 이상. 각주 번호(1~3자리 단독)는 값으로 안 본다.
NUM_RE = re.compile(r"^\(?-?(\d{1,3}(,\d{3})+|\d{4,})\)?$")


def load_key():
    k = os.environ.get("OPENDART_API_KEY")
    if k:
        return k.strip()
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("OPENDART_API_KEY") and "=" in line:
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("OPENDART_API_KEY 없음")


KEY = load_key()


def load_aliases(path=ALIASES_PATH):
    """account_aliases.yaml → (aliases {account:[kw...]}, diagnose_target, receivable_base). 최소 파서."""
    aliases, target, base = {}, None, []
    in_aliases = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("diagnose_target:"):
            target = s.split(":", 1)[1].strip()
            continue
        if s.startswith("receivable_base:"):
            base = _inline_list(s.split(":", 1)[1])
            continue
        if s == "aliases:":
            in_aliases = True
            continue
        if in_aliases and ":" in s and "[" in s:
            key, val = s.split(":", 1)
            aliases[key.strip()] = _inline_list(val)
    return aliases, target, base


def _inline_list(val):
    return [w.strip() for w in val.strip().strip("[]").split(",") if w.strip()]


def get_raw(path, params, retries=2):
    q = dict(params)
    q["crtfc_key"] = KEY
    url = f"{BASE}/{path}?{urllib.parse.urlencode(q)}"
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "spike/2.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.4 * (i + 1))
    return last


def get_json(path, params, retries=2):
    b = get_raw(path, params, retries)
    if isinstance(b, Exception):
        return {"status": "ERR", "message": str(b)}
    try:
        return json.loads(b.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"status": "ERR", "message": str(e)}


def _decode(b):
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "ignore")


def fetch_doc_text(rcept_no):
    blob = get_raw("document.xml", {"rcept_no": rcept_no})
    if isinstance(blob, Exception) or not blob or blob[:2] != b"PK":
        return ""
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return ""
    return "".join(_decode(zf.read(n)) for n in zf.namelist())


def parse_rows(text):
    """표의 각 행을 (라벨(공백제거), [화폐성숫자셀]) 로 반환."""
    rows = []
    for r in ROW_RE.findall(text):
        cells = [TAG_RE.sub("", c).replace("&nbsp;", " ").replace("&cr;", "").strip()
                 for c in CELL_RE.findall(r)]
        if not cells:
            continue
        label = cells[0].replace(" ", "")
        nums = [c for c in cells[1:] if NUM_RE.match(c.replace(" ", ""))]
        rows.append((label, nums))
    return rows


def flat_text(text):
    return re.sub(r"\s+", "", TAG_RE.sub("", text))


def account_in_numeric_row(rows, alias_list):
    for label, nums in rows:
        if nums and any(a.replace(" ", "") in label for a in alias_list):
            return True
    return False


def alias_in_text(flat, alias_list):
    return any(a.replace(" ", "") in flat for a in alias_list)


def extract_found(rows, aliases):
    """계정별로 '숫자 있는 표 행에 별칭이 등장' 하면 확보로 본다."""
    return {acct for acct, al in aliases.items() if account_in_numeric_row(rows, al)}
