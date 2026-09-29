import { chromium } from "playwright";
import { tmpdir } from "node:os";
import { join } from "node:path";

const browser = await chromium.launch({
  headless: true,
  args: ["--enable-webgl", "--use-gl=angle", "--use-angle=swiftshader"],
});
const targetUrl = process.env.CME_TEST_URL || "http://127.0.0.1:5173/";
const mobile = process.env.CME_TEST_MOBILE === "1";
const page = await browser.newPage({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 } });
const errors = [];
const failedRequests = [];
let stage = "startup";
let buildingTileResponses = 0;
const safeError = value => value.replace(/([?&]key=)[^\s)]+/g, "$1[redacted]");
page.on("pageerror", error => errors.push(`${stage}: ${safeError(error.stack || error.message)}`));
page.on("console", message => { if (message.type() === "error") errors.push(`${stage}: ${safeError(message.text())}`); });
page.on("requestfailed", request => {
  const reason = request.failure()?.errorText;
  if (reason !== "net::ERR_ABORTED") failedRequests.push(`${new URL(request.url()).hostname}: ${reason}`);
});
page.on("response", response => {
  if (response.url().includes("/tiles/v4/") && response.status() === 200) {
    buildingTileResponses += 1;
  }
  if (response.url().includes("api.maptiler.com") && response.status() >= 400) {
    failedRequests.push(`MapTiler ${response.status()}`);
  }
});

try {
  await page.goto(targetUrl, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => !!window.maplibregl, { timeout: 15000 });
  const started = Date.now();
  stage = "city";
  await page.evaluate(() => window.open3D());
  await page.waitForFunction(() => {
    const map = mlMap;
    return map?.isStyleLoaded() && map.getSource("buildings-tiles") &&
      map.querySourceFeatures("buildings-tiles", { sourceLayer: "building" }).length > 0;
  }, null, { timeout: 30000 });
  const city = await page.evaluate(() => ({
    zoom: mlMap.getZoom(),
    buildings: mlMap.querySourceFeatures("buildings-tiles", { sourceLayer: "building" }).length,
    terrain: !!mlMap.getTerrain(),
  }));
  const cityLoadMs = Date.now() - started;
  await page.evaluate(() => hideSplash());
  await page.waitForTimeout(500);
  await page.screenshot({ path: join(tmpdir(), mobile ? "chiangmaieyes-3d-mobile-check.png" : "chiangmaieyes-3d-city-check.png") });

  stage = "overview";
  await page.locator("#tdProvince").click();
  await page.waitForFunction(() => mlMap?.getZoom() < 12 && !!mlMap.getTerrain(), null, { timeout: 15000 });
  const overview = await page.evaluate(() => ({ zoom: mlMap.getZoom(), terrain: !!mlMap.getTerrain() }));

  if (!buildingTileResponses) throw new Error("No successful building vector tile response");
  console.log(JSON.stringify({ city, cityLoadMs, buildingTileResponses, overview, pageErrors: errors, failedRequestCount: failedRequests.length }));
} catch (error) {
  console.error(JSON.stringify({ message: error.message, map: await page.evaluate(() => ({
    hasMap: !!mlMap,
    hasKey: !!window.mapTilerKey,
    styleLoaded: mlMap?.isStyleLoaded(),
    hasBuildingSource: !!mlMap?.getSource("buildings-tiles"),
    buildingFeatures: mlMap?.getSource("buildings-tiles") ? mlMap.querySourceFeatures("buildings-tiles", { sourceLayer: "building" }).length : null,
  })), buildingTileResponses, errors, failedRequests: failedRequests.slice(0, 15) }));
  throw error;
} finally {
  await browser.close();
}
