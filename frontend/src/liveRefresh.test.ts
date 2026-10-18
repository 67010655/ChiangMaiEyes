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
