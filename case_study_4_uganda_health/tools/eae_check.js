// Check the notebook against the live Energy Access Explorer tool.
//
// Opens the EAE web tool in a headless browser with the settings the notebook wrote to
// outputs/validation/eae_check_settings.json, runs EAE's own analysis, and saves its
// district scores to outputs/validation/eae_tool_ani_districts.json.
//
// Usage, from the case_study_4_uganda_health folder (needs Node and Playwright with Chromium):
//   node tools/eae_check.js [settings.json] [output.json]
const { chromium } = require('playwright');
const fs = require('fs');

const settingsPath = process.argv[2] || 'outputs/validation/eae_check_settings.json';
const outPath = process.argv[3] || 'outputs/validation/eae_tool_ani_districts.json';
const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
const toolUrl = `https://www.energyaccessexplorer.org/tool/a/?id=${settings.geography}`;

(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

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
  console.log(`EAE tool: ${Object.keys(result.areas).length} districts scored, ${result.analysed_cells} cells analysed -> ${outPath}`);
  await browser.close();
})().catch(e => { console.error('EAE check failed:', e.message); process.exit(1); });
