// Pruebas del núcleo i18n: `node --test frontend/src/platform/i18n/i18n.test.mjs`
import test from 'node:test';
import assert from 'node:assert/strict';
import * as i18n from './core.js';

test.beforeEach(() => i18n.resetI18n());

test('espacios de nombres, anidado y fallback al español', () => {
  i18n.registerMessages('platform', { es: { nav: { home: 'Inicio' }, solo: 'Solo es' }, en: { nav: { home: 'Home' } } });
  i18n.registerMessages('proyecto', { es: { titulo: 'Artículos' } });
  assert.equal(i18n.translate('nav.home'), 'Inicio');
  assert.equal(i18n.translate('proyecto:titulo'), 'Artículos');
  i18n.setLocale('en', { persist: false });
  assert.equal(i18n.translate('nav.home'), 'Home');
  assert.equal(i18n.translate('solo'), 'Solo es');
  assert.equal(i18n.translate('no.existe'), 'no.existe');
});

test('interpolación y plurales con Intl.PluralRules', () => {
  i18n.registerMessages('platform', {
    es: { saludo: 'Hola {name}', n_one: '{count} fuente', n_other: '{count} fuentes' },
    en: { n_one: '{count} source', n_other: '{count} sources' },
  });
  assert.equal(i18n.translate('saludo', { name: 'Ana' }), 'Hola Ana');
  assert.equal(i18n.translate('saludo'), 'Hola {name}');
  assert.equal(i18n.translate('n', { count: 1 }), '1 fuente');
  assert.equal(i18n.translate('n', { count: 3 }), '3 fuentes');
  i18n.setLocale('en', { persist: false });
  assert.equal(i18n.translate('n', { count: 1 }), '1 source');
});

test('detección de idioma y rechazo de idiomas no soportados', () => {
  assert.equal(i18n.detectLocale({ stored: 'en', navigatorLanguages: ['es'] }), 'en');
  assert.equal(i18n.detectLocale({ stored: null, navigatorLanguages: ['fr-FR', 'en-US'] }), 'en');
  assert.equal(i18n.detectLocale({ stored: null, navigatorLanguages: ['fr'] }), 'es');
  assert.equal(i18n.setLocale('fr', { persist: false }), null);
  assert.equal(i18n.getLocale(), 'es');
});

test('cambiar de idioma notifica a los suscriptores', () => {
  let n = 0;
  const off = i18n.subscribe(() => { n += 1; });
  i18n.setLocale('en', { persist: false });
  assert.equal(n, 1);
  off();
  i18n.setLocale('es', { persist: false });
  assert.equal(n, 1);
});

test('formatos según el idioma activo', () => {
  i18n.setLocale('en', { persist: false });
  assert.equal(i18n.formatNumber(1234.5), '1,234.5');
});

// ── T29.10 / AC1, AC6: detección inicial, persistencia y <html lang> ─────────

function conAlmacenamiento(fn, almacen) {
  const previo = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  Object.defineProperty(globalThis, 'localStorage', { value: almacen, configurable: true, writable: true });
  try { return fn(); } finally {
    if (previo) Object.defineProperty(globalThis, 'localStorage', previo); else delete globalThis.localStorage;
  }
}

test('AC1: navegador es/en -> ese idioma; cualquier otro -> es', () => {
  const sinGuardado = (navigatorLanguages) => i18n.detectLocale({ stored: null, navigatorLanguages });
  assert.equal(sinGuardado(['es-CL']), 'es');
  assert.equal(sinGuardado(['en-US', 'es']), 'en');
  assert.equal(sinGuardado(['fr-FR', 'de']), 'es');
  assert.equal(sinGuardado(['fr', 'en']), 'en');
  assert.equal(sinGuardado([]), 'es');
  // La preferencia guardada manda sobre el navegador; una guardada inválida no.
  assert.equal(i18n.detectLocale({ stored: 'en', navigatorLanguages: ['es'] }), 'en');
  assert.equal(i18n.detectLocale({ stored: 'xx', navigatorLanguages: ['en'] }), 'en');
});

test('AC6: setLocale persiste, actualiza <html lang> y notifica sin recargar', () => {
  const datos = new Map();
  const almacen = { getItem: (k) => datos.get(k) ?? null, setItem: (k, v) => datos.set(k, v) };
  globalThis.document = { documentElement: { lang: 'es' } };
  try {
    conAlmacenamiento(() => {
      let avisos = 0;
      const baja = i18n.subscribe(() => { avisos += 1; });
      assert.equal(i18n.setLocale('en'), 'en');
      assert.equal(datos.get(i18n.STORAGE_KEY), 'en');
      assert.equal(document.documentElement.lang, 'en');
      assert.equal(avisos, 1);
      assert.equal(i18n.detectLocale({ navigatorLanguages: ['es'] }), 'en'); // lo guardado
      assert.equal(i18n.setLocale('fr'), null);
      assert.equal(i18n.getLocale(), 'en');
      baja();
    }, almacen);
  } finally { delete globalThis.document; }
});

test('el almacenamiento puede faltar o lanzar: no rompe el cambio ni la detección', () => {
  const roto = { getItem() { throw new Error('bloqueado'); }, setItem() { throw new Error('cuota'); } };
  conAlmacenamiento(() => {
    assert.equal(i18n.setLocale('en'), 'en');
    assert.equal(i18n.getLocale(), 'en');
    assert.equal(i18n.detectLocale({ navigatorLanguages: ['en'] }), 'en');
    assert.equal(i18n.detectLocale({ navigatorLanguages: ['fr'] }), 'es');
  }, roto);
  assert.equal(i18n.setLocale('es'), 'es'); // sin localStorage definido
});

test('AC6: fechas y números siguen el idioma activo (Intl)', () => {
  const fecha = new Date(Date.UTC(2026, 10, 5, 12));
  const opts = { timeZone: 'UTC', dateStyle: 'long' };
  assert.equal(i18n.formatNumber(1234567.5), '1.234.567,5');
  assert.match(i18n.formatDate(fecha, opts), /noviembre/);
  i18n.setLocale('en', { persist: false });
  assert.equal(i18n.formatNumber(1234567.5), '1,234,567.5');
  assert.match(i18n.formatDate(fecha, opts), /November/);
});
