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
  python3 scan.py URL --render                # renderiza com navegador (sites em JavaScript)
  python3 scan.py URL --print                 # salva print desktop e mobile (exige --render)

Saída (pasta --saida, padrão ./scan-ultra-saida):
  <site>.json        mapa completo
  <site>.md          resumo para leitura rápida
  comparativo.md     tabela lado a lado, quando há mais de uma URL

Só usa a biblioteca padrão do Python 3.8+. O modo --render usa Playwright, se
estiver instalado (pip install playwright && playwright install chromium).
"""

from __future__ import annotations

import argparse
import colorsys
import gzip
import json
import re
import sys
import time
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

VERSAO = "1.0.0"
UA = "Mozilla/5.0 (compatible; scan-ultra/1.0; +https://github.com/)"
MAX_BYTES = 6_000_000

# --------------------------------------------------------------------------
# Rede
# --------------------------------------------------------------------------


def baixar(url: str, timeout: float = 20.0, metodo: str = "GET", max_bytes: int = MAX_BYTES) -> dict:
    """Baixa uma URL e mede o tempo. Nunca levanta exceção: devolve o erro no dict."""
    req = Request(url, method=metodo, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,text/css,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
        "Accept-Encoding": "gzip, deflate",
    })
    t0 = time.perf_counter()
    out = {"url": url, "status": None, "url_final": url, "ttfb_ms": None, "total_ms": None,
           "bytes": 0, "headers": {}, "texto": "", "erro": None}
    try:
        try:
            resp = urlopen(req, timeout=timeout)
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
        out["bytes"] = len(corpo)
        out["texto"] = decodificar(corpo, hdr.get("content-type", ""))
    except (URLError, OSError, ValueError) as e:
        out["erro"] = f"{type(e).__name__}: {getattr(e, 'reason', e)}"
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


def renderizar(url: str, timeout: float, prints: bool, pasta: Path, slug: str) -> dict:
    """Renderiza com Chromium via Playwright. Devolve html e caminhos dos prints."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"erro": "Playwright não instalado. Rode: pip install playwright && playwright install chromium"}
    out = {"html": "", "prints": [], "erro": None, "total_ms": None, "console_erros": []}
    t0 = time.perf_counter()
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch()
            for nome, vw, vh, mobile in (("desktop", 1440, 900, False), ("mobile", 390, 844, True)):
                if nome == "mobile" and not prints:
                    break
                ctx = nav.new_context(viewport={"width": vw, "height": vh}, is_mobile=mobile,
                                      user_agent=UA, locale="pt-BR")
                pg = ctx.new_page()
                if nome == "desktop":
                    pg.on("console", lambda m: out["console_erros"].append(m.text[:200]) if m.type == "error" else None)
                pg.goto(url, wait_until="networkidle", timeout=int(timeout * 1000))
                if nome == "desktop":
                    out["html"] = pg.content()
                    out["total_ms"] = round((time.perf_counter() - t0) * 1000)
                if prints:
                    arq = pasta / f"{slug}-{nome}.png"
                    pg.screenshot(path=str(arq), full_page=True)
                    out["prints"].append(str(arq))
                ctx.close()
            nav.close()
    except Exception as e:  # noqa: BLE001 - qualquer falha do navegador vira lacuna, não crash
        out["erro"] = f"{type(e).__name__}: {str(e)[:300]}"
    return out


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
    mapa["verificacao"] = verificar(mapa, html, p)
    mapa["sinais"] = sinais(mapa)
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
    check("HTTP 200", 200, st, st == 200, mapa["http"].get("erro") or "")
    ctype = mapa["http"]["headers"].get("content-type", "") if mapa["origem_html"] == "http" else "text/html (renderizado)"
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
    depende_js = palavras < 150 and (mapa["tecnologia"]["scripts_externos"] >= 2 or mapa["tecnologia"]["raiz_spa"])
    nota = ("página parece montada por JavaScript: rode de novo com --render" if depende_js
            else ("página curta, mas sem sinais de depender de JavaScript" if palavras < 150 else ""))
    check("Conteúdo legível sem JavaScript", "texto no HTML", f"{palavras} palavras", not depende_js, nota)

    if mapa["url_final"].rstrip("/") != mapa["url"].rstrip("/"):
        check("Sem redirecionamento", mapa["url"], mapa["url_final"], False, "a URL redirecionou")

    erros = [c for c in checks if not c["ok"]]
    graves = [c for c in erros if c["item"] in ("HTTP 200", "Resposta é HTML", "Conteúdo legível sem JavaScript")]
    confianca = "baixa" if graves else ("média" if erros else "alta")
    lacunas = ["Visual (cores aplicadas, imagens, hierarquia na tela): só visto com --render --print",
               "Comportamento ao clicar (modais, checkout, cálculos): não executado",
               "Áreas com login e conteúdo carregado depois de interação"]
    if mapa["origem_html"] == "http":
        lacunas.append("Rastreadores carregados via GTM/JavaScript podem não aparecer no HTML")
    return {"confianca": confianca, "checks": checks, "lacunas": lacunas}


def sinais(m: dict) -> list[str]:
    """Achados objetivos que viram munição para a análise. Só fatos do mapa."""
    s = []
    c = m["contato_e_confianca"]
    o = m["sinais_de_oferta"]
    if not c["whatsapp"]:
        s.append("Nenhum link de WhatsApp na página")
    if not c["cnpj"]:
        s.append("CNPJ não aparece no texto")
    if not m["numeros"]["precos"]:
        s.append("Nenhum preço visível")
    if not o["teste_gratis"]:
        s.append("Sem menção a teste grátis")
    if not o["garantia"]:
        s.append("Sem menção a garantia ou reembolso")
    if not o["prova_social"] and not m["numeros"]["prova_social_numerica"]:
        s.append("Sem prova social detectável (depoimentos, avaliações, números de clientes)")
    if m["seo"]["h1_quantidade"] != 1:
        s.append(f"{m['seo']['h1_quantidade']} H1 na página (o normal é 1)")
    if not m["seo"].get("viewport"):
        s.append("Sem meta viewport: no celular a página abre como versão de computador encolhida")
    if not m["seo"]["meta_description"]:
        s.append("Sem meta description")
    if not m["rastreamento"]["ferramentas"]:
        s.append("Nenhum rastreador encontrado no HTML (pode estar via GTM ou ausente)")
    elif "Meta Pixel" not in m["rastreamento"]["ferramentas"]:
        s.append("Meta Pixel não encontrado no HTML")
    sem_destino = [x["texto"] for x in m["ctas"] if x["tipo"] in ("sem_href", "botao")]
    if sem_destino:
        s.append(f"{len(sem_destino)} CTA(s) sem link (ação via JavaScript): {', '.join(sem_destino[:4])}")
    if m["imagens"]["sem_alt"]:
        s.append(f"{m['imagens']['sem_alt']} imagem(ns) sem texto alternativo")
    a = m.get("arquivos_do_site", {})
    if a.get("robots", {}).get("bloqueia_tudo"):
        s.append("robots.txt bloqueia todo o site")
    if a.get("sitemap", {}).get("status") not in (200, None):
        s.append("sitemap.xml não encontrado")
    ttfb = m["http"].get("ttfb_ms")
    if ttfb and ttfb > 800:
        s.append(f"Servidor lento para responder: {ttfb} ms até o primeiro byte")
    quebrados = [l for l in m.get("links_testados", []) if l.get("status") and l["status"] >= 400]
    if quebrados:
        s.append(f"{len(quebrados)} link(s) interno(s) quebrado(s)")
    return s


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
             f"{round((h['bytes'] or 0) / 1024)} KB · HTML via {m['origem_html']} · {m['quando']}")
    if h.get("erro"):
        L.append(f"**Erro:** {h['erro']}")
    L.append(f"\n## Conferência do mapeamento: confiança {v['confianca'].upper()}")
    for c in v["checks"]:
        L.append(f"- {'✔' if c['ok'] else '✖'} {c['item']}: esperado {c['esperado']}, encontrado {c['encontrado']}"
                 + (f" ({c['nota']})" if c["nota"] else ""))
    L.append("Não coberto por este scan: " + "; ".join(v["lacunas"]))

    L.append("\n## Sinais objetivos")
    L += [f"- {x}" for x in m["sinais"]] or ["- nenhum"]

    L.append("\n## Estrutura (títulos na ordem)")
    for t in m["estrutura"][:80]:
        L.append(f"{'  ' * (t['nivel'] - 1)}- H{t['nivel']}: {t['texto']}")

    L.append("\n## CTAs (texto → destino)")
    for c in m["ctas"][:40]:
        L.append(f"- \"{c['texto']}\" → {c['destino'] or '(sem link)'}")
    L.append(f"Links por tipo: {m['links_resumo']}")

    n = m["numeros"]
    L.append("\n## Oferta e números")
    L.append(f"- Preços: {', '.join(n['precos']) or 'nenhum'}")
    L.append(f"- Percentuais: {', '.join(n['percentuais']) or 'nenhum'}")
    L.append(f"- Prova social numérica: {', '.join(n['prova_social_numerica']) or 'nenhuma'}")
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
    if args.render:
        render = renderizar(url, args.timeout * 2, args.print, pasta, slug)
        if render.get("html"):
            html, origem = render["html"], "navegador"

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
    if render:
        mapa["render"] = {k: render.get(k) for k in ("erro", "total_ms", "console_erros")}
        mapa["prints"] = render.get("prints", [])
        if render.get("erro"):
            mapa["verificacao"]["lacunas"].insert(0, f"Render falhou: {render['erro']}")
    if args.links:
        mapa["links_testados"] = testar_links(mapa["links"], pool, args.timeout)
        mapa["sinais"] = sinais(mapa)
    mapa["tempo_scan_ms"] = round((time.perf_counter() - t0) * 1000)

    (pasta / f"{slug}.json").write_text(json.dumps(mapa, ensure_ascii=False, indent=1), encoding="utf-8")
    (pasta / f"{slug}.md").write_text(para_md(mapa, args.max_secao), encoding="utf-8")
    mapa["_arquivos"] = [str(pasta / f"{slug}.json"), str(pasta / f"{slug}.md")]
    return mapa


def main(argv=None):
    ap = argparse.ArgumentParser(description="scan-ultra: mapa rápido e conferido de páginas web")
    ap.add_argument("urls", nargs="*", help="uma ou mais URLs")
    ap.add_argument("--arquivo", help="arquivo com uma URL por linha")
    ap.add_argument("--saida", default="scan-ultra-saida", help="pasta de saída")
    ap.add_argument("--workers", type=int, default=16, help="downloads em paralelo")
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--css", type=int, default=4, help="quantas folhas de CSS externas baixar (0 desliga)")
    ap.add_argument("--links", action="store_true", help="testar links internos (até 40)")
    ap.add_argument("--render", action="store_true", help="renderizar com navegador (Playwright)")
    ap.add_argument("--print", action="store_true", help="salvar prints desktop e mobile (liga --render)")
    ap.add_argument("--max-secao", type=int, default=1500, help="caracteres por seção no .md")
    args = ap.parse_args(argv)
    if args.print:
        args.render = True

    urls = list(args.urls)
    if args.arquivo:
        urls += [l.strip() for l in Path(args.arquivo).read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]
    if not urls:
        ap.error("passe pelo menos uma URL")
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    # pool interno para downloads; pool externo para páginas (render não é thread-safe → sequencial)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        if args.render:
            mapas = [escanear(u, args, pool, pasta) for u in urls]
        else:
            with ThreadPoolExecutor(max_workers=min(8, len(urls))) as externo:
                mapas = list(externo.map(lambda u: escanear(u, args, pool, pasta), urls))

    for m in mapas:
        v = m["verificacao"]
        print(f"[{m['http']['status']}] {m['url_final']}  {m['tempo_scan_ms']} ms  confiança {v['confianca']}  "
              f"{m['seo']['palavras_visiveis']} palavras  {len(m['ctas'])} CTAs  → {m['_arquivos'][1]}")
    if len(mapas) > 1:
        (pasta / "comparativo.md").write_text(comparativo_md(mapas), encoding="utf-8")
        (pasta / "comparativo.json").write_text(json.dumps(
            [{k: m[k] for k in ("url_final", "http", "seo", "numeros", "sinais_de_oferta", "contato_e_confianca",
                                "rastreamento", "identidade_visual", "sinais")} for m in mapas],
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"comparativo → {pasta / 'comparativo.md'}")
    print(f"total: {len(mapas)} página(s) em {round(time.perf_counter() - t0, 2)} s")
    baixa = [m for m in mapas if m["verificacao"]["confianca"] == "baixa"]
    return 2 if baixa and len(baixa) == len(mapas) else 0


if __name__ == "__main__":
    sys.exit(main())
