import html
from .models import Product

def render(p: Product, personalized: bool):
    # Intentionally changes ONE variable: a returning_customer cookie. Synthetic experiment.
    delta=12 if personalized and '/anchor' in p.url and '?offer=' not in p.url else 0
    fields=p.model_dump(mode='json')
    if delta:
        fields['advertised']=str(p.advertised+delta)
        fields['final']=str(p.final+delta)
    fields['materials']=';'.join(f'{m.name}:{m.fraction}' for m in p.materials)
    fields['recurring']='true' if p.recurring else 'false'
    fields.pop('claims')
    content=''.join(f'<dt>{html.escape(k.replace("_"," "))}</dt><dd data-qct="{k}">{html.escape(str(v))}</dd>' for k,v in fields.items() if v is not None)
    claims=''.join(f'<li data-qct="claim">{html.escape(c)}</li>' for c in p.claims)
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{html.escape(p.name)} · Controlled demo storefront</title>
    <style>body{{font:16px system-ui;background:#0a0d12;color:#e5eaf1;max-width:740px;margin:60px auto;padding:24px}}h1{{font-size:38px}}small{{color:#77d8bc}}dl{{display:grid;grid-template-columns:1fr 1fr;gap:14px;background:#141a23;padding:24px;border-radius:12px}}dt{{color:#8f9cab}}dd{{margin:0}}a{{color:#94d5ff}}</style>
    <small>QCT / CONTROLLED SYNTHETIC STOREFRONT / NOT A REAL RETAIL LISTING</small><h1>{html.escape(p.name)}</h1>
    <p>Demo merchant for DOM extraction, cookie-based price comparison and PayPal Sandbox checkout.</p>
    <p>Reference price: <s data-qct="slashed-reference">{p.reference or 'none'}</s></p><dl>{content}</dl><ul>{claims}</ul>
    <p>Final price includes item, shipping, tax and checkout fees. Recurring charges are separate.</p><a href="/">Return to terminal</a></html>'''
