content = open('main.py').read()
old = '''                if success:
                    successful_boxes.append(box_number)
                    logger.success(f"✅ Box {box_number} renewed successfully")
                else:
                    failed_boxes.append(box_number)
                    logger.error(f"❌ Box {box_number} failed after retries")
                await asyncio.sleep(config.delay_between_boxes)'''

new = '''                if success:
                    successful_boxes.append(box_number)
                    logger.success(f"✅ Box {box_number} renewed successfully")
                else:
                    failed_boxes.append(box_number)
                    logger.error(f"❌ Box {box_number} failed after retries")

                # Close any remaining popups before next box
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

content = content.replace(old, new)
open('main.py', 'w').write(content)
print('Done')
