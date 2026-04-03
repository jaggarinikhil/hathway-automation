content = open('main.py').read()
old = '''                # Close any remaining popups before next box
                await asyncio.sleep(2.0)
                await page.evaluate("""
                    var ids = ['MasterBody_pnlrenewalPlan','MasterBody_pnlAdd','mpeAdd_backgroundElement'];
                    ids.forEach(function(id) {
                        var el = document.getElementById(id);
                        if (el) el.style.display = 'none';
                    });
                    var btns = document.querySelectorAll('input[type=button],input[type=submit],button');
                    for (var i=0; i<btns.length; i++) {
                        var v = (btns[i].value || btns[i].innerText || '').trim().toUpperCase();
                        if (v === 'OK') { btns[i].click(); break; }
                    }
                """)
                await asyncio.sleep(config.delay_between_boxes)'''

new = '''                # Close any remaining popups before next box
                await asyncio.sleep(2.0)
                await page.evaluate("""
                    // Click OK or Cancel on any visible popup
                    var btns = document.querySelectorAll('input[type=button],input[type=submit],button');
                    for (var i=0; i<btns.length; i++) {
                        var v = (btns[i].value || btns[i].innerText || '').trim().toUpperCase();
                        if (v === 'OK') { btns[i].click(); break; }
                    }
                """)
                await asyncio.sleep(1.0)
                await page.evaluate("""
                    // Click Cancel if still visible
                    var btns = document.querySelectorAll('input[type=button],input[type=submit],button');
                    for (var i=0; i<btns.length; i++) {
                        var v = (btns[i].value || btns[i].innerText || '').trim().toUpperCase();
                        if (v === 'CANCEL') {
                            var el = btns[i];
                            if (el.offsetParent !== null) { el.click(); break; }
                        }
                    }
                    // Hide all popups
                    var ids = ['MasterBody_pnlrenewalPlan','MasterBody_pnlAdd','mpeAdd_backgroundElement'];
                    ids.forEach(function(id) {
                        var el = document.getElementById(id);
                        if (el) el.style.display = 'none';
                    });
                """)
                await asyncio.sleep(1.0)
                # Clear search box for next box
                await page.evaluate("""
                    var sb = document.getElementById('MasterBody_txtSearchParam');
                    if (sb) sb.value = '';
                """)
                await asyncio.sleep(config.delay_between_boxes)'''

content = content.replace(old, new)
open('main.py', 'w').write(content)
print('Done')
