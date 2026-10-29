'use strict';

const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const net = require('node:net');
const fs = require('node:fs/promises');
const path = require('node:path');

const DRIVER_PORT = 9515;
async function freePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => server.once('error', reject).listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}
async function eventually(fn, description, timeoutMs = 20000) {
  const end = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < end) {
    try { const value = await fn(); if (value) return value; } catch (error) { lastError = error; }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`Timed out waiting for ${description}${lastError ? `: ${lastError.message}` : ''}`);
}
class WebDriver {
  constructor() { this.sessionId = null; this.process = null; }
  async request(method, route, body) {
    const response = await fetch(`http://127.0.0.1:${DRIVER_PORT}${route}`, {
      method,
      headers: body === undefined ? {} : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok || result.value?.error) throw new Error(JSON.stringify(result.value || result));
    return result.value;
  }
  route(suffix) { return `/session/${this.sessionId}${suffix}`; }
  async start() {
    this.process = spawn('chromedriver', [`--port=${DRIVER_PORT}`], { stdio: 'ignore' });
    await eventually(async () => (await fetch(`http://127.0.0.1:${DRIVER_PORT}/status`)).ok, 'ChromeDriver readiness');
    const created = await this.request('POST', '/session', { capabilities: { alwaysMatch: {
      browserName: 'chrome',
      'goog:chromeOptions': { args: ['--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1365,900'] },
      'goog:loggingPrefs': { browser: 'ALL' },
    } } });
    this.sessionId = created.sessionId;
  }
  async navigate(url) { await this.request('POST', this.route('/url'), { url }); }
  async script(script) { return this.request('POST', this.route('/execute/sync'), { script, args: [] }); }
  async element(selector) {
    const result = await this.request('POST', this.route('/element'), { using: 'css selector', value: selector });
    return result['element-6066-11e4-a52e-4f735466cecf'];
  }
  async click(selector) { const id = await this.element(selector); await this.request('POST', this.route(`/element/${id}/click`), {}); }
  async setSize(width, height) { await this.request('POST', this.route('/window/rect'), { width, height }); }
  async logs() { return this.request('POST', this.route('/log'), { type: 'browser' }); }
  async screenshot(file) {
    const data = await this.request('GET', this.route('/screenshot'));
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, Buffer.from(data, 'base64'));
  }
  async stop() {
    if (this.sessionId) await this.request('DELETE', this.route('')).catch(() => {});
    if (this.process && this.process.exitCode === null) this.process.kill('SIGTERM');
  }
}
async function main() {
  const port = await freePort();
  const backend = spawn(process.env.PYTHON || 'python', ['-m', 'uvicorn', 'app.api:app', '--host', '127.0.0.1', '--port', String(port)], {
    cwd: path.resolve(__dirname, '..'),
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
    stdio: 'ignore',
  });
  const browser = new WebDriver();
  try {
    await eventually(async () => {
      if (backend.exitCode !== null) throw new Error(`API exited with code ${backend.exitCode}`);
      try { return (await fetch(`http://127.0.0.1:${port}/ready`)).ok; } catch { return false; }
    }, 'production-mode candidate API readiness');
    await browser.start();
    await browser.navigate(`http://127.0.0.1:${port}/`);
    await browser.script("window.__testErrors=[]; addEventListener('error', event => window.__testErrors.push(event.message));");
    await eventually(() => browser.script("return document.querySelector('#service-state')?.textContent === 'Model ready'"), 'model readiness in the running UI');
    await browser.click('#submit');
    await eventually(() => browser.script("return document.querySelector('#answer')?.hidden === false"), 'model-backed result card');
    const result = await browser.script("return { score: document.querySelector('#score').textContent, risk: document.querySelector('#risk-chip').textContent, error: document.querySelector('#error').textContent }");
    const probability = Number.parseFloat(result.score);
    assert.ok(Number.isFinite(probability) && probability >= 0 && probability <= 100, `result probability must be bounded: ${JSON.stringify(result)}`);
    assert.ok(['LOW RISK', 'MEDIUM RISK', 'HIGH RISK'].includes(result.risk.toUpperCase()), `known risk level required: ${JSON.stringify(result)}`);
    assert.equal(result.error, '', 'valid fixture profile should not show a form error');

    await browser.setSize(390, 844);
    const mobile = await browser.script("return { width:innerWidth, scrollWidth:document.documentElement.scrollWidth, formVisible:!!document.querySelector('#predict-form')?.getClientRects().length, resultVisible:!!document.querySelector('#answer')?.getClientRects().length }");
    assert.ok(mobile.width <= 430 && mobile.scrollWidth <= mobile.width + 1 && mobile.formVisible && mobile.resultVisible, `mobile inference UI should fit and show both form and result: ${JSON.stringify(mobile)}`);
    assert.deepEqual(await browser.script('return window.__testErrors'), [], 'page should have no uncaught errors');
    const severeLogs = (await browser.logs()).filter((item) => item.level === 'SEVERE');
    assert.deepEqual(severeLogs, [], 'browser console should not contain severe errors');
    console.log(`PASS: isolated model readiness, browser form/API inference (${result.risk}, ${result.score}), mobile layout, and browser errors`);
  } catch (error) {
    await browser.screenshot(path.resolve(__dirname, '../test-results/churn-browser-failure.png')).catch(() => {});
    console.error('Churn browser regression failed; screenshot attempted at test-results/churn-browser-failure.png');
    throw error;
  } finally {
    await browser.stop();
    if (backend.exitCode === null) backend.kill('SIGTERM');
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
