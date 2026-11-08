// Check the notebook against the live Energy Access Explorer tool.
//
// Opens the EAE web tool in a headless browser with the settings the notebook wrote to
// outputs/validation/eae_check_settings.json, runs EAE's own analysis, and saves its
// district scores to outputs/validation/eae_tool_ani_districts.json. It also saves a screenshot of
// the tool at district level (outputs/figures/fig0_eae_tool_screenshot.png).
//
// Usage, from the repository root (needs Node and Playwright with Chromium):
//   node tools/eae_check.js [settings.json] [output.json] [screenshot.png]
const { chromium } = require('playwright');
const fs = require('fs');

const settingsPath = process.argv[2] || 'outputs/validation/eae_check_settings.json';
const outPath = process.argv[3] || 'outputs/validation/eae_tool_ani_districts.json';
const shotPath = process.argv[4] || 'outputs/figures/fig0_eae_tool_screenshot.png';
const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
const toolUrl = `https://www.energyaccessexplorer.org/tool/a/?id=${settings.geography}`;

(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

  // The tool restores a saved analysis from sessionStorage 'config' on load.
  await page.goto(toolUrl, { waitUntil: 'domcontentloaded', timeout: 120000 });
  const config = {
    index: settings.index, view: 'outputs', variant: 'raster', tab: 'controls',
    datasets: settings.datasets.map(d => ({
      id: d.id, name: d.id, weight: d.weight,
      domain: { min: d.min, max: d.max }, _domain: { min: d.min, max: d.max },
    })),
  };
  await page.evaluate(c => sessionStorage.setItem('config', JSON.stringify(c)), config);
  await page.goto(toolUrl, { waitUntil: 'domcontentloaded', timeout: 120000 });

  // Wait until every active layer's raster has loaded (the outline is always active too).
  await page.waitForFunction(n => {
    try {
      return typeof STATE !== 'undefined' && STATE.datasets.length >= n &&
        STATE.datasets.every(d => d.raster && d.raster.data);
    } catch (e) { return false; }
  }, settings.datasets.length, { timeout: 240000, polling: 1000 });

  const result = await page.evaluate(async ({ index, tier }) => {
    const analysis = await import('/tool/a/analysis.js');
    await new Promise(r => setTimeout(r, 3000));
    const res = await analysis.analysis_result(index, tier);
    const areas = {};
    for (const id in res.areas) {
      areas[id] = { score: res.areas[id].score, bucket: res.areas[id].bucket && res.areas[id].bucket.label };
    }
    let analysed = 0;
    for (let i = 0; i < res.cells.length; i++) if (res.cells[i] > 0) analysed++;
    return {
      active: STATE.datasets.map(d => ({ id: d.id, weight: d.weight, _domain: d._domain, index: d.index })),
      areas, analysed_cells: analysed, retrieved: new Date().toISOString(),
    };
  }, { index: settings.index, tier: settings.divtier });

  fs.writeFileSync(outPath, JSON.stringify(result, null, 1));

  // Screenshot: district view of the Assistance Need Index with EAE's results panel.
  const ok = page.getByText('OK', { exact: true });
  if (await ok.count()) await ok.first().click().catch(() => {});
  const area = page.locator('select').first();
  const options = await area.locator('option').allTextContents();
  const district = options.find(o => /district/i.test(o));
  if (district) await area.selectOption({ label: district });
  await page.getByText('Hide all layers').click().catch(() => {});
  await page.waitForTimeout(6000);
  await page.getByText('Show Analysis Results').click().catch(() => {});
  await page.waitForTimeout(6000);
  await page.screenshot({ path: shotPath });
  console.log(`EAE tool: ${Object.keys(result.areas).length} districts scored, ${result.analysed_cells} cells analysed -> ${outPath}, ${shotPath}`);
  await browser.close();
})().catch(e => { console.error('EAE check failed:', e.message); process.exit(1); });
