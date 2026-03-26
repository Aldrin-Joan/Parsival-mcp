import re, base64
from bs4 import BeautifulSoup
text='<html><body><img src="http://example.com/image.png" /><img src="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD" /></body></html>'
EXTERNAL_URL_PATTERN = re.compile(r'^https?://', re.IGNORECASE)
DATA_URI_PATTERN = re.compile(r'^data:(image/[^;]+);base64,(.+)$', re.IGNORECASE)
soup = BeautifulSoup(text, 'lxml')
for img in soup.find_all('img'):
    src = img.attrs.get('src','').strip()
    print('src', src, 'external', bool(EXTERNAL_URL_PATTERN.match(src)))
    m = DATA_URI_PATTERN.match(src)
    print('m', m)
    if m:
        mime,b64payload = m.groups()
        payload = base64.b64decode(b64payload)
        print('decoded', mime, len(payload))
