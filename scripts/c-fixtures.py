"""Generate wholly synthetic parser fixtures. Python stdlib; optional pypdf for encryption.
No original user material. Run from repository root. pypdf is a test generator only.
"""
from pathlib import Path
import io, zipfile, sys, base64

root = Path('tests/fixtures/c')
root.mkdir(parents=True, exist_ok=True)

def pdf(pages):
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'']
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    kids = []
    for value in pages:
        page_id = len(objects)+1
        kids.append(f'{page_id} 0 R')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id+1} 0 R >>'.encode())
        stream = ('BT /F1 12 Tf 40 740 Td ('+value+') Tj ET').encode()
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream')
    objects[1] = f'<< /Type /Pages /Count {len(kids)} /Kids [{" ".join(kids)}] >>'.encode()
    out = b'%PDF-1.4\n'; offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out)); out += f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start = len(out)
    out += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    out += b''.join(f'{x:010d} 00000 n \n'.encode() for x in offsets[1:])
    out += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
    return out

(root/'book.pdf').write_bytes(pdf(['Synthetic field notebook. Page one has background only.', 'Delivery instruction: leave the prism in the indigo cabinet, drawer L-42.', 'Inspection code: QUARTZ-6815. This is the final page.']))
(root/'blank.pdf').write_bytes(pdf(['', '']))
(root/'damaged.pdf').write_bytes(b'%PDF-1.7\nBroken synthetic fixture')
(root/'large.pdf').write_bytes(pdf(['Book page '+str(i)+'. '+('A bounded paragraph. '*80) for i in range(700)]))
(root/'notes.md').write_bytes(('\ufeff# Synthetic notes\r\n'+('Context 🦉. '*1000)+'\r\nTail: archive drawer R-17.').encode())

def epub(path, extra=None, chapter2=None):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        z.writestr('META-INF/container.xml','<?xml version="1.0"?><container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>')
        z.writestr('OPS/book.opf','<package><manifest><item id="a" href="one.xhtml" media-type="application/xhtml+xml"/><item id="b" href="two.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>')
        z.writestr('OPS/one.xhtml','<html><head><style>ignore me</style></head><body><h1>First chapter</h1><p>'+('Background 🦉. '*900)+'</p><script>fetch("https://invalid.test/")</script></body></html>')
        z.writestr('OPS/two.xhtml', chapter2 or '<html><body><h1>Second chapter</h1><p>The survey beacon is stored in the copper alcove, niche M-73.</p><p>Validation phrase: LICHEN-2948.</p></body></html>')
        if extra:
            for name, content in extra.items(): z.writestr(name, content)

epub(root/'book.epub')
with zipfile.ZipFile(root/'book.epub') as z:
    image_files = {n:z.read(n) for n in z.namelist()}
image_files['OPS/one.xhtml'] = b'<html><body><img src="cover.png" alt=""/></body></html>'
image_files['OPS/two.xhtml'] = image_files['OPS/one.xhtml']
image_files['OPS/book.opf'] = image_files['OPS/book.opf'].replace(b'</manifest>', b'<item id="cover" href="cover.png" media-type="image/png"/></manifest>')
image_files['OPS/cover.png'] = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jYZkAAAAASUVORK5CYII=')
with zipfile.ZipFile(root/'image-only.epub', 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for n,b in image_files.items():
        z.writestr(n, b, compress_type=zipfile.ZIP_STORED if n=='mimetype' else zipfile.ZIP_DEFLATED)
epub(root/'encrypted.epub', {'META-INF/encryption.xml':'<encryption/>'})
epub(root/'traversal.epub', {'../escape.txt':'must never be written'})
epub(root/'remote.epub', chapter2='<html><body><img src="https://invalid.test/x"/><p>Visible local text.</p></body></html>')
epub(root/'entities.epub', chapter2='<!DOCTYPE html [<!ENTITY x SYSTEM "file:///secret">]><html><body>&x;</body></html>')
epub(root/'output-limit.epub', chapter2='<html><body>'+('A'*8_000_020)+'</body></html>')
with zipfile.ZipFile(root/'zip-limit.epub', 'w', compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr('large-entry', b'A'*(16*1024*1024+1))
epub(root/'partial.epub', chapter2='<html><body>Good partial content.</body></html>')
# A missing reading-order item is an explicitly unavailable section.
with zipfile.ZipFile(root/'partial.epub') as z: data = {n:z.read(n) for n in z.namelist() if n!='OPS/two.xhtml'}
with zipfile.ZipFile(root/'partial.epub','w') as z:
    for n,b in data.items():z.writestr(n,b)
try:
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter();writer.append(PdfReader(io.BytesIO((root/'book.pdf').read_bytes())))
    writer.encrypt('synthetic-password')
    with (root/'encrypted.pdf').open('wb') as f:writer.write(f)
except ImportError:
    print('pypdf unavailable; existing encrypted.pdf was preserved', file=sys.stderr)
