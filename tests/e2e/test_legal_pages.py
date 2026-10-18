"""Öffentlich erreichbar, Navigation ohne JavaScript und mobile Darstellung."""
import sys
from umgebung import BASE  # Testserver je Gruppe (parallel)
from playwright.sync_api import sync_playwright
results=[]
def check(name, value):
    results.append(bool(value)); print(('PASS ' if value else 'FAIL ')+name)
with sync_playwright() as p:
    browser=p.chromium.launch()
    context=browser.new_context(java_script_enabled=False)
    page=context.new_page()
    for width in [390,1280]:
        page.set_viewport_size({'width':width,'height':900})
        for slug,title in [('kontakt','Persönlich für Sie da.'),('impressum','Unser Unternehmen.'),('datenschutz','Ihre Daten. Klar erklärt.')]:
            response=page.goto(BASE + '/'+slug+'/')
            check(f'{slug} public {width}',response.status==200 and page.get_by_role('heading',level=1).inner_text()==title)
            check(f'{slug} no overflow {width}',page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            check(f'{slug} navigation {width}',page.locator('footer nav a').count()==3)
    page.goto(BASE + '/')
    page.get_by_role('navigation',name='Kontakt und Rechtliches').get_by_role('link',name='Impressum').click()
    check('public footer works without JavaScript',page.url.endswith('/impressum/'))
    check('confirmed registration and VAT present',all(s in page.locator('main').inner_text() for s in ['HRA 82828','HRB 52268','DE118949959']))
    page.get_by_role('link',name='Kontakt',exact=True).click()
    check('phone actionable',page.locator('a[href="tel:+49404325880"]').count()==1)
    check('email actionable',page.locator('a[href="mailto:info@standard-fleisch.de"]').count()==1)
    check('no embedded third-party content',page.locator('iframe, img[src^="https:"], script[src^="https:"]').count()==0)
    browser.close()
print(f'{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
