#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CazaChollos Amazon ES  ·  v1  (fuente: Chollometro, gratis)
==================================================================
Lee el RSS de Chollometro cada vez que se ejecuta, se queda con las
ofertas de AMAZON, las va acumulando en un HISTORIAL (sin repetir) y
genera un panel HTML (index.html) con todas, cada una con su ENLACE.

Tú no miras nada: pones esto a ejecutarse solo (ver INSTRUCCIONES al
final) y abres el panel cuando quieras.

SIN DEPENDENCIAS: solo Python 3 (no hay que instalar nada).

NOTA HONESTA SOBRE EL "≥50%":
El RSS de Chollometro trae la tienda y el PRECIO actual, pero NO trae
el precio anterior ni el % de descuento como dato fiable. Por eso:
  - El bot captura TODAS las ofertas de Amazon (precio + enlace).
  - Detecta el % SOLO cuando la propia oferta lo dice en el título
    (p. ej. "-50%..."). El resto quedan como "% desconocido".
  - En el panel puedes filtrar por "solo ≥50% detectado", categoría,
    texto y ordenar por precio.
El % real y exhaustivo solo se consigue con Keepa (de pago).
==================================================================
"""

import os
import re
import json
import html
import datetime
import urllib.request
import xml.etree.ElementTree as ET

# ======================= CONFIGURACION ============================
FEEDS = [
    "https://www.chollometro.com/rss",   # ofertas nuevas de Chollometro
]

TIENDAS = ["Amazon"]          # tiendas a incluir (por nombre en el feed)
INCLUIR_AMAZON_EXTRANJERO = False   # True = incluir Amazon.de/.fr/.it, etc.

UMBRAL_DESCUENTO = 50         # % para marcar/filtrar como "chollo top"
SOLO_CON_DESCUENTO = False    # True = guardar SOLO ofertas con % detectado >= UMBRAL
MAX_ITEMS = 4000              # tope del historial (para no inflar el HTML)

HIST_FILE = "historial_chollos.json"
HTML_OUT  = "index.html"
# ==================================================================

NS = {
    "pepper": "http://www.pepper.com/rss",
    "media": "http://search.yahoo.com/mrss/",
}


def http_get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (CazaChollos/1.0; RSS reader)"
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def extraer_descuento(*textos):
    """Detecta el % de descuento SOLO si aparece de forma explícita.
    Conservador a propósito, para no confundir '65% algodón' con un descuento."""
    patrones = [
        r"-\s*(\d{1,3})\s*%",                                   # "-50%"
        r"(\d{1,3})\s*%\s*(?:de\s+)?(?:dto\.?|desc\.?|descuento|off|rebaj)",
    ]
    for texto in textos:
        if not texto:
            continue
        for pat in patrones:
            m = re.search(pat, texto, re.I)
            if m:
                n = int(m.group(1))
                if 5 <= n <= 95:
                    return n
    return None


def precio_a_numero(precio_txt):
    """'89,99€' -> 89.99 ; devuelve None si no se puede."""
    if not precio_txt:
        return None
    m = re.search(r"(\d[\d.\s]*),?(\d{0,2})", precio_txt.replace(".", "").replace(" ", ""))
    if not m:
        return None
    entero = re.sub(r"\D", "", m.group(1))
    dec = m.group(2) or "0"
    try:
        return float(f"{entero}.{dec}")
    except ValueError:
        return None


def tienda_valida(nombre):
    if not nombre:
        return False
    n = nombre.strip()
    for t in TIENDAS:
        if n == t:
            return True
        if INCLUIR_AMAZON_EXTRANJERO and n.lower().startswith(t.lower()):
            return True
    return False


def parse_feed(xml_text, fuente="Chollometro"):
    """Devuelve lista de ofertas (dicts) desde el texto XML de un RSS de Chollometro."""
    root = ET.fromstring(xml_text)
    ofertas = []
    for item in root.findall(".//item"):
        merch = item.find("pepper:merchant", NS)
        tienda = merch.get("name") if merch is not None else None
        if not tienda_valida(tienda):
            continue

        titulo = (item.findtext("title") or "").strip()
        descripcion = item.findtext("description") or ""
        precio_txt = merch.get("price") if merch is not None else None
        media = item.find("media:content", NS)
        imagen = media.get("url") if media is not None else None

        ofertas.append({
            "id": (item.findtext("guid") or item.findtext("link") or titulo).strip(),
            "titulo": titulo,
            "tienda": tienda,
            "precio_txt": precio_txt,
            "precio_num": precio_a_numero(precio_txt),
            "descuento": extraer_descuento(titulo, descripcion),
            "categoria": (item.findtext("category") or "Otros").strip(),
            "enlace": (item.findtext("link") or "").strip(),
            "imagen": imagen,
            "fecha_pub": (item.findtext("pubDate") or "").strip(),
            "fuente": fuente,
        })
    return ofertas


def cargar_historial():
    if os.path.exists(HIST_FILE):
        try:
            with open(HIST_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            print("⚠ historial ilegible, empiezo uno nuevo.")
    return {}


def guardar_historial(hist):
    # Recorta al tope, quedándonos con las más recientes por 'primera_vez'
    if len(hist) > MAX_ITEMS:
        ordenadas = sorted(hist.values(), key=lambda o: o.get("primera_vez", ""), reverse=True)
        hist = {o["id"]: o for o in ordenadas[:MAX_ITEMS]}
    with open(HIST_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)
    return hist


def generar_html(hist):
    items = sorted(hist.values(), key=lambda o: o.get("primera_vez", ""), reverse=True)
    con_desc = sum(1 for o in items if o.get("descuento") is not None)
    top = sum(1 for o in items if (o.get("descuento") or 0) >= UMBRAL_DESCUENTO)
    cats = sorted({o.get("categoria", "Otros") for o in items})

    datos_json = json.dumps(items, ensure_ascii=False)
    cats_json = json.dumps(cats, ensure_ascii=False)
    actualizado = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    return HTML_TEMPLATE.format(
        total=len(items), con_desc=con_desc, top=top, umbral=UMBRAL_DESCUENTO,
        actualizado=html.escape(actualizado), datos=datos_json, cats=cats_json,
    )


def main():
    hist = cargar_historial()
    nuevas = 0
    ahora = datetime.datetime.now().isoformat(timespec="seconds")

    for url in FEEDS:
        try:
            xml_text = http_get(url)
        except Exception as e:  # noqa: BLE001
            print(f"⚠ No pude leer {url}: {e}")
            continue
        for oferta in parse_feed(xml_text):
            if SOLO_CON_DESCUENTO and (oferta.get("descuento") or 0) < UMBRAL_DESCUENTO:
                continue
            oid = oferta["id"]
            if oid in hist:
                # ya lo teníamos: actualizamos precio por si cambió, mantenemos primera_vez
                hist[oid]["precio_txt"] = oferta["precio_txt"]
                hist[oid]["precio_num"] = oferta["precio_num"]
                if oferta["descuento"] is not None:
                    hist[oid]["descuento"] = oferta["descuento"]
            else:
                oferta["primera_vez"] = ahora
                hist[oid] = oferta
                nuevas += 1

    hist = guardar_historial(hist)
    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(generar_html(hist))

    print(f"✅ {nuevas} ofertas nuevas de Amazon. Historial total: {len(hist)}.")
    print(f"   Panel: {os.path.abspath(HTML_OUT)}")


# ----------------------------- PANEL HTML ------------------------------
# El historial se incrusta como JSON y se filtra/pinta en el navegador,
# así puedes filtrar por ≥50% detectado, categoría, texto y ordenar.
HTML_TEMPLATE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Historial de chollos · Amazon España</title>
<style>
:root{{--bg:#0e141b;--panel:#161f2b;--panel2:#1d2836;--line:#26374a;--tx:#e9eff5;--mut:#8fa2b6;--save:#2fbf71;--gold:#ffb020}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1240px;margin:0 auto;padding:26px 18px 60px}}
header h1{{margin:0 0 6px;font-size:24px;letter-spacing:-.02em}}
header h1 .es{{color:var(--save)}}
.sub{{color:var(--mut);font-size:13px}}
.sub b{{color:var(--tx)}}
.controls{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:18px 0;padding:14px;background:var(--panel);border:1px solid var(--line);border-radius:12px}}
.controls input,.controls select{{background:var(--panel2);color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:13px}}
.controls input[type=search]{{flex:1;min-width:160px}}
.chk{{display:flex;align-items:center;gap:7px;font-size:13px;color:var(--mut);cursor:pointer;user-select:none}}
.chk input{{width:16px;height:16px;accent-color:var(--save)}}
#n{{font-size:13px;color:var(--mut);margin-left:auto}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:14px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column;transition:transform .12s,border-color .12s}}
.card:hover{{transform:translateY(-3px);border-color:var(--save)}}
.thumb{{background:#fff;height:160px;display:flex;align-items:center;justify-content:center;padding:10px;position:relative}}
.thumb img{{max-width:100%;max-height:100%;object-fit:contain}}
.tag-cat{{position:absolute;top:8px;left:8px;background:rgba(13,20,28,.82);color:#cbd6e2;font-size:10px;padding:3px 7px;border-radius:6px}}
.badge{{position:absolute;top:8px;right:8px;font-weight:800;font-size:13px;padding:3px 8px;border-radius:7px}}
.badge.top{{background:var(--save);color:#04210f}}
.badge.mid{{background:var(--gold);color:#3a2600}}
.body{{padding:11px 12px 13px;display:flex;flex-direction:column;gap:7px;flex:1}}
.title{{font-size:13px;line-height:1.34;color:var(--tx);text-decoration:none;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;min-height:52px}}
.title:hover{{color:var(--save)}}
.row{{display:flex;align-items:baseline;gap:8px;margin-top:auto}}
.price{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:18px;font-weight:700}}
.store{{font-size:11px;color:var(--mut)}}
.date{{font-size:10px;color:var(--mut)}}
.empty{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:40px;text-align:center;color:var(--mut)}}
.foot{{margin-top:30px;color:var(--mut);font-size:12px;line-height:1.7;border-top:1px solid var(--line);padding-top:16px}}
</style></head><body>
<div class="wrap">
  <header>
    <h1>🎯 Historial de chollos · <span class="es">Amazon España</span></h1>
    <div class="sub">Fuente: Chollometro · Actualizado: <b>{actualizado}</b> ·
      <b>{total}</b> ofertas guardadas · <b>{con_desc}</b> con % detectado ·
      <b>{top}</b> con ≥{umbral}% detectado</div>
  </header>

  <div class="controls">
    <input type="search" id="q" placeholder="Buscar producto...">
    <select id="cat"><option value="">Todas las categorías</option></select>
    <select id="sort">
      <option value="fecha">Más recientes</option>
      <option value="precio_asc">Precio: menor a mayor</option>
      <option value="precio_desc">Precio: mayor a menor</option>
      <option value="desc_desc">Mayor % detectado</option>
    </select>
    <label class="chk"><input type="checkbox" id="only"> Solo ≥{umbral}% detectado</label>
    <span id="n"></span>
  </div>

  <div id="grid" class="grid"></div>

  <div class="foot">
    Datos de Chollometro (ofertas publicadas por su comunidad). El % solo se muestra
    cuando la propia oferta lo indica; el precio de referencia real no viene en el feed.
    Comprueba siempre el precio final en la tienda antes de comprar.
  </div>
</div>

<script>
const DATA = {datos};
const CATS = {cats};
const UMBRAL = {umbral};

const grid = document.getElementById('grid');
const q = document.getElementById('q');
const cat = document.getElementById('cat');
const sort = document.getElementById('sort');
const only = document.getElementById('only');
const n = document.getElementById('n');

CATS.forEach(c => {{ const o=document.createElement('option'); o.value=c; o.textContent=c; cat.appendChild(o); }});

function esc(s){{ return (s||'').replace(/[&<>"]/g, m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[m])); }}

function card(o){{
  const badge = o.descuento!=null
    ? `<span class="badge ${{o.descuento>=UMBRAL?'top':'mid'}}">-${{o.descuento}}%</span>` : '';
  const img = o.imagen
    ? `<img src="${{esc(o.imagen)}}" alt="" loading="lazy" onerror="this.style.display='none'">` : '';
  const precio = o.precio_txt ? esc(o.precio_txt) : '—';
  return `<article class="card">
    <div class="thumb"><span class="tag-cat">${{esc(o.categoria)}}</span>${{badge}}${{img}}</div>
    <div class="body">
      <a class="title" href="${{esc(o.enlace)}}" target="_blank" rel="noopener">${{esc(o.titulo)}}</a>
      <div class="row"><span class="price">${{precio}}</span><span class="store">${{esc(o.tienda)}}</span></div>
      <span class="date">Visto: ${{esc((o.primera_vez||'').replace('T',' ').slice(0,16))}}</span>
    </div>
  </article>`;
}}

function render(){{
  const term = q.value.trim().toLowerCase();
  const c = cat.value;
  let items = DATA.filter(o => {{
    if (only.checked && !(o.descuento!=null && o.descuento>=UMBRAL)) return false;
    if (c && o.categoria!==c) return false;
    if (term && !(o.titulo||'').toLowerCase().includes(term)) return false;
    return true;
  }});
  const s = sort.value;
  items.sort((a,b)=>{{
    if(s==='precio_asc') return (a.precio_num??1e12)-(b.precio_num??1e12);
    if(s==='precio_desc') return (b.precio_num??-1)-(a.precio_num??-1);
    if(s==='desc_desc') return (b.descuento??-1)-(a.descuento??-1);
    return (b.primera_vez||'').localeCompare(a.primera_vez||'');
  }});
  n.textContent = items.length + ' resultado(s)';
  grid.innerHTML = items.length ? items.map(card).join('')
    : '<div class="empty">No hay ofertas con estos filtros.</div>';
}}

[q,cat,sort,only].forEach(el => el.addEventListener('input', render));
render();
</script>
</body></html>"""


if __name__ == "__main__":
    main()
