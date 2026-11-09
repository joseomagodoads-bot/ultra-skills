#!/usr/bin/env python3
"""
scan-ultra: lê uma página inteira de uma vez e transforma em um mapa estruturado.

Em vez de ler a página aos pedaços, o script baixa tudo em paralelo (página,
CSS, robots.txt, sitemap.xml, llms.txt e, se pedido, os links internos), extrai
tudo o que importa para vender e confere se o próprio mapeamento está certo.

Uso:
  python3 scan.py URL [URL ...]               # uma ou várias páginas, em paralelo
  python3 scan.py --arquivo urls.txt          # uma URL por linha
  python3 scan.py URL --links                 # também testa os links internos
  python3 scan.py URL --print                 # salva print desktop e mobile
  python3 scan.py URL --navegador nenhum      # só HTTP, sem abrir navegador

No Windows use "python" ou "py" no lugar de "python3".

Como lê (cascata automática):
  1. HTTP direto, com cabeçalhos de navegador real (passa pela maioria dos firewalls)
  2. Se o site for montado em JavaScript ou bloquear robôs: abre um navegador sem janela
     (Playwright, se instalado; senão o Chrome, Edge, Brave ou Chromium do próprio computador)
  3. Se nada abrir: lê os dados embutidos na página (Next.js, JSON) e avisa o que faltou
Depois lê sozinho as páginas-chave (preços, termos, contato, reembolso, sobre, FAQ) para
completar o que a página principal não mostra (CNPJ, garantia, contato).

Saída (pasta --saida, padrão ./scan-ultra-saida):
  <site>.json        mapa completo
  <site>.md          resumo para leitura rápida
  comparativo.md     tabela lado a lado, quando há mais de uma URL

Só usa a biblioteca padrão do Python 3.8+. Opcionais: certifi (certificados no macOS),
brotli, playwright. Nenhum é obrigatório.
"""

from __future__ import annotations

import argparse
import colorsys
import glob
import gzip
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

VERSAO = "2.0.0"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")
MAX_BYTES = 6_000_000
try:  # brotli é opcional
    import brotli  # type: ignore
except ImportError:
    brotli = None
RE_BLOQUEIO = re.compile(r"just a moment|cf-chl|attention required|captcha|access denied|"
                         r"verify you are human|ddos protection|bot detection|perimeterx|datadome", re.I)


def _contexto_ssl_certifi():
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return None

# --------------------------------------------------------------------------
# Rede
# --------------------------------------------------------------------------


def baixar(url: str, timeout: float = 20.0, metodo: str = "GET", max_bytes: int = MAX_BYTES) -> dict:
    """Baixa uma URL e mede o tempo. Nunca levanta exceção: devolve o erro no dict."""
    req = Request(url, method=metodo, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate" + (", br" if brotli else ""),
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
    })
    t0 = time.perf_counter()
    out = {"url": url, "status": None, "url_final": url, "ttfb_ms": None, "total_ms": None,
           "bytes": 0, "headers": {}, "texto": "", "erro": None, "bloqueado": False}
    try:
        try:
            try:
                resp = urlopen(req, timeout=timeout)
            except URLError as e:  # certificado: comum no Python do macOS → tenta com certifi
                ctx = _contexto_ssl_certifi()
                if ctx is None or not isinstance(getattr(e, "reason", None), ssl.SSLError):
                    raise
                resp = urlopen(req, timeout=timeout, context=ctx)
        except HTTPError as e:  # 4xx/5xx ainda têm corpo
            resp = e
        out["ttfb_ms"] = round((time.perf_counter() - t0) * 1000)
        out["status"] = resp.getcode() if hasattr(resp, "getcode") else resp.code
        out["url_final"] = resp.geturl() if hasattr(resp, "geturl") else url
        hdr = {k.lower(): v for k, v in resp.headers.items()}
        out["headers"] = {k: hdr[k] for k in (
            "content-type", "content-encoding", "server", "x-powered-by", "cache-control",
            "content-security-policy", "strict-transport-security", "x-vercel-id", "cf-ray",
        ) if k in hdr}
        corpo = b"" if metodo == "HEAD" else resp.read(max_bytes + 1)
        enc = hdr.get("content-encoding", "")
        if "gzip" in enc:
            corpo = gzip.decompress(corpo)
        elif "deflate" in enc:
            try:
                corpo = zlib.decompress(corpo)
            except zlib.error:
                corpo = zlib.decompress(corpo, -zlib.MAX_WBITS)
        elif "br" in enc and brotli:
            corpo = brotli.decompress(corpo)
        out["bytes"] = len(corpo)
        out["texto"] = decodificar(corpo, hdr.get("content-type", ""))
        if out["status"] in (401, 403, 429, 503) and (RE_BLOQUEIO.search(out["texto"][:20000])
                                                     or "cloudflare" in hdr.get("server", "").lower()
                                                     or out["status"] in (403, 429)):
            out["bloqueado"] = True
    except (URLError, OSError, ValueError) as e:
        motivo = getattr(e, "reason", e)
        out["erro"] = f"{type(e).__name__}: {motivo}"
        if isinstance(motivo, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(motivo):
            out["erro"] += (" | Certificado: rode 'pip install certifi' (no macOS também: "
                            "abra 'Install Certificates.command' na pasta do Python)")
    out["total_ms"] = round((time.perf_counter() - t0) * 1000)
    return out


def decodificar(corpo: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    charset = m.group(1) if m else None
    if not charset:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", corpo[:4096], re.I)
        charset = m.group(1).decode() if m else "utf-8"
    try:
        return corpo.decode(charset, errors="replace")
    except LookupError:
        return corpo.decode("utf-8", errors="replace")


def achar_chrome() -> str | None:
    """Acha Chrome, Edge, Brave ou Chromium instalados no computador."""
    env = os.environ.get("SCAN_ULTRA_CHROME")
    if env and Path(env).exists():
        return env
    candidatos = []
    # headless-shell (do Playwright) é o mais estável para ler páginas sem janela
    for padrao in ("~/.cache/ms-playwright/chromium_headless_shell-*/chrome-*/chrome-headless-shell*",
                   "/opt/pw-browsers/chromium_headless_shell-*/chrome-*/chrome-headless-shell",
                   "~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-*/chrome-headless-shell",
                   os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright", "chromium_headless_shell-*", "chrome-*",
                                "chrome-headless-shell.exe")):
        candidatos += sorted(glob.glob(os.path.expanduser(padrao)), reverse=True)
    if sys.platform.startswith("win"):
        for base in (os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", "")):
            if base:
                candidatos += [rf"{base}\Google\Chrome\Application\chrome.exe",
                               rf"{base}\Microsoft\Edge\Application\msedge.exe",
                               rf"{base}\BraveSoftware\Brave-Browser\Application\brave.exe",
                               rf"{base}\Chromium\Application\chrome.exe"]
    elif sys.platform == "darwin":
        candidatos += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                       "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                       "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                       "/Applications/Chromium.app/Contents/MacOS/Chromium",
                       os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    for nome in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
                 "microsoft-edge-stable", "brave-browser", "chrome", "msedge"):
        w = shutil.which(nome)
        if w:
            candidatos.append(w)
    for padrao in ("~/.cache/ms-playwright/chromium-*/chrome-*/chrome", "/opt/pw-browsers/chromium-*/chrome-*/chrome",
                   "~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"):
        candidatos += sorted(glob.glob(os.path.expanduser(padrao)), reverse=True)
    return next((c for c in candidatos if c and Path(c).exists()), None)


def _render_playwright(url: str, timeout: float, prints: bool, pasta: Path, slug: str) -> dict:
    from playwright.sync_api import sync_playwright  # ImportError tratado por quem chama
    out = {"html": "", "prints": [], "erro": None, "total_ms": None, "console_erros": [], "motor": "playwright"}
    t0 = time.perf_counter()
    with sync_playwright() as p:
        nav = p.chromium.launch()
        for nome, vw, vh, mobile, ua in (("desktop", 1440, 900, False, UA), ("mobile", 390, 844, True, UA_MOBILE)):
            if nome == "mobile" and not prints:
                break
            ctx = nav.new_context(viewport={"width": vw, "height": vh}, is_mobile=mobile, user_agent=ua, locale="pt-BR")
            pg = ctx.new_page()
            if nome == "desktop":
                pg.on("console", lambda m: out["console_erros"].append(m.text[:200]) if m.type == "error" else None)
            try:
                pg.goto(url, wait_until="networkidle", timeout=int(timeout * 1000))
            except Exception:  # noqa: BLE001 - networkidle pode nunca chegar; usa o que carregou
                pg.wait_for_timeout(1500)
            if nome == "desktop":
                pg.mouse.wheel(0, 20000)  # dispara conteúdo carregado ao rolar
                pg.wait_for_timeout(800)
                out["html"] = pg.content()
                out["total_ms"] = round((time.perf_counter() - t0) * 1000)
            if prints:
                arq = pasta / f"{slug}-{nome}.png"
                pg.screenshot(path=str(arq), full_page=True)
                out["prints"].append(str(arq))
            ctx.close()
        nav.close()
    return out


def _render_chrome(chrome: str, url: str, timeout: float, prints: bool, pasta: Path, slug: str) -> dict:
    out = {"html": "", "prints": [], "erro": None, "total_ms": None, "console_erros": [],
           "motor": f"navegador do sistema ({Path(chrome).name})"}
    t0 = time.perf_counter()
    perfil = tempfile.mkdtemp(prefix="scan-ultra-")
    shell = "headless-shell" in Path(chrome).name
    base = [chrome] + ([] if shell else ["--headless=new"]) + ["--disable-gpu", "--disable-component-update",
                                                               "--disable-background-networking", "--hide-scrollbars", "--mute-audio", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions", f"--user-data-dir={perfil}", "--lang=pt-BR"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        base.append("--no-sandbox")
    try:
        limite = min(timeout, 30) + 10
        r = subprocess.run(base + [f"--user-agent={UA}", "--virtual-time-budget=8000", "--dump-dom", url],
                           capture_output=True, timeout=limite)
        out["html"] = r.stdout.decode("utf-8", errors="replace")
        if not out["html"].strip():
            out["erro"] = "o navegador não devolveu conteúdo: " + r.stderr.decode("utf-8", "replace")[-300:]
        out["total_ms"] = round((time.perf_counter() - t0) * 1000)
        if prints:
            for nome, tam, ua in (("desktop", "1440,3200", UA), ("mobile", "390,2800", UA_MOBILE)):
                arq = (pasta / f"{slug}-{nome}.png").resolve()
                try:
                    subprocess.run(base + [f"--user-agent={ua}", f"--window-size={tam}", "--virtual-time-budget=8000",
                                           f"--screenshot={arq}", url], capture_output=True, timeout=limite)
                except subprocess.TimeoutExpired:
                    pass
                if arq.exists():
                    out["prints"].append(str(arq))
    except subprocess.TimeoutExpired:
        out["erro"] = (f"{Path(chrome).name} travou ao abrir a página (comum em servidor/contêiner). "
                       "Instale o Playwright: pip install playwright && playwright install chromium")
    except OSError as e:
        out["erro"] = f"não consegui abrir o navegador: {e}"
    finally:
        shutil.rmtree(perfil, ignore_errors=True)
    return out


def renderizar(url: str, timeout: float, prints: bool, pasta: Path, slug: str, motor: str = "auto") -> dict:
    """Abre a página num navegador sem janela. Tenta Playwright e depois o navegador do sistema."""
    erros = []
    if motor in ("auto", "playwright"):
        try:
            out = _render_playwright(url, timeout, prints, pasta, slug)
            if out["html"]:
                return out
        except ImportError:
            erros.append("Playwright não instalado")
        except Exception as e:  # noqa: BLE001
            erros.append(f"Playwright: {str(e)[:160]}")
    if motor in ("auto", "chrome"):
        chrome = achar_chrome()
        if chrome:
            out = _render_chrome(chrome, url, timeout, prints, pasta, slug)
            if out["html"]:
                return out
            erros.append(out["erro"] or "navegador sem conteúdo")
        else:
            erros.append("nenhum Chrome/Edge/Brave/Chromium encontrado (ou defina SCAN_ULTRA_CHROME com o caminho)")
    return {"html": "", "prints": [], "erro": "; ".join(erros) or "navegador desativado", "total_ms": None,
            "console_erros": [], "motor": None}


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

PULAR = {"script", "style", "noscript", "template", "svg", "head"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
CAPTURAR = {"a", "button", "h1", "h2", "h3", "h4", "h5", "h6", "label", "summary", "title", "option"}


class MapaParser(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.lang = None
        self.title = ""
        self.metas: dict[str, str] = {}
        self.links_head: list[dict] = []
        self.headings: list[dict] = []
        self.ancoras: list[dict] = []
        self.botoes: list[dict] = []
        self.forms: list[dict] = []
        self.campos_soltos: list[dict] = []
        self.imagens: list[dict] = []
        self.scripts_src: list[str] = []
        self.scripts_inline: list[str] = []
        self.jsonld: list[str] = []
        self.styles: list[str] = []
        self.estilos_inline: list[str] = []
        self.iframes: list[str] = []
        self.videos: list[str] = []
        self.ids_raiz: list[str] = []
        self.secoes: list[dict] = [{"titulo": "(topo)", "nivel": 0, "linhas": []}]
        self._pular: list[str] = []
        self._captura: list[dict] = []
        self._script_buf: list[str] | None = None
        self._script_tipo = ""
        self._style_buf: list[str] | None = None
        self._form_atual: dict | None = None
        self._labels_for: dict[str, str] = {}

    # ---- tags ----
    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if a.get("style"):
            self.estilos_inline.append(a["style"])
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "meta":
            chave = a.get("name") or a.get("property") or a.get("http-equiv")
            if chave and "content" in a:
                self.metas[chave.lower()] = a["content"]
        elif tag == "link":
            self.links_head.append({"rel": a.get("rel", "").lower(), "href": urljoin(self.base, a.get("href", "")),
                                    "hreflang": a.get("hreflang")})
        elif tag == "script":
            if a.get("src"):
                self.scripts_src.append(urljoin(self.base, a["src"]))
            self._script_buf = []
            self._script_tipo = a.get("type", "").lower()
        elif tag == "style":
            self._style_buf = []
        elif tag == "img":
            self.imagens.append({"src": urljoin(self.base, a.get("src") or a.get("data-src", "")),
                                 "alt": a.get("alt"), "lazy": a.get("loading") == "lazy"})
            for c in self._captura:  # alt de imagem dentro de link/botão conta como texto
                if a.get("alt"):
                    c["texto"].append(a["alt"])
        elif tag == "iframe":
            self.iframes.append(urljoin(self.base, a.get("src", "")))
        elif tag in ("video", "source") and a.get("src"):
            self.videos.append(urljoin(self.base, a["src"]))
        elif tag == "form":
            self._form_atual = {"action": urljoin(self.base, a.get("action", "")) if a.get("action") else "",
                                "method": a.get("method", "get").lower(), "campos": []}
            self.forms.append(self._form_atual)
        elif tag in ("input", "select", "textarea"):
            campo = {"tag": tag, "tipo": a.get("type", "text" if tag == "input" else tag),
                     "nome": a.get("name") or a.get("id") or "", "placeholder": a.get("placeholder", ""),
                     "obrigatorio": "required" in a, "id": a.get("id", ""),
                     "aria": a.get("aria-label", "")}
            if campo["tipo"] not in ("hidden",):
                (self._form_atual["campos"] if self._form_atual else self.campos_soltos).append(campo)
        elif tag == "div" and a.get("id") in ("root", "__next", "app", "__nuxt", "svelte"):
            self.ids_raiz.append(a["id"])

        if tag in PULAR and tag not in VOID:
            self._pular.append(tag)
        if tag in CAPTURAR:
            self._captura.append({"tag": tag, "attrs": a, "texto": []})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in CAPTURAR:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "script" and self._script_buf is not None:
            conteudo = "".join(self._script_buf)
            if "ld+json" in self._script_tipo:
                self.jsonld.append(conteudo)
            elif conteudo.strip():
                self.scripts_inline.append(conteudo[:20000])
            self._script_buf = None
        elif tag == "style" and self._style_buf is not None:
            self.styles.append("".join(self._style_buf))
            self._style_buf = None
        elif tag == "form":
            self._form_atual = None
        if self._pular and tag in PULAR:
            # fecha a ocorrência mais recente dessa tag
            for i in range(len(self._pular) - 1, -1, -1):
                if self._pular[i] == tag:
                    del self._pular[i:]
                    break
        if tag in CAPTURAR:
            for i in range(len(self._captura) - 1, -1, -1):
                if self._captura[i]["tag"] == tag:
                    c = self._captura.pop(i)
                    self._fechar_captura(c)
                    break

    def _fechar_captura(self, c):
        texto = limpar(" ".join(c["texto"]))
        tag, a = c["tag"], c["attrs"]
        if tag == "title" and not self.title:
            self.title = texto
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            nivel = int(tag[1])
            self.headings.append({"nivel": nivel, "texto": texto})
            if nivel <= 2 and texto:
                self.secoes.append({"titulo": texto, "nivel": nivel, "linhas": []})
        elif tag == "a":
            self.ancoras.append({"texto": texto or a.get("aria-label", "") or a.get("title", ""),
                                 "href_bruto": a.get("href", ""), "href": urljoin(self.base, a.get("href", "")),
                                 "classe": a.get("class", ""), "alvo": a.get("target", "")})
        elif tag == "button":
            self.botoes.append({"texto": texto or a.get("aria-label", ""), "tipo": a.get("type", ""),
                                "classe": a.get("class", "")})
        elif tag == "label" and a.get("for"):
            self._labels_for[a["for"]] = texto

    def handle_data(self, data):
        if self._script_buf is not None:
            self._script_buf.append(data)
            return
        if self._style_buf is not None:
            self._style_buf.append(data)
            return
        for c in self._captura:
            c["texto"].append(data)
        if self._pular:
            return
        t = limpar(data)
        if len(t) > 1:
            linhas = self.secoes[-1]["linhas"]
            # títulos já ficam na estrutura; evita repetir a linha do heading
            if not (self._captura and self._captura[-1]["tag"] in ("h1", "h2")):
                if not linhas or linhas[-1] != t:
                    linhas.append(t)

    def finalizar(self):
        while self._captura:
            self._fechar_captura(self._captura.pop())
        for f in self.forms:
            for c in f["campos"]:
                c["label"] = self._labels_for.get(c["id"], "")
        for c in self.campos_soltos:
            c["label"] = self._labels_for.get(c["id"], "")


def limpar(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


# --------------------------------------------------------------------------
# Extração de sinais
# --------------------------------------------------------------------------

RE_PRECO = re.compile(r"R\$\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?|US\$\s?\d[\d.,]*|\$\s?\d[\d.,]*(?:/m[eê]s)?")
RE_PCT = re.compile(r"\b\d{1,3}(?:[.,]\d{1,2})?\s?%")
RE_TEL = re.compile(r"\(?\b\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b")
RE_CNPJ = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
RE_PROVA_NUM = re.compile(
    r"(\+?\s?\d[\d.,]*\s?(?:mil|k|mi|milh[õo]es|M)?\+?)\s+(?:de\s+)?"
    r"(clientes|usu[aá]rios|restaurantes|empresas|lojas|alunos|pedidos|avalia[çc][õo]es|downloads|"
    r"neg[óo]cios|assinantes|vendas|profissionais|pessoas|estabelecimentos|pizzarias|hamburguerias|lanchonetes|"
    r"bares|cl[ií]nicas|academias|escolas|marcas|ag[eê]ncias|lojistas|vendedores|membros|seguidores|"
    r"inscritos|unidades|franquias|deliverys?)", re.I)
RE_EMPRESA = re.compile(r"(?:[A-ZÀ-Ú0-9][\wÀ-ú&.'\-]*,?\s+(?:(?:de|da|do|dos|das|e|&)\s+)?){1,6}"
                        r"(?:LTDA|Ltda\.?|EIRELI|S\.?/?A\.?|EPP|LLC|Inc\.?|Corp\.?|Limited|Ltd\.?)(?=\W|$)")
RE_CHAVE = re.compile(r"pre[çc]os?|planos?|pricing|plans|termos|terms|privacidade|privacy|reembolso|refund|garantia|"
                      r"guarantee|devolu|cancel|contato|contact|fale|sobre|about|quem-somos|faq|ajuda|help|suporte|"
                      r"support|entrega|delivery|shipping|pol[ií]tica|policy", re.I)
RE_BONUS = r"b[oô]nus|brinde|de presente|gr[aá]tis junto|incluso sem custo"
PADROES_TEXTO = {
    "teste_gratis": r"teste\s+gr[aá]tis|gr[aá]tis\s+por\s+\d+\s+dias|\d+\s+dias\s+gr[aá]tis|free\s+trial|sem\s+cart[aã]o",
    "garantia": r"garantia|reembolso|devolu[çc][aã]o\s+do\s+dinheiro|dinheiro\s+de\s+volta|risco\s+zero",
    "cancelamento_livre": r"cancel[ae]\s+quando\s+quiser|sem\s+fidelidade|sem\s+multa",
    "urgencia_escassez": r"vagas|[uú]ltimas|por\s+tempo\s+limitado|s[oó]\s+hoje|at[eé]\s+\d{1,2}/\d{1,2}|primeiros\s+\d+|lote",
    "prova_social": r"depoimento|avalia[çc]|estrelas|★|cases?\s+de\s+sucesso|clientes\s+(?:dizem|falam)|quem\s+usa",
    "desconto": r"desconto|off\b|promo[çc][aã]o|de\s+R\$[^a]{0,20}por\s+R\$|economi[zs]e",
}
RE_CTA = re.compile(
    r"comec|começ|criar|crie|cadastr|assin|compr|quero|test|agend|fale|falar|baix|entrar|planos|escolh|"
    r"garant|solicit|experiment|contrat|pedir|pe[çc]a|chamar|whats|saiba|conhe[çc]|ver\s|simul|calcul|"
    r"start|sign|buy|get\s|try|book|join|demo", re.I)

RASTREADORES = {
    "Meta Pixel": [r"connect\.facebook\.net/[^\"']*fbevents", r"fbq\(\s*['\"]init"],
    "Google Analytics 4": [r"gtag/js\?id=G-", r"['\"]G-[A-Z0-9]{6,}['\"]"],
    "Google Tag Manager": [r"googletagmanager\.com/gtm\.js", r"GTM-[A-Z0-9]{4,}"],
    "Google Ads": [r"['\"/]AW-\d{6,}"],
    "TikTok Pixel": [r"analytics\.tiktok\.com", r"ttq\.load"],
    "Hotjar": [r"static\.hotjar\.com", r"hjid"],
    "Microsoft Clarity": [r"clarity\.ms"],
    "LinkedIn Insight": [r"snap\.licdn\.com"],
    "Pinterest Tag": [r"pintrk\("],
    "RD Station": [r"rdstation|d335luupugsy2\.cloudfront"],
    "HubSpot": [r"js\.hs-scripts\.com|js\.hsforms"],
    "PostHog": [r"posthog"],
    "Plausible": [r"plausible\.io"],
    "Vercel Analytics": [r"/_vercel/insights|va\.vercel-scripts"],
    "Stripe": [r"js\.stripe\.com|checkout\.stripe\.com|buy\.stripe\.com"],
    "Hotmart": [r"hotmart"],
    "Kiwify": [r"kiwify"],
    "Intercom": [r"widget\.intercom\.io"],
    "Crisp": [r"client\.crisp\.chat"],
    "Tawk.to": [r"embed\.tawk\.to"],
    "Zendesk": [r"static\.zdassets\.com"],
    "reCAPTCHA": [r"recaptcha"],
}
IDS_RASTREIO = {
    "ga4": r"\bG-[A-Z0-9]{6,12}\b",
    "gtm": r"\bGTM-[A-Z0-9]{4,8}\b",
    "google_ads": r"\bAW-\d{6,12}\b",
    "meta_pixel": r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{8,20})",
}
STACK = {
    "Next.js": r"__NEXT_DATA__|/_next/static",
    "Nuxt": r"__NUXT__|/_nuxt/",
    "React (SPA)": r"id=[\"']root[\"']|react-dom",
    "Vite": r"/assets/index-[\w-]+\.js|type=[\"']module[\"'][^>]+/assets/",
    "WordPress": r"wp-content|wp-includes",
    "Elementor": r"elementor",
    "Wix": r"wixstatic|_wix",
    "Webflow": r"webflow",
    "Framer": r"framerusercontent|framer\.com",
    "Shopify": r"cdn\.shopify|shopify",
    "Lovable": r"lovable",
    "Bubble": r"bubble\.io|bubbleapps",
    "Cloudflare": r"cdn-cgi|cf-ray",
    "Tailwind": r"\b(?:tw-|text-\w+-\d{3}|bg-\w+-\d{3})",
}
GENERICAS = {"inherit", "initial", "unset", "sans-serif", "serif", "monospace", "system-ui", "-apple-system",
             "blinkmacsystemfont", "cursive", "fantasy", "ui-sans-serif", "ui-serif", "ui-monospace", "emoji"}


def texto_embutido(scripts: list[str], limite: int = 400) -> list[str]:
    """Tira frases de dados JSON embutidos (Next.js, estado inicial de SPAs)."""
    linhas, vistos = [], set()
    for sc in scripts:
        bruto = sc.strip()
        m = re.match(r"^(?:window\.)?[\w.$]+\s*=\s*(\{.*\})\s*;?\s*$", bruto, re.S)
        if m:
            bruto = m.group(1)
        if not bruto.startswith(("{", "[")):
            continue
        try:
            dado = json.loads(bruto)
        except (json.JSONDecodeError, ValueError):
            continue
        pilha = [dado]
        while pilha and len(linhas) < limite:
            d = pilha.pop()
            if isinstance(d, dict):
                pilha.extend(d.values())
            elif isinstance(d, list):
                pilha.extend(d)
            elif isinstance(d, str):
                t = limpar(re.sub(r"<[^>]+>", " ", d))
                if len(t) >= 12 and " " in t and not re.match(r"^(https?:|/|\{|data:)", t) and t not in vistos:
                    vistos.add(t)
                    linhas.append(t)
    return linhas


def trechos(pad: str, texto: str, n: int = 3) -> list[str]:
    return achar(rf"[^.!?\n]{{0,60}}(?:{pad})[^.!?\n]{{0,60}}", texto)[:n]


def achar(padrao, texto, flags=re.I):
    it = padrao.finditer(texto) if isinstance(padrao, re.Pattern) else re.finditer(padrao, texto, flags)
    return sorted(set(m.group(0).strip() for m in it))


def normalizar_cor(c: str) -> str | None:
    c = c.strip().lower()
    if c.startswith("#"):
        h = c[1:]
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h[:3])
        elif len(h) in (6, 8):
            h = h[:6]
        else:
            return None
        return "#" + h if re.fullmatch(r"[0-9a-f]{6}", h) else None
    m = re.match(r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)", c)
    if m:
        r, g, b = (min(255, int(x)) for x in m.groups())
        return f"#{r:02x}{g:02x}{b:02x}"
    m = re.match(r"hsla?\(\s*([\d.]+)(?:deg)?[,\s]+([\d.]+)%[,\s]+([\d.]+)%", c)
    if m:
        h, s, light = float(m.group(1)) / 360, float(m.group(2)) / 100, float(m.group(3)) / 100
        r, g, b = colorsys.hls_to_rgb(h, light, s)
        return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"
    return None


RE_COR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]+\)|hsla?\([^)]+\)")


def extrair_visual(css: str, theme_color: str | None, fontes_links: list[str]) -> dict:
    cores = Counter()
    for m in RE_COR.finditer(css):
        n = normalizar_cor(m.group(0))
        if n:
            cores[n] += 1
    variaveis = {}
    for m in re.finditer(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8}\b|rgba?\([^)]+\)|hsla?\([^)]+\))", css):
        n = normalizar_cor(m.group(2))
        if n and len(variaveis) < 40:
            variaveis.setdefault(m.group(1), n)
    fontes = Counter()
    for m in re.finditer(r"font-family\s*:\s*([^;}{]+)", css, re.I):
        primeira = m.group(1).split(",")[0].strip().strip("\"'").strip()
        if primeira and primeira.lower() not in GENERICAS and not primeira.startswith("var("):
            fontes[primeira] += 1
    for href in fontes_links:
        for fam in re.findall(r"family=([^&:]+)", href):
            fontes[fam.replace("+", " ")] += 5
    neutras = {"#ffffff", "#000000"}
    destaque = [c for c, _ in cores.most_common(30) if c not in neutras and not cinza(c)]
    return {
        "theme_color": theme_color,
        "cores_mais_usadas": [{"cor": c, "usos": n} for c, n in cores.most_common(12)],
        "cores_de_destaque": destaque[:6],
        "variaveis_de_cor": variaveis,
        "fontes": [f for f, _ in fontes.most_common(6)],
    }


def cinza(hexcor: str) -> bool:
    r, g, b = (int(hexcor[i:i + 2], 16) for i in (1, 3, 5))
    return max(r, g, b) - min(r, g, b) < 14


def classificar_link(href: str, host: str, bruto: str = "") -> str:
    if bruto.startswith("#"):
        return "ancora"
    p = urlparse(href)
    if href.startswith(("mailto:",)):
        return "email"
    if href.startswith("tel:"):
        return "telefone"
    if "wa.me" in href or "whatsapp.com" in href:
        return "whatsapp"
    if p.scheme not in ("http", "https"):
        return "outro"
    if p.netloc == host:
        return "ancora" if p.fragment and p.path in ("", "/") else "interno"
    base = host.removeprefix("www.")
    if p.netloc.endswith("." + base) or p.netloc == base:
        return "subdominio"
    return "externo"


REDES = {"instagram.com": "Instagram", "facebook.com": "Facebook", "youtube.com": "YouTube",
         "tiktok.com": "TikTok", "linkedin.com": "LinkedIn", "x.com": "X", "twitter.com": "X",
         "pinterest.com": "Pinterest", "threads.net": "Threads"}


# --------------------------------------------------------------------------
# Montagem do mapa
# --------------------------------------------------------------------------


def montar_mapa(url: str, resp: dict, html: str, css_extra: str, arquivos: dict, origem: str) -> dict:
    base = resp.get("url_final") or url
    host = urlparse(base).netloc
    p = MapaParser(base)
    try:
        p.feed(html)
        p.close()
    except Exception as e:  # noqa: BLE001
        resp.setdefault("avisos", []).append(f"parser: {e}")
    p.finalizar()

    # site em JavaScript sem render: recupera o texto dos dados embutidos
    palavras_html = sum(len(l.split()) for s_ in p.secoes for l in s_["linhas"])
    embutido = []
    if palavras_html < 150 and (origem == "http" or palavras_html < 40):
        embutido = texto_embutido(p.scripts_inline)
        if embutido:
            p.secoes.append({"titulo": "(texto recuperado de dados embutidos na página)", "nivel": 2, "linhas": embutido})
            origem = origem + " + dados embutidos"

    # linhas separadas por \n: os trechos de contexto não atravessam blocos diferentes
    texto_visivel = "\n".join(l for s in p.secoes for l in s["linhas"])
    texto_busca = "\n".join(h["texto"] for h in p.headings) + "\n" + texto_visivel
    palavras = len(texto_visivel.split())

    # links
    links = []
    for a in p.ancoras:
        tipo = classificar_link(a["href"], host, a["href_bruto"]) if a["href_bruto"] else "sem_href"
        links.append({"texto": a["texto"][:120], "destino": a["href"] if a["href_bruto"] else "", "tipo": tipo,
                      "cta": bool(a["texto"] and (RE_CTA.search(a["texto"]) or re.search(r"btn|button|cta", a["classe"], re.I)))})
    ctas = [l for l in links if l["cta"]]
    for b in p.botoes:
        if b["texto"] and (b["tipo"] != "submit" or RE_CTA.search(b["texto"])):
            ctas.append({"texto": b["texto"][:120], "destino": "(botão, ação via JavaScript)", "tipo": "botao", "cta": True})
    contagem_tipos = Counter(l["tipo"] for l in links)

    # cruzamentos
    todo_html = html
    scripts_tudo = "\n".join(p.scripts_src) + "\n" + "\n".join(p.scripts_inline)
    rastreadores = {nome: True for nome, pads in RASTREADORES.items()
                    if any(re.search(pd, scripts_tudo + todo_html, re.I) for pd in pads)}
    ids = {}
    for chave, pad in IDS_RASTREIO.items():
        achados = sorted(set(m.group(1) if m.groups() else m.group(0) for m in re.finditer(pad, todo_html)))
        if achados:
            ids[chave] = achados[:5]
    stack = [nome for nome, pad in STACK.items() if re.search(pad, todo_html, re.I)]

    jsonld_tipos = []
    for bloco in p.jsonld:
        try:
            dado = json.loads(bloco)
        except json.JSONDecodeError:
            continue
        pilha = [dado]
        while pilha:
            d = pilha.pop()
            if isinstance(d, list):
                pilha.extend(d)
            elif isinstance(d, dict):
                t = d.get("@type")
                if t:
                    jsonld_tipos.extend(t if isinstance(t, list) else [t])
                pilha.extend(v for v in d.values() if isinstance(v, (dict, list)))

    redes = sorted({nome for l in links for dom, nome in REDES.items() if dom in l["destino"]})
    whats = sorted({l["destino"] for l in links if l["tipo"] == "whatsapp"})
    tel = sorted({l["destino"] for l in links if l["tipo"] == "telefone"} | set(achar(RE_TEL, texto_visivel)))
    emails = sorted({l["destino"].removeprefix("mailto:") for l in links if l["tipo"] == "email"}
                    | set(achar(RE_EMAIL, texto_visivel)))

    sinais_texto = {k: achar(rf"[^.!?\n]{{0,60}}(?:{pad})[^.!?\n]{{0,60}}", texto_busca)[:6]
                    for k, pad in PADROES_TEXTO.items()}

    css_total = "\n".join(p.styles) + "\n" + "\n".join(p.estilos_inline) + "\n" + css_extra
    fontes_links = [l["href"] for l in p.links_head if "fonts.googleapis" in l["href"]]
    visual = extrair_visual(css_total, p.metas.get("theme-color"), fontes_links)

    h1s = [h["texto"] for h in p.headings if h["nivel"] == 1]
    seo = {
        "title": p.title, "title_tamanho": len(p.title),
        "meta_description": p.metas.get("description", ""),
        "meta_description_tamanho": len(p.metas.get("description", "")),
        "h1": h1s, "h1_quantidade": len(h1s),
        "canonical": next((l["href"] for l in p.links_head if l["rel"] == "canonical"), None),
        "robots_meta": p.metas.get("robots"),
        "lang": p.lang,
        "viewport": p.metas.get("viewport"),
        "og_title": p.metas.get("og:title"), "og_image": p.metas.get("og:image"),
        "hreflang": [l["hreflang"] for l in p.links_head if l["hreflang"]],
        "jsonld_tipos": sorted(set(jsonld_tipos)),
        "imagens_sem_alt": sum(1 for i in p.imagens if not i["alt"]),
        "palavras_visiveis": palavras,
    }

    mapa = {
        "scan_ultra": VERSAO,
        "url": url, "url_final": base, "origem_html": origem,
        "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
        "http": {k: resp.get(k) for k in ("status", "ttfb_ms", "total_ms", "bytes", "headers", "erro")},
        "seo": seo,
        "estrutura": p.headings,
        "secoes": [{"titulo": s["titulo"], "nivel": s["nivel"], "texto": " ".join(s["linhas"])}
                   for s in p.secoes if s["linhas"] or s["nivel"]],
        "ctas": ctas,
        "links_resumo": dict(contagem_tipos),
        "links": links,
        "formularios": p.forms + ([{"action": "(fora de <form>)", "method": "", "campos": p.campos_soltos}]
                                  if p.campos_soltos else []),
        "numeros": {
            "precos": achar(RE_PRECO, texto_visivel),
            "percentuais": achar(RE_PCT, texto_visivel)[:30],
            "prova_social_numerica": sorted(set(
                limpar(" ".join(m.groups())) for m in RE_PROVA_NUM.finditer(texto_busca)
                if not re.search(r"(primeir[oa]s|at[eé]|m[aá]ximo|limite)\s*$", texto_busca[max(0, m.start() - 12):m.start()], re.I)
            ))[:10],
        },
        "sinais_de_oferta": sinais_texto,
        "contato_e_confianca": {
            "whatsapp": whats, "telefones": tel[:5], "emails": emails[:5],
            "cnpj": achar(RE_CNPJ, texto_visivel), "redes": redes,
            "empresa": achar(RE_EMPRESA, texto_visivel)[:3],
            "politicas": sorted({l["destino"] for l in links if l["tipo"] in ("interno", "subdominio")
                                 and re.search(r"termo|terms|privac|reembolso|refund|cancel|pol[ií]tica|policy",
                                               l["texto"] + " " + l["destino"], re.I)})[:8],
            "fontes": {},
        },
        "rastreamento": {"ferramentas": sorted(rastreadores), "ids": ids},
        "tecnologia": {"stack_provavel": stack, "scripts_externos": len(p.scripts_src),
                       "scripts_inline": len(p.scripts_inline), "folhas_css": sum(1 for l in p.links_head if "stylesheet" in l["rel"]),
                       "iframes": p.iframes[:10], "videos": p.videos[:10], "raiz_spa": p.ids_raiz},
        "imagens": {"total": len(p.imagens), "sem_alt": seo["imagens_sem_alt"],
                    "lazy": sum(1 for i in p.imagens if i["lazy"]), "amostra": p.imagens[:15]},
        "identidade_visual": visual,
        "arquivos_do_site": arquivos,
    }
    mapa["sinais_de_oferta"]["bonus"] = trechos(RE_BONUS, texto_busca, 4)
    mapa["verificacao"] = verificar(mapa, html, p)
    if embutido:
        mapa["verificacao"]["lacunas"].insert(0, f"{len(embutido)} trechos vieram de dados embutidos (JSON), não do HTML "
                                                 "renderizado: a ordem na página pode ser outra")
    mapa["sinais"] = sinais(mapa)
    mapa["raio_x"] = raio_x(mapa)
    return mapa


# --------------------------------------------------------------------------
# Conferência do mapeamento
# --------------------------------------------------------------------------


def verificar(mapa: dict, html: str, p: MapaParser) -> dict:
    """Confere o mapa contra o HTML bruto. Se as contagens não batem, o mapa está incompleto."""
    checks = []

    def check(item, esperado, encontrado, ok, nota=""):
        checks.append({"item": item, "esperado": esperado, "encontrado": encontrado, "ok": bool(ok), "nota": nota})

    st = mapa["http"]["status"]
    lido_nav = mapa["origem_html"].startswith(("navegador", "playwright")) and mapa["seo"]["palavras_visiveis"] > 50
    check("Página acessível", 200, st if not lido_nav else f"{st} (lida pelo navegador)", st == 200 or lido_nav,
          mapa["http"].get("erro") or ("site bloqueia robôs; leitura feita pelo navegador" if lido_nav and st != 200 else ""))
    ctype = (mapa["http"]["headers"].get("content-type", "") if mapa["origem_html"].startswith("http")
             else "text/html (renderizado)")
    check("Resposta é HTML", "text/html", ctype, "html" in ctype)
    sem_scripts = re.sub(r"<script\b.*?</script>|<!--.*?-->|<noscript\b.*?</noscript>|<template\b.*?</template>",
                         "", html, flags=re.S | re.I)
    for nome, pad, achado in (
        ("Links <a>", r"<a\b", len(p.ancoras)),
        ("Títulos <h1>–<h6>", r"<h[1-6]\b", len(p.headings)),
        ("Formulários <form>", r"<form\b", len(p.forms)),
        ("Imagens <img>", r"<img\b", len(p.imagens)),
    ):
        bruto = len(re.findall(pad, sem_scripts, re.I))
        check(nome, bruto, achado, bruto == achado, "" if bruto == achado else "contagem do parser difere do HTML bruto")

    texto_bruto = re.sub(r"<[^>]+>", " ", sem_scripts)
    precos_brutos = set(achar(RE_PRECO, texto_bruto))
    precos_mapa = set(mapa["numeros"]["precos"])
    faltando = sorted(precos_brutos - precos_mapa)
    check("Preços capturados", len(precos_brutos), len(precos_mapa), not faltando,
          f"no HTML mas fora do mapa: {', '.join(faltando[:5])}" if faltando else "")
    precos_em_js = sorted(set(achar(RE_PRECO, " ".join(p.scripts_inline))) - precos_mapa)
    if precos_em_js:
        check("Preços só dentro de scripts", 0, len(precos_em_js), False,
              f"conteúdo provavelmente montado por JavaScript: {', '.join(precos_em_js[:5])}")

    palavras = mapa["seo"]["palavras_visiveis"]
    via_nav = mapa["origem_html"].startswith(("navegador", "playwright"))
    depende_js = (not via_nav and palavras < 150
                  and (mapa["tecnologia"]["scripts_externos"] >= 2 or mapa["tecnologia"]["raiz_spa"]))
    nota = ("página montada por JavaScript e nenhum navegador abriu: instale o Playwright "
            "(pip install playwright && playwright install chromium) ou tenha Chrome/Edge instalado" if depende_js
            else "lida pelo navegador" if via_nav
            else ("página curta, mas sem sinais de depender de JavaScript" if palavras < 150 else ""))
    check("Conteúdo legível", "texto da página", f"{palavras} palavras", not depende_js, nota)

    if mapa["url_final"].rstrip("/") != mapa["url"].rstrip("/"):
        check("Sem redirecionamento", mapa["url"], mapa["url_final"], False, "a URL redirecionou")

    erros = [c for c in checks if not c["ok"]]
    graves = [c for c in erros if c["item"] in ("Página acessível", "Resposta é HTML", "Conteúdo legível")]
    confianca = "baixa" if graves else ("média" if erros else "alta")
    lacunas = ["Visual (cores aplicadas, imagens, hierarquia na tela): só visto com --print",
               "Comportamento ao clicar (modais, checkout, cálculos): não executado",
               "Áreas com login e conteúdo carregado depois de interação"]
    if mapa["origem_html"].startswith("http"):
        lacunas.append("Rastreadores carregados via GTM/JavaScript podem não aparecer no HTML")
    return {"confianca": confianca, "checks": checks, "lacunas": lacunas}


def sinais(m: dict) -> list[str]:
    """Achados objetivos, ordenados por gravidade. Só fatos do mapa."""
    achados = []

    def add(grav, texto):
        achados.append((grav, texto))

    c = m["contato_e_confianca"]
    o = m["sinais_de_oferta"]
    if m["http"].get("status") is None and m["seo"]["palavras_visiveis"] == 0:
        add(0, f"Página não foi lida: {m['http'].get('erro') or 'sem resposta'}")
    if m.get("bloqueado"):
        add(0, "O site bloqueia robôs (firewall/Cloudflare)" + (": lido pelo navegador" if m["seo"]["palavras_visiveis"] > 50 else ""))
    if not m["seo"]["h1"]:
        add(0, "Sem H1: a página não declara a promessa principal")
    if not m["ctas"]:
        add(0, "Nenhum CTA encontrado")
    sem_destino = [x["texto"] for x in m["ctas"] if x["tipo"] in ("sem_href", "botao")]
    if sem_destino:
        add(1, f"{len(sem_destino)} CTA(s) sem link (ação via JavaScript): {', '.join(sem_destino[:4])}")
    if not (c["cnpj"] or c.get("empresa")):
        add(0, "Empresa não identificada: sem CNPJ nem razão social" + (" (nem nas páginas-chave)" if m.get("paginas_chave") else ""))
    if not (c["whatsapp"] or c["telefones"] or c["emails"]):
        add(0, "Nenhum contato: sem WhatsApp, telefone ou e-mail")
    elif not c["whatsapp"]:
        add(2, "Sem link de WhatsApp")
    if not m["numeros"]["precos"]:
        add(1, "Nenhum preço visível")
    if not o["garantia"]:
        add(1, "Sem garantia ou reembolso escrito")
    if not o["teste_gratis"]:
        add(2, "Sem teste grátis")
    if not o["prova_social"] and not m["numeros"]["prova_social_numerica"]:
        add(1, "Sem prova social detectável (depoimentos, avaliações, números de clientes)")
    if not m["seo"].get("viewport"):
        add(0, "Sem meta viewport: no celular a página abre como versão de computador encolhida")
    quebrados = [l for l in m.get("links_testados", []) if l.get("status") and l["status"] >= 400]
    if quebrados:
        add(0, f"{len(quebrados)} link(s) interno(s) quebrado(s)")
    ttfb = m["http"].get("ttfb_ms")
    if ttfb and ttfb > 800:
        add(1, f"Servidor lento: {ttfb} ms até o primeiro byte")
    f = m["rastreamento"]["ferramentas"]
    if not f:
        add(1, "Nenhum rastreador no HTML (pode estar via GTM ou ausente)")
    elif "Meta Pixel" not in f:
        add(2, "Meta Pixel não encontrado no HTML")
    if m["seo"]["h1_quantidade"] > 1:
        add(2, f"{m['seo']['h1_quantidade']} H1 na página (o normal é 1)")
    if not m["seo"]["meta_description"]:
        add(2, "Sem meta description")
    a = m.get("arquivos_do_site", {})
    if a.get("robots", {}).get("bloqueia_tudo"):
        add(0, "robots.txt bloqueia todo o site no Google")
    if a.get("sitemap", {}).get("status") not in (200, None):
        add(2, "sitemap.xml não encontrado")
    if m["imagens"]["sem_alt"]:
        add(2, f"{m['imagens']['sem_alt']} imagem(ns) sem texto alternativo")
    nomes = {0: "ALTA", 1: "MÉDIA", 2: "BAIXA"}
    return [f"[{nomes[g]}] {t}" for g, t in sorted(achados, key=lambda x: x[0])]


def raio_x(m: dict) -> dict:
    """Leitura estratégica: o que um comprador encontra em cada pilar de venda. Nota 0 a 2 por pilar."""
    secoes = m["secoes"]
    heroi = next((s_ for s_ in secoes if s_["nivel"] == 1), secoes[0] if secoes else {"titulo": "", "texto": ""})
    h1 = m["seo"]["h1"][0] if m["seo"]["h1"] else ""
    sub = heroi["texto"][:260]
    cta_heroi = next((c for c in m["ctas"] if c["texto"] and c["texto"] in heroi["texto"]), None)
    acima = {"h1": h1, "subtitulo": sub, "primeiro_cta": cta_heroi}

    o, n, c = m["sinais_de_oferta"], m["numeros"], m["contato_e_confianca"]
    t = m["seo"]
    P = []

    def pilar(nome, nota, viu, falta):
        P.append({"pilar": nome, "nota": nota, "viu": viu, "falta": falta})

    especifico = bool(re.search(r"\d", h1 + " " + sub[:120]))
    pilar("Promessa", 0 if not h1 else (2 if especifico else 1),
          f"H1: {h1[:110]}" if h1 else "sem H1",
          "" if (h1 and especifico) else ("escrever um H1 com a promessa" if not h1 else "número ou resultado concreto no H1/subtítulo"))
    itens_oferta = {"preço": bool(n["precos"]), "garantia": bool(o["garantia"]), "teste": bool(o["teste_gratis"]),
                    "urgência/escassez": bool(o["urgencia_escassez"]), "bônus/desconto": bool(o.get("bonus") or o["desconto"])}
    tem = [k for k, v in itens_oferta.items() if v]
    pilar("Oferta", 2 if len(tem) >= 3 else (1 if tem else 0), ", ".join(tem) or "nada",
          ", ".join(k for k, v in itens_oferta.items() if not v))
    prova = n["prova_social_numerica"] + o["prova_social"][:2]
    pilar("Prova", 2 if (n["prova_social_numerica"] and o["prova_social"]) else (1 if prova else 0),
          "; ".join(prova[:3]) or "nada", "" if len(prova) >= 2 else "números de clientes e depoimentos com nome")
    conf = {"empresa/CNPJ": bool(c["cnpj"] or c.get("empresa")), "contato": bool(c["whatsapp"] or c["telefones"] or c["emails"]),
            "políticas": bool(c.get("politicas")), "redes": bool(c["redes"])}
    ok = [k for k, v in conf.items() if v]
    pilar("Confiança", 2 if len(ok) >= 3 else (1 if ok else 0), ", ".join(ok) or "nada",
          ", ".join(k for k, v in conf.items() if not v))
    validos = [x for x in m["ctas"] if x["tipo"] not in ("sem_href", "botao", "ancora")]
    pilar("Ação (CTA)", 2 if (cta_heroi and validos) else (1 if m["ctas"] else 0),
          (f"no topo: \"{cta_heroi['texto']}\" -> {cta_heroi['destino']}" if cta_heroi else "nenhum CTA no topo")
          + f"; {len(m['ctas'])} CTAs no total",
          "" if cta_heroi else "CTA visível logo abaixo do H1")
    obrig = sum(1 for f_ in m["formularios"] for x in f_["campos"] if x["obrigatorio"])
    sem_dest = sum(1 for x in m["ctas"] if x["tipo"] in ("sem_href", "botao"))
    quebr = sum(1 for l in m.get("links_testados", []) if l.get("status") and l["status"] >= 400)
    lento = (m["http"].get("ttfb_ms") or 0) > 800
    problemas = [x for x, v in (("campos obrigatórios: " + str(obrig), obrig > 4), ("CTAs sem link: " + str(sem_dest), sem_dest),
                                ("links quebrados: " + str(quebr), quebr), ("servidor lento", lento)) if v]
    pilar("Atrito (2 = pouco)", 2 if not problemas else (1 if len(problemas) == 1 else 0),
          "; ".join(problemas) or "nada travando", "; ".join(problemas))
    f = m["rastreamento"]["ferramentas"]
    med = ("Meta Pixel" in f) + any(x in f for x in ("Google Analytics 4", "Google Tag Manager"))
    pilar("Medição", med, ", ".join(f) or "nada no HTML", "" if med == 2 else "Meta Pixel e GA4/GTM")
    a = m.get("arquivos_do_site", {})
    desc = [x for x, v in (("title", t["title"]), ("description", t["meta_description"]), ("1 H1", t["h1_quantidade"] == 1),
                           ("sitemap", a.get("sitemap", {}).get("status") == 200), ("dados estruturados", t["jsonld_tipos"]))
            if v]
    pilar("Descoberta (SEO)", 2 if len(desc) >= 4 else (1 if len(desc) >= 2 else 0), ", ".join(desc) or "nada",
          ", ".join(x for x in ("title", "description", "1 H1", "sitemap", "dados estruturados") if x not in desc))
    total = sum(x["nota"] for x in P)
    return {"acima_da_dobra": acima, "pilares": P, "nota": total, "maximo": 2 * len(P)}


# --------------------------------------------------------------------------
# Arquivos do site e links
# --------------------------------------------------------------------------


ARQUIVOS = (("robots", "/robots.txt"), ("sitemap", "/sitemap.xml"), ("llms", "/llms.txt"))


def disparar_arquivos(base: str, pool: ThreadPoolExecutor, timeout: float) -> dict:
    raiz = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    return {nome: pool.submit(baixar, raiz + caminho, timeout, "GET", 2_000_000) for nome, caminho in ARQUIVOS}


def robots_bloqueia_tudo(texto: str) -> bool:
    agentes, bloqueia = [], False
    lendo_regras = False
    for linha in texto.splitlines():
        linha = linha.split("#")[0].strip()
        if ":" not in linha:
            continue
        chave, valor = (x.strip() for x in linha.split(":", 1))
        chave = chave.lower()
        if chave == "user-agent":
            if lendo_regras:
                agentes, lendo_regras = [], False
            agentes.append(valor)
        elif chave in ("disallow", "allow"):
            lendo_regras = True
            if "*" in agentes and chave == "disallow" and valor == "/":
                bloqueia = True
    return bloqueia


def ler_arquivos(futs: dict) -> dict:
    out = {}
    for nome, f in futs.items():
        r = f.result()
        info = {"status": r["status"], "url": r["url"]}
        if nome == "robots" and r["status"] == 200:
            info["sitemaps"] = re.findall(r"(?im)^sitemap:\s*(\S+)", r["texto"])
            info["bloqueia_tudo"] = robots_bloqueia_tudo(r["texto"])
        if nome == "sitemap" and r["status"] == 200:
            info["urls"] = len(re.findall(r"<loc>", r["texto"]))
        if nome == "llms":
            info["existe"] = r["status"] == 200 and len(r["texto"].strip()) > 0
        out[nome] = info
    return out


def escolher_paginas_chave(mapa: dict, limite: int) -> list[str]:
    base = mapa["url_final"].split("#")[0].rstrip("/")
    vistos, out = set(), []
    for l in mapa["links"]:
        if l["tipo"] not in ("interno", "subdominio"):
            continue
        u = l["destino"].split("#")[0]
        if not u or u.rstrip("/") == base or u in vistos or re.search(r"\.(pdf|jpe?g|png|webp|zip)$", u, re.I):
            continue
        if RE_CHAVE.search(l["texto"]) or RE_CHAVE.search(urlparse(u).path):
            vistos.add(u)
            out.append(u)
    return out[:limite]


def ler_pagina_chave(u: str, timeout: float) -> dict:
    r = baixar(u, timeout)
    info = {"url": u, "status": r["status"], "erro": r["erro"]}
    if not r["texto"]:
        return info
    p = MapaParser(r["url_final"])
    try:
        p.feed(r["texto"])
        p.close()
    except Exception:  # noqa: BLE001
        pass
    p.finalizar()
    texto = "\n".join(h["texto"] for h in p.headings) + "\n" + "\n".join(l for s_ in p.secoes for l in s_["linhas"])
    if len(texto.split()) < 60:
        texto += "\n" + "\n".join(texto_embutido(p.scripts_inline))
    info.update({
        "titulo": p.title, "palavras": len(texto.split()),
        "cnpj": achar(RE_CNPJ, texto), "empresa": achar(RE_EMPRESA, texto)[:3],
        "emails": achar(RE_EMAIL, texto)[:5], "telefones": achar(RE_TEL, texto)[:5],
        "whatsapp": sorted({a["href"] for a in p.ancoras if "wa.me" in a["href"] or "whatsapp.com" in a["href"]}),
        "precos": achar(RE_PRECO, texto)[:10],
        "garantia": trechos(PADROES_TEXTO["garantia"], texto), "teste_gratis": trechos(PADROES_TEXTO["teste_gratis"], texto),
        "cancelamento_livre": trechos(PADROES_TEXTO["cancelamento_livre"], texto),
    })
    return info


def juntar_paginas_chave(mapa: dict, infos: list[dict]):
    c, o, fontes = mapa["contato_e_confianca"], mapa["sinais_de_oferta"], mapa["contato_e_confianca"]["fontes"]
    caminho = lambda u: urlparse(u).path or "/"  # noqa: E731
    for i in infos:
        for campo in ("cnpj", "empresa", "emails", "telefones", "whatsapp"):
            novos = [x for x in i.get(campo, []) if x not in c[campo]]
            if novos:
                c[campo] = c[campo] + novos
                fontes.setdefault(campo, []).append(caminho(i["url"]))
        for campo in ("garantia", "teste_gratis", "cancelamento_livre"):
            for t in i.get(campo, []):
                marcado = f"{t} (em {caminho(i['url'])})"
                if marcado not in o[campo]:
                    o[campo].append(marcado)
        if i.get("precos") and not mapa["numeros"]["precos"]:
            mapa["numeros"]["precos_em_outras_paginas"] = {caminho(i["url"]): i["precos"]}


def testar_links(links: list[dict], pool: ThreadPoolExecutor, timeout: float, limite: int = 40) -> list[dict]:
    alvos = []
    vistos = set()
    for l in links:
        d = l["destino"].split("#")[0]
        if l["tipo"] in ("interno", "subdominio") and d and d not in vistos:
            vistos.add(d)
            alvos.append(d)
    alvos = alvos[:limite]
    res = list(pool.map(lambda u: baixar(u, timeout, "GET", 200_000), alvos))
    return [{"url": r["url"], "status": r["status"], "ms": r["total_ms"], "erro": r["erro"]} for r in res]


# --------------------------------------------------------------------------
# Saída
# --------------------------------------------------------------------------


def slug_de(url: str) -> str:
    p = urlparse(url)
    s = (p.netloc + p.path).strip("/").replace("/", "_") or "pagina"
    return re.sub(r"[^\w.-]", "_", s)[:80]


def para_md(m: dict, max_secao: int) -> str:
    L = []
    h, seo, v = m["http"], m["seo"], m["verificacao"]
    L.append(f"# Scan: {m['url_final']}")
    L.append(f"Status {h['status']} · {h['ttfb_ms']} ms até o 1º byte · {h['total_ms']} ms total · "
             f"{round((h['bytes'] or 0) / 1024)} KB · lido via {m['origem_html']} · {m['quando']}")
    if h.get("erro"):
        L.append(f"**Erro no HTTP:** {h['erro']}")
    rx = m.get("raio_x")
    if rx:
        ad = rx["acima_da_dobra"]
        L.append(f"\n## Raio-X de venda: {rx['nota']}/{rx['maximo']}")
        L.append("| Pilar | Nota | O que o scan viu | O que falta |")
        L.append("|---|---|---|---|")
        for x in rx["pilares"]:
            L.append(f"| {x['pilar']} | {x['nota']}/2 | {x['viu']} | {x['falta'] or '—'} |".replace("\n", " "))
        L.append("\n## Acima da dobra (o que o visitante vê primeiro)")
        L.append(f"- **H1:** {ad['h1'] or '— (sem H1)'}")
        L.append(f"- **Logo abaixo:** {ad['subtitulo'] or '—'}")
        cta = ad["primeiro_cta"]
        L.append(f"- **Primeiro CTA:** " + (f"\"{cta['texto']}\" -> {cta['destino']}" if cta else "nenhum no topo"))
    L.append("\n## Achados por gravidade")
    L += [f"- {x}" for x in m["sinais"]] or ["- nenhum"]
    if m.get("paginas_chave"):
        L.append("\n## Páginas-chave lidas")
        for i in m["paginas_chave"]:
            achou = [k for k in ("cnpj", "empresa", "emails", "telefones", "whatsapp", "garantia", "teste_gratis", "precos") if i.get(k)]
            L.append(f"- {i['status']} {i['url']}: " + (", ".join(achou) if achou else "nada relevante"))
    L.append(f"\n## Conferência do mapeamento: confiança {v['confianca'].upper()}")
    for c in v["checks"]:
        L.append(f"- {'✔' if c['ok'] else '✖'} {c['item']}: esperado {c['esperado']}, encontrado {c['encontrado']}"
                 + (f" ({c['nota']})" if c["nota"] else ""))
    L.append("Não coberto por este scan: " + "; ".join(v["lacunas"]))

    L.append("\n## Estrutura (títulos na ordem)")
    for t in m["estrutura"][:80]:
        L.append(f"{'  ' * (t['nivel'] - 1)}- H{t['nivel']}: {t['texto']}")

    L.append("\n## CTAs (texto -> destino)")
    for c in m["ctas"][:40]:
        L.append(f"- \"{c['texto']}\" -> {c['destino'] or '(sem link)'}")
    L.append(f"Links por tipo: {m['links_resumo']}")

    n = m["numeros"]
    L.append("\n## Oferta e números")
    L.append(f"- Preços: {', '.join(n['precos']) or 'nenhum'}")
    L.append(f"- Percentuais: {', '.join(n['percentuais']) or 'nenhum'}")
    L.append(f"- Prova social numérica: {', '.join(n['prova_social_numerica']) or 'nenhuma'}")
    if n.get("precos_em_outras_paginas"):
        L.append(f"- Preços em outras páginas: {n['precos_em_outras_paginas']}")
    for k, vals in m["sinais_de_oferta"].items():
        L.append(f"- {k.replace('_', ' ')}: " + (" | ".join(vals) if vals else "não encontrado"))

    L.append("\n## Formulários")
    if not m["formularios"]:
        L.append("- nenhum")
    for f in m["formularios"]:
        campos = ", ".join(f"{c['label'] or c['placeholder'] or c['nome'] or c['tipo']}"
                           f"{'*' if c['obrigatorio'] else ''} ({c['tipo']})" for c in f["campos"])
        L.append(f"- {f['method'].upper()} {f['action'] or '(sem action)'}: {campos or 'sem campos'}")

    c = m["contato_e_confianca"]
    L.append("\n## Contato e confiança")
    L.append(f"- WhatsApp: {', '.join(c['whatsapp']) or 'não'} · Telefones: {', '.join(c['telefones']) or 'não'} · "
             f"E-mails: {', '.join(c['emails']) or 'não'} · CNPJ: {', '.join(c['cnpj']) or 'não'} · "
             f"Redes: {', '.join(c['redes']) or 'nenhuma'}")
    L.append(f"- Empresa: {', '.join(c.get('empresa', [])) or 'não identificada'} · Políticas: "
             f"{', '.join(urlparse(x).path for x in c.get('politicas', [])) or 'nenhuma'}"
             + (f" · Achado em: {c['fontes']}" if c.get("fontes") else ""))

    r = m["rastreamento"]
    L.append("\n## Rastreamento e tecnologia")
    L.append(f"- Ferramentas: {', '.join(r['ferramentas']) or 'nenhuma no HTML'} · IDs: {r['ids'] or '—'}")
    t = m["tecnologia"]
    L.append(f"- Stack provável: {', '.join(t['stack_provavel']) or '?'} · scripts externos {t['scripts_externos']}, "
             f"inline {t['scripts_inline']}, CSS {t['folhas_css']}")
    a = m["arquivos_do_site"]
    L.append(f"- robots.txt {a.get('robots', {}).get('status')} · sitemap.xml {a.get('sitemap', {}).get('status')} "
             f"({a.get('sitemap', {}).get('urls', 0)} URLs) · llms.txt {a.get('llms', {}).get('status')}")
    if m.get("links_testados"):
        q = [l for l in m["links_testados"] if not l["status"] or l["status"] >= 400]
        L.append(f"- Links internos testados: {len(m['links_testados'])}, com problema: {len(q)}"
                 + "".join(f"\n  - {l['status']} {l['url']}" for l in q[:10]))

    L.append("\n## SEO")
    L.append(f"- Title ({seo['title_tamanho']}): {seo['title']}")
    L.append(f"- Description ({seo['meta_description_tamanho']}): {seo['meta_description'] or '—'}")
    L.append(f"- H1 ({seo['h1_quantidade']}): {' | '.join(seo['h1']) or '—'} · canonical: {seo['canonical']} · "
             f"lang: {seo['lang']} · JSON-LD: {', '.join(seo['jsonld_tipos']) or 'nenhum'} · "
             f"palavras visíveis: {seo['palavras_visiveis']}")

    iv = m["identidade_visual"]
    L.append("\n## Identidade visual (do CSS)")
    L.append(f"- theme-color: {iv['theme_color']} · destaque: {', '.join(iv['cores_de_destaque']) or '—'} · "
             f"fontes: {', '.join(iv['fontes']) or '—'}")
    if iv["variaveis_de_cor"]:
        L.append("- Variáveis: " + ", ".join(f"--{k}: {v}" for k, v in list(iv["variaveis_de_cor"].items())[:12]))
    if m.get("prints"):
        L.append("- Prints: " + ", ".join(m["prints"]))

    L.append("\n## Texto por seção")
    for s in m["secoes"]:
        txt = s["texto"]
        if len(txt) > max_secao:
            txt = txt[:max_secao] + f" […+{len(s['texto']) - max_secao} caracteres no JSON]"
        L.append(f"\n### {s['titulo']}\n{txt}")
    return "\n".join(L) + "\n"


def comparativo_md(mapas: list[dict]) -> str:
    cab = ["Site", "Status", "1º byte", "Palavras", "Preços", "CTAs", "Teste grátis", "Garantia",
           "Prova social", "WhatsApp", "Meta Pixel", "GA4/GTM", "Cores destaque", "Fontes"]
    L = ["# Comparativo scan-ultra", "", "| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    for m in mapas:
        f = m["rastreamento"]["ferramentas"]
        o = m["sinais_de_oferta"]
        L.append("| " + " | ".join(str(x) for x in [
            urlparse(m["url_final"]).netloc, m["http"]["status"], f"{m['http']['ttfb_ms']} ms",
            m["seo"]["palavras_visiveis"], ", ".join(m["numeros"]["precos"][:4]) or "—", len(m["ctas"]),
            "sim" if o["teste_gratis"] else "não", "sim" if o["garantia"] else "não",
            ", ".join(m["numeros"]["prova_social_numerica"][:2]) or ("sim" if o["prova_social"] else "não"),
            "sim" if m["contato_e_confianca"]["whatsapp"] else "não",
            "sim" if "Meta Pixel" in f else "não",
            "sim" if ("Google Analytics 4" in f or "Google Tag Manager" in f) else "não",
            " ".join(m["identidade_visual"]["cores_de_destaque"][:3]) or "—",
            ", ".join(m["identidade_visual"]["fontes"][:2]) or "—",
        ]) + " |")
    pil = [x["pilar"] for x in mapas[0]["raio_x"]["pilares"]] if mapas and mapas[0].get("raio_x") else []
    if pil:
        L.append("\n## Raio-X lado a lado (0 a 2 por pilar)")
        L.append("| Site | " + " | ".join(pil) + " | Total |")
        L.append("|" + "---|" * (len(pil) + 2))
        for m in mapas:
            rx = m["raio_x"]
            L.append(f"| {urlparse(m['url_final']).netloc} | " + " | ".join(str(x["nota"]) for x in rx["pilares"])
                     + f" | {rx['nota']}/{rx['maximo']} |")
    L.append("\n## H1 de cada site")
    for m in mapas:
        L.append(f"- **{urlparse(m['url_final']).netloc}**: {' | '.join(m['seo']['h1']) or '—'}")
    L.append("\n## Oferta de cada site")
    for m in mapas:
        o = m["sinais_de_oferta"]
        partes = [f"{k.replace('_', ' ')}: {o[k][0]}" for k in ("teste_gratis", "garantia", "urgencia_escassez", "desconto") if o[k]]
        L.append(f"- **{urlparse(m['url_final']).netloc}**: " + (" · ".join(partes) or "nenhum sinal de oferta"))
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------


import threading  # noqa: E402

TRAVA_NAVEGADOR = threading.Lock()


def palavras_html(html: str) -> int:
    corpo = re.sub(r"<(script|style|noscript|template|svg)\b.*?</\1>", " ", html or "", flags=re.S | re.I)
    return len(re.sub(r"<[^>]+>", " ", corpo).split())


def parece_spa(html: str) -> bool:
    if not html:
        return False
    raiz = re.search(r"<div[^>]+id=[\"'](root|__next|app|__nuxt|svelte)[\"']", html, re.I)
    scripts = len(re.findall(r"<script\b", html, re.I))
    p = palavras_html(html)
    return (bool(raiz) and p < 150) or (p < 40 and scripts >= 2)


def escanear(url: str, args, pool: ThreadPoolExecutor, pasta: Path) -> dict:
    sem_esquema = not re.match(r"https?://", url)
    if sem_esquema:
        url = "https://" + url
    t0 = time.perf_counter()
    resp = baixar(url, args.timeout)
    if sem_esquema and resp["erro"]:  # sem https? tenta http
        alt = baixar("http://" + url.removeprefix("https://"), args.timeout)
        if not alt["erro"]:
            url, resp = alt["url"], alt
    futs_arquivos = disparar_arquivos(url, pool, args.timeout)
    html, origem = resp["texto"], "http"
    slug = slug_de(url)
    render = None
    motivo = ("pedido" if (args.render or args.print) else "bloqueio" if resp["bloqueado"]
              else "sem resposta HTTP" if resp["status"] is None else "site em JavaScript" if parece_spa(html) else None)
    if motivo and args.navegador != "nenhum":
        with TRAVA_NAVEGADOR:
            render = renderizar(url, args.timeout * 2, args.print, pasta, slug, args.navegador)
        if render.get("html") and palavras_html(render["html"]) >= palavras_html(html):
            html, origem = render["html"], render["motor"]
        render["motivo"] = motivo

    # CSS externo em paralelo (cores e fontes moram aqui)
    css_extra = ""
    if args.css:
        hrefs = re.findall(r"<link[^>]+rel=[\"']?stylesheet[\"']?[^>]*>", html, re.I)
        urls_css = []
        for tag in hrefs:
            m = re.search(r"href=[\"']([^\"']+)", tag)
            if m:
                urls_css.append(urljoin(resp["url_final"], m.group(1)))
        urls_css = [u for u in urls_css if "fonts.googleapis" not in u][: args.css]
        css_extra = "\n".join(r["texto"] for r in pool.map(lambda u: baixar(u, args.timeout, "GET", 3_000_000), urls_css)
                              if r["status"] == 200)

    mapa = montar_mapa(url, resp, html, css_extra, ler_arquivos(futs_arquivos), origem)
    mapa["bloqueado"] = resp["bloqueado"]
    if render:
        mapa["render"] = {k: render.get(k) for k in ("motivo", "motor", "erro", "total_ms", "console_erros")}
        mapa["prints"] = render.get("prints", [])
        if render.get("erro") and not render.get("html"):
            mapa["verificacao"]["lacunas"].insert(0, f"Navegador não abriu ({render['motivo']}): {render['erro']}")
    if args.paginas:
        urls_chave = escolher_paginas_chave(mapa, args.paginas)
        mapa["paginas_chave"] = list(pool.map(lambda u: ler_pagina_chave(u, args.timeout), urls_chave))
        juntar_paginas_chave(mapa, mapa["paginas_chave"])
    if args.links:
        mapa["links_testados"] = testar_links(mapa["links"], pool, args.timeout)
    mapa["sinais"] = sinais(mapa)
    mapa["raio_x"] = raio_x(mapa)
    mapa["tempo_scan_ms"] = round((time.perf_counter() - t0) * 1000)

    (pasta / f"{slug}.json").write_text(json.dumps(mapa, ensure_ascii=False, indent=1), encoding="utf-8")
    (pasta / f"{slug}.md").write_text(para_md(mapa, args.max_secao), encoding="utf-8")
    mapa["_arquivos"] = [str(pasta / f"{slug}.json"), str(pasta / f"{slug}.md")]
    return mapa


def main(argv=None):
    for fluxo in (sys.stdout, sys.stderr):  # terminal do Windows (cp1252) não quebra com acentos e símbolos
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="scan-ultra: mapa rápido e conferido de páginas web")
    ap.add_argument("urls", nargs="*", help="uma ou mais URLs")
    ap.add_argument("--arquivo", help="arquivo com uma URL por linha")
    ap.add_argument("--saida", default="scan-ultra-saida", help="pasta de saída")
    ap.add_argument("--workers", type=int, default=16, help="downloads em paralelo")
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--css", type=int, default=4, help="quantas folhas de CSS externas baixar (0 desliga)")
    ap.add_argument("--links", action="store_true", help="testar links internos (até 40)")
    ap.add_argument("--render", action="store_true", help="forçar leitura pelo navegador")
    ap.add_argument("--print", action="store_true", help="salvar prints desktop e mobile")
    ap.add_argument("--navegador", default="auto", choices=["auto", "playwright", "chrome", "nenhum"],
                    help="auto: Playwright se houver, senão Chrome/Edge/Brave do computador; nenhum: só HTTP")
    ap.add_argument("--paginas", type=int, default=6, help="páginas-chave para ler (preços, termos, contato...); 0 desliga")
    ap.add_argument("--max-secao", type=int, default=1500, help="caracteres por seção no .md")
    args = ap.parse_args(argv)

    urls = list(args.urls)
    if args.arquivo:
        urls += [l.strip() for l in Path(args.arquivo).read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]
    if not urls:
        ap.error("passe pelo menos uma URL")
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    # pool interno para downloads; pool externo para páginas; o navegador é usado um de cada vez (trava)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        with ThreadPoolExecutor(max_workers=min(8, len(urls))) as externo:
            mapas = list(externo.map(lambda u: escanear(u, args, pool, pasta), urls))

    for m in mapas:
        v, rx = m["verificacao"], m["raio_x"]
        via = m["origem_html"]
        print(f"[{m['http']['status']}] {m['url_final']}  {m['tempo_scan_ms']} ms  via {via}  confianca {v['confianca']}  "
              f"Raio-X {rx['nota']}/{rx['maximo']}  {m['seo']['palavras_visiveis']} palavras  -> {m['_arquivos'][1]}")
        if m["seo"]["palavras_visiveis"] == 0:
            print("   ! nada lido. Motivo: " + (m["http"].get("erro") or "conteúdo montado por JavaScript")
                  + (f" | navegador: {m['render']['erro']}" if m.get("render", {}).get("erro") else ""))
    if len(mapas) > 1:
        (pasta / "comparativo.md").write_text(comparativo_md(mapas), encoding="utf-8")
        (pasta / "comparativo.json").write_text(json.dumps(
            [{k: m[k] for k in ("url_final", "http", "seo", "numeros", "sinais_de_oferta", "contato_e_confianca",
                                "rastreamento", "identidade_visual", "sinais", "raio_x")} for m in mapas],
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"comparativo -> {pasta / 'comparativo.md'}")
    print(f"total: {len(mapas)} pagina(s) em {round(time.perf_counter() - t0, 2)} s")
    nada = [m for m in mapas if m["seo"]["palavras_visiveis"] == 0]
    return 2 if len(nada) == len(mapas) else 0


if __name__ == "__main__":
    sys.exit(main())
