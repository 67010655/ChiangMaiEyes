import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createContext, runInContext } from 'node:vm';
import { JSDOM } from 'jsdom';
import { describe, expect, it, vi } from 'vitest';

const html = readFileSync(resolve(__dirname, '../index.html'), 'utf8');
const source = html.slice(html.indexOf('// ---- fetch with timeout'), html.indexOf('// Boot: always LIVE'));

function setup() {
  const dom = new JSDOM('<span id="footMode"></span><span id="connectionLabel"></span><div id="connectionStatus"></div><span id="publicBriefFreshness"></span><div id="mapRenderStatus" hidden></div><div id="liveLoading"></div><div id="phaseview"></div>');
  const response = { hotspots: { count: 3, items: [] } };
  const fetch = vi.fn(async (url: string) => ({ ok: true, json: async () => url === '/api/dashboard' ? response : null }));
  const paint = vi.fn(), toast = vi.fn();
  const ctx = createContext({ document: dom.window.document, AbortController, fetch,
    setTimeout: (callback: () => void, ms: number) => setTimeout(callback, ms === 1200 ? 0 : ms), clearTimeout,
    API_BASE: '', applyLive: paint, dataMode: 'live', liveDataQ: null, livePhasesPending: false,
    CmeEvidence: { stamp: (value: string) => value }, toast, console: { error: vi.fn() },
    hideSplash: vi.fn(), renderPhasePanel: vi.fn(),
  });
  runInContext(source, ctx);
  return { dom, ctx, fetch, paint, toast, response };
}

describe('dashboard connection and rendering states', () => {
  it('keeps a successful backend connection live when drawing fails', async () => {
    const { dom, ctx, paint } = setup();
    paint.mockImplementation(() => { throw new Error('canvas draw failed'); });
    await runInContext('goLive(false)', ctx);
    expect(dom.window.document.getElementById('footMode')!.textContent).toBe('LIVE');
    expect(dom.window.document.getElementById('connectionStatus')!.classList.contains('is-offline')).toBe(false);
    expect(dom.window.document.getElementById('mapRenderStatus')!.hidden).toBe(false);
    expect(runInContext('liveRefreshPending', ctx)).toBe(false);
    dom.window.close();
  });

  it('recovers from a rendering error and clears its separate warning', async () => {
    const { dom, ctx, paint } = setup();
    paint.mockImplementationOnce(() => { throw new Error('transient drawing failure'); });
    await runInContext('goLive(false)', ctx);
    expect(dom.window.document.getElementById('mapRenderStatus')!.hidden).toBe(false);
    await runInContext('goLive(true)', ctx);
    expect(dom.window.document.getElementById('mapRenderStatus')!.hidden).toBe(true);
    expect(dom.window.document.getElementById('footMode')!.textContent).toBe('LIVE');
    dom.window.close();
  });

  it('reports a genuine first-load connection failure without claiming cached data', async () => {
    const { dom, ctx, fetch, toast } = setup();
    fetch.mockRejectedValue(new TypeError('Failed to fetch'));
    await runInContext('goLive(false)', ctx);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(dom.window.document.getElementById('footMode')!.textContent).toBe('OFFLINE');
    expect(dom.window.document.getElementById('publicBriefFreshness')!.textContent).toContain('ยังไม่ได้รับข้อมูล');
    expect(toast.mock.calls.at(-1)![0]).toContain('ยังไม่มีข้อมูล');
    expect(dom.window.document.getElementById('mapRenderStatus')!.hidden).toBe(true);
    dom.window.close();
  });

  it('retains the last receipt time and does not repaint on a failed refresh', async () => {
    const { dom, ctx, fetch, paint } = setup();
    await runInContext('goLive(false)', ctx);
    const received = runInContext('lastDashboardReceivedAt', ctx);
    const count = paint.mock.calls.length;
    fetch.mockRejectedValue(new TypeError('Failed to fetch'));
    await runInContext('goLive(false)', ctx);
    expect(paint.mock.calls.length).toBe(count);
    expect(runInContext('lastDashboardReceivedAt', ctx)).toBe(received);
    expect(dom.window.document.getElementById('publicBriefFreshness')!.textContent).toContain(received);
    expect(dom.window.document.getElementById('connectionStatus')!.title).toContain('รับเมื่อ');
    dom.window.close();
  });

  it('does not relabel successful core data when optional history is unavailable', async () => {
    const { dom, ctx, fetch, response } = setup();
    fetch.mockImplementation(async url => {
      if (url !== '/api/dashboard') throw new TypeError('optional endpoint unavailable');
      return { ok: true, json: async () => response };
    });
    await runInContext('goLive(false)', ctx);
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(dom.window.document.getElementById('footMode')!.textContent).toBe('LIVE');
    expect(dom.window.document.getElementById('mapRenderStatus')!.hidden).toBe(true);
    dom.window.close();
  });

  it('keeps the connection live if a later history repaint fails', async () => {
    const { dom, ctx, fetch, response, paint } = setup();
    fetch.mockImplementation(async url => ({ ok: true, json: async () => url === '/api/dashboard' ? response : { hotspots: [] } }));
    paint.mockImplementationOnce(() => undefined).mockImplementation(() => { throw new Error('history repaint failed'); });
    await runInContext('goLive(false)', ctx);
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(paint.mock.calls.length).toBeGreaterThan(1);
    expect(dom.window.document.getElementById('footMode')!.textContent).toBe('LIVE');
    expect(dom.window.document.getElementById('mapRenderStatus')!.hidden).toBe(false);
    dom.window.close();
  });
});

describe('hotspot selection with a popup', () => {
  function setupSelection() {
    const dom = new JSDOM('<section id="detailBlock"><h2></h2></section><div id="detailEmpty"></div><div id="detailBody"></div><div id="publicBriefDetails" hidden></div>');
    const openDrawer = vi.fn(), closeDrawers = vi.fn(), flyTo = vi.fn();
    const ctx = createContext({ document: dom.window.document, selected: null,
      spreadCone: () => ({ km: 2 }), wind: () => ({ deg: 0 }), CRITICAL_FRP_MW: 50,
      CmeEvidence: { confidenceLabel: () => 'nominal', escapeHtml: (s: string) => s },
      CmeCoordination: { html: () => '<section>ใครควรดูแลจุดนี้</section>' },
      formatAge: () => '20 นาที', animateDetail: vi.fn(), map: { flyTo }, motionDuration: () => 0,
      isMobileViewport: () => true, openMobileDrawer: openDrawer, closeMobileDrawers: closeDrawers,
      toggleBriefDetails: vi.fn(), setTimeout: vi.fn(),
    });
    const start = html.indexOf('function selectHotspot(');
    runInContext(html.slice(start, html.indexOf('\nfunction ', start + 10)), ctx);
    return { dom, ctx, openDrawer, closeDrawers, flyTo };
  }

  it('leaves marker popup controls reachable without a second drawer or competing map pan', () => {
    const { dom, ctx, openDrawer, closeDrawers, flyTo } = setupSelection();
    runInContext("selectHotspot({id:'real-marker',lat:18.8,lon:98.9,conf:'nominal',detected:20},{fromMarker:true})", ctx);
    expect(dom.window.document.getElementById('detailBody')!.textContent).toContain('real-marker');
    expect(openDrawer).not.toHaveBeenCalled();
    expect(flyTo).not.toHaveBeenCalled();
    expect(closeDrawers).toHaveBeenCalledOnce();
    dom.window.close();
  });

  it('preserves opening the detail drawer when choosing an item from a list', () => {
    const { dom, ctx, openDrawer, flyTo } = setupSelection();
    runInContext("selectHotspot({id:'list-item',lat:18.8,lon:98.9,conf:'nominal',detected:20})", ctx);
    expect(openDrawer).toHaveBeenCalledWith('right');
    expect(flyTo).toHaveBeenCalledOnce();
    dom.window.close();
  });
});

describe('optional map layers cannot leave dashboard widgets stale', () => {
  function setupLayers() {
    const state = setup();
    const { dom, ctx } = state;
    dom.window.document.body.insertAdjacentHTML('beforeend', [
      'kpiHot', 'kpiCrit', 'kpiPm', 'kpiAqi', 'pmPeak', 'pmPeakTr', 'visKm', 'visTr', 'footUpd',
    ].map(id => `<div id="${id}">previous response</div>`).join('') + '<button class="layer on" data-layer="heat"></button>');
    const heat = {}, addLayer = vi.fn(() => { throw new Error('heat canvas failed'); });
    const jobs = Object.fromEntries(['renderHotspots', 'renderSpread', 'renderPm', 'renderWind', '_sync3DHotspots', 'buildAlerts', 'setWindBadge', 'rankList', 'lineChart', 'barChart', 'syncPublicMapLayers'].map(name => [name, vi.fn()]));
    Object.assign(ctx, jobs, {
      hotspots: [], pmStations: [{ pm: 12 }], currentDashboard: { pm25: { current_pm25: 12 } },
      liveDataQ: { hotspots: { source_mode: 'LIVE', is_stale: false }, pm25: { source_mode: 'LIVE', is_stale: false } },
      CRITICAL_FRP_MW: 50, updatePmTrendMean: vi.fn(), updatePublicBrief: vi.fn(),
      map: { removeLayer: vi.fn(), addLayer }, layers: { heat }, buildHeat: () => heat,
      analyticsEl: dom.window.document.createElement('section'), pm24: [12], hot7: [0], stamp: () => 'new response time',
    });
    ctx.CmeEvidence = { ...ctx.CmeEvidence, filterHotspots: (items: unknown[]) => items };
    for (const name of ['setKpis', 'rerenderAll']) {
      const start = html.indexOf('function ' + name + '(');
      runInContext(html.slice(start, html.indexOf('\nfunction ', start + 10)), ctx);
    }
    return { ...state, jobs, addLayer };
  }

  it('publishes zero hotspots and new PM/alerts/charts/time even if adding heat throws', () => {
    const { dom, ctx, jobs, addLayer } = setupLayers();
    dom.window.document.getElementById('kpiHot')!.textContent = '8';
    runInContext('rerenderAll()', ctx);
    expect(addLayer).toHaveBeenCalled();
    expect(dom.window.document.getElementById('kpiHot')!.textContent).toBe('0');
    expect(dom.window.document.getElementById('kpiPm')!.textContent).toContain('12');
    expect(dom.window.document.getElementById('footUpd')!.textContent).toBe('new response time');
    for (const name of ['buildAlerts', 'rankList', 'setWindBadge', 'lineChart', 'barChart', 'syncPublicMapLayers']) expect(jobs[name]).toHaveBeenCalledOnce();
    expect(dom.window.document.getElementById('mapRenderStatus')!.hidden).toBe(false);
    dom.window.close();
  });

  it('continues other layers when hotspot drawing fails and preserves both failures until recovered', () => {
    const { dom, ctx, jobs, addLayer } = setupLayers();
    jobs.renderHotspots.mockImplementation(() => { throw new Error('point layer failed'); });
    runInContext('rerenderAll()', ctx);
    for (const name of ['renderSpread', 'renderPm', 'renderWind', '_sync3DHotspots']) expect(jobs[name]).toHaveBeenCalled();
    expect(runInContext('[...mapRenderFailures].sort()', ctx)).toEqual(['heat', 'hotspots']);
    addLayer.mockImplementation(() => undefined);
    runInContext('rerenderAll()', ctx);
    expect(runInContext('[...mapRenderFailures]', ctx)).toEqual(['hotspots']);
    expect(dom.window.document.getElementById('mapRenderStatus')!.hidden).toBe(false);
    jobs.renderHotspots.mockImplementation(() => undefined);
    runInContext('rerenderAll()', ctx);
    expect(dom.window.document.getElementById('mapRenderStatus')!.hidden).toBe(true);
    dom.window.close();
  });
});

describe('boundary retrieval and map fitting have separate failures', () => {
  it('retains district data and draws districts when fitting the map throws', async () => {
    const { dom, ctx } = setup();
    dom.window.document.body.insertAdjacentHTML('beforeend', '<span id="lcBoundaries"></span>');
    const districts = { features: [{ properties: { nameTh: 'Fixture district' } }] };
    const geoJSON = vi.fn(() => ({ addTo: vi.fn().mockReturnThis(), getBounds: () => ({ valid: true }) }));
    const error = vi.fn();
    Object.assign(ctx, { fetch: vi.fn(async () => ({ ok: true, json: async () => districts })),
      window:dom.window,
      layers: { boundaries: { clearLayers: vi.fn() } }, L: { geoJSON },
      map: { fitBounds: vi.fn(() => { throw new Error('heat failed during fit'); }) },
      _districtFeatures: [], _provinceBoundsForFit: null, livePhases: null, console: { error },
    });
    const start = html.indexOf('async function loadBoundaries()');
    const end = html.indexOf('\nasync function ', start + 10);
    runInContext(html.slice(start, end), ctx);
    await runInContext('loadBoundaries()', ctx);
    expect(geoJSON).toHaveBeenCalledTimes(2);
    expect(ctx._districtFeatures).toEqual(districts.features);
    expect(dom.window.document.getElementById('lcBoundaries')!.textContent).toBe('1');
    expect(error.mock.calls.some(call => call[0].includes('boundary-fit'))).toBe(true);
    expect(error.mock.calls.some(call => call[0].includes('Failed to load boundary GeoJSON'))).toBe(false);
    expect(dom.window.document.getElementById('mapRenderStatus')!.hidden).toBe(false);
    dom.window.close();
  });
});
